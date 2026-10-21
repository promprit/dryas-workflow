import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BANNER = "Deprecated: removed in a future release. Dryas memory and the Dryas skills replace them."


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def section(text, heading):
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


class LaunchDocsTest(unittest.TestCase):
    def test_scorecard_page_framing(self):
        page = read("docs/judge-scorecard.md")
        for s in ("gated in CI", "tools/judge_score.py", "reference/judge-corpus/"):
            self.assertIn(s, page)

    def test_docs_index_links_resolve(self):
        t = read("docs/README.md")
        targets = re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", t)
        self.assertGreaterEqual(len(targets), 20)
        for target in targets:
            if "://" not in target:
                self.assertTrue((REPO / "docs" / target).exists(), target)
        for door in ("## Use it", "## Understand it", "## Run it in a team", "## History"):
            self.assertIn(door, t)

    def test_deprecation_banners(self):
        w = read("docs/workflow.md")
        self.assertIn(BANNER, section(w, "## 7. "))
        self.assertIn(BANNER, section(w, "## 8. "))
        i = read("docs/install.md")
        self.assertGreaterEqual(i.count(BANNER), 1)
        self.assertIn("dryas memory import-ruflo", i)

    def test_moved_reference_material(self):
        i = read("docs/install.md")
        for s in ("## Reference stack", "### Manual plugin route", "/plugin marketplace add promprit/dryas-workflow",
                  "--no-design", "--no-rea", "--with-rea", "--no-pstack-picks", "--keep-extras"):
            self.assertIn(s, i, s)


if __name__ == "__main__":
    unittest.main()
