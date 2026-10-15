import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import preflight


def ts(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t))


class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.logs = tempfile.mkdtemp()
        os.environ["JEV_LOG_DIR"] = self.logs
        self.cwd = os.path.realpath(tempfile.mkdtemp())
        self.now = time.time()

    def calls(self, *recs):
        with open(os.path.join(self.logs, "calls.jsonl"), "w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")

    def rec(self, mode, age=5, cwd=None):
        r = {"tool": "Bash", "ts": ts(self.now - age), "cwd": cwd or self.cwd}
        if mode:
            r["permission_mode"] = mode
        return r

    def test_auto_ok(self):
        self.calls(self.rec("auto"))
        r = preflight.check(self.cwd, self.now)
        self.assertEqual((r["ok"], r["mode"]), (True, "auto"))

    def test_bypass_ok(self):
        self.calls(self.rec("bypassPermissions"))
        self.assertTrue(preflight.check(self.cwd, self.now)["ok"])

    def test_default_mode_not_ok(self):
        self.calls(self.rec("default"))
        r = preflight.check(self.cwd, self.now)
        self.assertFalse(r["ok"])
        self.assertIn("Shift+Tab", r["say"])
        self.assertIn("auto mode", r["say"])

    def test_accept_edits_not_ok(self):
        self.calls(self.rec("acceptEdits"))
        self.assertFalse(preflight.check(self.cwd, self.now)["ok"])

    def test_newest_matching_record_wins(self):
        self.calls(self.rec("default", age=50), self.rec("auto", age=3), self.rec("default", age=1, cwd="/elsewhere"))
        self.assertEqual(preflight.check(self.cwd, self.now)["mode"], "auto")

    def test_no_mode_is_unknown_and_starts_with_warning(self):
        self.calls(self.rec(None))
        r = preflight.check(self.cwd, self.now)
        self.assertEqual((r["ok"], r["mode"]), (True, "unknown"))
        self.assertTrue(r["say"])

    def test_stale_or_missing_log_is_unknown(self):
        self.calls(self.rec("default", age=600))
        self.assertEqual(preflight.check(self.cwd, self.now)["mode"], "unknown")
        os.remove(os.path.join(self.logs, "calls.jsonl"))
        self.assertEqual(preflight.check(self.cwd, self.now)["mode"], "unknown")


if __name__ == "__main__":
    unittest.main()
