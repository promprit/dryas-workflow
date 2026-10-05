import sys, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import render
REPO = HERE.parents[1]


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def on(rel):
    return render.gate_blocks(read(rel), ["pstack-picks"])


class ReviewFixesTest(unittest.TestCase):
    def test_cleanup_pass2_limited_to_diff(self):
        t = read("claude/pstack/cleanup.md")
        self.assertIn("Delete every comment added or changed in the diff against the base branch that is not on this keep-list", t)
        self.assertNotIn("Delete every comment in scope", t)
        self.assertIn("Pass 2 limited to comments added or changed in the diff", read("claude/pstack/UPSTREAM.md"))

    def test_codex_interrogate_read_only_sections(self):
        t = read("codex/skills/interrogate/SKILL.md")
        for s in ("Scope:\n(none: read-only review)", "Failing test first: none (review)", "`.orchestrate/active.json`"):
            self.assertIn(s, t, s)

    def test_codex_orchestrate_parity(self):
        t = on("codex/skills/orchestrate/SKILL.md")
        for s in ("none (cleanup)", "none (review)", "skip the test-first step", "{{CD}}/pstack/benchmark-checklist.md",
                  "marked the change contested", "include the four principle lines", "at most once per model"):
            self.assertIn(s, t, s)

    def test_claude_rca_cap(self):
        self.assertIn("at most once per model", on("claude/skills/orchestrate/SKILL.md"))

    def test_executor_subtract_wording(self):
        t = on("claude/agents/executor.md")
        self.assertIn("remove code your change makes dead", t)
        self.assertNotIn("remove dead code in your scope first", t)


if __name__ == "__main__":
    unittest.main()
