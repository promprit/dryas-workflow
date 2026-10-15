import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import run_report


class RunReportTest(unittest.TestCase):
    def test_counts_this_worktree_since_start(self):
        d = tempfile.mkdtemp()
        wt = "/w/wt"
        def rec(**k):
            return dict({"ts": "2026-10-16T10:00:00+0700", "cwd": wt, "run": True}, **k)
        with open(os.path.join(d, "scope.jsonl"), "w") as f:
            for r in [rec(decision="deny", kind="deny", rule="sed"), rec(decision="allow", kind="allow", rule="inline_code"),
                      rec(decision="allow", kind="allow", rule="inline_code"), rec(decision="violation", kind="violation"),
                      rec(decision="ask"), rec(decision="deny", cwd="/other"), rec(decision="deny", ts="2026-10-16T08:00:00+0700")]:
                f.write(json.dumps(r) + "\n")
        with open(os.path.join(d, "gate.jsonl"), "w") as f:
            for r in [rec(decision="deny", rule="run_deny"), rec(decision="none", rule="planned"),
                      rec(decision="none", rule="orchestrator"), rec(decision="ask")]:
                f.write(json.dumps(r) + "\n")
        r = run_report.report(wt, "2026-10-16T09:00:00+0700", d)
        self.assertEqual(r, {"prompts": 2, "scope_denies": 1, "violations": 1, "run_denies": 1, "planned": 1,
                             "orchestrator": 1, "inline_code": 2})


if __name__ == "__main__":
    unittest.main()
