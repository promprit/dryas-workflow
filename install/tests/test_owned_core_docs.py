import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ["docs/workflow.md", "docs/architecture.md", "docs/memory-model.md", "docs/governance.md", "docs/install.md",
        "docs/harnesses.md", "docs/roles.md", "docs/execution-model.md", "docs/review-model.md",
        "docs/release-check.md", "docs/roadmap.md", "CONTRIBUTING.md"]
STALE = [r"the \*\*only\*\* memory", r"only memory/learning layer", r"Superpowers\*\* \(plugin\) \| Process",
         r"required by the plugin", r"required dependency", r"superpowers:[a-z]", r"Ruflo is the memory",
         r"installs Superpowers as a dependency", r"searches Ruflo memory", r"stored in Ruflo memory",
         r"Node is used only for the Ruflo MCP shim"]
FILES = DOCS + ["README.md", "reference/README.md", "docs/why-dryas.md", "docs/operating-model.md",
                "docs/adoption-guide.md"]


class DocsTest(unittest.TestCase):
    def text(self, p):
        return (ROOT / p).read_text(encoding="utf-8")

    def test_no_stale_requirement_claims(self):
        for p in FILES:
            t = self.text(p)
            for pat in STALE:
                self.assertIsNone(re.search(pat, t), "%s: %s" % (p, pat))

    def test_required_facts(self):
        need = {
            "docs/install.md": ["--judge local", "--with-ruflo", "--with-superpowers", "--with-design", "--memory",
                                "dryas memory import-ruflo", "Node"],
            "docs/workflow.md": ["mem-edit", "mem-session-end", "memory_search", "dryas:brainstorm", "/retro",
                                 "fast → standard → strong → frontier"],
            "docs/memory-model.md": ["dryas.db", "FTS5", "PageRank", "include_archive", "dryas memory consolidate"],
            "docs/governance.md": ["Judge providers", "deterministic rules", "judge-corpus"],
            "docs/harnesses.md": ["mem-session-start", "memory_search", "Claude Code only"],
            "docs/roadmap.md": ["owned core"],
        }
        for p, needles in need.items():
            t = self.text(p)
            for n in needles:
                self.assertIn(n, t, "%s lacks %r" % (p, n))


class RepositionTest(unittest.TestCase):
    def test_scorecard_page_matches(self):
        r = (ROOT / "docs/judge-scorecard.md").read_text(encoding="utf-8")
        block = r.split("<!-- scorecard:start -->")[1].split("<!-- scorecard:end -->")[0]
        card = (ROOT / "reference/judge-corpus/SCORECARD.md").read_text(encoding="utf-8")
        table = card[card.index("| Measure"):]
        self.assertEqual(block.strip(), table.strip())

    def test_readme_positioning(self):
        r = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Rules your AI agents can't ignore.", r)
        self.assertIn("target operating model", r)
        self.assertNotIn("built on Superpowers, Ruflo", r)
        self.assertIn("docs/install.md", r)
        i = (ROOT / "docs/install.md").read_text(encoding="utf-8")
        for flag in ("--with-ruflo", "--with-superpowers", "--judge"):
            self.assertIn(flag, i)

    def test_manifest_bindings(self):
        y = (ROOT / "reference/dryas.yaml").read_text(encoding="utf-8")
        for needle in ("provider: dryas:brainstorm", "provider: dryas", "process: dryas", "judge:"):
            self.assertIn(needle, y)
        self.assertNotIn("superpowers:brainstorming", y)
        s = (ROOT / "spec/dryas-spec-v1.md").read_text(encoding="utf-8")
        ex = s[s.index("9.2"):]
        self.assertNotIn("provider: ruflo\n", ex.split("```")[1] if "```" in ex else ex)
