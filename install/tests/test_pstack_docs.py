import unittest
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


class PstackDocsTest(unittest.TestCase):
    def test_readme(self):
        t = read("README.md")
        for s in ("pstack", "Lauren Tan", "Michael Denyer", "cursor-team-kit", "`--no-pstack-picks`", "NOTICE.md"):
            self.assertIn(s, t, s)
        self.assertNotIn("Third-party code is not vendored here.", t)

    def test_notice(self):
        t = read("NOTICE.md")
        for s in ("claude/pstack/NOTICE.md", "claude/pstack/UPSTREAM.md", "dc8e617", "MIT"):
            self.assertIn(s, t, s)

    def test_workflow(self):
        t = read("docs/workflow.md")
        for s in ("pstack picks", "needs_interrogate", "| interrogate | min_confidence 0.7 |", "`/interrogate`",
                  "`/benchmark-checklist`", "Root cause before each climb", "cleanup"):
            self.assertIn(s, t, s)
        self.assertNotIn("Last updated: 2026-10-03.", t)

    def test_harnesses_and_install(self):
        self.assertIn("$interrogate", read("docs/harnesses.md"))
        i = read("docs/install.md")
        for s in ("`--no-pstack-picks`", "pstack picks", "does not remove that component"):
            self.assertIn(s, i, s)


if __name__ == "__main__":
    unittest.main()
