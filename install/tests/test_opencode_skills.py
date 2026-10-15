import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import sync_opencode as so  # noqa: E402


class OpenCodeSkillsTest(unittest.TestCase):
    def test_hand_skills_match_claude_names(self):
        self.assertEqual(so.hand_drift(REPO), [])

    def test_hand_skills_are_marked_and_named(self):
        for h in so.HAND:
            text = (REPO / ("opencode/skill/dryas-%s/SKILL.md" % h)).read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\nname: dryas-%s\ndescription: " % h), h)
            self.assertIn(so.MARK, text)
            self.assertNotIn("mcp__", text)
            self.assertNotIn("$dryas:", text)

    def test_orchestrate_names_tiers_and_task_tool(self):
        text = (REPO / "opencode/skill/dryas-orchestrate/SKILL.md").read_text(encoding="utf-8")
        for t in so.TIERS:
            self.assertIn("dryas-executor-%s" % t, text)
        self.assertIn("task tool", text)
        self.assertIn("`haiku`", text)

    def test_missing_hand_skill_is_reported(self):
        lines = so.hand_drift(REPO / "no-such-repo")
        self.assertTrue(any("missing opencode/skill/dryas-orchestrate/SKILL.md" in l for l in lines))


if __name__ == "__main__":
    unittest.main()
