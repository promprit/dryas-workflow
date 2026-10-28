"""dryas:lens in the rules, docs, brainstorm and plan (spec 2026-10-28-lens-design.md §5)."""
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
OLD = "- Design work (UI/UX, layout, visual style, components, on-screen copy): use `ui-ux-pro-max` and `impeccable`."
CLAUDE_LENS_LINE = "- Design work (UI/UX, layout, visual style, components, on-screen copy) and new features: run `dryas:lens`."
CODEX_LENS_LINE = "- Brainstorm first: before new work, get the user's approval of a design (`$dryas:brainstorm`; design: `$dryas:lens`)."


def read(p):
    return (ROOT / p).read_text(encoding="utf-8")


class LensRulesTest(unittest.TestCase):
    def test_claude_template_rule(self):
        t = read("claude/CLAUDE.md.template")
        self.assertIn(CLAUDE_LENS_LINE, t)
        self.assertNotIn(OLD, t)

    def test_codex_rules(self):
        t = read("codex/AGENTS.md.template")
        self.assertIn(CODEX_LENS_LINE, t)
        self.assertIn("/lens", read("opencode/dryas/AGENTS.md.template"))

    def test_workflow_doc(self):
        t = read("docs/workflow.md")
        design = t.split("**Design work.**")[1].split("**Reverse-engineering work.**")[0]
        for s in ("`dryas:lens`", "design panel", "Artifact page", "**Product lens.**", "3 lens"):
            self.assertIn(s, design, s)
        self.assertIn("| skill `dryas:lens`, command `/lens` |", t)

    def test_brainstorm_runs_lens(self):
        t = read("claude/skills/brainstorm/SKILL.md")
        for s in ("`dryas:lens` design panel", "product panel before you propose approaches", "`## Lens` block"):
            self.assertIn(s, t, s)
        ref = read("claude/skills/brainstorm/reference.md").split("## Presenting the design")[1].split("\n## ")[0]
        self.assertIn("`## Lens` block", ref)
        self.assertIn("$dryas:lens", read("codex/skills/brainstorm/SKILL.md"))
        self.assertIn("dryas-lens", read("opencode/skill/dryas-brainstorm/SKILL.md"))

    def test_plan_carries_panel(self):
        t = read("claude/skills/plan/SKILL.md").split("## Global constraints")[1].split("\n## ")[0]
        self.assertIn("`Panel: design`", t)
        self.assertIn("Design checked by dryas:lens", t)


if __name__ == "__main__":
    unittest.main()
