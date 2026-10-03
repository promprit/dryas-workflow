import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scope_lock

PLAN = "## Task 1: a\nGoal: g\nScope:\n- src/feature/**\nDone:\n- d\n\n## Task 2: b\nGoal: g\nScope:\n- docs/x.md\nDone:\n- d\n"


class ScopeLockTest(unittest.TestCase):
    def setUp(self):
        self.wt = os.path.realpath(tempfile.mkdtemp())
        os.makedirs(os.path.join(self.wt, ".orchestrate"))
        # Write PLAN.md to .orchestrate/ (primary location)
        with open(os.path.join(self.wt, ".orchestrate", "PLAN.md"), "w") as f:
            f.write(PLAN)
        self.set_active(["1"])

    def set_active(self, ids):
        with open(os.path.join(self.wt, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": ids}, f)

    def ev(self, path, tool="Write", cwd=None):
        return {"tool_name": tool, "tool_input": {"file_path": path, "content": "x"}, "cwd": cwd or self.wt}

    def decision(self, out):
        return out["hookSpecificOutput"]["permissionDecision"] if out else None

    def test_in_scope_allowed(self):
        self.assertIsNone(scope_lock.run(self.ev(os.path.join(self.wt, "src/feature/a.ts"))))

    def test_out_of_scope_denied(self):
        out = scope_lock.run(self.ev(os.path.join(self.wt, "src/other.ts")))
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("src/other.ts", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_union_of_active_tasks(self):
        self.set_active(["1", "2"])
        self.assertIsNone(scope_lock.run(self.ev(os.path.join(self.wt, "docs/x.md"))))

    def test_new_file_new_dir_in_scope(self):
        self.assertIsNone(scope_lock.run(self.ev(os.path.join(self.wt, "src/feature/new/deep/b.ts"))))

    def test_relative_path_resolved(self):
        self.assertIsNone(scope_lock.run(self.ev("src/feature/a.ts")))
        self.assertEqual(self.decision(scope_lock.run(self.ev("src/zzz.ts"))), "deny")

    def test_outside_worktree_denied_while_active(self):
        self.assertEqual(self.decision(scope_lock.run(self.ev("/tmp/elsewhere.txt"))), "deny")

    def test_cwd_elsewhere_file_inside_worktree_still_checked(self):
        self.assertEqual(self.decision(scope_lock.run(self.ev(os.path.join(self.wt, "src/other.ts"), cwd="/tmp"))), "deny")

    def test_bookkeeping_files_allowed(self):
        # .orchestrate/* allowed from main thread
        self.assertIsNone(scope_lock.run(self.ev(os.path.join(self.wt, ".orchestrate/active.json"))))
        self.assertIsNone(scope_lock.run(self.ev(os.path.join(self.wt, ".orchestrate/PLAN.md"))))

    def test_no_active_file_no_lock(self):
        os.remove(os.path.join(self.wt, ".orchestrate", "active.json"))
        self.assertIsNone(scope_lock.run(self.ev(os.path.join(self.wt, "anything.ts"))))

    def test_empty_active_no_lock(self):
        self.set_active([])
        self.assertIsNone(scope_lock.run(self.ev(os.path.join(self.wt, "anything.ts"))))

    def test_missing_plan_with_active_denies(self):
        os.remove(os.path.join(self.wt, ".orchestrate", "PLAN.md"))
        self.assertEqual(self.decision(scope_lock.run(self.ev(os.path.join(self.wt, "src/feature/a.ts")))), "deny")

    def test_non_edit_tools_ignored(self):
        self.assertIsNone(scope_lock.run({"tool_name": "Bash", "tool_input": {"command": "rm x"}, "cwd": self.wt}))
        self.assertIsNone(scope_lock.run({"tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}, "cwd": self.wt}))

    def test_edit_tool_checked(self):
        e = {"tool_name": "Edit", "tool_input": {"file_path": os.path.join(self.wt, "src/x.ts")}, "cwd": self.wt}
        self.assertEqual(self.decision(scope_lock.run(e)), "deny")

    def test_active_null_denies(self):
        self.set_active(None)
        out = scope_lock.run(self.ev(os.path.join(self.wt, "src/feature/a.ts")))
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("unusable", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_active_number_denies(self):
        with open(os.path.join(self.wt, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": 5}, f)
        out = scope_lock.run(self.ev(os.path.join(self.wt, "src/feature/a.ts")))
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("unusable", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_active_string_denies(self):
        with open(os.path.join(self.wt, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": "12"}, f)
        out = scope_lock.run(self.ev(os.path.join(self.wt, "src/feature/a.ts")))
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("unusable", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_active_with_non_str_int_denies(self):
        with open(os.path.join(self.wt, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": [1, None, 3]}, f)
        out = scope_lock.run(self.ev(os.path.join(self.wt, "src/feature/a.ts")))
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("unusable", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_bookkeeping_with_agent_id_denied(self):
        ev = {"tool_name": "Write", "tool_input": {"file_path": os.path.join(self.wt, ".orchestrate", "active.json"), "content": "x"}, "cwd": self.wt, "agent_id": "abc"}
        out = scope_lock.run(ev)
        self.assertEqual(self.decision(out), "deny")

    def test_bookkeeping_without_agent_id_allowed(self):
        ev = {"tool_name": "Write", "tool_input": {"file_path": os.path.join(self.wt, ".orchestrate", "active.json"), "content": "x"}, "cwd": self.wt}
        self.assertIsNone(scope_lock.run(ev))

    def test_orchestrate_plan_md_with_agent_id_denied(self):
        # Executor cannot write .orchestrate/PLAN.md
        ev = {"tool_name": "Write", "tool_input": {"file_path": os.path.join(self.wt, ".orchestrate", "PLAN.md"), "content": "x"}, "cwd": self.wt, "agent_id": "xyz"}
        out = scope_lock.run(ev)
        self.assertEqual(self.decision(out), "deny")

    def test_orchestrate_plan_md_without_agent_id_allowed(self):
        # Main thread can write .orchestrate/PLAN.md
        ev = {"tool_name": "Write", "tool_input": {"file_path": os.path.join(self.wt, ".orchestrate", "PLAN.md"), "content": "x"}, "cwd": self.wt}
        self.assertIsNone(scope_lock.run(ev))

    def test_root_plan_md_fallback(self):
        # Remove .orchestrate/PLAN.md so fallback to root PLAN.md is used
        os.remove(os.path.join(self.wt, ".orchestrate", "PLAN.md"))
        with open(os.path.join(self.wt, "PLAN.md"), "w") as f:
            f.write(PLAN)
        # Should work with fallback
        self.assertIsNone(scope_lock.run(self.ev(os.path.join(self.wt, "src/feature/a.ts"))))


if __name__ == "__main__":
    unittest.main()
