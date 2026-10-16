import json
import os
import sys
import tempfile
import unittest
from unittest import mock

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
        self.logs = tempfile.mkdtemp()
        os.environ["JEV_LOG_DIR"] = self.logs

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
        self.assertIsNone(scope_lock.run({"tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}, "cwd": self.wt}))
        self.assertIsNone(scope_lock.run({"tool_name": "Grep", "tool_input": {"pattern": "rm x"}, "cwd": self.wt}))

    def bash(self, cmd, cwd=None, **extra):
        return dict({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd or self.wt}, **extra)

    SID = "0155kfr8-aaaa-bbbb-cccc-0123456789ab"

    def test_bash_never_asks(self):
        for cmd in ("rm x", "echo hi > out.txt", "cat a >> b", "sed -i 's/a/b/' f", "git checkout -- f", "git restore f",
                    "mv a b", "cp a b", "tee f", "truncate -s0 f", "dd if=a of=b", "git stash", "npm install left-pad",
                    "python3 - <<'EOF'\nopen('x', 'w')\nEOF", "rm $F", "./gen.sh"):
            out = scope_lock.run(self.bash(cmd, agent_id="a1"))
            self.assertNotEqual(self.decision(out), "ask", cmd)

    def test_bash_executor_in_scope_targets_allowed(self):
        for cmd in ("sed -i 's/a/b/' src/feature/a.ts", "echo hi > src/feature/out.txt", "cp x src/feature/b.ts",
                    "mkdir -p src/feature/new", "cd src && rm feature/old.ts"):
            self.assertIsNone(scope_lock.run(self.bash(cmd, agent_id="a1")), cmd)
        recs = self.scope_records()
        self.assertTrue(recs and all(r["decision"] == "allow" and r["kind"] == "allow" and r["run"] is True for r in recs))

    def test_bash_executor_out_of_scope_target_denied(self):
        for cmd, path in (("echo hi > out.txt", "out.txt"), ("rm src/other.ts", "src/other.ts"),
                          ("sed -i 's/a/b/' README.md", "README.md"), ("cp a /tmp/elsewhere-x", "/tmp/elsewhere-x")):
            out = scope_lock.run(self.bash(cmd, agent_id="a1"))
            self.assertEqual(self.decision(out), "deny", cmd)
            reason = out["hookSpecificOutput"]["permissionDecisionReason"]
            self.assertIn(path, reason)
            self.assertIn("Edit/Write inside your Scope", reason)
        self.assertTrue(all(r["kind"] == "deny" for r in self.scope_records()))

    def test_bash_unknown_writes_allowed_and_logged(self):
        for cmd in ("python3 - <<'EOF'\nopen('x', 'w')\nEOF", "rm $F", "./gen.sh", "git stash"):
            self.assertIsNone(scope_lock.run(self.bash(cmd, agent_id="a1")), cmd)
        self.assertEqual(self.scope_records()[0]["rule"], "inline_code")

    def test_bash_executor_orchestrate_denied(self):
        out = scope_lock.run(self.bash("echo x > .orchestrate/approved.json", agent_id="a1"))
        self.assertEqual(self.decision(out), "deny")
        self.assertEqual(self.scope_records()[-1]["rule"], "orchestrate")

    def test_bash_main_session_writes_never_ask(self):
        # the orchestrator (no agent_id) already edits any file with Edit/Write; asking about its shell writes only adds prompts
        for cmd in ("rm x", "echo hi > out.txt", "cat a >> .orchestrate/PLAN.md", "cp a b"):
            self.assertIsNone(scope_lock.run(self.bash(cmd)), cmd)
        self.assertEqual(self.scope_records(), [])

    def test_bash_codex_main_session_checked(self):
        with mock.patch.dict(os.environ, {"DRYAS_HARNESS": "codex"}):
            self.assertEqual(self.decision(scope_lock.run(self.bash("rm src/other.ts"))), "deny")
            self.assertIsNone(scope_lock.run(self.bash("rm src/feature/a.ts")))
            self.assertIsNone(scope_lock.run(self.bash("python3 -c 'x'")))
            self.assertIsNone(scope_lock.run(self.bash("echo x > .orchestrate/approved.json")))

    def test_bash_scratchpad_of_this_session_only(self):
        base = os.path.realpath(tempfile.mkdtemp())
        pad = os.path.join(base, "-enc-dir", self.SID, "scratchpad")
        os.makedirs(pad)
        os.symlink(os.path.join(self.wt, "src", "other.ts"), os.path.join(pad, "link.ts"))
        with mock.patch.object(scope_lock, "SCRATCH_BASE", base):
            ok = lambda p: scope_lock.run(self.bash("echo x > " + p, agent_id="a1", session_id=self.SID))
            self.assertIsNone(ok(os.path.join(pad, "probe.py")))
            for bad in (os.path.join(base, "-enc-dir", "other-session-id", "scratchpad", "x"),
                        os.path.join(base, "-enc-dir", self.SID, "scratchpad2", "x"),
                        os.path.join(pad, "link.ts")):
                self.assertEqual(self.decision(ok(bad)), "deny", bad)
            with mock.patch.dict(os.environ, {"DRYAS_HARNESS": "opencode"}):
                self.assertEqual(self.decision(ok(os.path.join(pad, "probe.py"))), "deny")

    def test_bash_read_only_allowed(self):
        for cmd in ("ls -la", "git status", "grep -rn foo src", "cat a 2>/dev/null", "python3 -m pytest -q", "echo '>' done"):
            self.assertIsNone(scope_lock.run(self.bash(cmd)), cmd)
        self.assertEqual(self.scope_records(), [])

    def test_bash_without_active_task_allowed(self):
        self.set_active([])
        self.assertIsNone(scope_lock.run(self.bash("rm -rf x")))
        os.remove(os.path.join(self.wt, ".orchestrate", "active.json"))
        self.assertIsNone(scope_lock.run(self.bash("rm -rf x")))

    def test_bash_unusable_active_json_denies_readable_targets(self):
        with open(os.path.join(self.wt, ".orchestrate", "active.json"), "w") as f:
            f.write("{not json")
        self.assertEqual(self.decision(scope_lock.run(self.bash("rm x", agent_id="a1"))), "deny")
        self.assertIsNone(scope_lock.run(self.bash("ls", agent_id="a1")))

    def test_non_dict_tool_input_no_crash(self):
        # a file tool with no path cannot be checked: denied while a task is active, ignored otherwise
        out = scope_lock.run({"tool_name": "Write", "tool_input": ["x"], "cwd": self.wt})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIsNone(scope_lock.run({"tool_name": "Bash", "tool_input": "rm x", "cwd": self.wt}))
        self.set_active([])
        self.assertIsNone(scope_lock.run({"tool_name": "Write", "tool_input": {}, "cwd": self.wt}))

    def test_task_active(self):
        self.assertTrue(scope_lock.task_active(self.wt))
        self.assertTrue(scope_lock.task_active(os.path.join(self.wt, "src", "deep")))
        self.set_active([])
        self.assertFalse(scope_lock.task_active(self.wt))
        self.assertFalse(scope_lock.task_active(tempfile.mkdtemp()))

    def _main(self, stdin, cwd):
        import subprocess
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scope_lock.py")
        return subprocess.run([sys.executable, script], input=stdin, capture_output=True, text=True, cwd=cwd, env=dict(os.environ))

    def test_main_malformed_stdin_fails_closed_while_active(self):
        for bad in ("not json", "[1, 2]", "\"str\"", "42"):
            p = self._main(bad, self.wt)
            self.assertEqual(p.returncode, 2, bad)
            self.assertIn("scope lock: malformed hook input", p.stderr)

    def test_main_malformed_stdin_silent_without_task(self):
        self.set_active([])
        for bad in ("not json", "[1, 2]"):
            p = self._main(bad, self.wt)
            self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""), bad)
        p = self._main("[1]", tempfile.mkdtemp())
        self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_main_well_formed_event_still_decides(self):
        p = self._main(json.dumps(self.ev(os.path.join(self.wt, "src/other.ts"))), self.wt)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

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

    def scope_records(self):
        p = os.path.join(self.logs, "scope.jsonl")
        if not os.path.exists(p):
            return []
        with open(p) as f:
            return [json.loads(l) for l in f]

    def test_deny_writes_scope_record(self):
        out = scope_lock.run(self.ev(os.path.join(self.wt, "src/other.ts")))
        self.assertEqual(self.decision(out), "deny")
        recs = self.scope_records()
        self.assertEqual(len(recs), 1)
        self.assertEqual((recs[0]["task"], recs[0]["path"], recs[0]["decision"]), (["1"], "src/other.ts", "deny"))

    def test_allow_writes_nothing(self):
        self.assertIsNone(scope_lock.run(self.ev(os.path.join(self.wt, "src/feature/a.ts"))))
        self.assertEqual(self.scope_records(), [])

    def test_unwritable_log_dir_still_denies(self):
        blocker = os.path.join(self.logs, "afile")
        open(blocker, "w").close()
        os.environ["JEV_LOG_DIR"] = os.path.join(blocker, "sub")  # parent is a file: makedirs fails
        out = scope_lock.run(self.ev(os.path.join(self.wt, "src/other.ts")))
        self.assertEqual(self.decision(out), "deny")


if __name__ == "__main__":
    unittest.main()
