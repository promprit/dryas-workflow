"""One minimum-code ladder for executors and the cleanup pass (owned core C, user-approved addition)."""
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
STEPS = ("YAGNI", "reuse", "stdlib", "native", "existing dependency", "one-liner", "minimum new code")
FILES = ("claude/agents/executor.md", "claude/pstack/cleanup.md", "codex/pstack/cleanup.md",
         "codex/skills/orchestrate/SKILL.md")


class LadderTest(unittest.TestCase):
    def test_ladder_in_order(self):
        for rel in FILES:
            text = (ROOT / rel).read_text(encoding="utf-8")
            at = [text.find(s) for s in STEPS]
            self.assertNotIn(-1, at, (rel, dict(zip(STEPS, at))))
            self.assertEqual(at, sorted(at), rel)


if __name__ == "__main__":
    unittest.main()
