import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import runrules

PLAN = ("## Risky actions\n- `pnpm db:reset*` — wipes the local test database.\n\n"
        "## Task 1: a\nGoal: g\nScope:\n- src/**\n")


class RunRulesBypassTest(unittest.TestCase):
    def setUp(self):
        self.wt = os.path.realpath(tempfile.mkdtemp())
        os.makedirs(os.path.join(self.wt, ".orchestrate"))
        with open(os.path.join(self.wt, ".orchestrate", "PLAN.md"), "w") as f:
            f.write(PLAN)
        with open(os.path.join(self.wt, ".orchestrate", "approved.json"), "w") as f:
            json.dump({"commands": [{"cmd": "rm -rf build", "task": "1", "reason": "r"}]}, f)

    def cov(self, cmd):
        return runrules.covered(cmd, self.wt, self.wt)

    def test_baseline_still_covered(self):
        self.assertEqual(self.cov("rm -rf build"), "orchestrator")
        self.assertEqual(self.cov("pnpm build && rm -rf build"), "orchestrator")
        self.assertEqual(self.cov("pnpm db:reset --force"), "planned")

    def test_cd_breaks_coverage(self):
        for c in ("cd /etc && rm -rf build", "cd /; rm -rf build", "pushd /etc; rm -rf build",
                  "popd; rm -rf build"):
            self.assertIsNone(self.cov(c), c)

    def test_output_redirect_breaks_coverage(self):
        for c in ("pnpm db:reset > /etc/passwd", "rm -rf build; echo hi > /etc/x", "rm -rf build >> log.txt"):
            self.assertIsNone(self.cov(c), c)
        self.assertEqual(self.cov("rm -rf build > /dev/null 2>&1"), "orchestrator")

    def test_pipe_into_shell_breaks_coverage(self):
        self.assertIsNone(self.cov("pnpm db:reset | sh"))
        self.assertIsNone(self.cov("pnpm db:reset | bash -s"))

    def test_write_outside_worktree_breaks_coverage(self):
        self.assertIsNone(self.cov("rm -rf build; touch /etc/x"))
        self.assertIsNone(self.cov("pnpm db:reset; cp a /tmp/elsewhere/b"))

    def test_git_global_options_do_not_hide_push(self):
        for c in ("git -C . push origin x", "git -c a=b push", "git --git-dir=.git push",
                  "git --work-tree=. push", "git -C . -c a=b push"):
            self.assertTrue(runrules.human_only(c.split(), self.wt, self.wt), c)
        self.assertFalse(runrules.human_only("git -C . status".split(), self.wt, self.wt))


if __name__ == "__main__":
    unittest.main()
