"""Canopy spec task 2: reviewer role values and role lessons in /orchestrate and review-request (all editions)."""
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
CLAUDE_LESSONS_STEP = (
    "Role lessons: right before each dispatch, call `mcp__plugin_dryas_jev__memory_search` once with namespace "
    "`role-<slug>`, query = the task title and task = the §5.5 id, where the slug is `builder` for coder, tester and "
    "docs, the review stage's own role for `reviewer-spec`, `reviewer-quality` and `reviewer-minimalist`, and "
    "`devils-advocate` for interrogate reviewers. Add the lessons it returns (at most 3, already cut to 600 "
    "characters) to the dispatch prompt under `Lessons from past <slug> work:`; none returned (or the switch "
    "`memory.role_lessons` is off): add nothing. The tool logs which lessons were loaded.")
CLAUDE_LESSONS_STORE = (
    "Role lessons, once per run after the merge: for each role that took part (`builder` when a build task ran, each "
    "review stage, `devils-advocate` when interrogate ran), store at most one lesson with "
    "`mcp__plugin_dryas_jev__memory_store`, namespace `role-<slug>`, kind outcome, a one-line title and a body under "
    "600 characters on what that role should do or avoid next time, taken from its review findings and escalations. "
    "Skip a role with nothing to learn. The tool tags the lesson with this repo and stores nothing when "
    "`memory.role_lessons` is off.")
REVIEW_ROLES = "role `reviewer-spec`, `reviewer-quality` or `reviewer-minimalist` (stage 1, 2 or 3)"
DESC_RULE = (
    "Every Agent dispatch's `description` starts with its role slug and a colon: `builder: ` (coder, tester, docs, "
    "cleanup), `reviewer-spec: `, `reviewer-quality: `, `reviewer-minimalist: ` or `devils-advocate: ` "
    "(interrogate), so observers such as FlowObserve's Canopy read the role instead of guessing it.")


def read(p):
    return (ROOT / p).read_text(encoding="utf-8")


class RoleMemoryDocsTest(unittest.TestCase):
    def test_orchestrate_loads_role_lessons(self):
        t = read("claude/skills/orchestrate/SKILL.md")
        dispatch = t.split("## 5. Dispatch")[1].split("\n## ")[0]
        self.assertIn(CLAUDE_LESSONS_STEP, dispatch)
        self.assertIn("reviewer-spec, reviewer-quality, reviewer-minimalist", dispatch)
        finish = t.split("## 8. Finish")[1].split("\n## ")[0]
        self.assertIn(CLAUDE_LESSONS_STORE, finish)

    def test_review_request_logs_stage_roles(self):
        self.assertIn(REVIEW_ROLES, read("claude/skills/review-request/SKILL.md"))
        self.assertNotIn("role reviewer, one per stage", read("claude/skills/review-request/SKILL.md"))

    def test_codex_and_opencode(self):
        for p, search in (("codex/skills/orchestrate/SKILL.md", "`memory_search`"),
                          ("opencode/skill/dryas-orchestrate/SKILL.md", "`jev_memory_search`")):
            t = read(p)
            self.assertIn("role-<slug>", t, p)
            self.assertIn(search, t, p)
            self.assertIn("memory.role_lessons", t, p)

    def test_description_prefix_rule(self):
        self.assertIn(DESC_RULE, read("claude/skills/orchestrate/SKILL.md").split("## 5. Dispatch")[1].split("\n## ")[0])
        self.assertIn("`reviewer-spec: `", read("claude/skills/review-request/SKILL.md"))
        self.assertIn("`devils-advocate: `", read("claude/skills/interrogate/SKILL.md"))
        for p in ("codex/skills/orchestrate/SKILL.md", "opencode/skill/dryas-orchestrate/SKILL.md",
                  "codex/skills/interrogate/SKILL.md", "opencode/skill/dryas-interrogate/SKILL.md",
                  "codex/skills/review-request/SKILL.md", "opencode/skill/dryas-review-request/SKILL.md"):
            t = read(p)
            self.assertTrue("`builder: `" in t or "`reviewer-spec: `" in t or "`devils-advocate: `" in t, p)

    def test_workflow_doc(self):
        t = read("docs/workflow.md")
        for s in ("role-<slug>", "memory.role_lessons", "reviewer-spec"):
            self.assertIn(s, t)


if __name__ == "__main__":
    unittest.main()
