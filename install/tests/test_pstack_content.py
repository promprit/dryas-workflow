# install/tests/test_pstack_content.py
import re, unittest
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
PSTACK = REPO / "claude" / "pstack"
LAYOUT = ["LICENSE", "LICENSE-cursor-team-kit", "NOTICE.md", "UPSTREAM.md", "cleanup.md", "benchmark-checklist.md",
          "interrogate/reviewer-prompt.md", "interrogate/rubric.md", "interrogate/code-quality-review.md",
          "interrogate/lead-judgment.md", "principles/fix-root-causes.md", "principles/prove-it-works.md",
          "principles/subtract-before-you-add.md", "principles/test-behavior-not-implementation.md",
          "principles/guard-the-context-window.md"]
EXEMPT = {"LICENSE", "LICENSE-cursor-team-kit", "NOTICE.md", "UPSTREAM.md"}
LEAK = re.compile(r"poteto|pstack:|setup-pstack|pstack-models|effort-|\b(opus|fable|sonnet|haiku)\b|just do it|never block|readonly",
                  re.I)
LINK = re.compile(r"\]\(([^)#:]+)(#[^)]*)?\)")


def vendored():
    return [p for p in PSTACK.rglob("*") if p.is_file() and p.relative_to(PSTACK).as_posix() not in EXEMPT]


class PstackContentTest(unittest.TestCase):
    def test_layout_complete(self):
        have = sorted(p.relative_to(PSTACK).as_posix() for p in PSTACK.rglob("*") if p.is_file())
        self.assertEqual(have, sorted(LAYOUT))

    def test_no_leaks(self):
        hits = ["%s:%d" % (p.relative_to(REPO).as_posix(), n)
                for p in vendored() for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                if LEAK.search(line)]
        self.assertEqual(hits, [])

    def test_no_frontmatter_or_home_paths(self):
        for p in vendored():
            t = p.read_text(encoding="utf-8")
            self.assertFalse(t.startswith("---"), p)
            self.assertNotIn("~/", t, p)

    def test_relative_links_resolve(self):
        for p in vendored():
            for m in LINK.finditer(p.read_text(encoding="utf-8")):
                self.assertTrue((p.parent / m.group(1)).resolve().is_file(), (p, m.group(1)))

    def test_licenses_verbatim_holders(self):
        lic = (PSTACK / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Copyright (c) 2026 Lauren Tan", lic)
        self.assertIn("Copyright (c) 2026 Michael Denyer", lic)
        self.assertIn("Cursor", (PSTACK / "LICENSE-cursor-team-kit").read_text(encoding="utf-8"))

    def test_upstream_lists_every_vendored_file(self):
        up = (PSTACK / "UPSTREAM.md").read_text(encoding="utf-8")
        self.assertIn("dc8e617f179cf0bdc68b61e672f33e9eb64c20cf", up)
        for rel in LAYOUT:
            if rel not in EXEMPT:
                self.assertIn("`%s`" % rel, up, rel)

    def test_cleanup_keeps_deslop_and_keep_list(self):
        t = (PSTACK / "cleanup.md").read_text(encoding="utf-8")
        for s in ("Casts to `any` used only to bypass type issues", "Keep behavior unchanged unless fixing a clear bug.",
                  "Legal or license headers.", "Doc comments that define a public API contract."):
            self.assertIn(s, t)
        for s in ("/how", "/why", "/architect", "comment-sicko", "MUST KILL"):
            self.assertNotIn(s, t)


if __name__ == "__main__":
    unittest.main()
