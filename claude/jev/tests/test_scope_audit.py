import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scope_audit

PLAN = ("## Task 1: a\nGoal: g\nScope:\n- src/a/**\nDone:\n- d\n\n"
        "## Task 2: b\nGoal: g\nScope:\n- src/b/**\nDone:\n- d\n")


class ScopeAuditTest(unittest.TestCase):
    def setUp(self):
        self.wt = os.path.realpath(tempfile.mkdtemp())
        self.logs = tempfile.mkdtemp()
        os.environ["JEV_LOG_DIR"] = self.logs
        self.git("init", "-q")
        with open(os.path.join(self.wt, ".git", "info", "exclude"), "a") as f:
            f.write(".orchestrate/\n")
        os.makedirs(os.path.join(self.wt, ".orchestrate"))
        with open(os.path.join(self.wt, ".orchestrate", "PLAN.md"), "w") as f:
            f.write(PLAN)
        with open(os.path.join(self.wt, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": ["1", "2"]}, f)
        self.base = self.commit("README.md", "chore: base")

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=self.wt, check=True,
                              capture_output=True, text=True).stdout.strip()

    def write(self, rel, text="x\n"):
        p = os.path.join(self.wt, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a") as f:
            f.write(text)

    def commit(self, rel, msg):
        self.write(rel)
        self.git("add", rel)
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def audit(self, task, shas, base=None):
        return scope_audit.audit(os.path.join(self.wt, ".orchestrate", "PLAN.md"), task, shas, base, self.wt)

    def test_in_scope_commit_ok(self):
        sha = self.commit("src/a/x.ts", "feat: x (task 1)")
        self.assertEqual(self.audit("1", [sha]), {"ok": True, "outside": [], "commits": [sha]})

    def test_commit_outside_scope_fails(self):
        sha = self.commit("src/b/x.ts", "feat: x (task 1)")
        r = self.audit("1", [sha])
        self.assertEqual((r["ok"], r["outside"]), (False, ["src/b/x.ts"]))
        with open(os.path.join(self.logs, "scope.jsonl")) as f:
            rec = json.loads(f.readlines()[-1])
        self.assertEqual((rec["kind"], rec["task"], rec["paths"]), ("violation", ["1"], ["src/b/x.ts"]))

    def test_other_task_commit_not_blamed(self):
        own = self.commit("src/a/x.ts", "feat: x (task 1)")
        self.commit("src/b/y.ts", "feat: y (task 2)")
        self.assertTrue(self.audit("1", [own])["ok"])

    def test_foreign_or_unknown_sha_fails(self):
        r = self.audit("1", ["0" * 40])
        self.assertFalse(r["ok"])
        self.assertIn("error", r)

    def test_uncommitted_checked_against_union(self):
        self.write("src/b/wip.ts")       # task 2 is active: its in-scope work is not task 1's fault
        self.assertTrue(self.audit("1", [])["ok"])
        self.write("docs/z.md")          # untracked, outside every active scope
        r = self.audit("1", [])
        self.assertEqual((r["ok"], r["outside"]), (False, ["docs/z.md"]))

    def test_rename_in_status(self):
        self.commit("src/a/old.ts", "feat: old (task 1)")
        self.git("mv", "src/a/old.ts", "src/a/new.ts")
        self.assertTrue(self.audit("1", [])["ok"])

    def test_fallback_finds_task_commits_by_subject(self):
        self.commit("src/b/x.ts", "feat: x (task 1)")
        r = self.audit("1", [], base=self.base)
        self.assertEqual((r["ok"], r["outside"], len(r["commits"])), (False, ["src/b/x.ts"], 1))

    def test_unknown_task(self):
        r = self.audit("9", [])
        self.assertFalse(r["ok"])
        self.assertIn("no Task 9", r["error"])

    def test_cli_prints_json_and_exits_zero(self):
        sha = self.commit("src/a/x.ts", "feat: x (task 1)")
        p = subprocess.run([sys.executable, scope_audit.__file__, ".orchestrate/PLAN.md", "1", sha], cwd=self.wt,
                           capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)["ok"]), (0, True))


if __name__ == "__main__":
    unittest.main()
