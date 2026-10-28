"""/orchestrate §8 runs dryas:lens only for a design-panel design, and publishes only when asked (spec D6)."""
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
CLAUDE_LENS_STEP = (
    "When the `## Lens` block in the spec named in the plan header (`**Spec:**` line of the plan the run was started "
    "from) has `Panel: design` or `Panel: design+product`, run the `dryas:lens` skill (design panel) on what was "
    "built before the review, in its § Inside /orchestrate mode: write `.orchestrate/<branch-slug>-lens.html` and "
    "name its path in the end report. Publish it as an Artifact only when the user asked for artifacts when starting "
    "the run. Its `change` findings join the reviewers' findings and are handled with `dryas:review-receive`. No `## Lens` "
    "block, no `Panel:` line, or `Panel: product`: no lens step.")
CODEX_LENS_STEP = (
    "When the `## Lens` block in the spec named in the plan header (`**Spec:**` line of the plan the run was started "
    "from) has `Panel: design` or `Panel: design+product`, run `$dryas:lens` (design panel) on what was built before "
    "the review, in its § Inside /orchestrate mode: write `.orchestrate/<branch-slug>-lens.html` and name its path "
    "in the end report. Its `change` findings join the reviewers' findings. No `## Lens` block, no `Panel:` line, "
    "or `Panel: product`: no lens step.")
OPENCODE_LENS_STEP = CODEX_LENS_STEP.replace("`$dryas:lens`", "the `dryas-lens` skill")


def read(p):
    return (ROOT / p).read_text(encoding="utf-8")


class LensOrchestrateTest(unittest.TestCase):
    def test_orchestrate_lens_step_gated(self):
        t = read("claude/skills/orchestrate/SKILL.md")
        finish = t.split("## 8. Finish")[1].split("\n## ")[0]
        self.assertIn(CLAUDE_LENS_STEP, finish)
        self.assertLess(finish.index(CLAUDE_LENS_STEP), finish.index("Review the worktree diff"))
        head = t.split("---", 2)[1]
        self.assertIn("Skill(dryas:lens)", head)
        self.assertIn("Artifact", head)
        for s in ("Skill(impeccable)", "Skill(impeccable:impeccable)", "Skill(ui-ux-pro-max)",
                  "Skill(ui-ux-pro-max:ui-ux-pro-max)", "Skill(artifact-design)"):
            self.assertIn(s, head, s)

    def test_codex_and_opencode(self):
        for p, step in (("codex/skills/orchestrate/SKILL.md", CODEX_LENS_STEP),
                        ("opencode/skill/dryas-orchestrate/SKILL.md", OPENCODE_LENS_STEP)):
            t = read(p)
            self.assertIn(step, t, p)
            self.assertNotIn("Artifact", t, p)


if __name__ == "__main__":
    unittest.main()
