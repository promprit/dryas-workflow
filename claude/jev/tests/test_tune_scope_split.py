import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tune


def write(d, name, recs):
    with open(os.path.join(d, name + ".jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")


class ScopeSplitTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.environ["JEV_LOG_DIR"] = self.d
        os.environ["JEV_THRESHOLDS"] = os.path.join(self.d, "thresholds.json")

    def test_split_counts(self):
        write(self.d, "scope", [{"task": ["1"], "path": "a", "decision": "deny"}] * 2
              + [{"task": ["1"], "tool": "Bash", "decision": "ask"}] * 3
              + [{"task": ["1"], "tool": "Bash", "decision": "allow", "kind": "allow", "rule": "inline_code", "run": True}] * 4
              + [{"task": ["1"], "tool": "audit", "decision": "violation", "kind": "violation", "run": True}])
        write(self.d, "gate", [{"tool": "Bash", "decision": "ask", "run": True}, {"tool": "Bash", "decision": "ask", "run": False}])
        d = tune.build()["delivery"]
        self.assertEqual((d["scope_denials"], d["scope_asks"], d["scope_violations"], d["run_prompts"]), (2, 3, 1, 1))

    def test_render_names_run_prompts(self):
        write(self.d, "gate", [{"tool": "Bash", "decision": "ask", "run": True}])
        self.assertIn("Prompts during runs (target 0): 1", tune.render(tune.build(), []))


if __name__ == "__main__":
    unittest.main()
