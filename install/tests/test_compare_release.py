import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import compare_release as cr  # noqa: E402


class CompareReleaseTest(unittest.TestCase):
    def side(self, p50, lo, hi, asks=0, blocks=0):
        return {"asks": asks, "blocks": blocks, "p50_ms": p50, "range_ms": [lo, hi]}

    def test_default_old_is_newest_other_cached_version(self):
        with tempfile.TemporaryDirectory() as t:
            for v in ("2.3.1", "2.3.2", "9.9.9", "junk"):
                (Path(t) / v / "jev").mkdir(parents=True)
                (Path(t) / v / "jev" / "chain.py").write_text("", encoding="utf-8")
            (Path(t) / "2.3.10" / "jev").mkdir(parents=True)
            self.assertEqual(cr.default_old(Path(t), "9.9.9"), Path(t) / "2.3.2")
            self.assertIsNone(cr.default_old(Path(t) / "none", "1.0.0"))

    def test_verdict(self):
        self.assertEqual(cr.verdict(self.side(50, 45, 55), self.side(52, 48, 56)), [])
        self.assertTrue(cr.verdict(self.side(50, 49, 51), self.side(60, 59, 61)))
        self.assertTrue(cr.verdict(self.side(50, 45, 55), self.side(50, 45, 55, blocks=1)))
        self.assertTrue(cr.verdict(self.side(50, 45, 55), self.side(50, 45, 55, asks=1)))

    def test_events_are_synthetic(self):
        evs = cr.events("/sandbox")
        self.assertEqual({e["_kind"] for e in evs}, {"prompt", "post"})
        self.assertTrue(all(e["session_id"] == cr.SID for e in evs))
        self.assertNotIn("/Users/", json.dumps(evs))

    def test_events_cover_post_failure(self):
        self.assertTrue(any(e["hook_event_name"] == "PostToolUseFailure" for e in cr.events("/sandbox")))

    def test_self_comparison_runs_clean(self):
        s = cr.run(REPO / "claude", 1)  # one run per side: about 30 hook processes
        self.assertEqual((s["new"]["asks"], s["new"]["blocks"]), (0, 0))
        self.assertGreater(s["new"]["p50_ms"], 0)


if __name__ == "__main__":
    unittest.main()
