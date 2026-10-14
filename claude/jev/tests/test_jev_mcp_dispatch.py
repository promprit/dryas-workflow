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


class ReturnPhaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, {"JEV_LOG_DIR": self.tmp, "JEV_THRESHOLDS": os.path.join(self.tmp, "t.json")})
        p.start()
        self.addCleanup(p.stop)

    def recs(self):
        with open(os.path.join(self.tmp, "dispatch.jsonl")) as f:
            return [json.loads(l) for l in f]

    def test_return_phase_is_recorded(self):
        # Defect: usage can only arrive on the dispatch-time record, so it is lost or the dispatch log moves.
        call(dict(BASE, score=42))
        r = call(dict(BASE, phase="return", tokens=900, duration_ms=5000, agent_id="a1"))
        self.assertFalse(r["result"]["isError"])
        first, second = self.recs()
        self.assertNotIn("phase", first)
        self.assertEqual((second["phase"], second["tokens"], second["duration_ms"], second["agent_id"]),
                         ("return", 900, 5000, "a1"))

    def test_invalid_phase_is_dropped_not_an_error(self):
        for bad in ("dispatch", "RETURN", 1, None, ["return"]):
            r = call(dict(BASE, phase=bad))
            self.assertFalse(r["result"]["isError"])
            self.assertNotIn("phase", self.recs()[-1])

    def test_schema_lists_phase(self):
        r = jev_mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool = next(t for t in r["result"]["tools"] if t["name"] == "log_dispatch")
        self.assertEqual(tool["inputSchema"]["properties"]["phase"]["enum"], ["return"])
        self.assertNotIn("phase", tool["inputSchema"]["required"])


class DispatchExtrasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, {"JEV_LOG_DIR": self.tmp, "JEV_THRESHOLDS": os.path.join(self.tmp, "t.json")})
        p.start()
        self.addCleanup(p.stop)

    def last(self):
        with open(os.path.join(self.tmp, "dispatch.jsonl")) as f:
            return [json.loads(l) for l in f][-1]

    def test_usage_and_score_are_recorded(self):
        r = call(dict(BASE, tokens=48210, duration_ms=93000, score=42, score_tier="sonnet", task_type="code+tests"))
        self.assertFalse(r["result"]["isError"])
        rec = self.last()
        self.assertEqual({k: rec[k] for k in ("tokens", "duration_ms", "score", "score_tier", "task_type")},
                         {"tokens": 48210, "duration_ms": 93000, "score": 42, "score_tier": "sonnet",
                          "task_type": "code+tests"})

    def test_old_calls_log_the_same_record(self):
        call(dict(BASE))
        rec = self.last()
        self.assertEqual(set(rec) - {"ts", "session_id", "cwd"}, {"task", "tier", "role", "attempt"})

    def test_invalid_optional_values_are_dropped_not_errors(self):
        r = call(dict(BASE, tokens=-1, duration_ms=1.5, score=101, score_tier="fable", task_type=7))
        self.assertFalse(r["result"]["isError"])
        rec = self.last()
        for k in ("tokens", "duration_ms", "score", "score_tier", "task_type"):
            self.assertNotIn(k, rec)
        call(dict(BASE, tokens=True, score="12", task_type="x" * 80))
        rec = self.last()
        self.assertNotIn("tokens", rec)
        self.assertEqual((rec["score"], len(rec["task_type"])), (12, 32))

    def test_schema_lists_the_optional_fields(self):
        r = jev_mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool = next(t for t in r["result"]["tools"] if t["name"] == "log_dispatch")
        props = tool["inputSchema"]["properties"]
        for k in ("tokens", "duration_ms", "score", "score_tier", "task_type"):
            self.assertIn(k, props)
        self.assertEqual(tool["inputSchema"]["required"], ["task", "tier", "role", "attempt"])

    def test_bool_nan_and_inf_are_dropped_without_a_crash(self):
        # Defect: bool passes as int (True -> 1), or NaN/inf reach json.dumps and write invalid JSON.
        r = call(dict(BASE, tokens=True, score=False))
        self.assertFalse(r["result"]["isError"])
        rec = self.last()
        self.assertNotIn("tokens", rec)
        self.assertNotIn("score", rec)
        for bad in (float("nan"), float("inf"), float("-inf")):
            r = call(dict(BASE, tokens=bad, duration_ms=bad, score=bad))
            self.assertFalse(r["result"]["isError"])
            rec = self.last()
            for k in ("tokens", "duration_ms", "score"):
                self.assertNotIn(k, rec)

    def test_score_bounds_are_inclusive(self):
        # Defect: off-by-one bounds (score 0 or 100 dropped, or -1 or 101 kept).
        for ok in (0, 100):
            call(dict(BASE, score=ok))
            self.assertEqual(self.last()["score"], ok)
        for bad in (-1, 101):
            call(dict(BASE, score=bad))
            self.assertNotIn("score", self.last())

    def test_zero_tokens_and_duration_are_recorded(self):
        # Defect: 0 treated as missing (falsy check instead of None check).
        r = call(dict(BASE, tokens=0, duration_ms=0))
        self.assertFalse(r["result"]["isError"])
        rec = self.last()
        self.assertEqual((rec["tokens"], rec["duration_ms"]), (0, 0))

    def test_blank_task_type_and_list_tier_are_dropped_without_error(self):
        # Defect: a blank task_type is logged, or a non-string tier raises instead of being dropped.
        for ttype in ("", "   "):
            r = call(dict(BASE, task_type=ttype))
            self.assertFalse(r["result"]["isError"])
            self.assertNotIn("task_type", self.last())
        r = call(dict(BASE, score_tier=["opus"]))
        self.assertFalse(r["result"]["isError"])
        self.assertNotIn("score_tier", self.last())

    def test_schema_bounds_score_and_enumerates_tier(self):
        # Defect: the schema omits the constraints that the runtime check enforces.
        r = jev_mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool = next(t for t in r["result"]["tools"] if t["name"] == "log_dispatch")
        props = tool["inputSchema"]["properties"]
        self.assertEqual((props["score"]["minimum"], props["score"]["maximum"]), (0, 100))
        self.assertEqual(props["score_tier"]["enum"], ["haiku", "sonnet", "opus"])
        self.assertEqual((props["tokens"]["minimum"], props["duration_ms"]["minimum"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
