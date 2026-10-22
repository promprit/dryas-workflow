import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]


class ReaDocsTest(unittest.TestCase):
    def test_install_doc(self):
        t = (ROOT / "docs/install.md").read_text(encoding="utf-8")
        for want in ("--no-rea", "--with-rea", "rea-agents", "6.7.0", "22.19", "claude mcp remove --scope user rea",
                     "rea uninstall", "reverse-engineer-anything"):
            self.assertIn(want, t, want)

    def test_skipped_first_install_not_recorded(self):
        t = (ROOT / "docs/install.md").read_text(encoding="utf-8")
        paras = [x for x in t.split("\n\n") if "not recorded" in x]
        self.assertTrue(any("--with-rea" in x for x in paras))

    def test_on_demand_docs_name_the_pinned_version_and_command(self):
        import sys
        sys.path.insert(0, str(ROOT / "install"))
        import rea_setup
        pin = "rea-agents@" + rea_setup.VERSION
        for rel in ("claude/skills/brainstorm/reference.md", "docs/install.md"):
            t = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn(pin, t, rel)
            self.assertIn("rea on", t, rel)
            self.assertNotIn("rea-agents@" + "0.0.0", t)
        self.assertIn("never `rea setup`", (ROOT / "claude" / "CLAUDE.md.template").read_text(encoding="utf-8"))

    def test_workflow_doc(self):
        t = (ROOT / "docs/workflow.md").read_text(encoding="utf-8")
        self.assertIn("**Reverse-engineering work.**", t)
        self.assertLess(t.index("**Design work.**"), t.index("**Reverse-engineering work.**"))
        self.assertIn("| MCP `rea` + skill `reverse-engineer-anything` |", t)


if __name__ == "__main__":
    unittest.main()
