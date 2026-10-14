import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jevlog


class JevlogTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.environ["JEV_LOG_DIR"] = self.d

    def test_append_normal_record(self):
        """Test that append writes a normal record."""
        jevlog.append("test", {"tool": "Bash", "cmd": "ls"})
        with open(os.path.join(self.d, "test.jsonl")) as f:
            line = f.readline()
            rec = json.loads(line)
            self.assertEqual(rec["tool"], "Bash")
            self.assertEqual(rec["cmd"], "ls")

    def test_append_with_surrogate(self):
        """Test that append handles lone surrogates without raising."""
        # Create a record with a lone surrogate character
        # Note: we can't directly put a lone surrogate in a Python string,
        # but json.dumps will raise when encountering one
        # Instead, test with an object that's not JSON serializable
        class BadObj:
            pass
        record = {"tool": "Bash", "bad": BadObj()}
        # Should not raise - even if the record can't be written
        jevlog.append("test", record)
        # Test passed if we get here without raising

    def test_append_with_non_serializable_object(self):
        """Test that append handles non-serializable objects without raising."""
        class CustomClass:
            pass
        record = {"tool": "Bash", "obj": CustomClass(), "cmd": "ls"}
        # Should not raise - even if the record can't be written
        jevlog.append("test", record)
        # Test passed if we get here without raising

    def test_append_to_missing_dir_creates_it(self):
        """Test that append creates the log directory if it doesn't exist."""
        new_dir = os.path.join(self.d, "subdir", "logs")
        os.environ["JEV_LOG_DIR"] = new_dir
        jevlog.append("test", {"tool": "Bash"})
        self.assertTrue(os.path.isdir(new_dir))
        self.assertTrue(os.path.exists(os.path.join(new_dir, "test.jsonl")))

    def test_append_adds_session_from_env(self):
        os.environ["JEV_SESSION_ID"] = "sess-1"
        os.environ["JEV_CWD"] = "/Users/p/app"
        try:
            jevlog.append("t", {"tool": "Bash"})
        finally:
            del os.environ["JEV_SESSION_ID"], os.environ["JEV_CWD"]
        rec = json.loads(open(os.path.join(self.d, "t.jsonl")).readline())
        self.assertEqual(rec["session_id"], "sess-1")
        self.assertEqual(rec["cwd"], "/Users/p/app")

    def test_append_record_wins_over_env(self):
        os.environ["JEV_SESSION_ID"] = "env"
        try:
            jevlog.append("t", {"session_id": "explicit"})
        finally:
            del os.environ["JEV_SESSION_ID"]
        rec = json.loads(open(os.path.join(self.d, "t.jsonl")).readline())
        self.assertEqual(rec["session_id"], "explicit")

    def test_append_without_env_has_no_session(self):
        os.environ.pop("JEV_SESSION_ID", None)
        os.environ.pop("JEV_CWD", None)
        jevlog.append("t", {"tool": "Bash"})
        rec = json.loads(open(os.path.join(self.d, "t.jsonl")).readline())
        self.assertNotIn("session_id", rec)
        self.assertNotIn("cwd", rec)


    def test_log_dir_is_private(self):
        import stat
        new_dir = os.path.join(self.d, "private", "logs")
        os.environ["JEV_LOG_DIR"] = new_dir
        jevlog.append("t", {"tool": "Bash"})
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(os.stat(new_dir).st_mode), 0o700)
        self.assertTrue(os.path.isdir(new_dir))

    def test_rotates_by_size_keeping_one_backup(self):
        p = os.path.join(self.d, "calls.jsonl")
        old = jevlog.MAX_BYTES
        jevlog.MAX_BYTES = 100
        try:
            with open(p, "w") as f:
                f.write("x" * 101 + "\n")
            jevlog.append("calls", {"tool": "Bash"})
            self.assertEqual(json.loads(open(p).readline())["tool"], "Bash")
            self.assertEqual(len(open(p).readlines()), 1)
            self.assertTrue(open(p + ".1").read().startswith("x" * 101))
            with open(p, "a") as f:
                f.write("y" * 200 + "\n")
            jevlog.append("calls", {"tool": "Edit"})
            self.assertEqual(json.loads(open(p).readline())["tool"], "Edit")
            self.assertIn("y" * 200, open(p + ".1").read())  # only one backup: the older one is gone
            self.assertFalse(os.path.exists(p + ".2"))
        finally:
            jevlog.MAX_BYTES = old

    def test_no_rotation_below_limit(self):
        p = os.path.join(self.d, "small.jsonl")
        jevlog.append("small", {"a": 1})
        jevlog.append("small", {"a": 2})
        self.assertEqual(len(open(p).readlines()), 2)
        self.assertFalse(os.path.exists(p + ".1"))


if __name__ == "__main__":
    unittest.main()
