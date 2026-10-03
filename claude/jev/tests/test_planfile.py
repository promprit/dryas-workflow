import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import planfile

PLAN = """# Plan

## Task 1: API route
Goal: add route
Scope:
- `src/app/api/**`

- ./tests/api.test.ts
Done:
- tests pass
Failing test first: tests/api.test.ts::returns 200

## Task 2: Docs
Goal: docs
Scope:
- docs/*.md
Done:
- written
"""


class PlanfileTest(unittest.TestCase):
    def test_sections(self):
        s = planfile.sections(PLAN)
        self.assertEqual(sorted(s), ["1", "2"])
        self.assertTrue(s["1"].startswith("## Task 1: API route"))
        self.assertNotIn("Task 2", s["1"])

    def test_scope_handles_backticks_blank_lines_and_stops_at_next_field(self):
        self.assertEqual(planfile.scope(planfile.sections(PLAN)["1"]), ["src/app/api/**", "./tests/api.test.ts"])

    def test_in_scope_globs(self):
        g = ["src/app/api/**", "./tests/api.test.ts", "docs/*.md", "lib/**/*.ts"]
        self.assertTrue(planfile.in_scope("src/app/api/x/route.ts", g))
        self.assertTrue(planfile.in_scope("tests/api.test.ts", g))
        self.assertTrue(planfile.in_scope("docs/a.md", g))
        self.assertFalse(planfile.in_scope("docs/sub/a.md", g))
        self.assertTrue(planfile.in_scope("lib/a.ts", g))
        self.assertTrue(planfile.in_scope("lib/x/y/a.ts", g))
        self.assertFalse(planfile.in_scope("src/app/page.tsx", g))
        self.assertFalse(planfile.in_scope(".env", g))


if __name__ == "__main__":
    unittest.main()
