import hashlib
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scope_audit
import test_scope_audit


class AuditBypassTest(test_scope_audit.ScopeAuditTest):
    def cli(self, *args):
        p = subprocess.run([sys.executable, scope_audit.__file__, ".orchestrate/PLAN.md", *args], cwd=self.wt,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_sensitive_ignored_files_are_outside(self):
        with open(os.path.join(self.wt, ".git", "info", "exclude"), "a") as f:
            f.write(".env*\nbuild/\n")
        self.write("build/out.js")             # ordinary ignored build output: not counted
        self.assertTrue(self.audit("1", [])["ok"])
        self.write(".orchestrate/approved.json", "{}")  # the orchestrator's own files: not counted
        self.assertTrue(self.audit("1", [])["ok"])
        self.write(".env.local")
        self.write("src/b/.env")                # in task 2's (active) Scope: allowed
        self.write(".orchestrate/notes.md")
        r = self.audit("1", [])
        self.assertEqual((r["ok"], r["outside"]), (False, [".env.local", ".orchestrate/notes.md"]))

    def test_base_checks_every_commit_against_union(self):
        self.commit("src/b/y.ts", "feat: y (task 2)")   # active task 2: in the union
        self.assertTrue(self.audit("1", [], base=self.base)["ok"])
        self.commit("docs/z.md", "chore: unlabelled")   # no "(task N)" and outside every Scope
        r = self.audit("1", [], base=self.base)
        self.assertEqual((r["ok"], r["outside"]), (False, ["docs/z.md"]))

    def test_base_with_shas_still_checks_every_commit(self):
        own = self.commit("src/a/x.ts", "feat: x (task 1)")
        self.commit("docs/z.md", "chore: unlabelled")
        r = self.audit("1", [own], base=self.base)
        self.assertEqual((r["ok"], r["outside"]), (False, ["docs/z.md"]))

    def test_approved_sha_printed_and_checked(self):
        empty = hashlib.sha256(b"").hexdigest()
        out = self.cli("1")
        self.assertEqual((out["ok"], out["approved_sha"]), (True, empty))
        self.assertTrue(self.cli("1", "--approved-sha", empty)["ok"])
        self.write(".orchestrate/approved.json", '{"x": 1}')
        now = hashlib.sha256(b'{"x": 1}').hexdigest()
        out = self.cli("1", "--approved-sha", empty)
        self.assertEqual((out["ok"], out["outside"], out["approved_sha"]), (False, [".orchestrate/approved.json"], now))
        self.assertIn("changed outside the orchestrator", out["error"])
        self.assertTrue(self.cli("1", "--approved-sha", now)["ok"])


if __name__ == "__main__":
    unittest.main()
