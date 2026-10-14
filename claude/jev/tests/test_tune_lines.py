import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jev_mcp
import tune_tasks as tt

TH = {"review": {"task_skip": False, "min_tasks": 2, "max_false_skip_rate": 0.01},
      "dispatch": {"scored_tier": False, "min_tasks": 2}}


def pair(task, tier, lines):
    base = {"task": task, "tier": tier, "role": "coder", "attempt": 1}
    return [base, dict(base, phase="return", lines=lines)]


def summ(dispatch):
    return tt.summary(tt.rows([], dispatch, [], []), [], [], TH)


class LinesTest(unittest.TestCase):
    def test_median_lines_per_task_and_per_tier(self):
        # Defect caught: no lines-per-task number in /tune, so diff size per task is invisible.
        d = pair("a", "haiku", 10) + pair("b", "haiku", 30) + pair("c", "haiku", 50) + pair("d", "opus", 200)
        s = summ(d)
        self.assertEqual(s["lines_median"], 40.0)
        self.assertEqual(s["lines_by_tier"], {"haiku": 30.0, "opus": 200.0})
        text = "\n".join(tt.lines(s))
        self.assertIn("- Lines changed per task (median): 40", text)
        self.assertIn("- Lines per task by start tier: haiku 30, opus 200", text)

    def test_bad_lines_is_none(self):
        r = tt.rows([], pair("a", "haiku", "x"), [], [])
        self.assertIsNone(r["a"]["lines"])
        s = tt.summary(r, [], [], TH)
        self.assertIsNone(s["lines_median"])
        self.assertIn("- Lines per task by start tier: n/a", tt.lines(s))


class McpLinesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, {"JEV_LOG_DIR": self.tmp,
                                         "JEV_THRESHOLDS": os.path.join(self.tmp, "none.json")})
        p.start()
        self.addCleanup(p.stop)

    def log(self, lines):
        jev_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "log_dispatch", "arguments": {
            "task": "t", "tier": "sonnet", "role": "coder", "attempt": 1, "phase": "return", "lines": lines}}})
        with open(os.path.join(self.tmp, "dispatch.jsonl")) as f:
            return [json.loads(l) for l in f][-1]

    def test_lines_logged_and_invalid_dropped(self):
        self.assertEqual(self.log(12)["lines"], 12)
        for bad in (-5, True, 1000001, "x", 1.5):
            self.assertNotIn("lines", self.log(bad), bad)


if __name__ == "__main__":
    unittest.main()
