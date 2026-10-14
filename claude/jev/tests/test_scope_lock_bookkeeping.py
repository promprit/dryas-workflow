import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scope_lock

WIDE = "## Task 1: a\nGoal: g\nScope:\n- **\n- .orchestrate/**\nDone:\n- d\n"


class BookkeepingTest(unittest.TestCase):
    def setUp(self):
        self.wt = os.path.realpath(tempfile.mkdtemp())
        os.makedirs(os.path.join(self.wt, ".orchestrate"))
        with open(os.path.join(self.wt, ".orchestrate", "PLAN.md"), "w") as f:
            f.write(WIDE)
        with open(os.path.join(self.wt, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": ["1"]}, f)
        p = mock.patch.dict(os.environ, {"JEV_LOG_DIR": tempfile.mkdtemp()})
        p.start()
        self.addCleanup(p.stop)
        self.active = os.path.join(self.wt, ".orchestrate", "active.json")

    def decision(self, out):
        return out["hookSpecificOutput"]["permissionDecision"] if out else None

    def edit(self, tool, path, agent=True):
        key = "notebook_path" if tool == "NotebookEdit" else "file_path"
        ev = {"tool_name": tool, "tool_input": {key: path}, "cwd": self.wt}
        if agent:
            ev["agent_id"] = "exec-1"
        return ev

    def bash(self, cmd, agent=True):
        ev = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": self.wt}
        if agent:
            ev["agent_id"] = "exec-1"
        return ev

    def test_executor_never_edits_active_json_even_when_scope_matches(self):
        for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            for path in (self.active, ".orchestrate/active.json", os.path.join(self.wt, ".orchestrate", "PLAN.md")):
                out = scope_lock.run(self.edit(tool, path))
                self.assertEqual(self.decision(out), "deny", (tool, path))
                self.assertIn("orchestrator bookkeeping", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_orchestrator_still_writes_active_json(self):
        self.assertIsNone(scope_lock.run(self.edit("Write", self.active, agent=False)))

    def test_wide_scope_still_allows_other_files(self):
        self.assertIsNone(scope_lock.run(self.edit("Write", os.path.join(self.wt, "src", "a.py"))))

    def test_executor_shell_write_to_orchestrate_denied(self):
        for cmd in ("echo '{}' > .orchestrate/active.json", "cp x.json .orchestrate/active.json",
                    "rm .orchestrate/active.json", "sed -i s/a/b/ .orchestrate/active.json"):
            self.assertEqual(self.decision(scope_lock.run(self.bash(cmd))), "deny", cmd)

    def test_orchestrator_shell_write_still_asks_and_reads_pass(self):
        self.assertEqual(self.decision(scope_lock.run(self.bash("rm .orchestrate/active.json", agent=False))), "ask")
        self.assertIsNone(scope_lock.run(self.bash("cat .orchestrate/active.json")))
        self.assertEqual(self.decision(scope_lock.run(self.bash("echo hi > out.txt"))), "ask")


    def test_executor_denied_every_spelling_of_orchestrate_path(self):
        os.makedirs(os.path.join(self.wt, "sub"))
        for path in ("./.orchestrate/active.json", "sub/../.orchestrate/active.json", ".orchestrate",
                     ".orchestrate/other.txt", os.path.join(self.wt, ".orchestrate")):
            out = scope_lock.run(self.edit("Write", path))
            self.assertEqual(self.decision(out), "deny", path)
            self.assertIn("orchestrator bookkeeping", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_executor_denied_symlink_in_scope_pointing_into_orchestrate(self):
        os.symlink(self.active, os.path.join(self.wt, "alias.json"))
        os.symlink(os.path.join(self.wt, ".orchestrate"), os.path.join(self.wt, "book"))
        for path in ("alias.json", os.path.join(self.wt, "book", "active.json"), "book/PLAN.md"):
            out = scope_lock.run(self.edit("Edit", path))
            self.assertEqual(self.decision(out), "deny", path)
            self.assertIn("orchestrator bookkeeping", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_executor_shell_write_forms_denied(self):
        for cmd in ("tee .orchestrate/active.json", "mv x .orchestrate/active.json",
                    "ln -sf x .orchestrate/active.json", "python3 -c \"open('.orchestrate/active.json','w')\"",
                    "cd .orchestrate && echo x > active.json"):
            out = scope_lock.run(self.bash(cmd))
            self.assertEqual(self.decision(out), "deny", cmd)
            self.assertIn("orchestrator bookkeeping", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_obfuscated_shell_write_never_allowed(self):
        # Literal matching is the deny line; forms that hide the name keep today's ask, never pass silently.
        for cmd in ("echo x > .orche''strate/active.json", "D=.orchestrate; echo x > $D/active.json",
                    "echo x > $D/active.json"):
            self.assertIn(self.decision(scope_lock.run(self.bash(cmd))), ("ask", "deny"), cmd)

    def test_executor_reads_pass_and_main_thread_unaffected(self):
        self.assertIsNone(scope_lock.run(self.bash("cat .orchestrate/PLAN.md")))
        self.assertIsNone(scope_lock.run(self.bash("cat .orchestrate/PLAN.md", agent=False)))
        for path in (self.active, ".orchestrate/PLAN.md", ".orchestrate/other.txt"):
            self.assertIsNone(scope_lock.run(self.edit("Write", path, agent=False)), path)
        self.assertEqual(self.decision(scope_lock.run(self.bash("tee .orchestrate/PLAN.md", agent=False))), "ask")
    def test_executor_denied_any_case_of_orchestrate(self):
        for path in (".ORCHESTRATE/active.json", ".Orchestrate/PLAN.md", os.path.join(self.wt, ".orchestrate".upper()),
                     "./.oRcHeStRaTe/other.txt"):
            out = scope_lock.run(self.edit("Write", path))
            self.assertEqual(self.decision(out), "deny", path)
            self.assertIn("orchestrator bookkeeping", out["hookSpecificOutput"]["permissionDecisionReason"])
        for cmd in ("echo x > .ORCHESTRATE/active.json", "rm .Orchestrate/PLAN.md", "cd .ORCHESTRATE && tee x"):
            out = scope_lock.run(self.bash(cmd))
            self.assertEqual(self.decision(out), "deny", cmd)
            self.assertIn("orchestrator bookkeeping", out["hookSpecificOutput"]["permissionDecisionReason"])
        # The main session keeps its bookkeeping rights in any case; a lookalike name is not bookkeeping.
        self.assertIsNone(scope_lock.run(self.edit("Write", ".ORCHESTRATE/active.json", agent=False)))
        self.assertIsNone(scope_lock.run(self.edit("Write", "src/.Orchestrate.txt")))


if __name__ == "__main__":
    unittest.main()
