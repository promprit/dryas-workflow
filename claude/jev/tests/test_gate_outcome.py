import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import gate

SCRIPT = os.path.join(HERE, "gate_outcome.py")


class GateOutcomeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.logs = os.path.join(self.tmp, "logs")

    def run_stage(self, stdin):
        env = dict(os.environ, JEV_LOG_DIR=self.logs)
        return subprocess.run([sys.executable, SCRIPT], input=stdin, env=env, capture_output=True, text=True,
                              timeout=20)

    def outcomes(self):
        try:
            with open(os.path.join(self.logs, "outcomes.jsonl"), encoding="utf-8") as f:
                return [json.loads(l) for l in f]
        except OSError:
            return []

    def test_logs_the_tool_use_id(self):
        os.makedirs(self.logs)
        with open(os.path.join(self.logs, "asks_pending.json"), "w", encoding="utf-8") as f:
            json.dump(["t1"], f)  # gate.py noted an ask for t1; only asked calls are logged
        r = self.run_stage(json.dumps({"tool_name": "Bash", "tool_use_id": "t1"}))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")
        rows = self.outcomes()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["tool_use_id"], rows[0]["tool"]), ("t1", "Bash"))

    def test_no_id_writes_nothing(self):
        self.assertEqual(self.run_stage(json.dumps({"tool_name": "Bash"})).returncode, 0)
        self.assertEqual(self.outcomes(), [])

    def test_failed_call_is_not_an_approval(self):
        ev = {"hook_event_name": "PostToolUseFailure", "tool_name": "Bash", "tool_use_id": "t2"}
        self.assertEqual(self.run_stage(json.dumps(ev)).returncode, 0)
        self.assertEqual(self.outcomes(), [])

    def test_non_json_exits_zero(self):
        r = self.run_stage("not json {")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.outcomes(), [])


class GateRecordIdTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, {"JEV_LOG_DIR": os.path.join(self.tmp, "logs"), "JEV_SSD_ROOT": self.tmp,
                                         "JEV_THRESHOLDS": os.path.join(self.tmp, "missing.json")})
        p.start()
        self.addCleanup(p.stop)

    def log(self):
        with open(os.path.join(self.tmp, "logs", "gate.jsonl")) as f:
            return [json.loads(l) for l in f]

    def test_gate_record_carries_tool_use_id(self):
        gate.run({"tool_name": "Bash", "tool_use_id": "t9", "tool_input": {"command": "ls"}})
        self.assertEqual(self.log()[-1]["tool_use_id"], "t9")

    def test_gate_record_without_id_has_no_field(self):
        gate.run({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertNotIn("tool_use_id", self.log()[-1])


if __name__ == "__main__":
    unittest.main()
