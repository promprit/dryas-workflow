import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate
import jev_mcp
import judge_policy
import route

KEY = {"OPENROUTER_API_KEY": "k", "DRYAS_OPENROUTER_KEY": "", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": ""}


def boom(state, questions):
    raise AssertionError("Jev called under a marker")


class Base(unittest.TestCase):
    def setUp(self):
        judge_policy.clear_cache()
        self.addCleanup(judge_policy.clear_cache)
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.logs = os.path.join(self.tmp, "logs")
        self.cwd = os.path.join(self.tmp, "VOID", "Pilot")
        os.makedirs(self.cwd)
        open(os.path.join(self.tmp, "VOID", ".dryas-judge"), "w").write("local\n")
        th = os.path.join(self.tmp, "t.json")
        with open(th, "w") as f:
            json.dump({"gate": {"prescreen": False}, "judge": {"provider": "jev", "shadow": "jev"}}, f)
        p = mock.patch.dict(os.environ, dict(KEY, JEV_LOG_DIR=self.logs, JEV_SSD_ROOT=self.tmp, JEV_THRESHOLDS=th))
        p.start()
        self.addCleanup(p.stop)

    def last(self, name):
        with open(os.path.join(self.logs, name + ".jsonl")) as f:
            return [json.loads(l) for l in f][-1]


class GatePolicyTest(Base):
    def test_gate_under_marker_never_calls_jev(self):
        ev = {"tool_name": "Bash", "tool_input": {"command": "rm -rf build"}, "cwd": self.cwd, "session_id": "s"}
        gate.run(ev, boom)
        rec = self.last("gate")
        self.assertEqual((rec["provider"], rec["judge_policy"]), ("local", "project_local"))
        self.assertNotIn("fallback", rec)
        self.assertNotIn("shadow_provider", rec)

    def test_gate_without_marker_has_no_policy_field(self):
        os.unlink(os.path.join(self.tmp, "VOID", ".dryas-judge"))
        ev = {"tool_name": "Bash", "tool_input": {"command": "rm -rf build"}, "cwd": self.cwd, "session_id": "s"}
        gate.run(ev, lambda s, q: {"answers": {
            "safe": {"type": "noul", "value": 0.9, "confidence": 0.9},
            "risk": {"type": "choice", "value": "routine", "confidence": 0.9, "probabilities": {}}},
            "latency_ms": 1, "input_tokens": 1, "cost": 0.0})
        self.assertNotIn("judge_policy", self.last("gate"))


class RoutePolicyTest(Base):
    def test_route_under_marker_injects_nothing(self):
        self.assertIsNone(route.run({"prompt": "build x", "cwd": self.cwd}, boom))
        rec = self.last("route")
        self.assertEqual((rec["provider"], rec["injected"], rec["judge_policy"]), ("local", False, "project_local"))


class McpPolicyTest(Base):
    def call(self, state, judge_fn=None):
        return jev_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "jev_judge", "arguments": {"state": state, "questions": {
                "q": {"type": "noul", "instructions": "ok?", "criteria": None}}}}}, judge_fn)

    def test_state_cwd_under_marker_is_local(self):
        self.call({"cwd": self.cwd}, boom)
        rec = self.last("mcp")
        self.assertEqual((rec["provider"], rec["judge_policy"]), ("local", "project_local"))

    def test_process_directory_under_marker_is_local(self):
        with mock.patch("os.getcwd", return_value=self.cwd):
            self.call({"task": "x"}, boom)
        self.assertEqual(self.last("mcp")["judge_policy"], "project_local")

    def test_unmarked_state_cwd_with_marked_process_is_local(self):
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        with mock.patch("os.getcwd", return_value=self.cwd):
            self.call({"cwd": outside}, boom)
        self.assertEqual(self.last("mcp")["judge_policy"], "project_local")


if __name__ == "__main__":
    unittest.main()
