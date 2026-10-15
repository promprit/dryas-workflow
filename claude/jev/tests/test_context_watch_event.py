import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import context_watch  # noqa: E402


def ev(sid, input_tokens, limit=0, model="mock/m1", **extra):
    e = {"session_id": sid, "cwd": "/tmp", "model": model, "context_limit": limit,
         "usage": {"input_tokens": input_tokens, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}
    e.update(extra)
    return e


class EventUsageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"JEV_HANDOFF_DIR": self.tmp, "DRYAS_HARNESS": "opencode"})
        self.env.start()
        os.environ.pop("JEV_CONTEXT_WINDOW", None)

    def tearDown(self):
        self.env.stop()

    def test_warns_from_event_usage(self):
        line = context_watch.run(ev("s1", 190000, limit=200000))
        self.assertIsNotNone(line)
        self.assertIn("run /handoff then /new", line)
        self.assertNotIn("/clear", line)

    def test_below_threshold_is_quiet(self):
        self.assertIsNone(context_watch.run(ev("s2", 1234, limit=200000)))

    def test_event_context_limit_sets_window(self):
        # 190k of a 1M window is 19%: quiet; the model-name guess (200k) would have warned.
        self.assertIsNone(context_watch.run(ev("s3", 190000, limit=1000000)))

    def test_env_window_beats_event_limit(self):
        with mock.patch.dict(os.environ, {"JEV_CONTEXT_WINDOW": "200000"}):
            self.assertIsNotNone(context_watch.run(ev("s4", 190000, limit=1000000)))

    def test_no_limit_falls_back_to_model_guess(self):
        self.assertIsNotNone(context_watch.run(ev("s5", 190000, limit=0, model="")))

    def test_tier_does_not_repeat(self):
        self.assertIsNotNone(context_watch.run(ev("s6", 170000, limit=200000)))
        self.assertIsNone(context_watch.run(ev("s6", 171000, limit=200000)))

    def test_bad_usage_is_ignored(self):
        for bad in ({"usage": "x"}, {"usage": {"input_tokens": True}}, {"usage": {}}, {"context_limit": "big"}):
            e = ev("s7", 190000, limit=200000)
            e.update(bad)
            context_watch.run(e)  # never raises
        self.assertIsNone(context_watch.run({"session_id": "s8", "usage": {"input_tokens": -5}}))

    def test_claude_wording_unchanged(self):
        with mock.patch.dict(os.environ, {"DRYAS_HARNESS": "claude"}):
            line = context_watch.run(ev("s9", 190000, limit=200000))
        self.assertIn("/handoff then /clear", line)


if __name__ == "__main__":
    unittest.main()
