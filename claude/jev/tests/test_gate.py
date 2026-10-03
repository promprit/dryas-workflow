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
        os.environ["JEV_THRESHOLDS"] = os.path.join(self.tmp, "none.json")
        os.environ["JEV_SSD_ROOT"] = self.tmp

    def bash(self, cmd):
        return {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "/tmp/dev/projects/demo"}

    def log(self):
        with open(os.path.join(self.tmp, "logs", "gate.jsonl")) as f:
            return [json.loads(l) for l in f]

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
        gate.run({"tool_name": "Write", "tool_input": {"file_path": "/x/a.ts", "content": fixture_body}, "cwd": "/x"}, j)
        state = j.calls[0][0]
        self.assertNotIn("TOP-SECRET-CONTENT", json.dumps(state))
        self.assertEqual(state["action"], {"tool": "Write", "file_path": "/x/a.ts", "bytes": len(fixture_body), "lines": 2})

    def test_edit_sends_line_counts_only(self):
        j = FakeJudge(answers(0.9))
        gate.run({"tool_name": "Edit", "tool_input": {"file_path": "/x/a.ts", "old_string": "a\nb", "new_string": "SECRETNEW"}, "cwd": "/x"}, j)
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
