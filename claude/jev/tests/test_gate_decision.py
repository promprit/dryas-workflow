import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate

NOKEY = {"OPENROUTER_API_KEY": "", "DRYAS_OPENROUTER_KEY": "", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": ""}
# Thresholds under which the Jev rules (decide) would never act on the local judge's answers.
STRICT = {"prescreen": False, "min_confidence": 0.99, "deny_safe_below": 0.9, "ask_risk": "worth_a_look"}


def answers(p_safe, risk="routine", risk_conf=0.9):
    return {"answers": {"safe": {"type": "noul", "value": p_safe, "confidence": max(p_safe, 1 - p_safe)},
                        "risk": {"type": "choice", "value": risk, "confidence": risk_conf, "probabilities": {}}},
            "latency_ms": 7, "input_tokens": 120, "cost": 0.000005}


def boom(state, questions):
    raise RuntimeError("judge broke")


class GateDecisionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        env = dict(NOKEY, JEV_LOG_DIR=os.path.join(self.tmp, "logs"), JEV_SSD_ROOT=self.tmp,
                   JEV_THRESHOLDS=os.path.join(self.tmp, "t.json"))
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        self.cwd = os.path.join(self.tmp, "proj")
        os.makedirs(self.cwd)
        self.th(STRICT)

    def th(self, gate_cfg, judge=None):
        data = {"gate": dict(gate_cfg)}
        if judge is not None:
            data["judge"] = judge
        with open(os.environ["JEV_THRESHOLDS"], "w") as f:
            json.dump(data, f)

    def bash(self, cmd):
        return {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": self.cwd}

    def log(self):
        with open(os.path.join(self.tmp, "logs", "gate.jsonl")) as f:
            return [json.loads(l) for l in f]

    def decision(self, out):
        return out["hookSpecificOutput"]["permissionDecision"] if out else None

    def test_local_decision_ignores_gate_thresholds(self):
        self.assertEqual(self.decision(gate.run(self.bash("rm -rf /"))), "deny")
        self.assertEqual(self.decision(gate.run(self.bash("git reset --hard"))), "ask")
        self.assertIsNone(gate.run(self.bash("make build")))

    def test_local_reason_text(self):
        out = gate.run(self.bash("rm -rf /"))
        self.assertIsNotNone(out)
        self.assertTrue(out["hookSpecificOutput"]["permissionDecisionReason"]
                        .startswith("Local judge: blocked (danger:rm_root)"),
                        out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_shadow_decision_is_the_local_verdict(self):
        out = gate.run(self.bash("git reset --hard"), lambda s, q: answers(0.9))
        self.assertIsNone(out)
        rec = self.log()[-1]
        self.assertEqual((rec["provider"], rec["shadow_provider"], rec["shadow_decision"]), ("jev", "local", "ask"))

    def test_any_jev_exception_falls_back(self):
        for fn in (boom, lambda s, q: {"oops": 1}):
            out = gate.run(self.bash("rm -rf /"), fn)
            self.assertEqual(self.decision(out), "deny")
            rec = self.log()[-1]
            self.assertEqual((rec["provider"], rec["fallback"]), ("local", "local"))
            if fn is boom:
                self.assertEqual(rec["error"], "RuntimeError")

    def test_shadow_failure_never_changes_decision(self):
        self.th(STRICT, {"provider": "local", "shadow": "jev"})
        out = gate.run(self.bash("rm -rf /"), boom)
        self.assertEqual(self.decision(out), "deny")
        rec = self.log()[-1]
        self.assertEqual((rec["provider"], rec["shadow_error"]), ("local", "RuntimeError"))

    def test_prescreen_runs_once_per_judged_call(self):
        self.th(dict(STRICT, prescreen=True))
        calls = []

        def risky(cmd):
            calls.append(cmd)
            return True

        with mock.patch.object(gate, "_risky", side_effect=risky):
            gate.run(self.bash("make build"))
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.log()[-1]["provider"], "local")


if __name__ == "__main__":
    unittest.main()
