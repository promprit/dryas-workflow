import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
read = lambda p: (ROOT / p).read_text(encoding="utf-8")


class WiringTest(unittest.TestCase):
    def test_orchestrate_uses_dryas_memory_tools(self):
        s = read("claude/skills/orchestrate/SKILL.md")
        for t in ("memory_search", "memory_store", "swarm_init"):
            self.assertIn("mcp__plugin_dryas_jev__" + t, s)
        self.assertNotIn("mcp__plugin_ruflo-core_ruflo__", s.split("---", 2)[1])  # allowed-tools front matter
        self.assertNotIn("Ruflo memory", s)
        cx = read("codex/skills/orchestrate/SKILL.md")
        self.assertNotIn("server `ruflo`", cx)
        self.assertIn("server `jev`", cx)

    def test_ruflo_reference_is_the_optional_extra(self):
        first = read("claude/skills/orchestrate/ruflo-tools.md").splitlines()[0]
        self.assertIn("optional", first.lower())

    def test_executor_commit_rule(self):
        e = read("claude/agents/executor.md")
        self.assertIn("5. Commit your own task only when the dispatch prompt allows it (explicit paths, conventional "
                      "message); never push, merge or create worktrees.", e)
        self.assertNotIn("Do not commit, push", e)
        self.assertIn("allows the executor to commit its own task", read("claude/skills/orchestrate/SKILL.md"))
        self.assertIn("commit its own task", read("codex/skills/orchestrate/SKILL.md"))

    def test_review_receive_pointer_is_shipped(self):
        for p in ("claude/skills/review-receive/SKILL.md", "codex/skills/review-receive/SKILL.md"):
            self.assertNotIn("docs/governance.md", read(p), p)

    def test_templates_describe_owned_layers(self):
        t = read("claude/CLAUDE.md.template")
        self.assertIn("scope lock -> gate -> memory -> observer", t)
        self.assertNotIn("the only memory/learning layer", t)
        a = read("codex/AGENTS.md.template")
        self.assertNotIn("Ruflo is the memory", a)
        self.assertIn("memory_search", a)

    def test_tune_command_has_no_ruflo_cost_note(self):
        self.assertNotIn("ruflo-cost-tracker", read("claude/commands/tune.md"))
