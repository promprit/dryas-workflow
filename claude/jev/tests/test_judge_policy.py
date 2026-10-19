import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import judge_policy


class JudgePolicyTest(unittest.TestCase):
    def setUp(self):
        judge_policy.clear_cache()
        self.addCleanup(judge_policy.clear_cache)
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.root = os.path.join(self.tmp, "VOID")
        for d in ("Pilot/src", "Pilot/.claude/worktrees/x/src", "void-data-platform-slug", "other"):
            os.makedirs(os.path.join(self.root, d))
        os.makedirs(os.path.join(self.tmp, "elsewhere"))

    def mark(self, content="local\n", where=None):
        with open(os.path.join(where or self.root, judge_policy.MARKER), "w") as f:
            f.write(content)

    def test_marker_at_root_covers_child_repo(self):
        self.mark()
        self.assertTrue(judge_policy.project_local(os.path.join(self.root, "Pilot")))

    def test_marker_covers_root_worktrees_and_siblings(self):
        self.mark()
        for d in ("", "Pilot/src", "Pilot/.claude/worktrees/x/src", "void-data-platform-slug"):
            self.assertTrue(judge_policy.project_local(os.path.join(self.root, d)), d)

    def unmarked_process(self):
        """Process folder unmarked and CLAUDE_PROJECT_DIR unset, so only the given cwd counts."""
        p = mock.patch.dict(os.environ)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        g = mock.patch("os.getcwd", return_value=os.path.join(self.tmp, "elsewhere"))
        g.start()
        self.addCleanup(g.stop)

    def test_no_marker_outside(self):
        self.mark()
        self.unmarked_process()
        self.assertFalse(judge_policy.project_local(os.path.join(self.tmp, "elsewhere")))

    def test_no_marker_anywhere(self):
        self.unmarked_process()
        self.assertFalse(judge_policy.project_local(os.path.join(self.root, "Pilot")))

    def test_any_content_means_local(self):
        for content in ("", "jev\n", "\x00junk"):
            judge_policy.clear_cache()
            self.mark(content)
            self.assertTrue(judge_policy.project_local(self.root), repr(content))

    def test_marker_directory_means_local(self):
        os.makedirs(os.path.join(self.root, judge_policy.MARKER))
        self.assertTrue(judge_policy.project_local(os.path.join(self.root, "other")))

    def test_broken_symlink_marker_means_local(self):
        if not hasattr(os, "symlink") or os.name == "nt":
            self.skipTest("symlinks")
        os.symlink(os.path.join(self.tmp, "missing"), os.path.join(self.root, judge_policy.MARKER))
        self.assertTrue(judge_policy.project_local(self.root))

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_unreadable_marker_means_local(self):
        self.mark()
        p = os.path.join(self.root, judge_policy.MARKER)
        os.chmod(p, 0)
        self.addCleanup(os.chmod, p, 0o644)
        self.assertTrue(judge_policy.project_local(self.root))

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "POSIX non-root")
    def test_unsearchable_parent_fails_closed(self):
        locked = os.path.join(self.tmp, "locked")
        os.makedirs(os.path.join(locked, "sub"))
        os.chmod(locked, 0)
        self.addCleanup(os.chmod, locked, 0o755)
        self.assertTrue(judge_policy.project_local(os.path.join(locked, "sub")))

    def test_symlink_into_marked_project(self):
        if not hasattr(os, "symlink") or os.name == "nt":
            self.skipTest("symlinks")
        self.mark()
        link = os.path.join(self.tmp, "elsewhere", "link")
        os.symlink(os.path.join(self.root, "Pilot"), link)
        self.assertTrue(judge_policy.project_local(link))

    def test_cwd_that_is_a_file_walks_parents(self):
        self.mark()
        f = os.path.join(self.root, "Pilot", "notes.txt")
        open(f, "w").close()
        self.assertTrue(judge_policy.project_local(f))

    def test_missing_cwd_uses_process_directory(self):
        self.mark()
        for cwd in (None, "", 7, ["x"]):
            judge_policy.clear_cache()
            with mock.patch("os.getcwd", return_value=os.path.join(self.root, "Pilot")):
                self.assertTrue(judge_policy.project_local(cwd), repr(cwd))

    def test_getcwd_failure_falls_back_to_process_start(self):
        self.mark()
        with mock.patch.object(judge_policy, "_PROCESS_START", os.path.join(self.root, "Pilot"), create=True), \
                mock.patch("os.getcwd", side_effect=FileNotFoundError):
            self.assertTrue(judge_policy.project_local(None))

    def test_getcwd_failure_without_process_start_fails_closed(self):
        with mock.patch.object(judge_policy, "_PROCESS_START", None, create=True), \
                mock.patch.dict(os.environ), mock.patch("os.getcwd", side_effect=FileNotFoundError):
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
            self.assertTrue(judge_policy.project_local(None))

    def test_claude_project_dir_marked(self):
        self.mark()
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": os.path.join(self.root, "Pilot")}), \
                mock.patch("os.getcwd", return_value=os.path.join(self.tmp, "elsewhere")):
            self.assertTrue(judge_policy.project_local(os.path.join(self.tmp, "elsewhere")))

    def test_logical_symlink_out_of_marked_folder(self):
        if not hasattr(os, "symlink") or os.name == "nt":
            self.skipTest("symlinks")
        self.mark()
        link = os.path.join(self.root, "data")
        os.symlink(os.path.join(self.tmp, "elsewhere"), link)
        self.unmarked_process()
        self.assertTrue(judge_policy.project_local(link))

    def test_negative_not_cached(self):
        self.unmarked_process()
        start = os.path.join(self.root, "Pilot")
        self.assertFalse(judge_policy.project_local(start))
        self.mark()
        self.assertTrue(judge_policy.project_local(start))

    def test_walk_stops_at_root(self):
        self.unmarked_process()
        self.assertFalse(judge_policy.project_local(os.path.abspath(os.sep)))

    def test_cache_skips_second_walk(self):
        self.mark()
        start = os.path.join(self.root, "Pilot", "src")
        self.assertTrue(judge_policy.project_local(start))
        with mock.patch("os.lstat", side_effect=AssertionError("walked again")):
            self.assertTrue(judge_policy.project_local(start))


if __name__ == "__main__":
    unittest.main()
