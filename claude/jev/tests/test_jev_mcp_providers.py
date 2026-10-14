import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jev_mcp

NOKEY = {"OPENROUTER_API_KEY": "", "DRYAS_OPENROUTER_KEY": "", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": ""}
QUESTIONS = {
    "specific": {"type": "noul", "instructions": "is this specific?", "criteria": None},
    "executor": {"type": "choice", "instructions": "who executes?", "criteria": {"coder": "writes code", "tester": "tests"}},
}
RES = {"answers": {"specific": {"type": "noul", "value": 0.9, "confidence": 0.9},
                   "executor": {"type": "choice", "value": "coder", "confidence": 0.95, "probabilities": {}}},
       "latency_ms": 9, "input_tokens": 200, "cost": 0.0000084}


def call(args, judge_fn=None):
    return jev_mcp.handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                           "params": {"name": "jev_judge", "arguments": args}}, judge_fn)


def payload(r):
    return r["result"]["content"][0]["text"]


class McpProvidersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, dict(NOKEY, JEV_LOG_DIR=self.tmp, JEV_THRESHOLDS=os.path.join(self.tmp, "t.json")))
        p.start()
        self.addCleanup(p.stop)

    def last(self):
        with open(os.path.join(self.tmp, "mcp.jsonl")) as f:
            return [json.loads(l) for l in f][-1]

    def test_no_key_escalates_every_question_without_error(self):
        r = call({"state": {}, "questions": QUESTIONS})
        self.assertFalse(r["result"]["isError"])
        p = json.loads(payload(r))
        self.assertEqual((p["answers"], p["escalate"], p["provider"]), ({}, ["executor", "specific"], "local"))
        self.assertEqual((self.last()["provider"], self.last()["escalate"]), ("local", ["executor", "specific"]))

    def test_invalid_questions_still_rejected_locally(self):
        r = call({"state": {}, "questions": {"q": {"type": "choice", "instructions": "x?", "criteria": "bad"}}})
        self.assertTrue(r["result"]["isError"])

    def test_missing_state_rejected_locally(self):
        self.assertTrue(call({"questions": QUESTIONS})["result"]["isError"])

    def test_injected_judge_still_answers_and_names_jev(self):
        p = json.loads(payload(call({"state": {}, "questions": QUESTIONS}, lambda s, q: RES)))
        self.assertEqual(p["answers"]["executor"]["value"], "coder")
        self.assertEqual(self.last()["provider"], "jev")
