import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate

NOKEY = {"OPENROUTER_API_KEY": "", "DRYAS_OPENROUTER_KEY": "", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": ""}
STRICT = {"prescreen": False, "min_confidence": 0.99, "deny_safe_below": 0.9, "ask_risk": "worth_a_look"}
PLAN = "## Risky actions\n- `git reset --hard` — throws away uncommitted edits in this worktree.\n\n## Task 1: a\nGoal: g\nScope:\n- src/**\n"


class GateRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        env = dict(NOKEY, JEV_LOG_DIR=os.path.join(self.tmp, "logs"), JEV_SSD_ROOT=self.tmp,
                   JEV_THRESHOLDS=os.path.join(self.tmp, "t.json"))
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        with open(os.environ["JEV_THRESHOLDS"], "w") as f:
            json.dump({"gate": STRICT}, f)
        self.wt = os.path.realpath(os.path.join(self.tmp, "wt"))
        os.makedirs(os.path.join(self.wt, ".git"))
        os.makedirs(os.path.join(self.wt, ".orchestrate"))
        with open(os.path.join(self.wt, ".orchestrate", "PLAN.md"), "w") as f:
            f.write(PLAN)

    def active(self, ids):
        with open(os.path.join(self.wt, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": ids}, f)

    def run_bash(self, cmd):
        out = gate.run({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": self.wt, "agent_id": "a1",
                        "tool_use_id": "toolu_1"})
        return (out["hookSpecificOutput"]["permissionDecision"], out["hookSpecificOutput"]["permissionDecisionReason"]) if out else (None, "")

    def last(self):
        with open(os.path.join(self.tmp, "logs", "gate.jsonl")) as f:
            return json.loads(f.readlines()[-1])

    def test_ask_outside_run_unchanged(self):
        self.assertEqual(self.run_bash("git clean -fd")[0], "ask")
        self.assertIs(self.last()["run"], False)

    def test_ask_becomes_deny_during_run(self):
        self.active(["1"])
        d, reason = self.run_bash("git clean -fd")
        self.assertEqual(d, "deny")
        self.assertIn("NEEDS DECISION", reason)
        self.assertNotIn("please confirm", reason)
        self.assertEqual((self.last()["run"], self.last()["rule"]), (True, "run_deny"))

    def test_planned_action_allowed_during_run(self):
        self.active(["1"])
        self.assertEqual(self.run_bash("git reset --hard")[0], None)
        self.assertEqual(self.last()["rule"], "planned")

    def test_orchestrator_approved_allowed(self):
        self.active(["1"])
        with open(os.path.join(self.wt, ".orchestrate", "approved.json"), "w") as f:
            json.dump({"commands": [{"cmd": "git clean -fd", "task": "1", "reason": "generated files only"}]}, f)
        self.assertEqual(self.run_bash("git clean -fd")[0], None)
        self.assertEqual(self.last()["rule"], "orchestrator")

    def test_deny_stays_deny(self):
        self.active(["1"])
        self.assertEqual(self.run_bash("rm -rf /")[0], "deny")

    def test_malformed_active_json_counts_as_run(self):
        with open(os.path.join(self.wt, ".orchestrate", "active.json"), "w") as f:
            f.write("{nope")
        self.assertEqual(self.run_bash("git clean -fd")[0], "deny")

    def test_no_ask_noted_during_run(self):
        self.active(["1"])
        with mock.patch.object(gate.gate_outcome, "note_ask") as note:
            self.run_bash("git clean -fd")
        note.assert_not_called()


if __name__ == "__main__":
    unittest.main()
