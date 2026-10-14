"""The Codex edition ships and names the Dryas process skills; no "Superpowers if installed" left (owned core C)."""
import io
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "install"))

USES = {
    "codex/AGENTS.md.template": ("$dryas:brainstorm",),
    "codex/skills/orchestrate/SKILL.md": ("$dryas:brainstorm", "$dryas:worktree", "$dryas:debug", "$dryas:verify",
                                          "<dryas-root>/skills/tdd/SKILL.md"),
    "codex/skills/wplan/SKILL.md": ("$dryas:plan",),
    "codex/skills/wreview/SKILL.md": ("$dryas:review-request", "$dryas:review-receive"),
}


class CodexWiringTest(unittest.TestCase):
    def test_codex_names_dryas_skills(self):
        for rel, needles in USES.items():
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("if it is installed", text, rel)
            self.assertNotIn("if installed", text, rel)
            for n in needles:
                self.assertIn(n, text, (rel, n))

    def test_no_superpowers_hint(self):
        import codex_target as ct
        self.assertFalse(hasattr(ct, "SP_HINT"))
        self.assertNotIn("SP_HINT", (ROOT / "install/codex_plugin_setup.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
