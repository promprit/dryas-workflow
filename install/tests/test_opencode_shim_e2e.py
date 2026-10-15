import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from opencode_e2e import Server, opencode_ok

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))
from mock_llm import RESET_CODE  # noqa: E402

SKIP = opencode_ok()


def say(s, sid, text):
    """Send one more user message into an existing session and wait for the reply."""
    s._http("POST", "/session/%s/message" % sid, {"parts": [{"type": "text", "text": text}]})


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

    def test_judge_ask_blocks_until_user_types_code(self):
        sid = self.s.prompt("RESET")
        bash = self.s.tools(sid)[0]
        self.assertEqual(bash[:2], ("bash", "error"), bash)
        code = re.search(r"dryas allow ([0-9a-f]{4})\b", bash[2])
        self.assertIsNotNone(code, bash[2])
        self.assertEqual(code.group(1), RESET_CODE)
        self.assertIsNone(self.s.asked(sid, timeout=1))
        say(self.s, sid, "dryas allow " + code.group(1))
        self.assertEqual([t[:2] for t in self.s.tools(sid) if t[0] == "bash"], [("bash", "error"), ("bash", "completed")])
        self.assertIsNone(self.s.asked(sid, timeout=1))

    def test_unused_approval_expires_at_next_user_message(self):
        sid = self.s.prompt("RESET")
        code = re.search(r"dryas allow ([0-9a-f]{4})\b", self.s.tools(sid)[0][2]).group(1)
        say(self.s, sid, "dryas allow %s NO_RETRY" % code)
        say(self.s, sid, "hello")
        say(self.s, sid, "RESET")
        self.assertEqual([t[:2] for t in self.s.tools(sid) if t[0] == "bash"], [("bash", "error"), ("bash", "error")])

    def test_code_in_subagent_prompt_does_not_approve(self):
        sid = self.s.prompt("DELEGATE_APPROVE")
        kids = self.s.children(sid)
        self.assertEqual(len(kids), 1)
        bash = [t for t in self.s.tools(kids[0]) if t[0] == "bash"]
        self.assertEqual(bash[0][1], "error", bash)
        self.assertIn("dryas allow " + RESET_CODE, bash[0][2])

    def test_memory_search_through_mcp(self):
        sid = self.s.prompt("MEMSEARCH")
        self.assertIn(("jev_memory_search", "completed"), [t[:2] for t in self.s.tools(sid)])


@unittest.skipIf(SKIP, SKIP)
class ShimEdgeTest(unittest.TestCase):
    def test_user_rules_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            # OpenCode applies the last matching pattern, so the user's "echo *" ask comes after "*".
            s = Server(Path(d), config_extra={"permission": {"bash": {"*": "allow", "echo *": "ask"}}})
            try:
                sid = s.prompt("ECHO", wait=False)
                self.assertIsNotNone(s.asked(sid), "the user's own ask rule must still reach the user")
                sid = s.prompt("LS")
                self.assertEqual([t[:2] for t in s.tools(sid)], [("bash", "completed")])
                self.assertIsNone(s.asked(sid, timeout=1))
            finally:
                s.close()

    def test_user_deny_kept(self):
        with tempfile.TemporaryDirectory() as d:
            s = Server(Path(d), config_extra={"permission": {"edit": "deny"}})
            try:
                sid = s.prompt("WRITE_ALLOWED")
                self.assertFalse((s.proj / "allowed.txt").exists(), s.tools(sid))
            finally:
                s.close()

    def test_broken_python_fails_closed_with_active_task(self):
        with tempfile.TemporaryDirectory() as d:
            s = Server(Path(d), env_extra={"DRYAS_PY": str(Path(d) / "no-such-python")})
            try:
                orch = s.proj / ".orchestrate"
                orch.mkdir()
                (orch / "PLAN.md").write_text(PLAN, encoding="utf-8")
                (orch / "active.json").write_text(json.dumps({"active": ["1"]}), encoding="utf-8")
                sid = s.prompt("WRITE_ALLOWED")
                self.assertFalse((s.proj / "allowed.txt").exists(), s.tools(sid))
                self.assertIn("could not run its checks", s.tools(sid)[0][2])
                shutil.rmtree(str(orch))
                sid = s.prompt("WRITE_ALLOWED")
                self.assertTrue((s.proj / "allowed.txt").exists(), s.tools(sid))
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
