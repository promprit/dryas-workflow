import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tune


class TuneBaselineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, {"JEV_LOG_DIR": self.tmp, "JEV_THRESHOLDS": os.path.join(self.tmp, "t.json")})
        p.start()
        self.addCleanup(p.stop)

    def write(self, name, recs):
        with open(os.path.join(self.tmp, name + ".jsonl"), "w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")

    def test_parallel_and_zero_call_tasks_count(self):
        self.write("gate", [
            {"tool": "Bash", "decision": "none", "provider": "jev", "task": "b:1"},
            {"tool": "Bash", "decision": "none", "provider": "jev", "task": "b:1"},
            {"tool": "Bash", "decision": "none", "provider": "jev", "tasks": ["b:2", "b:3"]},
        ])
        self.write("dispatch", [
            {"task": "b:%d" % i, "tier": "sonnet", "role": "coder", "attempt": 1} for i in range(1, 5)
        ])
        rep = tune.build(self.tmp)
        self.assertEqual(rep["gate_judged_per_task_median"], 1.0)

    def test_agreement_on_decided_records(self):
        def shadow(d, s):
            return {"tool": "Bash", "decision": d, "provider": "jev",
                    "shadow_provider": "local", "shadow_decision": s}
        self.write("gate", [shadow("none", "none") for _ in range(8)] + [shadow("deny", "none"), shadow("ask", "ask")])
        rep = tune.build(self.tmp)
        self.assertEqual(rep["shadow"]["calls"], 10)
        self.assertEqual(rep["shadow"]["agree"], 9)
        self.assertEqual(rep["shadow"]["decided_calls"], 2)
        self.assertEqual(rep["shadow"]["decided_agree"], 1)
        self.assertIn("90% of 10; where either side decided: 50% of 2", tune.render(rep, []))

    def test_local_route_records_are_not_calls(self):
        self.write("route", [{"provider": "local", "injected": False} for _ in range(3)]
                   + [{"provider": "jev", "injected": True}])
        rep = tune.build(self.tmp)
        self.assertEqual(rep["route_calls"], 1)
        self.assertEqual(rep["route_local"], 3)
        lines = tune.render(rep, []).splitlines()
        i = next(n for n, l in enumerate(lines) if l.startswith("- Route:"))
        self.assertEqual(lines[i + 1], "- Route hints skipped (local judge): 3")


if __name__ == "__main__":
    unittest.main()
