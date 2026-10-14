import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate
from jev_client import JevUnavailable


def answers(p_safe, risk="routine", risk_conf=0.9):
    return {"answers": {"safe": {"type": "noul", "value": p_safe, "confidence": max(p_safe, 1 - p_safe)},
                        "risk": {"type": "choice", "value": risk, "confidence": risk_conf, "probabilities": {}}},
            "latency_ms": 7, "input_tokens": 120, "cost": 0.000005}


class FakeJudge:
    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.calls = result, exc, []

    def __call__(self, state, questions):
        self.calls.append((state, questions))
        if self.exc:
            raise self.exc
        return self.result


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["JEV_LOG_DIR"] = os.path.join(self.tmp, "logs")
        os.environ["JEV_SSD_ROOT"] = self.tmp
        self.set_prescreen(False)  # existing tests cover allowlist/judge paths; prescreen tests opt in

    def bash(self, cmd):
        return {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "/tmp/dev/projects/demo"}

    def log(self):
        with open(os.path.join(self.tmp, "logs", "gate.jsonl")) as f:
            return [json.loads(l) for l in f]

    def set_prescreen(self, value):
        path = os.path.join(self.tmp, "t.json")
        with open(path, "w") as f:
            json.dump({"gate": {"prescreen": value}}, f)
        os.environ["JEV_THRESHOLDS"] = path

    def test_prescreen_skips_non_risky_bash(self):
        self.set_prescreen(True)
        j = FakeJudge(answers(0.9))
        self.assertIsNone(gate.run(self.bash("echo hello\ngrep -n foo README.md"), j))
        self.assertEqual(j.calls, [])
        rec = self.log()[-1]
        self.assertEqual((rec["decision"], rec["via"]), ("skipped", "prescreen"))

    def test_prescreen_on_by_default(self):
        os.environ["JEV_THRESHOLDS"] = os.path.join(self.tmp, "missing.json")
        j = FakeJudge(answers(0.9))
        self.assertIsNone(gate.run(self.bash("echo hello\ngrep -n foo README.md"), j))
        self.assertEqual(j.calls, [])
        rec = self.log()[-1]
        self.assertEqual((rec["decision"], rec["via"]), ("skipped", "prescreen"))

    def test_prescreen_import_error_other_than_importerror_still_judges(self):
        import builtins
        import importlib
        real = builtins.__import__

        def bad(name, *a, **k):
            if name == "prescreen":
                raise SyntaxError("broken prescreen")
            return real(name, *a, **k)
        builtins.__import__ = bad
        try:
            importlib.reload(gate)
        finally:
            builtins.__import__ = real
        try:
            self.assertIsNone(gate.prescreen)
            j = FakeJudge(answers(0.9))
            gate.run(self.bash("echo hello\ngrep -n foo README.md"), j)
            self.assertEqual(len(j.calls), 1)
        finally:
            importlib.reload(gate)

    def test_prescreen_risky_bash_goes_to_judge(self):
        self.set_prescreen(True)
        j = FakeJudge(answers(0.9))
        gate.run(self.bash("echo hi\nrm -rf build"), j)
        self.assertEqual(len(j.calls), 1)

    def test_prescreen_off_judges_non_risky(self):
        self.set_prescreen(False)
        j = FakeJudge(answers(0.9))
        gate.run(self.bash("echo hello\ngrep -n foo README.md"), j)
        self.assertEqual(len(j.calls), 1)

    def test_prescreen_exception_counts_as_risky(self):
        self.set_prescreen(True)
        class Boom:
            @staticmethod
            def risky(cmd):
                raise RuntimeError("x")
        old = gate.prescreen
        gate.prescreen = Boom
        try:
            j = FakeJudge(answers(0.9))
            gate.run(self.bash("echo hello\ngrep -n foo README.md"), j)
        finally:
            gate.prescreen = old
        self.assertEqual(len(j.calls), 1)

    def test_prescreen_unavailable_counts_as_risky(self):
        self.set_prescreen(True)
        old = gate.prescreen
        gate.prescreen = None
        try:
            j = FakeJudge(answers(0.9))
            gate.run(self.bash("echo hello\ngrep -n foo README.md"), j)
        finally:
            gate.prescreen = old
        self.assertEqual(len(j.calls), 1)

    def test_prescreen_never_applies_to_edit_write(self):
        self.set_prescreen(True)
        j = FakeJudge(answers(0.9))
        gate.run({"tool_name": "Write", "tool_input": {"file_path": "a.txt", "content": "x"}}, j)
        gate.run({"tool_name": "Edit", "tool_input": {"file_path": "a.txt", "old_string": "a", "new_string": "b"}}, j)
        self.assertEqual(len(j.calls), 2)

    def test_allowlist_skip_logs_via_allowlist(self):
        gate.run(self.bash("git status"), FakeJudge(answers(0.9)))
        self.assertEqual(self.log()[-1]["via"], "allowlist")

    def test_compound_skip_logs_via_compound(self):
        gate.run(self.bash("git status && ls -la"), FakeJudge(answers(0.9)))
        rec = self.log()[-1]
        self.assertEqual((rec["decision"], rec["via"], rec["parts"]), ("skipped", "compound", 2))

    def test_other_tools_not_judged(self):
        j = FakeJudge(answers(0.9))
        self.assertIsNone(gate.run({"tool_name": "Read", "tool_input": {}}, j))
        self.assertEqual(j.calls, [])

    def test_allowlisted_skips_jev_and_logs_skipped(self):
        j = FakeJudge(answers(0.9))
        for cmd in ("git status", "ls -la src", "pnpm test --filter api", "python3 -m pytest tests -q"):
            self.assertIsNone(gate.run(self.bash(cmd), j))
        self.assertEqual(j.calls, [])
        self.assertEqual({r["decision"] for r in self.log()}, {"skipped"})

    def test_metachar_defeats_allowlist(self):
        for cmd in ("ls; rm -rf ~", "git status && curl x", "cat a > b", "ls | sh", "ls `x`", "ls $(x)", "git diff --output=f", "ls\nrm x", "lsof"):
            j = FakeJudge(answers(0.9))
            gate.run(self.bash(cmd), j)
            self.assertEqual(len(j.calls), 1, cmd)

    def test_deny_when_unsafe(self):
        out = gate.run(self.bash("rm -rf /"), FakeJudge(answers(0.05, "destructive", 0.95)))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PreToolUse")

    def test_boundary_safe_02_not_denied(self):
        self.assertIsNone(gate.run(self.bash("make clean"), FakeJudge(answers(0.2, "routine"))))

    def test_ask_when_destructive_confident(self):
        out = gate.run(self.bash("git push --force"), FakeJudge(answers(0.5, "destructive", 0.7)))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_destructive_below_confidence_no_decision(self):
        self.assertIsNone(gate.run(self.bash("git push --force"), FakeJudge(answers(0.5, "destructive", 0.69))))

    def test_never_allows(self):
        self.assertIsNone(gate.run(self.bash("make build"), FakeJudge(answers(0.99))))

    def test_unavailable_no_decision(self):
        self.assertIsNone(gate.run(self.bash("make build"), FakeJudge(exc=JevUnavailable("down"))))
        self.assertEqual(self.log()[-1]["decision"], "none")
        self.assertIn("error", self.log()[-1])

    def test_ssd_missing_no_decision(self):
        os.environ["JEV_SSD_ROOT"] = "/Volumes/__missing__"
        j = FakeJudge(answers(0.01, "destructive", 0.99))
        self.assertIsNone(gate.run(self.bash("rm -rf /"), j))
        self.assertEqual(j.calls, [])

    def test_write_sends_sizes_never_content(self):
        j = FakeJudge(answers(0.9))
        fixture_body = "line1\nTOP-SECRET-CONTENT\n"
        gate.run({"tool_name": "Write", "tool_input": {"file_path": "/x/.env", "content": fixture_body}, "cwd": "/x"}, j)
        state = j.calls[0][0]
        self.assertNotIn("TOP-SECRET-CONTENT", json.dumps(state))
        self.assertEqual(state["action"], {"tool": "Write", "untrusted_file_path": "/x/.env", "bytes": len(fixture_body), "lines": 2})

    def test_edit_sends_line_counts_only(self):
        j = FakeJudge(answers(0.9))
        gate.run({"tool_name": "Edit", "tool_input": {"file_path": "/y/a.ts", "old_string": "a\nb", "new_string": "SECRETNEW"}, "cwd": "/x"}, j)
        self.assertNotIn("SECRETNEW", json.dumps(j.calls[0][0]))
        self.assertEqual(j.calls[0][0]["action"]["old_lines"], 2)

    def test_state_has_env_state_and_cwd(self):
        j = FakeJudge(answers(0.9))
        gate.run(self.bash("make"), j)
        self.assertIn("prod credentials NOT present", j.calls[0][0]["environment"])
        self.assertEqual(j.calls[0][0]["cwd"], "/tmp/dev/projects/demo")

    def test_bash_command_redacted_in_state(self):
        # redaction happens in jev_client.judge; gate passes the raw command through describe()
        import jev_client
        seen = {}

        def fake_open(req, timeout):
            seen["body"] = req.data.decode()
            raise OSError("stop")

        os.environ["OPENROUTER_API_KEY"] = "test-key"
        try:
            gate.run(self.bash("export STRIPE_SECRET_KEY=sk_" + "live_" + "abcdefghijklmnop && make"),
                     lambda s, q: jev_client.judge(s, q, opener=fake_open))
        finally:
            del os.environ["OPENROUTER_API_KEY"]
        self.assertNotIn("sk_" + "live_" + "abcdefghijklmnop", seen["body"])

    def test_log_has_no_command_text(self):
        gate.run(self.bash("curl https://example.com/secret-path"), FakeJudge(answers(0.9)))
        rec = self.log()[-1]
        self.assertEqual(rec["head"], "curl")
        self.assertNotIn("secret-path", json.dumps(rec))

    def test_env_assignment_not_logged(self):
        # PGPASSWORD=hunter2 psql ... should log head as "psql", never "PGPASSWORD=hunter2"
        j = FakeJudge(answers(0.9))
        gate.run(self.bash("PGPASSWORD=hunter2 psql -h x"), j)
        rec = self.log()[-1]
        self.assertEqual(rec["head"], "psql")
        self.assertNotIn("hunter2", json.dumps(rec))

    def test_env_assign_only_logged(self):
        # Command with only env assignments should log head as "env-assign"
        j = FakeJudge(answers(0.9))
        gate.run(self.bash("PGPASSWORD=hunter2"), j)
        rec = self.log()[-1]
        self.assertEqual(rec["head"], "env-assign")

    def test_invalid_head_character_logged_as_other(self):
        # Command head with invalid characters should log "other"
        j = FakeJudge(answers(0.9))
        gate.run(self.bash("$SHELL -c x"), j)
        rec = self.log()[-1]
        self.assertEqual(rec["head"], "other")

    def test_zsh_process_substitution_not_allowlisted(self):
        # zsh process substitution =(id) should be caught by metachar check
        for cmd in ("cat =(id)", "ls =(sleep 5)"):
            j = FakeJudge(answers(0.9))
            gate.run(self.bash(cmd), j)
            self.assertEqual(len(j.calls), 1, cmd)

    def test_zsh_glob_qualifier_not_allowlisted(self):
        # zsh glob qualifiers like (e:...:) should be caught
        for cmd in ("cat *(e:'id':)", "ls *(:T)"):
            j = FakeJudge(answers(0.9))
            gate.run(self.bash(cmd), j)
            self.assertEqual(len(j.calls), 1, cmd)

    def test_empty_allowlist_entry_does_not_allowlist(self):
        # Empty allowlist entry should not allowlist everything
        os.environ["JEV_THRESHOLDS"] = os.path.join(self.tmp, "threshold.json")
        import thresholds as th
        th_copy = th.load()
        th_copy["gate"]["allowlist"] = [""]
        with open(os.environ["JEV_THRESHOLDS"], "w") as f:
            import json as json_mod
            json_mod.dump(th_copy, f)
        j = FakeJudge(answers(0.9))
        gate.run(self.bash("rm -rf x"), j)
        self.assertEqual(len(j.calls), 1)  # Should still be judged

    def test_git_ext_diff_not_allowlisted(self):
        # git diff --ext-diff should not be allowlisted
        j = FakeJudge(answers(0.9))
        gate.run(self.bash("git diff --ext-diff"), j)
        self.assertEqual(len(j.calls), 1)

    def test_git_textconv_not_allowlisted(self):
        # git show --textconv should not be allowlisted
        j = FakeJudge(answers(0.9))
        gate.run(self.bash("git show --textconv"), j)
        self.assertEqual(len(j.calls), 1)

    def test_git_exec_not_allowlisted(self):
        # pytest --exec should not be allowlisted
        j = FakeJudge(answers(0.9))
        gate.run(self.bash("pytest --exec id"), j)
        self.assertEqual(len(j.calls), 1)

    def test_git_dashc_not_allowlisted(self):
        # git -c should not be allowlisted
        j = FakeJudge(answers(0.9))
        gate.run(self.bash("git -c core.pager=less log"), j)
        self.assertEqual(len(j.calls), 1)

    def test_missing_latency_ms_no_exception(self):
        # Malformed response missing latency_ms should not raise, just return None and log
        def bad_judge(s, q):
            return {"answers": {"safe": {"type": "noul", "value": 0.05, "confidence": 0.95},
                                "risk": {"type": "choice", "value": "destructive", "confidence": 0.95, "probabilities": {}}}}
        j = bad_judge
        out = gate.run(self.bash("rm -rf /"), j)
        # Should still return the deny decision
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_risk_conf_as_string_no_exception(self):
        # risk_conf as string instead of number should not raise (will fail comparison)
        def bad_judge(s, q):
            return {"answers": {"safe": {"type": "noul", "value": 0.5, "confidence": 0.95},
                                "risk": {"type": "choice", "value": "destructive", "confidence": "0.95", "probabilities": {}}},
                    "latency_ms": 7, "input_tokens": 120, "cost": 0.000005}
        out = gate.run(self.bash("rm -rf /"), bad_judge)
        self.assertIsNone(out)  # Should log error and return None

    def test_non_dict_tool_input_no_exception(self):
        # tool_input as string instead of dict should not raise
        event = {"tool_name": "Bash", "tool_input": "string-input", "cwd": "/x"}
        j = FakeJudge(answers(0.9))
        out = gate.run(event, j)
        self.assertIsNone(out)  # Should skip/log and return None


if __name__ == "__main__":
    unittest.main()


class GateFileToolsTest(unittest.TestCase):
    """MultiEdit/NotebookEdit coverage, the local-file skip and the untrusted envelope."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        os.environ["JEV_LOG_DIR"] = os.path.join(self.tmp, "logs")
        os.environ["JEV_SSD_ROOT"] = self.tmp
        os.environ["JEV_THRESHOLDS"] = os.path.join(self.tmp, "missing.json")

    def log(self):
        with open(os.path.join(self.tmp, "logs", "gate.jsonl")) as f:
            return [json.loads(l) for l in f]

    def ev(self, tool, path, **ti):
        key = "notebook_path" if tool == "NotebookEdit" else "file_path"
        return {"tool_name": tool, "tool_input": dict({key: path}, **ti), "cwd": self.tmp}

    def test_gate_tools_include_multiedit_and_notebookedit(self):
        self.assertTrue({"MultiEdit", "NotebookEdit"} <= gate.GATE_TOOLS)

    def test_multiedit_outside_cwd_is_judged_with_summary(self):
        j = FakeJudge(answers(0.9))
        edits = [{"old_string": "a\nb", "new_string": "SECRET1\nx\ny"}, {"old_string": "c", "new_string": "SECRET2", "replace_all": True}]
        gate.run(self.ev("MultiEdit", "/elsewhere/a.py", edits=edits), j)
        self.assertEqual(len(j.calls), 1)
        action = j.calls[0][0]["action"]
        self.assertNotIn("SECRET", json.dumps(j.calls[0][0]))
        self.assertEqual(action, {"tool": "MultiEdit", "untrusted_file_path": "/elsewhere/a.py", "edits": 2, "old_lines": 3,
                                  "new_lines": 4, "new_bytes": 18, "replace_all": True})

    def test_multiedit_bad_edits_shape_judged_not_crash(self):
        j = FakeJudge(answers(0.9))
        self.assertIsNone(gate.run(self.ev("MultiEdit", "/elsewhere/a.py", edits="nope"), j))
        self.assertEqual(j.calls[0][0]["action"]["edits"], 0)

    def test_notebookedit_judged_with_cell_summary(self):
        j = FakeJudge(answers(0.9))
        gate.run(self.ev("NotebookEdit", "/elsewhere/n.ipynb", cell_id="c1", cell_type="code", edit_mode="insert",
                         new_source="import os\nSECRETSRC"), j)
        action = j.calls[0][0]["action"]
        self.assertNotIn("SECRETSRC", json.dumps(j.calls[0][0]))
        self.assertEqual(action, {"tool": "NotebookEdit", "untrusted_file_path": "/elsewhere/n.ipynb", "edit_mode": "insert",
                                  "cell_type": "code", "new_lines": 2, "new_bytes": 19})

    def test_notebookedit_deny_passes_through(self):
        out = gate.run(self.ev("NotebookEdit", "/elsewhere/n.ipynb", new_source="x"), FakeJudge(answers(0.05)))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_local_plain_file_skips_judge_and_logs(self):
        j = FakeJudge(answers(0.9))
        for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            self.assertIsNone(gate.run(self.ev(tool, os.path.join(self.tmp, "src", "a.py")), j))
            self.assertIsNone(gate.run(self.ev(tool, "src/relative.py"), j))
        self.assertEqual(j.calls, [])
        rec = self.log()[-1]
        self.assertEqual((rec["decision"], rec["via"]), ("skipped", "local_file"))

    def test_sensitive_local_files_are_judged(self):
        for rel in (".git/config", ".github/workflows/ci.yml", ".env", ".env.local", ".claude/settings.json", "Makefile",
                    "package.json", "pyproject.toml", "setup.py", "scripts/deploy.sh", "certs/server.key", "a/.hidden/x.py",
                    "Dockerfile.dev", "docker-compose.override.yml", "requirements-dev.txt", "build.gradle.kts", "PACKAGE.JSON"):
            j = FakeJudge(answers(0.9))
            gate.run(self.ev("Write", os.path.join(self.tmp, rel), content="x"), j)
            self.assertEqual(len(j.calls), 1, rel)

    def test_combined_event_is_judged_when_any_listed_path_is_sensitive(self):
        j = FakeJudge(answers(0.9))
        ev = self.ev("Write", os.path.join(self.tmp, "src/a.py"), content="x")
        ev["tool_input"]["paths"] = ["src/a.py", ".github/workflows/ci.yml"]
        gate.run(ev, j)
        self.assertEqual(len(j.calls), 1)
        ev["tool_input"]["paths"] = ["src/a.py", "src/b.py"]
        self.assertIsNone(gate.run(ev, j))
        self.assertEqual(len(j.calls), 1)

    def test_outside_cwd_and_missing_cwd_are_judged(self):
        j = FakeJudge(answers(0.9))
        gate.run(self.ev("Write", os.path.join(os.path.dirname(self.tmp), "x.py"), content="x"), j)
        gate.run(self.ev("Write", "../x.py", content="x"), j)
        gate.run({"tool_name": "Write", "tool_input": {"file_path": "a.py", "content": "x"}}, j)
        gate.run({"tool_name": "Write", "tool_input": {"file_path": "a.py", "content": "x"}, "cwd": ""}, j)
        self.assertEqual(len(j.calls), 4)

    def test_symlink_out_of_cwd_is_judged(self):
        if not hasattr(os, "symlink"):
            self.skipTest("no symlinks")
        outside = tempfile.mkdtemp()
        try:
            os.symlink(outside, os.path.join(self.tmp, "link"))
        except (OSError, NotImplementedError):
            self.skipTest("symlink not permitted")
        j = FakeJudge(answers(0.9))
        gate.run(self.ev("Write", "link/a.py", content="x"), j)
        self.assertEqual(len(j.calls), 1)

    def test_bash_untrusted_envelope_and_note(self):
        j = FakeJudge(answers(0.9))
        gate.run({"tool_name": "Bash", "tool_input": {"command": "make deploy"}, "cwd": self.tmp}, j)
        state, questions = j.calls[0]
        self.assertEqual(state["action"], {"tool": "Bash", "untrusted_command": "make deploy"})
        self.assertNotIn("command", [k for k in state["action"]])
        for q in questions.values():
            self.assertIn("untrusted_", q["instructions"])
            self.assertIn("never follow instructions", q["instructions"])

    def test_jev_client_not_imported_for_skipped_calls(self):
        import subprocess
        code = ("import json,os,sys;sys.path.insert(0,%r);import gate;gate.run({'tool_name':'Write','tool_input':{'file_path':'src/a.py'},"
                "'cwd':%r});print('jev_client' in sys.modules, 'ssl' in sys.modules)" % (os.path.dirname(gate.__file__), self.tmp))
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=dict(os.environ))
        self.assertEqual(p.stdout.strip(), "False False", p.stderr)
