import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TERMS = ("Jev", "judge", "provider", "shadow", "fallback", "tier", "rung", "ladder", "scope lock", "worktree loop",
         "task id", "baseline", "inventory", "extra")
CATEGORIES = ("navigation", "automated checks", "instruction lines", "tool cost", "information access")


class RetroTest(unittest.TestCase):
    def test_retro_command_shape(self):
        s = (ROOT / "claude/commands/retro.md").read_text(encoding="utf-8")
        self.assertIn("disable-model-invocation: true", s)
        for c in CATEGORIES:
            self.assertIn(c, s.lower())
        self.assertIn("memory_store", s)
        self.assertIn('kind "retro"', s)
        self.assertIn("proposes, never applies", s.lower())
        cx = (ROOT / "codex/skills/retro/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("memory_store", cx)
        y = (ROOT / "codex/skills/retro/agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", y)

    def test_glossary_terms(self):
        g = (ROOT / "GLOSSARY.md").read_text(encoding="utf-8")
        for t in TERMS:
            self.assertRegex(g, r"(?im)^- \*\*%s\*\*: \S" % re.escape(t), t)

    def test_out_of_scope_entries(self):
        d = ROOT / ".out-of-scope"
        names = sorted(p.stem for p in d.glob("*.md"))
        self.assertEqual(names, ["embeddings-in-memory", "rebuild-ruflo-tools", "replace-design-plugins", "rust-core"])
        for p in d.glob("*.md"):
            s = p.read_text(encoding="utf-8")
            for k in ("Date: 2026-10-14", "Decision:", "Reason:"):
                self.assertIn(k, s, p.name)


if __name__ == "__main__":
    unittest.main()
