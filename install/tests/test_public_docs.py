import unittest
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


class PublicDocsTest(unittest.TestCase):
    def test_workflow_not_machine_bound(self):
        t = read("docs/workflow.md")
        for s in ("on this Mac", "Canonical copy", "DryasWorkflow.md"):
            self.assertNotIn(s, t, s)
        for s in ("~/.claude/docs/dryas-workflow.md", "claude/CLAUDE.md.template", "example layout"):
            self.assertIn(s, t, s)

    def test_readme_use_it_yourself(self):
        t = read("README.md")
        self.assertIn("## Use it for yourself", t)
        for s in ("Fork", "claude/CLAUDE.md.template", "docs/workflow.md", "install/install.sh"):
            self.assertIn(s, t, s)


if __name__ == "__main__":
    unittest.main()
