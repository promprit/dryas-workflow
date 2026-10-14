import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
read = lambda p: (ROOT / p).read_text(encoding="utf-8")
RULE = "Every changed line traces to your task. Report unrelated issues (dead code, bugs, style) in your report; do not fix them."


class SurgicalTest(unittest.TestCase):
    def test_executor_rule_and_review_check(self):
        self.assertIn(RULE, read("claude/agents/executor.md"))
        self.assertIn("reports unrelated issues (dead code, bugs, style) instead of fixing them",
                      read("codex/skills/orchestrate/SKILL.md"))
        for ed in ("claude", "codex"):
            s = read(ed + "/skills/review-request/SKILL.md")
            self.assertIn("Unrelated change", s, ed)
            self.assertIn('"unrelated change" finding', s, ed)
