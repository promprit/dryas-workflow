import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))
import context_watch
from tx_helpers import assistant, user, write_jsonl


def with_usage(tokens, cache_read=0, cache_create=0, model=None):
    r = assistant("x")
    r["message"]["usage"] = {"input_tokens": tokens, "cache_read_input_tokens": cache_read,
                             "cache_creation_input_tokens": cache_create, "output_tokens": 5}
    if model:
        r["message"]["model"] = model
    return r


ENVS = ("JEV_HANDOFF_DIR", "JEV_THRESHOLDS", "JEV_CONTEXT_WINDOW", "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE")


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for k in ENVS:
            os.environ.pop(k, None)
        os.environ["JEV_HANDOFF_DIR"] = os.path.join(self.tmp, "handoff")
        os.environ["JEV_THRESHOLDS"] = os.path.join(self.tmp, "th.json")
        json.dump({"context": {"warn_pct": 0.55}}, open(os.environ["JEV_THRESHOLDS"], "w"))  # pin: tier logic, not the default
        self.tp = os.path.join(self.tmp, "t.jsonl")

    def tearDown(self):
        for k in ENVS:
            os.environ.pop(k, None)

    def ev(self, sid="s1"):
        return {"transcript_path": self.tp, "session_id": sid}

    def test_below_threshold_silent(self):
        write_jsonl(self.tp, [user("q"), with_usage(100000)])
        self.assertIsNone(context_watch.run(self.ev()))

    def test_warns_with_sum_of_tokens(self):
        write_jsonl(self.tp, [with_usage(10, 90000, 20000)])  # 55%
        msg = context_watch.run(self.ev())
        self.assertIn("Context 55%", msg)
        self.assertIn("/handoff", msg)
        self.assertIn("/clear", msg)
        self.assertIn("auto-compaction is at 95%", msg)

    def test_autocompact_pct_from_env(self):
        os.environ["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] = "70"
        write_jsonl(self.tp, [with_usage(112000)])
        self.assertIn("auto-compaction is at 70%", context_watch.run(self.ev()))
        os.environ["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] = "junk"
        write_jsonl(self.tp, [with_usage(124000)])
        self.assertIn("auto-compaction is at 95%", context_watch.run(self.ev()))

    def test_uses_last_assistant_with_usage(self):
        write_jsonl(self.tp, [with_usage(190000), with_usage(1000), user("q"), assistant("no usage")])
        self.assertIsNone(context_watch.run(self.ev()))

    def test_tiers_once_each(self):
        write_jsonl(self.tp, [with_usage(112000)])  # 56%
        self.assertIsNotNone(context_watch.run(self.ev()))
        self.assertIsNone(context_watch.run(self.ev()))
        write_jsonl(self.tp, [with_usage(122000)])  # 61%
        self.assertIn("Context 61%", context_watch.run(self.ev()))
        self.assertIsNone(context_watch.run(self.ev()))
        write_jsonl(self.tp, [with_usage(160000)])
        self.assertIsNone(context_watch.run(self.ev()))

    def test_jump_to_second_tier_does_not_repeat_first(self):
        write_jsonl(self.tp, [with_usage(125000)])
        self.assertIsNotNone(context_watch.run(self.ev()))
        write_jsonl(self.tp, [with_usage(112000)])
        self.assertIsNone(context_watch.run(self.ev()))

    def test_tiers_reset_after_compaction_drop(self):
        write_jsonl(self.tp, [with_usage(125000)])
        self.assertIsNotNone(context_watch.run(self.ev()))
        write_jsonl(self.tp, [with_usage(30000)])  # >30% drop: compaction/clear happened
        self.assertIsNone(context_watch.run(self.ev()))
        write_jsonl(self.tp, [with_usage(112000)])
        self.assertIsNotNone(context_watch.run(self.ev()))

    def test_small_dip_does_not_reset(self):
        write_jsonl(self.tp, [with_usage(125000)])
        self.assertIsNotNone(context_watch.run(self.ev()))
        write_jsonl(self.tp, [with_usage(112000)])  # -10%
        self.assertIsNone(context_watch.run(self.ev()))
        write_jsonl(self.tp, [with_usage(113000)])
        self.assertIsNone(context_watch.run(self.ev()))

    def test_per_session(self):
        write_jsonl(self.tp, [with_usage(130000)])
        self.assertIsNotNone(context_watch.run(self.ev("a")))
        self.assertIsNotNone(context_watch.run(self.ev("b")))

    def test_no_usage_or_missing_transcript(self):
        write_jsonl(self.tp, [user("q"), assistant("a")])
        self.assertIsNone(context_watch.run(self.ev()))
        self.assertIsNone(context_watch.run({"transcript_path": "/nope", "session_id": "s"}))
        self.assertIsNone(context_watch.run({"session_id": "s"}))
        self.assertIsNone(context_watch.run({"transcript_path": self.tp}))

    def test_window_env_wins(self):
        os.environ["JEV_CONTEXT_WINDOW"] = "1000000"
        write_jsonl(self.tp, [with_usage(130000)])
        self.assertIsNone(context_watch.run(self.ev()))
        os.environ["JEV_CONTEXT_WINDOW"] = "garbage"
        self.assertIsNotNone(context_watch.run(self.ev()))  # falls back to detection -> 200000

    def test_window_detected_1m_from_model(self):
        write_jsonl(self.tp, [with_usage(130000, model="claude-opus-4-5[1m]")])
        self.assertIsNone(context_watch.run(self.ev()))  # 13% of 1M
        write_jsonl(self.tp, [with_usage(560000, model="claude-opus-4-5[1m]")])
        self.assertIn("Context 56%", context_watch.run(self.ev()))

    def test_window_model_table(self):
        # Same table as flowobserve server/test/transcript.test.ts ("window: model table").
        for m in ("claude-fable-5-1", "claude-mythos-5-1", "claude-opus-5-5", "claude-opus-5", "claude-opus-4-6",
                  "claude-sonnet-5-5", "claude-sonnet-5", "claude-sonnet-4-6"):
            self.assertEqual(context_watch._window(m, 10), 1000000, m)
        for m in ("claude-haiku-4-5", "claude-haiku-4-5-20251001", "claude-opus-4-5-20251101", "claude-sonnet-4-5",
                  "claude-opus-4-1", "claude-sonnet-4-20250514", "claude-3-opus-20240229",
                  "claude-3-5-sonnet-20241022", "claude-3-7-sonnet-20250219", "", "m"):
            self.assertEqual(context_watch._window(m, 10), 200000, m)

    def test_window_1m_model_without_tag(self):
        write_jsonl(self.tp, [with_usage(141000, model="claude-opus-5-5")])
        self.assertIsNone(context_watch.run(self.ev()))  # 14% of 1M, not 70% of 200k

    def test_window_detected_1m_from_observed_usage_over_200k(self):
        write_jsonl(self.tp, [with_usage(250000), with_usage(130000)])
        self.assertIsNone(context_watch.run(self.ev()))  # 13% of 1M, not 65% of 200k

    def test_warn_pct_threshold_and_clamp(self):
        json.dump({"context": {"warn_pct": 0.8}}, open(os.environ["JEV_THRESHOLDS"], "w"))
        write_jsonl(self.tp, [with_usage(130000)])
        self.assertIsNone(context_watch.run(self.ev()))
        json.dump({"context": {"warn_pct": 0.01}}, open(os.environ["JEV_THRESHOLDS"], "w"))
        write_jsonl(self.tp, [with_usage(10000)])
        self.assertIsNone(context_watch.run(self.ev("other")))

    def test_state_perms(self):
        write_jsonl(self.tp, [with_usage(130000)])
        context_watch.run(self.ev())
        wd = os.path.join(self.tmp, "handoff", ".warned")
        f = os.path.join(wd, os.listdir(wd)[0])
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(wd).st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(os.stat(f).st_mode), 0o600)

    def test_reads_only_tail(self):
        with open(self.tp, "w") as f:
            f.write(json.dumps(with_usage(190000)) + "\n")
            for _ in range(2500):
                f.write(json.dumps(user("p" * 1000)) + "\n")
            f.write(json.dumps(with_usage(1000)) + "\n")
        self.assertIsNone(context_watch.run(self.ev()))

    def test_cli_output_json(self):
        write_jsonl(self.tp, [with_usage(125000)])
        p = subprocess.run([sys.executable, os.path.join(HERE, "context_watch.py")], input=json.dumps(self.ev()),
                           capture_output=True, text=True)
        out = json.loads(p.stdout)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("Context 62%", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
