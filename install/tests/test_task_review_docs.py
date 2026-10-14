import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import sync_codex_plugin

CLI = '"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/task_review.py" answer'


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


class TaskReviewDocsTest(unittest.TestCase):
    def test_claude_orchestrate_asks_task_review_and_passes_usage(self):
        t = read("claude/skills/orchestrate/SKILL.md")
        for s in (CLI + " .orchestrate/PLAN.md <N>", '"review_version": 1', "dispatch.scored_tier", "review.task_skip",
                  "tokens and duration_ms", "score, score_tier and task_type", "agent_id"):
            self.assertIn(s, t, s)
        for rel in ("claude/skills/orchestrate/SKILL.md", "claude/commands/orchestrate.md"):
            front = read(rel).split("---", 2)[1]
            self.assertIn('Bash(%s:*)' % CLI, front, rel)

    def test_codex_orchestrate_matches(self):
        t = read("codex/skills/orchestrate/SKILL.md")
        for s in ('"<dryas-py>" -X utf8 "<dryas-root>/jev/task_review.py" answer', '"review_version": 1',
                  "dispatch.scored_tier", "tokens and duration_ms"):
            self.assertIn(s, t, s)
        self.assertEqual(sync_codex_plugin.skill_drift(REPO), [])

    def test_governance_describes_switches_and_classes(self):
        t = read("docs/governance.md")
        for s in ("## Task-level judgement", "`review.task_skip`", "`dispatch.scored_tier`", "`history.min_tasks`",
                  "`review.max_false_skip_rate`", "`baseline.until`", "PASS or FAIL", "`git restore <path>` without `--staged`",
                  "`git stash clear`", "every edit is judged", "build files and scripts"):
            self.assertIn(s, t, s)


if __name__ == "__main__":
    unittest.main()
