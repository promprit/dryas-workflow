import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jev_mcp
from jev_client import JevUnavailable

RES = {"answers": {"specific": {"type": "noul", "value": 0.9, "confidence": 0.9},
                   "executor": {"type": "choice", "value": "coder", "confidence": 0.55, "probabilities": {}}},
       "latency_ms": 9, "input_tokens": 200, "cost": 0.0000084}

VALID_QUESTIONS = {
    "specific": {"type": "noul", "instructions": "is this specific?", "criteria": None},
    "executor": {"type": "choice", "instructions": "who executes?", "criteria": {"coder": "writes code", "tester": "tests"}}
}


def call(name, args, judge_fn=None):
    return jev_mcp.handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": name, "arguments": args}}, judge_fn)


class McpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["JEV_LOG_DIR"] = self.tmp
        os.environ["JEV_THRESHOLDS"] = os.path.join(self.tmp, "none.json")

    def read(self, name):
        with open(os.path.join(self.tmp, name + ".jsonl")) as f:
            return [json.loads(l) for l in f]

    def test_initialize_echoes_protocol(self):
        r = jev_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
        self.assertEqual(r["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("tools", r["result"]["capabilities"])
        self.assertEqual(r["result"]["serverInfo"]["name"], "jev")

    def test_notification_gets_no_reply(self):
        self.assertIsNone(jev_mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_tools_list(self):
        r = jev_mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(sorted(t["name"] for t in r["result"]["tools"]),
                         ["jev_judge", "log_dispatch", "log_escalation", "log_merge", "log_override", "log_review"])

    def test_log_dispatch(self):
        r = call("log_dispatch", {"task": "t1", "tier": "sonnet", "role": "coder", "attempt": "1", "extra": "x"})
        self.assertFalse(r["result"]["isError"])
        rec = self.read("dispatch")[0]
        self.assertEqual({k: rec[k] for k in ("task", "tier", "role", "attempt")},
                         {"task": "t1", "tier": "sonnet", "role": "coder", "attempt": 1})
        self.assertNotIn("extra", rec)

    def test_log_review(self):
        call("log_review", {"task": "feat-x", "round": 2, "critical": 0, "important": 3, "minor": 1})
        rec = self.read("review")[0]
        self.assertEqual((rec["round"], rec["important"]), (2, 3))

    def test_log_merge_with_and_without_cost(self):
        call("log_merge", {"task": "feat-x", "branch": "feat-x", "tasks_merged": 5, "cost_usd": 4.2})
        call("log_merge", {"task": "feat-y", "branch": "feat-y", "tasks_merged": 2})
        a, b = self.read("merge")
        self.assertEqual(a["cost_usd"], 4.2)
        self.assertNotIn("cost_usd", b)

    def test_log_tools_reject_bad_input_and_write_nothing(self):
        bad = [("log_dispatch", {"task": "t1", "tier": "sonnet", "role": "coder"}),              # missing attempt
               ("log_dispatch", {"task": "", "tier": "sonnet", "role": "coder", "attempt": 1}),  # empty task
               ("log_dispatch", {"task": "t1", "tier": "sonnet", "role": "coder", "attempt": True}),
               ("log_dispatch", {"task": "t1", "tier": "sonnet", "role": "coder", "attempt": 1.5}),
               ("log_review", {"task": "b", "round": 0, "critical": 0, "important": 0, "minor": 0}),
               ("log_review", {"task": "b", "round": 1, "critical": -1, "important": 0, "minor": 0}),
               ("log_merge", {"task": "b", "branch": "b", "tasks_merged": "many"})]
        for name, args in bad:
            r = call(name, args)
            self.assertTrue(r["result"]["isError"], (name, args))
        for f in ("dispatch", "review", "merge"):
            self.assertFalse(os.path.exists(os.path.join(self.tmp, f + ".jsonl")), f)

    def test_log_merge_ignores_bad_cost(self):
        call("log_merge", {"task": "b", "branch": "b", "tasks_merged": 1, "cost_usd": "nan"})
        call("log_merge", {"task": "c", "branch": "c", "tasks_merged": 1, "cost_usd": -3})
        self.assertTrue(all("cost_usd" not in r for r in self.read("merge")))

    def test_judge_marks_escalations_and_logs(self):
        r = call("jev_judge", {"state": {"x": 1}, "questions": VALID_QUESTIONS}, lambda s, q: RES)
        payload = json.loads(r["result"]["content"][0]["text"])
        self.assertEqual(payload["escalate"], ["executor"])
        self.assertFalse(r["result"].get("isError", False))
        self.assertEqual(self.read("mcp")[0]["answers"]["executor"], {"value": "coder", "confidence": 0.55})

    def test_judge_unavailable_is_tool_error(self):
        def boom(s, q):
            raise JevUnavailable("HTTPError 400")
        r = call("jev_judge", {"state": {}, "questions": VALID_QUESTIONS}, boom)
        self.assertTrue(r["result"]["isError"])
        self.assertIn("HTTPError 400", r["result"]["content"][0]["text"])
        self.assertIn("Opus decides", r["result"]["content"][0]["text"])

    def test_judge_missing_questions_is_tool_error(self):
        r = call("jev_judge", {"state": {}}, lambda s, q: RES)
        self.assertTrue(r["result"]["isError"])

    def test_log_escalation(self):
        call("log_escalation", {"task": "T2", "reason": "failed twice on sonnet", "decided_by": "opus", "from_model": "sonnet", "to_model": "fable"})
        self.assertEqual(self.read("escalations")[0]["to_model"], "fable")

    def test_log_override(self):
        call("log_override", {"question": "executor", "jev_answer": "docs", "jev_confidence": 0.8, "opus_decision": "coder", "reason": "needs code"})
        self.assertEqual(self.read("overrides")[0]["question"], "executor")

    def test_unknown_method(self):
        r = jev_mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})
        self.assertEqual(r["error"]["code"], -32601)

    def test_unknown_tool(self):
        r = call("nope", {})
        self.assertTrue(r["result"]["isError"])

    def test_tools_call_handles_bad_arguments(self):
        # Test that bad arguments don't crash the server - arguments as string instead of dict
        r = jev_mcp.handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "jev_judge", "arguments": "notadict"}})
        self.assertTrue(r["result"]["isError"])

    def test_initialize_validates_protocol_version(self):
        # Unknown protocol version -> use default
        r = jev_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "9999-99-99"}})
        self.assertEqual(r["result"]["protocolVersion"], "2025-06-18")
        # Supported version is echoed back
        r = jev_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}})
        self.assertEqual(r["result"]["protocolVersion"], "2024-11-05")

    def test_non_dict_params_returns_invalid_params(self):
        r = jev_mcp.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": "notadict"})
        self.assertEqual(r["error"]["code"], -32602)

    def test_non_dict_message_returns_invalid_request(self):
        r = jev_mcp.handle([1, 2, 3])
        self.assertEqual(r["error"]["code"], -32600)

    def test_log_escalation_truncates_long_strings(self):
        # 2 MB reason field should be truncated to 500 chars
        long_reason = "x" * (2 * 1024 * 1024)
        call("log_escalation", {"task": "T1", "reason": long_reason, "decided_by": "opus", "from_model": "sonnet", "to_model": "opus"})
        log_entry = self.read("escalations")[0]
        self.assertLessEqual(len(log_entry["reason"]), 500)
        self.assertEqual(len(log_entry["reason"]), 500)

    def test_log_escalation_excludes_extra_keys(self):
        call("log_escalation", {"task": "T2", "reason": "test", "decided_by": "opus", "from_model": "sonnet", "to_model": "opus", "api_key": "secret", "ts": "override"})
        log_entry = self.read("escalations")[0]
        self.assertNotIn("api_key", log_entry)
        # ts should be set by server, not from caller
        self.assertIn("ts", log_entry)
        # Only whitelisted fields should be present
        self.assertEqual(set(log_entry.keys()) - {"ts"}, {"task", "reason", "decided_by", "from_model", "to_model"})

    def test_log_override_truncates_and_sanitizes(self):
        # Test large jev_answer truncation
        large_answer = "y" * (2 * 1024)
        call("log_override", {"question": "q", "jev_answer": large_answer, "jev_confidence": 0.9, "opus_decision": "d", "reason": "r"})
        log_entry = self.read("overrides")[0]
        self.assertLessEqual(len(log_entry["jev_answer"]), 500)

    def test_log_override_confidence_nan_to_null(self):
        # NaN should become null
        call("log_override", {"question": "q", "jev_answer": "a", "jev_confidence": float('nan'), "opus_decision": "d", "reason": "r"})
        log_entry = self.read("overrides")[0]
        self.assertIsNone(log_entry["jev_confidence"])

    def test_log_override_excludes_extra_keys(self):
        call("log_override", {"question": "q", "jev_answer": "a", "jev_confidence": 0.8, "opus_decision": "d", "reason": "r", "state": "secret", "ts": "override"})
        log_entry = self.read("overrides")[0]
        self.assertNotIn("state", log_entry)
        # Only whitelisted fields should be present
        self.assertEqual(set(log_entry.keys()) - {"ts"}, {"question", "jev_answer", "jev_confidence", "opus_decision", "reason"})

    def test_judge_caps_choice_value_at_64_chars(self):
        long_choice_res = {"answers": {"executor": {"type": "choice", "value": "x" * 100, "confidence": 0.9, "probabilities": {}}},
                          "latency_ms": 10, "input_tokens": 100, "cost": 0.001}
        questions = {"executor": {"type": "choice", "instructions": "test", "criteria": {"opt": "desc"}}}
        r = call("jev_judge", {"state": {}, "questions": questions}, lambda s, q: long_choice_res)
        log_entry = self.read("mcp")[0]
        self.assertLessEqual(len(log_entry["answers"]["executor"]["value"]), 64)

    def test_judge_caps_question_name_at_64_chars(self):
        long_q_name = "q" * 100
        long_q_res = {"answers": {long_q_name: {"type": "noul", "value": 0.5, "confidence": 0.7}},
                     "latency_ms": 10, "input_tokens": 100, "cost": 0.001}
        questions = {long_q_name: {"type": "noul", "instructions": "test", "criteria": None}}
        r = call("jev_judge", {"state": {}, "questions": questions}, lambda s, q: long_q_res)
        log_entry = self.read("mcp")[0]
        self.assertTrue(any(len(k) <= 64 for k in log_entry["answers"].keys()))

    def test_stdio_survives_invalid_utf8(self):
        # Test subprocess with invalid UTF-8 bytes
        invalid_utf8_line = b'\xff\xfe garbage\n'
        valid_line = b'{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
        stdin_data = invalid_utf8_line + valid_line
        result = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "jev_mcp.py")],
            input=stdin_data,
            capture_output=True,
            env={**os.environ, "JEV_LOG_DIR": self.tmp}
        )
        # Should succeed (rc 0) and produce the tools/list response
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.decode("utf-8", "replace").strip().split("\n")
        # Should have at least one line of output (the tools/list response)
        self.assertGreater(len(lines), 0)
        # Last line should be valid JSON with tools/list response
        response = json.loads(lines[-1])
        self.assertIn("result", response)
        self.assertIn("tools", response["result"])

    def test_malformed_json_returns_parse_error(self):
        # Test via subprocess to capture stdout
        stdin_data = b'not valid json\n'
        result = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "jev_mcp.py")],
            input=stdin_data,
            capture_output=True,
            env={**os.environ, "JEV_LOG_DIR": self.tmp}
        )
        self.assertEqual(result.returncode, 0)
        response = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(response["error"]["code"], -32700)
        self.assertEqual(response["error"]["message"], "parse error")

    def test_judge_normalizes_choice_list_criteria_to_dict(self):
        # choice with list criteria should be normalized to dict
        list_criteria_questions = {
            "executor": {"type": "choice", "instructions": "choose", "criteria": ["coder", "tester"]}
        }
        received_questions = []
        def capture_judge(state, questions):
            received_questions.append(questions)
            return RES
        r = call("jev_judge", {"state": {}, "questions": list_criteria_questions}, capture_judge)
        self.assertFalse(r["result"].get("isError", False))
        # Verify the question was normalized
        normalized_q = received_questions[0]["executor"]
        self.assertEqual(normalized_q["criteria"], {"coder": "coder", "tester": "tester"})

    def test_judge_normalizes_score_dict_criteria_to_list(self):
        # score with dict criteria should be normalized to list
        dict_criteria_questions = {
            "rating": {"type": "score", "instructions": "rate", "criteria": {"bad": "bad", "good": "good"}}
        }
        received_questions = []
        def capture_judge(state, questions):
            received_questions.append(questions)
            return {"answers": {"rating": {"type": "score", "value": 2.5, "confidence": 0.8, "legend": {}}},
                   "latency_ms": 10, "input_tokens": 100, "cost": 0.001}
        r = call("jev_judge", {"state": {}, "questions": dict_criteria_questions}, capture_judge)
        self.assertFalse(r["result"].get("isError", False))
        # Verify the question was normalized
        normalized_q = received_questions[0]["rating"]
        self.assertIsInstance(normalized_q["criteria"], list)
        self.assertEqual(len(normalized_q["criteria"]), 2)

    def test_judge_normalizes_noul_list_criteria_to_dict(self):
        # noul with 2-element list criteria should be normalized to dict with true/false
        list_criteria_questions = {
            "binary": {"type": "noul", "instructions": "yes or no", "criteria": ["yes", "no"]}
        }
        received_questions = []
        def capture_judge(state, questions):
            received_questions.append(questions)
            return {"answers": {"binary": {"type": "noul", "value": 0.7, "confidence": 0.8}},
                   "latency_ms": 10, "input_tokens": 100, "cost": 0.001}
        r = call("jev_judge", {"state": {}, "questions": list_criteria_questions}, capture_judge)
        self.assertFalse(r["result"].get("isError", False))
        # Verify the question was normalized
        normalized_q = received_questions[0]["binary"]
        self.assertEqual(normalized_q["criteria"], {"true": "yes", "false": "no"})

    def test_judge_rejects_invalid_question_type(self):
        invalid_questions = {
            "bad": {"type": "invalid", "instructions": "test", "criteria": None}
        }
        r = call("jev_judge", {"state": {}, "questions": invalid_questions}, lambda s, q: RES)
        self.assertTrue(r["result"]["isError"])
        self.assertIn("type must be", r["result"]["content"][0]["text"])
        log_entry = self.read("mcp")[0]
        self.assertEqual(log_entry["error"], "invalid_question")

    def test_judge_rejects_missing_instructions(self):
        invalid_questions = {
            "bad": {"type": "choice", "criteria": {"a": "a"}}
        }
        r = call("jev_judge", {"state": {}, "questions": invalid_questions}, lambda s, q: RES)
        self.assertTrue(r["result"]["isError"])
        self.assertIn("instructions", r["result"]["content"][0]["text"])

    def test_judge_rejects_invalid_choice_criteria(self):
        invalid_questions = {
            "bad": {"type": "choice", "instructions": "test"}
        }
        r = call("jev_judge", {"state": {}, "questions": invalid_questions}, lambda s, q: RES)
        self.assertTrue(r["result"]["isError"])
        self.assertIn("choice criteria must be a map", r["result"]["content"][0]["text"])

    def test_judge_rejects_invalid_score_criteria(self):
        invalid_questions = {
            "bad": {"type": "score", "instructions": "test", "criteria": ["only_one"]}
        }
        r = call("jev_judge", {"state": {}, "questions": invalid_questions}, lambda s, q: RES)
        self.assertTrue(r["result"]["isError"])
        self.assertIn("score criteria must be a list of 2–10", r["result"]["content"][0]["text"])

    def test_jev_unavailable_with_httperror_code(self):
        def boom_http(s, q):
            raise JevUnavailable("HTTPError 400")
        r = call("jev_judge", {"state": {}, "questions": VALID_QUESTIONS}, boom_http)
        self.assertTrue(r["result"]["isError"])
        self.assertIn("HTTPError 400", r["result"]["content"][0]["text"])
        log_entry = self.read("mcp")[0]
        self.assertEqual(log_entry["error"], "HTTPError 400")


if __name__ == "__main__":
    unittest.main()
