import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class UnattendedDocsTest(unittest.TestCase):
    def test_orchestrate_runs_unattended(self):
        s = read("claude/skills/orchestrate/SKILL.md")
        for needle in ("jev/preflight.py", "## Risky actions", "jev/scope_audit.py", "--base", "NEEDS DECISION",
                       ".orchestrate/approved.json", "NEEDS USER", "jev/run_report.py", "PushNotification",
                       '"base"', "nobody is asked"):
            self.assertIn(needle, s, needle)

    def test_orchestrate_pins_approved_json(self):
        for rel in ("claude/skills/orchestrate/SKILL.md", "codex/skills/orchestrate/SKILL.md",
                    "opencode/skill/dryas-orchestrate/SKILL.md"):
            s = read(rel)
            for needle in ("--approved-sha", "approved_sha"):
                self.assertIn(needle, s, "%s: %s" % (rel, needle))

    def test_orchestrate_tools_allow_the_new_scripts(self):
        for rel in ("claude/skills/orchestrate/SKILL.md", "claude/commands/orchestrate.md"):
            head = read(rel).split("\n---", 1)[0]
            for needle in ("jev/scope_audit.py", "jev/preflight.py", "jev/run_report.py", "git rev-parse",
                           "PushNotification"):
                self.assertIn(needle, head, "%s: %s" % (rel, needle))

    def test_executor_reports_commits_and_decisions(self):
        s = read("claude/agents/executor.md")
        for needle in ("COMMITS:", "(task N)", "NEEDS DECISION:", "checked when you report back"):
            self.assertIn(needle, s, needle)
        self.assertNotIn("a shell write makes the user confirm it", s)

    def test_plan_proposes_risky_actions_in_plain_words(self):
        for rel in ("claude/skills/plan/SKILL.md", "claude/commands/wplan.md"):
            s = read(rel)
            self.assertIn("## Risky actions", s, rel)
            self.assertIn("plain", s, rel)

    def test_interrogate_never_asks_during_a_run(self):
        self.assertIn("during /orchestrate", read("claude/skills/interrogate/SKILL.md"))


if __name__ == "__main__":
    unittest.main()
