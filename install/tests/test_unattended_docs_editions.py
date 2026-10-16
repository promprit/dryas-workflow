import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class EditionsDocsTest(unittest.TestCase):
    def test_codex_and_opencode_orchestrate(self):
        for rel in ("codex/skills/orchestrate/SKILL.md", "opencode/skill/dryas-orchestrate/SKILL.md"):
            s = read(rel)
            for needle in ("jev/preflight.py", "## Risky actions", "jev/scope_audit.py", "NEEDS DECISION",
                           ".orchestrate/approved.json", "NEEDS USER", "jev/run_report.py", "nobody is asked"):
                self.assertIn(needle, s, "%s: %s" % (rel, needle))

    def test_opencode_command_loads_the_unattended_skill(self):
        # The command is rendered by tools/sync_opencode.py and only loads the skill; the skill carries the rule.
        self.assertIn("dryas-orchestrate", read("opencode/command/orchestrate.md"))
        self.assertIn("nobody is asked", read("opencode/skill/dryas-orchestrate/SKILL.md"))

    def test_gov2_row(self):
        row = [l for l in read("reference/README.md").splitlines() if l.startswith("| GOV-2 |")][0]
        self.assertIn("audited against its scope", row)
        self.assertIn("partial", row)
        self.assertNotIn("shell-command edits are a known limit", row)


if __name__ == "__main__":
    unittest.main()
