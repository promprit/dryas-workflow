"""Plan 2, step-2 rows of the shim: observe-only chain calls and usage, against a real opencode serve."""
import json
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

from opencode_e2e import Server, opencode_ok

SKIP = opencode_ok()
PLAN = "## Task 1: t\nGoal: g\nScope:\n- src/**\nDone:\n- d\nFailing test first: none (review)\n"


def wait_for(fn, timeout=30.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.3)
    return fn()


def probe_chain(path: Path, log: Path) -> None:
    """A chain.json whose observe kinds append each event to LOG (one JSON line); pretool and prompt stay empty."""
    cmd = ["$PY", "-c", "import sys; open(sys.argv[1], 'a').write(sys.stdin.read().replace('\\n', ' ') + '\\n')",
           str(log).replace("\\", "/")]
    kinds = ("post", "stop", "subagent-stop", "session-start", "session-end", "precompact")
    path.write_text(json.dumps({k: [{"name": "probe", "harness": ["opencode"], "cmd": cmd, "timeout": 5,
                                     "observe": True}] for k in kinds}), encoding="utf-8")


@unittest.skipIf(SKIP, SKIP)
class ProbeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="dryas-oc-probe-"))
        cls.log = cls.dir / "events.jsonl"
        cls.log.touch()
        probe_chain(cls.dir / "chain.json", cls.log)
        cls.s = Server(cls.dir / "srv", env_extra={"JEV_CHAIN_CONFIG": str(cls.dir / "chain.json")})

    @classmethod
    def tearDownClass(cls):
        cls.s.close()
        shutil.rmtree(str(cls.dir), ignore_errors=True)

    def events(self, name, sid=None):
        evs = [json.loads(l) for l in self.log.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [e for e in evs if e.get("hook_event_name") == name and (sid is None or e.get("session_id") == sid)]

    def test_post_reaches_chain(self):
        sid = self.s.prompt("WRITE_ALLOWED")
        post = wait_for(lambda: self.events("PostToolUse", sid))
        self.assertEqual(post[0]["tool_name"], "Write")
        self.assertTrue(post[0]["tool_input"]["file_path"].endswith("allowed.txt"))
        self.assertTrue(post[0]["tool_use_id"])

    def test_session_start_and_stop_reach_chain(self):
        sid = self.s.prompt("hello")
        self.assertTrue(wait_for(lambda: self.events("SessionStart", sid)))
        self.assertTrue(wait_for(lambda: self.events("Stop", sid)))

    def test_subagent_stop_carries_agent_identity(self):
        sid = self.s.prompt("DELEGATE")
        kid = self.s.children(sid)[0]
        stop = wait_for(lambda: self.events("SubagentStop", kid))
        self.assertEqual(stop[0]["agent_id"], kid)
        self.assertEqual(stop[0]["agent_type"], "dryas-executor-fast")
        self.assertFalse(self.events("SessionStart", kid), "a subagent session is not a session start")

    def test_session_end_on_delete(self):
        sid = self.s.prompt("hello")
        self.s._http("DELETE", "/session/%s" % sid)
        self.assertTrue(wait_for(lambda: self.events("SessionEnd", sid)))


@unittest.skipIf(SKIP, SKIP)
class RealStageTest(unittest.TestCase):
    """The default chain: memory rows, context warning, and no failed edit for a call the shim blocked."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="dryas-oc-real-")
        cls.s = Server(Path(cls.dir))

    @classmethod
    def tearDownClass(cls):
        cls.s.close()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def rows(self, sql, *args):
        db = self.s.data / "dryas.db"
        if not db.exists():
            return []
        con = sqlite3.connect(str(db))
        try:
            return con.execute(sql, args).fetchall()
        except sqlite3.OperationalError:
            return []
        finally:
            con.close()

    def test_edit_is_recorded(self):
        sid = self.s.prompt("WRITE_ALLOWED")
        self.assertEqual(wait_for(lambda: self.rows("SELECT ok FROM edits WHERE session = ?", sid)), [(1,)])

    def test_blocked_write_is_not_a_failed_edit(self):
        orch = self.s.proj / ".orchestrate"
        orch.mkdir()
        try:
            (orch / "PLAN.md").write_text(PLAN, encoding="utf-8")
            (orch / "active.json").write_text(json.dumps({"active": ["1"]}), encoding="utf-8")
            sid = self.s.prompt("DELEGATE")
            kid = self.s.children(sid)[0]
            self.assertEqual([t[1] for t in self.s.tools(kid) if t[0] == "write"], ["error"])
            self.assertTrue(wait_for(lambda: self.rows("SELECT task_id FROM tasks WHERE task_id LIKE '%:1'")))  # "<branch>:<id>"  # subagent-stop
            time.sleep(2)
            self.assertEqual(self.rows("SELECT ok FROM edits WHERE session = ?", kid), [])
        finally:
            shutil.rmtree(str(orch))

    def test_context_warning_reaches_model(self):
        sid = self.s.prompt("BIGUSAGE")
        self.s._http("POST", "/session/%s/message" % sid, {"parts": [{"type": "text", "text": "next"}]})
        last = [r for r in self.s.requests() if "next" in r.get("user", "")]
        self.assertTrue(last and "run /handoff then /new" in last[-1]["user"], last[-1:] or self.s.requests()[-1:])


if __name__ == "__main__":
    unittest.main()
