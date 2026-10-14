import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tune


class TuneProvidersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, {"JEV_LOG_DIR": self.tmp, "JEV_THRESHOLDS": os.path.join(self.tmp, "t.json")})
        p.start()
        self.addCleanup(p.stop)

    def write(self, name, recs):
        with open(os.path.join(self.tmp, name + ".jsonl"), "w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")

    def test_providers_shadow_and_per_task(self):
        self.write("gate", [
            {"tool": "Bash", "decision": "none", "provider": "jev", "latency_ms": 5, "cost": 0.001,
             "shadow_provider": "local", "shadow_decision": "none", "task": "b:1"},
            {"tool": "Bash", "decision": "none", "provider": "jev", "latency_ms": 5, "cost": 0.001,
             "shadow_provider": "local", "shadow_decision": "ask", "task": "b:1"},
            {"tool": "Bash", "decision": "deny", "provider": "local", "local_ms": 0.3, "fallback": "local",
             "error": "JevUnavailable", "task": "b:2"},
            {"tool": "Bash", "decision": "none", "provider": "local", "local_ms": 0.2,
             "shadow_provider": "jev", "shadow_decision": "none", "shadow_cost": 0.002},
            {"tool": "Bash", "decision": "skipped", "via": "allowlist", "task": "b:1"},
            {"tool": "Bash", "decision": "none", "latency_ms": 4},
        ])
        rep = tune.build(self.tmp)
        self.assertEqual(rep["judge_providers"], {"jev": 2, "local": 2})
        self.assertEqual(rep["judge_fallbacks"], 1)
        self.assertEqual(rep["shadow"], {"calls": 3, "agree": 2, "by_provider": {"local": 2, "jev": 1}})
        self.assertEqual(rep["gate_judged_per_task_median"], 1.5)
        self.assertAlmostEqual(rep["shadow_spend_usd"], 0.002)
        text = tune.render(rep, [])
        self.assertIn('- Judge providers (gate): {"jev": 2, "local": 2}, fallbacks to local: 1', text)
        self.assertIn("- Shadow agreement (gate): 67% of 3", text)
        self.assertIn("- Judged gate calls per task (median): 1.50", text)

    def test_empty_logs_render_na(self):
        text = tune.render(tune.build(self.tmp), [])
        self.assertIn("- Judge providers (gate): {}, fallbacks to local: 0", text)
        self.assertIn("- Shadow agreement (gate): n/a", text)
        self.assertIn("- Judged gate calls per task (median): n/a", text)

    def test_spend_includes_shadow_cost(self):
        self.write("gate", [{"decision": "none", "provider": "local", "shadow_provider": "jev",
                             "shadow_decision": "none", "shadow_cost": 0.5}])
        self.assertAlmostEqual(tune.build(self.tmp)["jev_spend_usd"], 0.5)

    def test_new_lines_follow_gate_skips_and_old_lines_stay(self):
        lines = tune.render(tune.build(self.tmp), []).splitlines()
        i = next(n for n, l in enumerate(lines) if l.startswith("- gate skips:"))
        self.assertTrue(lines[i + 1].startswith("- Judge providers (gate):"))
        self.assertTrue(lines[i + 2].startswith("- Shadow agreement (gate):"))
        self.assertTrue(lines[i + 3].startswith("- Judged gate calls per task (median):"))
        self.assertTrue(lines[i + 4].startswith("- Route:"))
