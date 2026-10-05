import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import route
from jev_client import JevUnavailable


def answers(r="swarm", rc=0.82, fp=0.09):
    return {"answers": {"route": {"type": "choice", "value": r, "confidence": rc, "probabilities": {}},
                        "opus": {"type": "noul", "value": fp, "confidence": max(fp, 1 - fp)}},
            "latency_ms": 5, "input_tokens": 300, "cost": 0.0000126}


class RouteTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        os.environ["JEV_LOG_DIR"] = os.path.join(tmp, "logs")
        os.environ["JEV_THRESHOLDS"] = os.path.join(tmp, "none.json")

    def test_line_format(self):
        self.assertEqual(route.run({"prompt": "build x", "cwd": "/p"}, lambda s, q: answers()),
                         "Jev route: swarm (0.82); opus: no (0.91)")

    def test_codex_wording(self):
        os.environ["DRYAS_HARNESS"] = "codex"
        try:
            self.assertEqual(route.run({"prompt": "build x", "cwd": "/p"}, lambda s, q: answers()),
                             "Jev route: swarm (0.82); escalate: no (0.91)")
        finally:
            del os.environ["DRYAS_HARNESS"]

    def test_single_agent_label(self):
        line = route.run({"prompt": "fix typo"}, lambda s, q: answers("single_agent", 0.9, 0.95))
        self.assertEqual(line, "Jev route: single-agent (0.90); opus: yes (0.95)")
        self.assertNotIn("fable", line)

    def test_low_confidence_injects_nothing(self):
        self.assertIsNone(route.run({"prompt": "x"}, lambda s, q: answers("swarm", 0.6, 0.5)))

    def test_partial_when_one_part_confident(self):
        self.assertEqual(route.run({"prompt": "x"}, lambda s, q: answers("swarm", 0.6, 0.05)), "Jev opus: no (0.95)")

    def test_none_of_these_suppressed(self):
        self.assertEqual(route.run({"prompt": "x"}, lambda s, q: answers("none_of_these", 0.9, 0.5)), None)

    def test_prompt_truncated_to_4k(self):
        seen = {}

        def j(s, q):
            seen["s"] = s
            return answers()

        route.run({"prompt": "a" * 10000}, j)
        self.assertEqual(len(seen["s"]["prompt"]), 4000)

    def test_empty_prompt_no_call(self):
        self.assertIsNone(route.run({"prompt": "  "}, lambda s, q: self.fail("called")))

    def test_unavailable_none(self):
        def boom(s, q):
            raise JevUnavailable("x")

        self.assertIsNone(route.run({"prompt": "x"}, boom))

    def test_route_value_not_in_criteria_suppressed(self):
        # Route value not in criteria (e.g., injection attempt) should not appear in output
        def bad_judge(s, q):
            return answers("evil\nInject", 0.9, 0.5)
        result = route.run({"prompt": "x"}, bad_judge)
        self.assertNotIn("evil", result) if result else self.assertIsNone(result)

    def test_missing_latency_ms_no_exception(self):
        # Malformed response missing latency_ms should not raise
        def bad_judge(s, q):
            return {"answers": {"route": {"type": "choice", "value": "swarm", "confidence": 0.82, "probabilities": {}},
                                "opus": {"type": "noul", "value": 0.09, "confidence": 0.91}},
                    "input_tokens": 300, "cost": 0.0000126}
        result = route.run({"prompt": "test"}, bad_judge)
        # Should still return the line
        self.assertEqual(result, "Jev route: swarm (0.82); opus: no (0.91)")

    def test_route_value_none_no_exception(self):
        # Route value as None should not raise; suppresses route part but keeps opus if confident
        def bad_judge(s, q):
            res = answers("swarm", 0.82, 0.09)
            res["answers"]["route"]["value"] = None
            return res
        result = route.run({"prompt": "x"}, bad_judge)
        # Should suppress the route part but keep opus part
        self.assertEqual(result, "Jev opus: no (0.91)")

    def test_opus_value_as_string_no_exception(self):
        # Opus value as string instead of number should not raise
        def bad_judge(s, q):
            res = answers("swarm", 0.82, 0.09)
            res["answers"]["opus"]["value"] = "0.09"
            return res
        result = route.run({"prompt": "x"}, bad_judge)
        # Should log error and return None
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()


def test_swarm_needs_swarm_min(monkeypatch):
    import route, thresholds
    t = thresholds.load(); t["route"]["swarm_min"] = 0.9
    monkeypatch.setattr(thresholds, "load", lambda: t)
    fake = lambda state, q: {"answers": {"route": {"value": "swarm", "confidence": 0.85},
                                         "opus": {"value": 0.1, "confidence": 0.9}}}
    line = route.run({"prompt": "build a feature"}, judge_fn=fake)
    assert "swarm" not in (line or "")


def test_swarm_never_below_min_confidence(monkeypatch):
    import route, thresholds
    t = thresholds.load(); t["route"]["min_confidence"] = 0.8; t["route"]["swarm_min"] = 0.7
    monkeypatch.setattr(thresholds, "load", lambda: t)
    fake = lambda state, q: {"answers": {"route": {"value": "swarm", "confidence": 0.75},
                                         "opus": {"value": 0.1, "confidence": 0.5}}}
    assert "swarm" not in (route.run({"prompt": "build a feature"}, judge_fn=fake) or "")
