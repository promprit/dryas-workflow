import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import runrules

PLAN = ("## Risky actions\n- `rm -rf dist` — deletes the build folder.\n"
        "- `pnpm db:reset*` — wipes the local test database.\n- `git push origin feat/x` — publishes the branch.\n"
        "- `vercel*` — deploys.\n\n## Task 1: a\nGoal: g\nScope:\n- src/**\n")


class RunRulesTest(unittest.TestCase):
    def setUp(self):
        self.wt = os.path.realpath(tempfile.mkdtemp())
        os.makedirs(os.path.join(self.wt, ".orchestrate"))
        with open(os.path.join(self.wt, ".orchestrate", "PLAN.md"), "w", encoding="utf-8") as f:
            f.write(PLAN)

    def approve(self, *cmds):
        with open(os.path.join(self.wt, ".orchestrate", "approved.json"), "w") as f:
            json.dump({"commands": [{"cmd": c, "task": "1", "reason": "r"} for c in cmds]}, f)

    def cov(self, cmd):
        return runrules.covered(cmd, self.wt, self.wt)

    def test_planned_exact_and_prefix(self):
        self.assertEqual(self.cov("rm -rf dist"), "planned")
        self.assertEqual(self.cov("pnpm db:reset --force"), "planned")
        self.assertIsNone(self.cov("pnpm db:resetall"))
        self.assertIsNone(self.cov("rm -rf distro"))

    def test_compound_needs_every_risky_part_covered(self):
        self.assertEqual(self.cov("pnpm build && rm -rf dist"), "planned")
        self.assertIsNone(self.cov("pnpm db:reset && git reset --hard"))

    def test_nothing_matched_is_not_covered(self):
        self.assertIsNone(self.cov("make build"))

    def test_orchestrator_exact_only(self):
        self.approve("git reset --hard HEAD~1")
        self.assertEqual(self.cov("git reset --hard HEAD~1"), "orchestrator")
        self.assertIsNone(self.cov("git reset --hard HEAD~2"))

    def test_human_only_never_from_orchestrator_or_prefix(self):
        self.approve("git push origin main", "rm -rf /tmp/elsewhere-dir", "terraform apply")
        self.assertIsNone(self.cov("git push origin main"))
        self.assertIsNone(self.cov("rm -rf /tmp/elsewhere-dir"))
        self.assertIsNone(self.cov("terraform apply"))
        self.assertIsNone(self.cov("vercel deploy --prod"))         # plan prefix cannot cover a human-only action
        self.assertEqual(self.cov("git push origin feat/x"), "planned")  # an exact plan entry can

    def test_plan_not_in_utf8_covers_nothing(self):
        # e.g. a PLAN.md saved in a Windows code page: no crash, nothing pre-approved
        with open(os.path.join(self.wt, ".orchestrate", "PLAN.md"), "wb") as f:
            f.write(PLAN.encode("utf-8").replace("\u2014".encode("utf-8"), b"\x97"))
        self.assertIsNone(self.cov("rm -rf dist"))

    def test_unreadable_files_cover_nothing(self):
        with open(os.path.join(self.wt, ".orchestrate", "approved.json"), "w") as f:
            f.write("{broken")
        self.assertIsNone(self.cov("git reset --hard HEAD~1"))
        os.remove(os.path.join(self.wt, ".orchestrate", "PLAN.md"))
        self.assertIsNone(self.cov("rm -rf dist"))


if __name__ == "__main__":
    unittest.main()
