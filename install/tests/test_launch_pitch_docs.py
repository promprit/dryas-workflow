import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BANNED = ("revolutionary", "ai-powered", "seamless", "supercharge", "unleash", "game-changing",
          "cutting-edge", "blazing", "effortless")


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


class PitchDocsTest(unittest.TestCase):
    def test_why_dryas_opens_with_problem(self):
        t = read("docs/why-dryas.md")
        head = t.split("\n## ", 2)
        self.assertIn("Brilliant agents. No discipline.", head[0] + head[1][:400])
        self.assertNotIn("hardened on install", t)
        self.assertNotIn("Ruflo", t)
        self.assertNotIn("Superpowers", t)
        self.assertIn("OpenCode", t.split("## What Dryas is not", 1)[1])
        for w in BANNED:
            self.assertNotIn(w, t.lower(), w)

    def test_roadmap_and_harnesses(self):
        r = read("docs/roadmap.md")
        self.assertIn("## Next: retire the optional extras", r)
        self.assertIn("owned core", r)
        h = read("docs/harnesses.md")
        self.assertIn("| OpenCode | Supported (core)", h)

    def test_contributing(self):
        self.assertNotIn("rough edges", read("CONTRIBUTING.md"))

    def test_changelog_unreleased(self):
        c = read("CHANGELOG.md")
        u = c.index("## Unreleased")
        self.assertLess(u, c.index("## 2.0.1"))
        self.assertIn("### Docs", c[u:c.index("## 2.0.1")])


if __name__ == "__main__":
    unittest.main()
