import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import planfile

PLAN = "\n".join([
    "# Plan", "",
    "## Risky actions",
    "- `rm -rf dist` — deletes the build folder; it is rebuilt automatically, nothing of yours is lost.",
    "- `pnpm db:reset*` — wipes the local test database and refills it with sample data.",
    "- `git push` no sentence, skipped",
    "- rm -rf build — no backticks, skipped", "",
    "## Task 1: a", "Goal: g", "Scope:", "- src/**", ""])


class RiskyTest(unittest.TestCase):
    def test_bullets_with_command_and_sentence(self):
        self.assertEqual(planfile.risky(PLAN), ["rm -rf dist", "pnpm db:reset*"])

    def test_no_section(self):
        self.assertEqual(planfile.risky("## Task 1: a\n"), [])

    def test_sections_ignore_risky(self):
        self.assertEqual(list(planfile.sections(PLAN)), ["1"])


if __name__ == "__main__":
    unittest.main()
