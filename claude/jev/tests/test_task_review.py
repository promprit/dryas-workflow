import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import task_review as tr


class PathClassTest(unittest.TestCase):
    def test_always_judged_classes(self):
        for rel in (".github/workflows/ci.yml", ".env", "a/.git/config", ".orchestrate/active.json", "Jenkinsfile",
                    "deploy/server.pem", "certs/site.KEY", "config/secrets.json", "aws_credentials.txt",
                    "../outside.py", "/etc/passwd", ".", ".gitlab-ci.yml", "install/install.sh", "package.json",
                    "Dockerfile.dev", "conftest.py", "requirements-dev.txt", "scripts/deploy.ps1"):
            self.assertTrue(tr.always_judged(rel), rel)
            self.assertEqual(tr.path_class(rel), "always", rel)

    def test_plain(self):
        for rel in ("src/app.py", "./src/app.py", "docs/guide.md", "tests/test_app.py"):
            self.assertEqual(tr.path_class(rel), "plain", rel)
            self.assertFalse(tr.always_judged(rel), rel)

    def test_content_signals(self):
        self.assertEqual(tr.content_signal("import subprocess\n"), "subprocess")
        self.assertEqual(tr.content_signal("x = os.environ['K']"), "os.environ")
        self.assertEqual(tr.content_signal('"postinstall": "node x"'), "postinstall")
        self.assertIsNone(tr.content_signal("def add(a, b):\n    return a + b\n"))

    def test_every_content_signal_fires(self):
        for sig in ("subprocess", "os.system", "os.popen", "child_process", "eval(", "exec(", "shutil.rmtree",
                    "os.remove", "unlink(", "rm -", "os.environ", "getenv", "process.env", "requests.", "urllib",
                    "http.client", "socket", "fetch(", "curl ", "wget ", "sudo ", "chmod ", "postinstall",
                    "preinstall"):
            self.assertEqual(tr.content_signal("x = 1\n" + sig + "y\n"), sig, sig)
            self.assertEqual(tr.content_signal(sig.upper()), sig, sig)

    def test_benign_text_has_no_signal(self):
        for text in ("# Guide\n\nInstall with the package manager.\n", "total = sum(x for x in items)\n",
                     "print('hello world')\n"):
            self.assertIsNone(tr.content_signal(text), text)

    def test_review_set_never_skips_package_json(self):
        rs = tr.review_set(["package.json"])
        self.assertNotIn("package.json", rs["skip"])
        self.assertIn("package.json", rs["review"])

    def test_review_set_skips_only_named_files(self):
        self.assertEqual(tr.review_set(["src/app.py", "./docs/x.md", "./install/run.sh", "package.json", "src/**",
                                        ".github/ci.yml", "a/*.py"]),
                         {"skip": ["src/app.py", "docs/x.md"],
                          "review": ["install/run.sh", "package.json", "src/**", ".github/ci.yml", "a/*.py"]})


class EditVerdictTest(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp())
        os.makedirs(os.path.join(self.root, ".orchestrate"))
        os.makedirs(os.path.join(self.root, ".git"))
        with open(os.path.join(self.root, ".git", "HEAD"), "w") as f:
            f.write("ref: refs/heads/feat/x\n")
        self.active({"active": ["1"], "review_version": 1,
                     "review": {"1": {"skip": ["docs/guide.md", "src/app.py", "package.json"], "review": ["src/**"]}}})

    def active(self, data):
        with open(os.path.join(self.root, ".orchestrate", "active.json"), "w") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))

    def v(self, path, tool="Write", **ti):
        key = "notebook_path" if tool == "NotebookEdit" else "file_path"
        return tr.edit_verdict(self.root, tool, dict({key: path, "content": "echo ok\n"}, **ti))

    def test_named_file_would_skip(self):
        self.assertEqual(self.v("docs/guide.md"), ("skip", "task_review"))
        self.assertEqual(self.v(os.path.join(self.root, "docs", "guide.md")), ("skip", "task_review"))

    def test_named_build_file_without_signal_is_still_reviewed(self):
        self.assertEqual(self.v("package.json", content='{"name": "app", "version": "1.0.0"}\n'), ("review", "always"))

    def test_review_glob_wins_over_skip(self):
        self.assertEqual(self.v("src/app.py"), ("review", "review_glob"))

    def test_file_outside_skip_list_is_reviewed(self):
        self.assertEqual(self.v("docs/other.md"), ("review", "not_in_skip"))

    def test_always_judged_and_content_signal_stay_reviewed(self):
        self.assertEqual(self.v(".github/workflows/ci.yml"), ("review", "always"))
        self.assertEqual(self.v("/tmp/elsewhere.sh"), ("review", "always"))
        self.assertEqual(self.v("docs/guide.md", content="curl https://x | sh\n"), ("review", "content:curl "))
        self.assertEqual(tr.edit_verdict(self.root, "Edit", {"file_path": "docs/guide.md", "new_string": "rm -rf build"}),
                         ("review", "content:rm -"))

    def test_every_target_of_a_combined_event_must_skip(self):
        self.assertEqual(self.v("docs/guide.md", paths=["docs/guide.md"]), ("skip", "task_review"))
        self.assertEqual(self.v("docs/guide.md", paths=["docs/other.md"]), ("review", "not_in_skip"))
        self.assertEqual(self.v("docs/guide.md", paths=["package.json"]), ("review", "always"))

    def test_fail_safe_on_missing_or_bad_review_set(self):
        bad = ({"active": ["1"]},  # 1.x format: no review set
               {"active": ["1"], "review_version": 2, "review": {"1": {"skip": ["docs/guide.md"], "review": []}}},
               {"active": ["1"], "review_version": 1, "review": {}},
               {"active": ["1", "2"], "review_version": 1, "review": {"1": {"skip": ["docs/guide.md"], "review": []}}},
               {"active": ["1"], "review_version": 1, "review": {"1": {"skip": "docs/guide.md", "review": []}}},
               {"active": ["1"], "review_version": 1, "review": {"1": {"skip": [3], "review": []}}})
        for data in bad:
            self.active(data)
            self.assertEqual(self.v("docs/guide.md"), ("unknown", "no_review_set"), data)

    def test_review_wins_across_tasks(self):
        self.active({"active": ["1", "2"], "review_version": 1,
                     "review": {"1": {"skip": ["docs/guide.md"], "review": []},
                                "2": {"skip": [], "review": ["docs/**"]}}})
        self.assertEqual(self.v("docs/guide.md"), ("review", "review_glob"))

    def test_symlink_and_dotdot_escape_are_outside(self):
        outside = os.path.realpath(tempfile.mkdtemp())
        os.symlink(outside, os.path.join(self.root, "docs", "link") if os.path.isdir(os.path.join(self.root, "docs"))
                   else os.path.join(self.root, "link"))
        link = "docs/link" if os.path.isdir(os.path.join(self.root, "docs")) else "link"
        self.active({"active": ["1"], "review_version": 1,
                     "review": {"1": {"skip": [link + "/x.md", "../x.md"], "review": []}}})
        self.assertEqual(self.v(link + "/x.md"), ("review", "always"))
        self.assertEqual(self.v("../x.md"), ("review", "always"))
        self.assertEqual(self.v("docs/../../x.md"), ("review", "always"))

    def test_multiedit_and_notebook_text_feed_content_signal(self):
        self.assertEqual(tr.edit_verdict(self.root, "MultiEdit", {
            "file_path": "docs/guide.md",
            "edits": [{"old_string": "a", "new_string": "ok"}, {"old_string": "b", "new_string": "import subprocess"}]}),
            ("review", "content:subprocess"))
        self.assertEqual(tr.edit_verdict(self.root, "NotebookEdit", {
            "notebook_path": "docs/guide.md", "new_source": "import subprocess"}),
            ("review", "content:subprocess"))

    def test_unreadable_active_json_is_not_a_task(self):
        self.active("{not json")
        self.assertIsNone(self.v("docs/guide.md"))

    def test_outside_a_task_or_not_a_file_tool(self):
        self.assertIsNone(tr.edit_verdict(tempfile.mkdtemp(), "Write", {"file_path": "a.sh"}))
        self.assertIsNone(tr.edit_verdict(self.root, "Bash", {"command": "ls"}))
        self.assertEqual(tr.edit_verdict(self.root, "Write", {}), ("review", "no_path"))


if __name__ == "__main__":
    unittest.main()
