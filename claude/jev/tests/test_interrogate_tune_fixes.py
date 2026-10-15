"""Interrogate fixes (owned core D, Task 21): read-only allowlist proposals, in-process gate-outcome that logs
only asked ids, /tune robust to malformed rows."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import chain
import gate
import gate_outcome
import local_judge
import thresholds
import tune_judge
import tune_tasks

G = lambda **k: dict({"tool": "Bash", "provider": "local", "decision": "ask"}, **k)


def approved(heads, n):
    g = [G(head=h, tool_use_id="%s-%d" % (h, i)) for h in heads for i in range(n)]
    return tune_judge.approved_asks(g, [{"tool_use_id": r["tool_use_id"], "tool": "Bash"} for r in g])


class TuneFixTest(unittest.TestCase):
    MULTI = ["terraform", "gh", "tar", "cargo", "go", "systemctl", "nc", "crontab", "truncate", "shred", "kubectl",
             "docker", "npm", "pnpm"]

    def test_multipurpose_heads_never_proposed(self):
        a = approved(self.MULTI, 99)
        self.assertEqual(len(a), len(self.MULTI))
        self.assertIsNone(tune_judge.allowlist_proposal(a, [], 3))

    def test_read_only_heads_are_proposed(self):
        p = tune_judge.allowlist_proposal(approved(["jq", "stat", "terraform"], 5), ["ls"], 3)
        self.assertEqual(p["new"], ["ls", "jq", "stat"])

    def test_heads_with_exec_or_write_flags_never_proposed(self):
        # rg --pre, fd -x, bat --pager run a command; sort -o, uniq OUT, tree -o, yq -i write a file; less +! runs one.
        heads = ["rg", "fd", "bat", "sort", "uniq", "tree", "yq", "less", "more", "file"]
        self.assertIsNone(tune_judge.allowlist_proposal(approved(heads, 9), [], 3))

    def test_proposable_heads_pass_validate_and_are_not_arg_judged(self):
        self.assertIsInstance(tune_judge.PROPOSABLE_HEADS, frozenset)
        self.assertFalse(tune_judge.PROPOSABLE_HEADS & local_judge.ARG_JUDGED_HEADS)
        for h in tune_judge.PROPOSABLE_HEADS:
            self.assertIsNone(thresholds.validate("gate.allowlist", [h]), h)

    def test_arg_judged_heads_are_public_and_complete(self):
        self.assertIsInstance(local_judge.ARG_JUDGED_HEADS, frozenset)
        for h in ("rm", "dd", "eval", "chmod", "git", "format", "del", "erase", "sh", "bash", "psql", "sqlite3",
                  "pwsh", "powershell", "sudo", "env", "xargs", "timeout", "mkfs"):
            self.assertIn(h, local_judge.ARG_JUDGED_HEADS, h)

    def test_arg_judged_heads_never_proposed_even_if_listed(self):
        heads = sorted(local_judge.ARG_JUDGED_HEADS)
        with mock.patch.object(tune_judge, "PROPOSABLE_HEADS", tune_judge.PROPOSABLE_HEADS | frozenset(heads)):
            self.assertIsNone(tune_judge.allowlist_proposal(approved(heads, 9), [], 3))

    def test_malformed_tool_use_ids_do_not_crash(self):
        g = [G(head="jq", tool_use_id=["x"]), G(head="jq", tool_use_id={"a": 1}), "junk", None]
        o = [{"tool_use_id": ["x"]}, {"tool_use_id": "y"}, 7]
        self.assertEqual(tune_judge.approved_asks(g, o), {})


class TuneTasksMalformedTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {"JEV_THRESHOLDS": os.path.join(tempfile.mkdtemp(), "missing.json")})
        p.start()
        self.addCleanup(p.stop)

    def test_list_valued_task_is_skipped_in_every_loop(self):
        bad = ["t1"]
        dispatch = [{"task": "t1", "role": "coder", "tier": "sonnet", "attempt": 1, "ts": "2026-10-01T00:00:00"},
                    {"task": bad, "role": "coder", "tier": "sonnet", "attempt": 1},
                    {"task": bad, "phase": "return", "lines": 4, "tokens": 9},
                    {"task": "t1", "phase": "return", "role": "coder", "attempt": 1, "lines": 3, "tokens": 5}]
        esc = [{"task": bad, "reason": "x"}]
        mcp = [{"tool": "task_review", "task": bad, "score": 0.5, "score_tier": "sonnet"}]
        gate_rows = [{"task": bad, "tool": "Edit", "decision": "ask"}, {"task": "t1", "tasks": [bad, 3]}]
        review = [{"task": bad, "critical": 1}]
        rows = tune_tasks.rows(gate_rows, dispatch, esc, mcp)
        self.assertEqual(list(rows), ["t1"])
        self.assertEqual(rows["t1"]["lines"], 3)
        s = tune_tasks.summary(rows, gate_rows, review, thresholds.load())
        self.assertEqual(s["tasks"], 1)
        tune_tasks.lines(s)


class GateOutcomeInprocTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.logs = os.path.join(self.tmp, "logs")
        th = os.path.join(self.tmp, "thresholds.json")
        with open(th, "w", encoding="utf-8") as f:
            json.dump({"judge": {"provider": "local", "shadow": "none"}}, f)
        p = mock.patch.dict(os.environ, {"JEV_LOG_DIR": self.logs, "JEV_SSD_ROOT": self.tmp, "JEV_THRESHOLDS": th,
                                         "JEV_CHAIN_LOCAL": os.path.join(self.tmp, "none.json")})
        p.start()
        self.addCleanup(p.stop)
        p2 = mock.patch.dict(os.environ)
        p2.start()
        os.environ.pop("JEV_CHAIN_CONFIG", None)
        self.addCleanup(p2.stop)

    def outcomes(self):
        try:
            with open(os.path.join(self.logs, "outcomes.jsonl"), encoding="utf-8") as f:
                return [json.loads(l) for l in f]
        except OSError:
            return []

    def post(self, tid, failed=False):
        ev = {"hook_event_name": "PostToolUseFailure" if failed else "PostToolUse", "tool_name": "Bash",
              "tool_use_id": tid, "tool_input": {"command": "x"}}
        with mock.patch.object(chain.subprocess, "run") as run:
            chain.observe(ev, json.dumps(ev), chain.load_stages("post"))
        return run

    def test_chain_json_stage_is_inproc_on_claude_and_opencode_not_codex(self):
        with open(os.path.join(HERE, "chain.json"), encoding="utf-8") as f:
            st = [s for s in json.load(f)["post"] if s["name"] == "gate-outcome"][0]
        self.assertEqual(st.get("inproc"), "gate_outcome")
        self.assertEqual(st["harness"], ["claude", "opencode"])
        self.assertNotIn("codex", st["harness"])

    def test_bash_call_without_prior_ask_writes_nothing_and_spawns_nothing(self):
        run = self.post("t1")
        run.assert_not_called()
        self.assertEqual(self.outcomes(), [])

    def test_ask_then_ran_logs_once(self):
        gate.run({"tool_name": "Bash", "tool_use_id": "t7", "tool_input": {"command": "git push --force origin x"}})
        with open(os.path.join(self.logs, "asks_pending.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), ["t7"])
        self.post("t7").assert_not_called()
        self.post("t7")
        self.assertEqual([(r["tool_use_id"], r["tool"]) for r in self.outcomes()], [("t7", "Bash")])

    def test_refused_ask_is_dropped_unlogged(self):
        gate_outcome.note_ask("t8")
        self.post("t8", failed=True)
        self.post("t8")
        self.assertEqual(self.outcomes(), [])

    def test_skipped_command_is_not_pending(self):
        gate.run({"tool_name": "Bash", "tool_use_id": "t9", "tool_input": {"command": "ls"}})
        self.assertFalse(os.path.exists(os.path.join(self.logs, "asks_pending.json")))

    def test_pending_is_bounded(self):
        for i in range(250):
            gate_outcome.note_ask("id%d" % i)
        with open(os.path.join(self.logs, "asks_pending.json"), encoding="utf-8") as f:
            ids = json.load(f)
        self.assertEqual(len(ids), gate_outcome.MAX_PENDING)
        self.assertEqual(ids[-1], "id249")
        self.assertNotIn("id0", ids)

    def test_record_never_raises_or_prints(self):
        with open(os.path.join(self.tmp, "x"), "w"):
            pass
        os.makedirs(self.logs, exist_ok=True)
        with open(os.path.join(self.logs, "asks_pending.json"), "w", encoding="utf-8") as f:
            f.write("{not json")
        with mock.patch("sys.stdout") as out:
            for ev in (None, [], {"tool_use_id": ["x"]}, {"tool_use_id": "q"}):
                gate_outcome.record(ev)
            gate_outcome.note_ask("q")
        out.write.assert_not_called()
        self.assertEqual(self.outcomes(), [])

    def test_chain_swallows_inproc_errors(self):
        with mock.patch.object(gate_outcome, "record", side_effect=RuntimeError("boom")):
            self.post("t1").assert_not_called()


if __name__ == "__main__":
    unittest.main()
