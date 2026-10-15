import json
import shutil
import tempfile
import unittest
from pathlib import Path

from opencode_e2e import Server, opencode_ok

SKIP = opencode_ok()
PLAN = "## Task 1: t\nGoal: g\nScope:\n- src/**\nDone:\n- d\nFailing test first: none (review)\n"


@unittest.skipIf(SKIP, SKIP)
class ShimTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="dryas-oc-")
        cls.s = Server(Path(cls.dir))

    @classmethod
    def tearDownClass(cls):
        cls.s.close()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_rules_reach_the_model(self):
        self.s.prompt("hello")
        self.assertTrue(any("Dryas Workflow (OpenCode)" in str(x) for r in self.s.requests() for x in r["system"]))

    def test_allowed_write_lands(self):
        sid = self.s.prompt("WRITE_ALLOWED")
        self.assertTrue((self.s.proj / "allowed.txt").exists(), self.s.tools(sid))

    def test_executor_out_of_scope_write_is_blocked(self):
        orch = self.s.proj / ".orchestrate"
        orch.mkdir()
        try:
            (orch / "PLAN.md").write_text(PLAN, encoding="utf-8")
            (orch / "active.json").write_text(json.dumps({"active": ["1"]}), encoding="utf-8")
            sid = self.s.prompt("DELEGATE")
            kids = self.s.children(sid)
            self.assertEqual(len(kids), 1)
            write = [t for t in self.s.tools(kids[0]) if t[0] == "write"]
            self.assertEqual(write[0][1], "error")
            self.assertIn("[scope-lock]", write[0][2])
            self.assertFalse((self.s.proj / "out.txt").exists())
        finally:
            shutil.rmtree(str(orch))

    def test_judge_ask_waits_for_the_user(self):
        sid = self.s.prompt("RESET", wait=False)
        asked = self.s.asked(sid)
        self.assertIsNotNone(asked)
        self.assertEqual(asked["permission"], "bash")
        self.assertEqual(self.s.tools(sid)[0][:2], ("bash", "running"))
        self.s.reply(sid, asked["id"], "reject")
        for _ in range(40):
            if self.s.tools(sid)[0][1] == "error":
                break
            __import__("time").sleep(0.5)
        self.assertEqual(self.s.tools(sid)[0][1], "error")

    def test_memory_search_through_mcp(self):
        sid = self.s.prompt("MEMSEARCH")
        self.assertIn(("jev_memory_search", "completed"), [t[:2] for t in self.s.tools(sid)])


@unittest.skipIf(SKIP, SKIP)
class ShimEdgeTest(unittest.TestCase):
    def test_user_ask_rule_is_kept(self):
        with tempfile.TemporaryDirectory() as d:
            s = Server(Path(d), config_extra={"permission": {"bash": {"echo *": "ask", "*": "allow"}}})
            try:
                sid = s.prompt("ECHO", wait=False)
                self.assertIsNotNone(s.asked(sid), "the user's own ask rule must still reach the user")
            finally:
                s.close()

    def test_broken_python_fails_open(self):
        with tempfile.TemporaryDirectory() as d:
            s = Server(Path(d), env_extra={"DRYAS_PY": str(Path(d) / "no-such-python")})
            try:
                sid = s.prompt("WRITE_ALLOWED")
                self.assertTrue((s.proj / "allowed.txt").exists(), s.tools(sid))
            finally:
                s.close()


if __name__ == "__main__":
    unittest.main()
