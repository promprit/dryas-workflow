import re, sys, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import render
REPO = HERE.parents[1]
TPL = REPO / "claude" / "CLAUDE.md.template"


class ClaudeMdTemplateTest(unittest.TestCase):
    def setUp(self):
        self.text = TPL.read_text(encoding="utf-8")
        self.on = render.gate_blocks(self.text, list(render.GATED))
        self.off = render.gate_blocks(self.text, [])

    def test_rules_present(self):
        for s in ("~/.claude/docs/dryas-workflow.md", "superpowers:brainstorming", "ui-ux-pro-max", "impeccable",
                  "/orchestrate", "git worktree", "One agent per worktree", "/wreview",
                  "superpowers:verification-before-completion", "Ask before any install", ".orchestrate/",
                  "scope lock -> Jev -> Ruflo", "/handoff", "Edit the repo"):
            self.assertIn(s, self.off, s)

    def test_pstack_rules_gated(self):
        self.assertIn("/interrogate", self.on)
        self.assertIn("benchmark-checklist", self.on)
        self.assertNotIn("/interrogate", self.off)

    def test_no_section_numbers_or_old_paths(self):
        self.assertIsNone(re.search(r"§\d", self.text))
        self.assertNotIn("DryasWorkflow.md", self.text)
        self.assertNotIn("/Volumes/", self.text)
        self.assertNotIn("Promprit", self.text)

    def test_small(self):
        self.assertLess(len(self.on.encode("utf-8")), 5 * 1024)


if __name__ == "__main__":
    unittest.main()
