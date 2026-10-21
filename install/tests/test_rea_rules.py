import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
LINE = "- Reverse-engineering work (how software you don't have the source for does something): use REA; brainstorm says when it recommends it, the user can decline."


class ReaRulesTest(unittest.TestCase):
    def read(self, p):
        return (ROOT / p).read_text(encoding="utf-8")

    def test_template_rule(self):
        for p, anchor in (("claude/CLAUDE.md.template", "- Design work"), ("codex/AGENTS.md.template", "- Brainstorm first")):
            t = self.read(p)
            self.assertIn(LINE, t, p)
            self.assertLess(t.index(anchor), t.index(LINE), p)

    def test_brainstorm_offers_rea(self):
        t = self.read("claude/skills/brainstorm/reference.md")
        sect = t.split("Exploring approaches")[1].split("\n## ")[0]
        for want in ("investigate with REA first", "install.sh --with-rea", "evidence"):
            self.assertIn(want, sect)

    def test_plan_carries_evidence(self):
        self.assertIn("REA finding", self.read("claude/skills/plan/SKILL.md"))


if __name__ == "__main__":
    unittest.main()
