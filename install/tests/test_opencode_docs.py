import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


class OpenCodeDocsTest(unittest.TestCase):
    def test_conformance_table_has_oc_column(self):
        text = (REPO / "reference/README.md").read_text(encoding="utf-8")
        self.assertIn("| Rule | CC | CX | OC | How |", text)
        rows = [l for l in text.splitlines() if re.match(r"^\| [A-Z]+-\d", l)]
        self.assertTrue(rows)
        for row in rows:
            cells = [c.strip() for c in row.strip("|").split("|")]
            self.assertEqual(len(cells), 5, row)
            self.assertRegex(cells[3], r"^(met|partial|not met)\b", row)

    def test_harness_docs_name_opencode(self):
        self.assertIn("## OpenCode", (REPO / "docs/harnesses.md").read_text(encoding="utf-8"))
        self.assertIn("--harness opencode", (REPO / "docs/install.md").read_text(encoding="utf-8"))
        self.assertIn("--harness opencode", (REPO / "README.md").read_text(encoding="utf-8"))
        self.assertNotIn("parked 2026-10-15", (REPO / "docs/roadmap.md").read_text(encoding="utf-8"))

    def test_docs_describe_approval_code(self):
        harn = (REPO / "docs/harnesses.md").read_text(encoding="utf-8")
        self.assertIn("dryas allow", harn)
        for rel in ("docs/harnesses.md", "docs/install.md", "reference/README.md"):
            text = (REPO / rel).read_text(encoding="utf-8")
            for phrase in ("answers OpenCode's permission", "becomes an OpenCode permission prompt", "stops Dryas answering"):
                self.assertNotIn(phrase, text, rel)


if __name__ == "__main__":
    unittest.main()
