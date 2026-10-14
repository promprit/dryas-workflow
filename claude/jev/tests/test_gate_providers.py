import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate
from jev_client import JevUnavailable

NOKEY = {"OPENROUTER_API_KEY": "", "DRYAS_OPENROUTER_KEY": "", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": ""}


def answers(p_safe, risk="routine", risk_conf=0.9):
    return {"answers": {"safe": {"type": "noul", "value": p_safe, "confidence": max(p_safe, 1 - p_safe)},
                        "risk": {"type": "choice", "value": risk, "confidence": risk_conf, "probabilities": {}}},
            "latency_ms": 7, "input_tokens": 120, "cost": 0.000005}


def down(state, questions):
    raise JevUnavailable("HTTPError 503")


class GateProvidersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        env = dict(NOKEY, JEV_LOG_DIR=os.path.join(self.tmp, "logs"), JEV_SSD_ROOT=self.tmp,
                   JEV_THRESHOLDS=os.path.join(self.tmp, "t.json"))
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        self.cwd = os.path.join(self.tmp, "proj")
        os.makedirs(self.cwd)
        self.th(None)

    def th(self, judge):
        data = {"gate": {"prescreen": False}}
        if judge is not None:
            data["judge"] = judge
        with open(os.environ["JEV_THRESHOLDS"], "w") as f:
            json.dump(data, f)

    def bash(self, cmd):
        return {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": self.cwd}

    def log(self):
        with open(os.path.join(self.tmp, "logs", "gate.jsonl")) as f:
            return [json.loads(l) for l in f]

    def test_no_key_local_denies_catastrophe(self):
        out = gate.run(self.bash("rm -rf /"))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertTrue(out["hookSpecificOutput"]["permissionDecisionReason"].startswith("Local judge:"))
        rec = self.log()[-1]
        self.assertEqual((rec["provider"], rec["decision"], rec["reasons"]), ("local", "deny", ["danger:rm_root"]))
        self.assertNotIn("latency_ms", rec)
        self.assertIn("local_ms", rec)

    def test_no_key_everyday_command_passes_through(self):
        self.assertIsNone(gate.run(self.bash("make build")))
        self.assertEqual((self.log()[-1]["decision"], self.log()[-1]["provider"]), ("none", "local"))

    def test_jev_unavailable_falls_back_and_still_denies(self):
        out = gate.run(self.bash("rm -rf /"), down)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        rec = self.log()[-1]
        self.assertEqual((rec["provider"], rec["fallback"], rec["error"]), ("local", "local", "JevUnavailable"))

    def test_shadow_never_changes_the_output(self):
        cases = [("git reset --hard", answers(0.9)), ("rm -rf /", answers(0.9)),
                 ("make build", answers(0.05)), ("make build", answers(0.9, "destructive")),
                 ("git push --force", answers(0.5, "worth_a_look"))]
        for cmd, res in cases:
            self.th({"shadow": "local"})
            a = gate.run(self.bash(cmd), lambda s, q: res)
            self.th({"shadow": "none"})
            b = gate.run(self.bash(cmd), lambda s, q: res)
            self.assertEqual(a, b, cmd)

    def test_jev_reason_text_unchanged(self):
        out = gate.run(self.bash("make build"), lambda s, q: answers(0.05))
        self.assertTrue(out["hookSpecificOutput"]["permissionDecisionReason"].startswith("Jev gate:"))

    def test_shadow_fields_logged(self):
        gate.run(self.bash("git reset --hard"), lambda s, q: answers(0.9))
        rec = self.log()[-1]
        self.assertEqual((rec["provider"], rec["decision"], rec["shadow_provider"], rec["shadow_decision"]),
                         ("jev", "none", "local", "ask"))
        self.assertEqual((rec["shadow_risk"], rec["shadow_reasons"]), ("destructive", ["destructive:git_reset_hard"]))
        self.assertIn("latency_ms", rec)
        self.assertIn("shadow_p_safe", rec)

    def test_local_internal_error_asks(self):
        with mock.patch("local_judge.danger", side_effect=RuntimeError("x")):
            out = gate.run(self.bash("make build"))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertEqual(self.log()[-1]["reasons"], ["error:RuntimeError"])

    def orchestrated(self):
        os.makedirs(os.path.join(self.cwd, ".orchestrate"))
        os.makedirs(os.path.join(self.cwd, ".git"))
        with open(os.path.join(self.cwd, ".git", "HEAD"), "w") as f:
            f.write("ref: refs/heads/feat/a\n")
        with open(os.path.join(self.cwd, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": ["2"]}, f)

    def test_task_id_on_judged_records(self):
        self.orchestrated()
        gate.run(self.bash("make build"))
        self.assertEqual(self.log()[-1]["task"], "feat/a:2")

    def test_task_id_on_skipped_records(self):
        self.orchestrated()
        gate.run(self.bash("ls"))
        rec = self.log()[-1]
        self.assertEqual((rec["decision"], rec["task"]), ("skipped", "feat/a:2"))
