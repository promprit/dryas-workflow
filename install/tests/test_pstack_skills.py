# install/tests/test_pstack_skills.py
import re, sys, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import codex_target as ct
from test_pstack_content import LEAK
REPO = HERE.parents[1]
NAMES = ("interrogate", "benchmark-checklist")
OURS = {"orchestrate", "wplan", "wreview", "commit", "tune", "handoff"}
SUPERPOWERS = {"brainstorming", "using-git-worktrees", "test-driven-development", "requesting-code-review",
               "receiving-code-review", "verification-before-completion", "writing-plans", "systematic-debugging",
               "subagent-driven-development", "executing-plans", "dispatching-parallel-agents",
               "finishing-a-development-branch", "diagnosing-superpowers", "writing-skills", "using-superpowers"}
CD_PATH = re.compile(r"\{\{CD\}\}/([A-Za-z0-9_./-]+)")


def skill(h, n):
    return (REPO / h / "skills" / n / "SKILL.md").read_text(encoding="utf-8")


class PstackSkillsTest(unittest.TestCase):
    def test_skills_exist(self):
        for h in ("claude", "codex"):
            for n in NAMES:
                self.assertTrue(skill(h, n).startswith("---\nname: %s\ndescription: " % n), (h, n))
        self.assertEqual(tuple(ct.PSTACK_SKILLS), NAMES)

    def test_claude_skills_not_model_invoked(self):
        for n in NAMES:
            head = skill("claude", n).split("---", 2)[1]
            self.assertIn("\ndisable-model-invocation: true\n", head, n)

    def test_no_name_collisions(self):
        for n in NAMES:
            self.assertNotIn(n, OURS | SUPERPOWERS)

    def test_no_leaks(self):
        for h in ("claude", "codex"):
            for n in NAMES:
                for i, line in enumerate(skill(h, n).splitlines(), 1):
                    self.assertIsNone(LEAK.search(line), (h, n, i, line))

    def test_cd_paths_resolve(self):
        for h in ("claude", "codex"):
            for n in NAMES:
                for rel in CD_PATH.findall(skill(h, n)):
                    self.assertTrue((REPO / "claude" / rel.rstrip(".")).exists(), (h, n, rel))

    def test_interrogate_read_only_panel(self):
        t = skill("claude", "interrogate")
        self.assertIn("Scope:\n(none: read-only review)", t)
        self.assertIn("never the top rung", t)
        self.assertIn("after every build task has left `.orchestrate/active.json`", t)


if __name__ == "__main__":
    unittest.main()
