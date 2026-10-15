import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

JEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JEV)
import cloud_check as cc

LIC = ".dryas/licenses/LICENSE-dryas"
NOTE = "- Dryas 9.9.9 (MIT): " + LIC


class Copy:
    """A small repo copy written by hand: the shape `dryas cloud init` leaves."""

    def __init__(self, root):
        self.root = root
        self.files = {}

    def put(self, rel, text, **meta):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        e = dict(sha256=cc.sha256(text.encode("utf-8")), source="test", group="dryas", version="9.9.9", licence="MIT",
                 licence_file=LIC, notice=NOTE)
        e.update(meta)
        self.files[rel] = e

    def save(self, version="9.9.9", config=None):
        m = dict(format=1, dryas=dict(version=version, commit="c0ffee", files_hash="x"), options={}, files=self.files,
                 config=config or {})
        with open(os.path.join(self.root, cc.MANIFEST), "w", encoding="utf-8") as f:
            json.dump(m, f)


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.repo, True)
        self.copy = Copy(self.repo)
        self.copy.put(LIC, "MIT License\n")
        self.copy.put(cc.NOTICE, "Dryas 9.9.9, copied by dryas cloud.\n" + NOTE + "\n")
        self.copy.put(".dryas/jev/tool.py", "import json\nimport helper\n")
        self.copy.put(".dryas/jev/helper.py", "import os\n")
        self.copy.put(".claude/commands/tune.md", 'Run `".dryas/bin/dryas-py" ".dryas/jev/tune.py" report`.\n')
        self.copy.save()
        self.write(".gitignore", "node_modules/\n.dryas/state/\n")
        self.write("CLAUDE.md", "# Repo\n\n<!-- dryas:start -->\nDryas rules\n<!-- dryas:end -->\n")

    def write(self, rel, text):
        with open(os.path.join(self.repo, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def test_intact_copy_has_no_problems(self):
        self.assertEqual(cc.check(self.repo, "9.9.9"), [])

    def test_hand_edit_and_missing_file_are_drift(self):
        self.write(".claude/commands/tune.md", "changed\n")
        os.remove(os.path.join(self.repo, ".dryas/jev/helper.py"))
        probs = cc.check(self.repo)
        self.assertIn("drift (hand-edited): .claude/commands/tune.md", probs)
        self.assertIn("missing: .dryas/jev/helper.py", probs)

    def test_paths_that_only_work_on_the_mac(self):
        self.copy.put(".claude/skills/x/SKILL.md", "see /Users/someone/notes, ~/.dryas/jev/logs, ${CLAUDE_PLUGIN_ROOT}/jev\n")
        self.copy.put(".dryas/jev/doc.md", "default ~/.dryas and ${CLAUDE_PLUGIN_ROOT}\n")
        self.copy.save()
        probs = cc.check(self.repo)
        skill = [p for p in probs if p.startswith(".claude/skills/x/SKILL.md:1:")]
        self.assertEqual(len(skill), 3, probs)
        self.assertTrue(any("absolute Mac path" in p for p in skill))
        self.assertFalse(any(p.startswith(".dryas/jev/doc.md") for p in probs))

    def test_non_stdlib_import(self):
        self.copy.put(".dryas/jev/needs.py", "import json\nimport requests\n")
        self.copy.save()
        self.assertIn(".dryas/jev/needs.py: imports non-stdlib requests", cc.check(self.repo))

    def test_licence_and_notice(self):
        self.copy.put(".claude/skills/d/SKILL.md", "d\n", group="design", licence="Apache-2.0",
                      licence_file=".dryas/licenses/d-LICENSE", notice="- d 1.0 (Apache-2.0): .dryas/licenses/d-LICENSE")
        self.copy.save()
        probs = cc.check(self.repo)
        self.assertIn(".claude/skills/d/SKILL.md: licence file .dryas/licenses/d-LICENSE is missing", probs)
        self.assertIn(".claude/skills/d/SKILL.md: no NOTICE line '- d 1.0 (Apache-2.0): .dryas/licenses/d-LICENSE'",
                      probs)

    def test_repo_level_problems(self):
        self.write(".gitignore", "node_modules/\n")
        self.write("CLAUDE.md", "# Repo\n")
        probs = cc.check(self.repo, "9.9.10")
        self.assertIn(".gitignore: .dryas/state/ is not ignored", probs)
        self.assertIn("CLAUDE.md: the Dryas rules block is missing", probs)
        self.assertIn("copy is Dryas 9.9.9, this Dryas is 9.9.10: run dryas cloud update", probs)

    def test_home_path_in_dryas_config_entries(self):
        self.copy.save(config={"settings": {"added": {"env": {"X": "~/x"}}}, "mcp": {"entry": {"args": ["/Volumes/d"]}}})
        probs = cc.check(self.repo)
        self.assertIn(".claude/settings.json: a Dryas entry names a home or Mac path", probs)
        self.assertIn(".mcp.json: a Dryas entry names a home or Mac path", probs)

    def test_dryas_env_in_settings_is_a_problem(self):
        self.copy.save(config={"settings": {"added": {"env": {"DRYAS_DATA_ROOT": "x"}}}})
        self.assertIn(".claude/settings.json: Dryas entries set env (hooks get it from cloud_hook.py only)",
                      cc.check(self.repo))

    def test_no_copy(self):
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, True)
        self.assertEqual(cc.check(empty), ["no Dryas copy here (.dryas/manifest.json is missing); run dryas cloud init"])

    def test_cli_exit_codes(self):
        self.copy.save(version=cc.own_version() or "9.9.9")  # the CLI compares the copy with this Dryas's version
        cli = [sys.executable, os.path.join(JEV, "cloud_check.py"), "--repo", self.repo]
        p = subprocess.run(cli, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn("dryas cloud check: 0 problems", p.stdout)
        self.write(".claude/commands/tune.md", "changed\n")
        p = subprocess.run(cli, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 1)
        self.assertIn("drift (hand-edited): .claude/commands/tune.md", p.stdout)


class GapTest(unittest.TestCase):
    """Gaps a wrong implementation could pass: dynamic imports, bad manifests, unowned files, escaped paths."""
    setUp = CheckTest.setUp
    write = CheckTest.write

    def test_dynamic_imports_of_non_stdlib_are_found(self):
        code = ("import importlib\nimportlib.import_module('requests')\n__import__('yaml')\n"
                "importlib.import_module('json')\n__import__('os')\nimportlib.import_module('numpy.linalg')\n")
        self.assertEqual(cc.nonstdlib_imports(code, []), ["numpy", "requests", "yaml"])

    def test_dynamic_import_in_copy_is_reported(self):
        self.copy.put(".dryas/jev/sneaky.py", "__import__('requests')\n")
        self.copy.save()
        self.assertIn(".dryas/jev/sneaky.py: imports non-stdlib requests", cc.check(self.repo))

    def test_malformed_manifests_do_not_crash(self):
        path = os.path.join(self.repo, cc.MANIFEST)
        for body in ("{not json", "[]", '{"files": []}', '{"format": 1}'):
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
            probs = cc.check(self.repo)
            self.assertEqual(len(probs), 1, (body, probs))
            self.assertIn("unreadable", probs[0])
        with self.assertRaises(ValueError):
            cc.load_manifest(self.repo)

    def test_non_dict_file_record_does_not_crash(self):
        self.copy.files[".dryas/jev/helper.py"] = "oops"
        self.copy.save()
        self.assertTrue(cc.check(self.repo))

    def test_unowned_file_under_copy_is_a_problem(self):
        self.write(".dryas/jev/extra.py", "x = 1\n")
        os.makedirs(os.path.join(self.repo, ".dryas/state"))
        self.write(".dryas/state/log.txt", "state is allowed\n")
        probs = cc.check(self.repo)
        self.assertIn("unowned: .dryas/jev/extra.py", probs)
        self.assertFalse(any("state/log.txt" in p or ".dryas/manifest.json" in p for p in probs), probs)

    def test_json_escaped_mac_path_is_found(self):
        self.assertEqual(cc.scan_text("a.json", '{"p": "\\/Users\\/x\\/y"}'), ["a.json:1: absolute Mac path"])

    def test_deleted_owned_file_reports_exactly_that(self):
        os.remove(os.path.join(self.repo, ".claude/commands/tune.md"))
        self.assertEqual(cc.check(self.repo, "9.9.9"), ["missing: .claude/commands/tune.md"])

    def test_mac_path_in_claude_md_block(self):
        self.write("CLAUDE.md", "<!-- dryas:start -->\nsee /Users/x/y\n<!-- dryas:end -->\n")
        self.assertIn("CLAUDE.md:2: absolute Mac path", cc.check(self.repo))


class ScanTest(unittest.TestCase):
    def test_scan_rules(self):
        self.assertEqual(cc.scan_text("a/b.md", "src/Users/model.py, ~/project and ~/.config/git/ignore"), [])
        self.assertEqual(cc.scan_text(".dryas/jev/a.py", "p = '/Volumes/disk/x'"), [".dryas/jev/a.py:1: absolute Mac path"])

    def test_stdlib_detection(self):
        code = "import json, os.path\nfrom urllib import request\nfrom . import x\nimport helper\nimport numpy.linalg\n"
        self.assertEqual(cc.nonstdlib_imports(code, ["helper"]), ["numpy"])
        self.assertEqual(cc.nonstdlib_imports("def (:\n", []), ["<unparseable>"])
        for name in ("json", "sqlite3", "msvcrt", "fcntl", "__future__"):
            self.assertTrue(cc.is_stdlib(name), name)

    def test_files_hash_depends_on_path_and_content(self):
        a = cc.files_hash({"x": cc.sha256(b"1"), "y": cc.sha256(b"2")})
        self.assertEqual(a, cc.files_hash({"y": cc.sha256(b"2"), "x": cc.sha256(b"1")}))
        self.assertNotEqual(a, cc.files_hash({"x": cc.sha256(b"2"), "y": cc.sha256(b"1")}))

    def test_shipped_runtime_is_cloud_clean(self):
        """Everything dryas cloud copies from claude/jev and claude/pstack: no Mac path, stdlib only."""
        hits = []
        for base in ("jev", "pstack"):
            root = os.path.join(os.path.dirname(JEV), base)
            for d, dirs, files in os.walk(root):
                dirs[:] = [x for x in dirs if x not in ("tests", "__pycache__", "logs", "compact")]
                for f in files:
                    p = os.path.join(d, f)
                    rel = ".dryas/%s/%s" % (base, os.path.relpath(p, root).replace(os.sep, "/"))
                    try:
                        with open(p, encoding="utf-8") as fh:
                            text = fh.read()
                    except UnicodeDecodeError:
                        continue
                    hits += cc.scan_text(rel, text)
                    if f.endswith(".py"):
                        hits += ["%s: %s" % (rel, m) for m in cc.nonstdlib_imports(text, cc.siblings(p))]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
