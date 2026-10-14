import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jev_mcp

BASE = {"task": "feat/x:2", "tier": "haiku", "role": "coder", "attempt": 1}


def call(args):
    return jev_mcp.handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                           "params": {"name": "log_dispatch", "arguments": args}})


class AgentIdTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, {"JEV_LOG_DIR": self.tmp, "JEV_THRESHOLDS": os.path.join(self.tmp, "t.json")})
        p.start()
        self.addCleanup(p.stop)

    def last(self):
        with open(os.path.join(self.tmp, "dispatch.jsonl")) as f:
            return [json.loads(l) for l in f][-1]

    def test_agent_id_is_recorded(self):
        # Defect: the executor's agent id is dropped, so FlowObserve cannot pair a task tag with its executor.
        r = call(dict(BASE, agent_id="a1b2c3"))
        self.assertFalse(r["result"]["isError"])
        self.assertEqual(self.last()["agent_id"], "a1b2c3")

    def test_agent_id_is_stored_stripped_and_at_64_chars(self):
        # Defect: surrounding whitespace is kept, or the 64-char limit is off by one.
        call(dict(BASE, agent_id="  abc  "))
        self.assertEqual(self.last()["agent_id"], "abc")
        call(dict(BASE, agent_id="x" * 64))
        self.assertEqual(self.last()["agent_id"], "x" * 64)

    def test_invalid_agent_id_is_dropped_not_an_error(self):
        # Defect: a bad agent_id is logged, or it turns the call into an error.
        for bad in ("x" * 65, "", "   ", 7, True, ["a"]):
            r = call(dict(BASE, agent_id=bad))
            self.assertFalse(r["result"]["isError"], repr(bad))
            self.assertNotIn("agent_id", self.last(), repr(bad))

    def test_schema_lists_agent_id_with_max_length(self):
        r = jev_mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool = next(t for t in r["result"]["tools"] if t["name"] == "log_dispatch")
        self.assertEqual(tool["inputSchema"]["properties"]["agent_id"], {"type": "string", "maxLength": 64})
        self.assertIn("agent_id: the Agent result's agent id", tool["description"])
        self.assertEqual(tool["inputSchema"]["required"], ["task", "tier", "role", "attempt"])

    def test_call_without_agent_id_logs_the_same_keys(self):
        # Defect: an absent agent_id adds a key (for example agent_id: null) to the record.
        call(dict(BASE))
        rec = self.last()
        self.assertEqual(set(rec) - {"ts", "session_id", "cwd"}, {"task", "tier", "role", "attempt"})
        self.assertNotIn("agent_id", rec)


if __name__ == "__main__":
    unittest.main()
