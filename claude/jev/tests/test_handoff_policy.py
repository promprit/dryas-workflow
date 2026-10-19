import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import compact_keep
import handoff
import judge_policy
from test_handoff import HandoffBase
from tx_helpers import user, write_jsonl


def boom(state, questions):
    raise AssertionError("Jev called with a local provider")


class HandoffPolicyTest(HandoffBase):
    def setUp(self):
        super().setUp()
        judge_policy.clear_cache()
        self.addCleanup(judge_policy.clear_cache)
        p = mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k",
                                         "JEV_COMPACT_DIR": os.path.join(self.tmp, "compact")})
        p.start()
        self.addCleanup(p.stop)
        write_jsonl(self.tp, [user("u0")] + self.chatter(50))

    def mark(self):
        open(os.path.join(self.cwd, ".dryas-judge"), "w").write("local\n")

    def log(self, name):
        with open(os.path.join(self.tmp, "logs", name + ".jsonl")) as f:
            return [json.loads(l) for l in f][-1]

    def test_handoff_under_marker_never_calls_jev(self):
        self.mark()
        msg = handoff.run(self.cwd, self.tp, boom)
        self.assertIn("local judge (project policy)", msg)
        self.assertIn("note 49", self.body())
        rec = self.log("handoff")
        self.assertEqual((rec["jev_ok"], rec["judge_policy"]), ("local", "project_local"))

    def test_compact_under_marker_never_calls_jev(self):
        self.mark()
        compact_keep.run({"session_id": "s1", "cwd": self.cwd, "transcript_path": self.tp}, boom)
        rec = self.log("compact")
        self.assertEqual((rec["jev_ok"], rec["judge_policy"]), ("local", "project_local"))

    def test_global_local_provider_never_calls_jev(self):
        with open(os.environ["JEV_THRESHOLDS"], "w") as f:
            json.dump({"judge": {"provider": "local"}}, f)
        msg = handoff.run(self.cwd, self.tp, boom)
        self.assertIn("local judge — kept newest 30", msg)
        rec = self.log("handoff")
        self.assertEqual(rec["jev_ok"], "local")
        self.assertNotIn("judge_policy", rec)


if __name__ == "__main__":
    unittest.main()
