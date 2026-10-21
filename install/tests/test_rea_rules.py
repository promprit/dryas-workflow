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

    def test_opencode_rule_says_unavailable(self):
        t = self.read("opencode/dryas/AGENTS.md.template")
        self.assertNotIn("use REA;", t)
        self.assertIn("REA is not set up for OpenCode", t)

    def test_brainstorm_offers_rea(self):
        t = self.read("claude/skills/brainstorm/reference.md")
        sect = t.split("Exploring approaches")[1].split("\n## ")[0]
        for want in ("investigate with REA first", "install.sh --with-rea", "evidence"):
            self.assertIn(want, sect)

    def test_install_hint_per_harness(self):
        sect = lambda p: self.read(p).split("Exploring approaches")[1].split("\n## ")[0]
        self.assertIn("install/install.sh --with-rea", sect("claude/skills/brainstorm/reference.md"))
        self.assertIn("install/install.sh --harness codex --with-rea", sect("codex/skills/brainstorm/reference.md"))
        oc = sect("opencode/skill/dryas-brainstorm/reference.md")
        self.assertIn("not set up for OpenCode", oc)
        self.assertNotIn("investigate with REA first", oc)

    def test_plan_carries_evidence(self):
        self.assertIn("REA finding", self.read("claude/skills/plan/SKILL.md"))


if __name__ == "__main__":
    unittest.main()
