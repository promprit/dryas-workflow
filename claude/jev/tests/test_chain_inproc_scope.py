import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import chain
import scope_lock

PLAN = "## Task 1: a\nGoal: g\nScope:\n- src/feature/**\nDone:\n- d\n"
SCOPE_STAGE = {"name": "scope-lock", "inproc": "scope_lock", "cmd": ["unused"],
               "match": "Bash|Edit|Write|MultiEdit|NotebookEdit", "fail_closed": True}


class InprocScopeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["JEV_LOG_DIR"] = os.path.join(self.tmp, "logs")
        self.wt = os.path.join(self.tmp, "wt")
        os.makedirs(os.path.join(self.wt, ".orchestrate"))
        with open(os.path.join(self.wt, ".orchestrate", "PLAN.md"), "w", encoding="utf-8") as f:
            f.write(PLAN)
        self.active = os.path.join(self.wt, ".orchestrate", "active.json")
        with open(self.active, "w", encoding="utf-8") as f:
            json.dump({"active": ["1"]}, f)

    def _pre(self, event):
        return chain.pretool(event, json.dumps(event), [SCOPE_STAGE])

    def _write(self, rel):
        return {"tool_name": "Write", "tool_input": {"file_path": os.path.join(self.wt, rel), "content": "x"},
                "cwd": self.wt, "agent_id": "a1"}

    def test_scope_lock_runs_without_a_subprocess(self):
        def fake(st, raw):
            if st.get("name") == "scope-lock":
                raise AssertionError("scope-lock must not run as a subprocess")
            return 0, "", ""
        with mock.patch.object(chain, "_run", side_effect=fake) as m:
            out = self._pre(self._write("docs/a.md"))
        m.assert_not_called()
        hso = out["hookSpecificOutput"]
        self.assertEqual(hso["permissionDecision"], "deny")
        self.assertTrue(hso["permissionDecisionReason"].startswith("[scope-lock] scope lock:"), hso)

    def test_in_scope_allowed(self):
        self.assertIsNone(self._pre(self._write("src/feature/a.py")))

    def test_bash_out_of_scope_denied_in_process(self):
        ev = {"tool_name": "Bash", "tool_input": {"command": "echo x > docs/a.md"}, "cwd": self.wt, "agent_id": "a1"}
        out = self._pre(ev)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_crash_fails_closed_while_active(self):
        ev = self._write("src/feature/a.py")
        with mock.patch.object(scope_lock, "run", side_effect=RuntimeError("boom")):
            out = self._pre(ev)
            self.assertIn("fail closed", out["hookSpecificOutput"]["permissionDecisionReason"])
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
            os.remove(self.active)
            self.assertIsNone(self._pre(ev))

    def test_chain_json_scope_stage_is_inproc(self):
        with open(os.path.join(HERE, "chain.json"), encoding="utf-8") as f:
            stages = json.load(f)["pretool"]
        st = [s for s in stages if s["name"] == "scope-lock"][0]
        self.assertEqual(st.get("inproc"), "scope_lock")


if __name__ == "__main__":
    unittest.main()
