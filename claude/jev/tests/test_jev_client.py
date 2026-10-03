import http.client
import json
import os
import socket
import sys
import time
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jev_client import JevUnavailable, judge

RESPONSE = {
    "answers": {
        "is_bug": {"type": "noul", "noul": 0.96},
        "team": {"type": "choice", "choice": "payments", "confidence": 0.75, "probabilities": {"payments": 0.84, "frontend": 0.16}},
        "urgency": {"type": "score", "score": 1.99, "confidence": 0.99, "legend": {"0": "low", "1": "mid", "2": "high"}, "probabilities": {}},
    },
    "usage": {"input_tokens": 476, "output_tokens": 70, "cost": 0.000019992},
}


class FakeResp:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_returning(body, seen):
    def op(req, timeout):
        seen.append((req, timeout))
        return FakeResp(body)
    return op


def opener_raising(exc):
    def op(req, timeout):
        raise exc
    return op


@mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
class ClientTest(unittest.TestCase):
    def test_request_shape_and_normalized_answers(self):
        seen = []
        res = judge({"cmd": "export X_TOKEN=abc"}, {"q": {"type": "noul", "instructions": "?"}}, opener=opener_returning(json.dumps(RESPONSE).encode(), seen))
        req, timeout = seen[0]
        self.assertEqual(req.full_url, "https://openrouter.ai/api/v1/systemone")
        self.assertEqual(req.get_header("Authorization"), "Bearer test-key")
        body = json.loads(req.data.decode())
        self.assertEqual(body["model"], "typesafe/jev-1.13")
        self.assertNotIn("abc", body["state"]["cmd"])
        self.assertEqual(timeout, 3.0)
        a = res["answers"]
        self.assertEqual(a["is_bug"]["value"], 0.96)
        self.assertAlmostEqual(a["is_bug"]["confidence"], 0.96)
        self.assertEqual((a["team"]["value"], a["team"]["confidence"]), ("payments", 0.75))
        self.assertEqual(a["urgency"]["value"], 1.99)
        self.assertEqual(res["input_tokens"], 476)
        self.assertEqual(res["cost"], 0.000019992)

    def test_noul_low_p_has_high_confidence(self):
        body = json.dumps({"answers": {"s": {"type": "noul", "noul": 0.1}}}).encode()
        a = judge({}, {}, opener=opener_returning(body, []))["answers"]["s"]
        self.assertAlmostEqual(a["confidence"], 0.9)

    def test_missing_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(JevUnavailable):
                judge({}, {}, opener=opener_returning(b"{}", []))

    def test_http_error(self):
        err = urllib.error.HTTPError("u", 402, "Payment Required", {}, None)
        with self.assertRaises(JevUnavailable):
            judge({}, {}, opener=opener_raising(err))

    def test_timeout(self):
        with self.assertRaises(JevUnavailable):
            judge({}, {}, opener=opener_raising(socket.timeout("timed out")))

    def test_garbage_json(self):
        with self.assertRaises(JevUnavailable):
            judge({}, {}, opener=opener_returning(b"<html>", []))

    def test_missing_answers(self):
        with self.assertRaises(JevUnavailable):
            judge({}, {}, opener=opener_returning(b'{"error":{"code":429}}', []))

    def test_malformed_answer(self):
        body = json.dumps({"answers": {"x": {"type": "choice"}}}).encode()
        with self.assertRaises(JevUnavailable):
            judge({}, {}, opener=opener_returning(body, []))

    def test_incomplete_read_error(self):
        err = http.client.IncompleteRead(b"")
        with self.assertRaises(JevUnavailable):
            judge({}, {}, opener=opener_raising(err))

    def test_http_exception(self):
        err = http.client.HTTPException("connection error")
        with self.assertRaises(JevUnavailable):
            judge({}, {}, opener=opener_raising(err))

    def test_usage_not_dict_list(self):
        body = json.dumps({"answers": {"s": {"type": "noul", "noul": 0.5}}, "usage": []}).encode()
        with self.assertRaises(JevUnavailable):
            judge({}, {}, opener=opener_returning(body, []))

    def test_usage_input_tokens_not_int(self):
        body = json.dumps({"answers": {"s": {"type": "noul", "noul": 0.5}}, "usage": {"input_tokens": "abc"}}).encode()
        with self.assertRaises(JevUnavailable):
            judge({}, {}, opener=opener_returning(body, []))

    def test_non_serializable_state(self):
        with self.assertRaises(JevUnavailable):
            judge({42}, {}, opener=opener_returning(json.dumps(RESPONSE).encode(), []))

    def test_key_with_newline_not_leaked(self):
        err = ValueError("Invalid header value b'Bearer test-key\\n'")
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key\n"}):
            with self.assertRaises(JevUnavailable) as cm:
                judge({}, {}, opener=opener_raising(err))
            self.assertNotIn("test-key", str(cm.exception))

    def test_noul_huge_number_overflow(self):
        body = b'{"answers":{"s":{"type":"noul","noul":1e999}}}'
        with self.assertRaises(JevUnavailable):
            judge({}, {}, opener=opener_returning(body, []))

    def test_redaction_timing_guard(self):
        # Ensure redaction doesn't catastrophically backtrack on repeated patterns
        big_state = "KEY=" * 1000
        t0 = time.monotonic()
        try:
            judge({"data": big_state}, {}, opener=opener_returning(json.dumps(RESPONSE).encode(), []))
        except JevUnavailable:
            pass
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 0.5)


if __name__ == "__main__":
    unittest.main()
