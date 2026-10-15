import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import release_check


class ReleaseTest(unittest.TestCase):
    def test_versions_are_2_0_x(self):
        self.assertTrue(json.loads((ROOT / "claude/.claude-plugin/plugin.json").read_text())["version"].startswith("2.0."))
        self.assertEqual(release_check.version_problems(ROOT), [])  # all five agree

    def test_changelog_2_0_0(self):
        c = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        top = [s for s in c.split("\n## ") if s.startswith("2.0.0 - ")][0]  # patch releases sit above it
        for s in ("### Added", "### Changed", "### Kept (optional extras)", "### Upgrade"):
            self.assertIn(s, top)
        for n in ("dryas memory import-ruflo", "--judge", "--with-ruflo", "/retro"):
            self.assertIn(n, top)

    def test_before_2_0_items(self):
        e = (ROOT / "claude/agents/executor.md").read_text(encoding="utf-8")
        self.assertIn("Commit your own task only when the dispatch prompt allows it", e)
        self.assertNotIn("docs/governance.md", (ROOT / "claude/skills/review-receive/SKILL.md").read_text())
        # The parity and redact tests carry the relative timing logic; the heredoc test reuses the parity helpers.
        for f in ("claude/jev/tests/test_local_judge_parity.py", "claude/jev/tests/test_redact.py"):
            t = (ROOT / f).read_text(encoding="utf-8")
            self.assertTrue(re.search(r"median", t) and re.search(r"baseline", t), f + ": timing budget is still absolute")
        h = (ROOT / "claude/jev/tests/test_local_judge_heredoc.py").read_text(encoding="utf-8")
        self.assertIn("from test_local_judge_parity import _timed, assert_fast", h)


if __name__ == "__main__":
    unittest.main()
