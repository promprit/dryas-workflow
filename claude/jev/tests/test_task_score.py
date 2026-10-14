import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import task_review
import task_score as ts
import thresholds

TH = {"history": {"min_tasks": 3}}
SECTION = ("## Task 2: tidy\nGoal: g\nScope:\n- src/app.py\n- src/util/**\nDone:\n"
           "- `python3 -m pytest -q tests` passes\nFailing test first: tests/test_app.py :: T :: t\n")


class ScoreTest(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp())
        self.logs = os.path.join(self.root, "logs")
        os.makedirs(self.logs)
        p = mock.patch.dict(os.environ, {"JEV_LOG_DIR": self.logs,
                                         "JEV_THRESHOLDS": os.path.join(self.root, "t.json")})
        p.start()
        self.addCleanup(p.stop)
        self.put("src/app.py", 250)
        self.put("src/util/a.py", 120)
        self.put("src/util/b.py", 30)
        self.put("src/other.py", 999)
        self.put("node_modules/x/src/util/c.py", 999)

    def put(self, rel, n):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("x\n" * n)

    def log(self, name, recs):
        with open(os.path.join(self.logs, name + ".jsonl"), "a") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")

    def test_size_counts_files_and_lines_in_scope_only(self):
        self.assertEqual(ts.scope_size(self.root, ["src/app.py", "src/util/**"]), (3, 400, False))
        self.assertEqual(ts.scope_size(self.root, ["src/new.py"]), (1, 0, False))

    def test_done_check_runs_a_test(self):
        self.assertTrue(ts.runs_test(SECTION))
        self.assertFalse(ts.runs_test("## Task 1: d\nScope:\n- a.md\nDone:\n- the page reads well\n"))

    def test_task_type(self):
        self.assertEqual(ts.task_type(["docs/x.md", "README.md"]), "docs")
        self.assertEqual(ts.task_type(["src/a.py", "tests/test_a.py"]), "code+tests")
        self.assertEqual(ts.task_type([]), "none")

    def test_score_table(self):
        rows = [((1, 50, ["plain"], True, None), {"size": 3, "risk": 0, "tests": 0, "history": 0, "total": 3}),
                ((4, 900, ["plain", "plain"], False, None), {"size": 21, "risk": 0, "tests": 15, "history": 0, "total": 36}),
                ((1, 10, ["always", "plain"], True, None), {"size": 3, "risk": 20, "tests": 0, "history": 0, "total": 23}),
                ((30, 9000, ["always"], False, 1.0), {"size": 50, "risk": 20, "tests": 15, "history": 30, "total": 100}),
                ((2, 0, ["plain"], True, 0.5), {"size": 6, "risk": 0, "tests": 0, "history": 15, "total": 21})]
        for args, want in rows:
            self.assertEqual(ts.score(*args), want, args)

    def test_tiers_and_buckets(self):
        self.assertEqual([ts.tier(s) for s in (0, 29, 30, 59, 60, 100)],
                         ["haiku", "haiku", "sonnet", "sonnet", "opus", "opus"])
        self.assertEqual([ts.bucket(s) for s in (5, 45, 75)], ["0-29", "30-59", "60-100"])

    def test_history_counts_only_after_min_tasks(self):
        self.log("dispatch", [{"task": "b:%d" % i, "tier": "sonnet", "role": "coder", "attempt": 1} for i in range(4)])
        self.log("mcp", [{"tool": "task_review", "task": "b:%d" % i, "task_type": "code+tests"} for i in range(2)])
        self.log("escalations", [{"task": "b:0", "reason": "failed twice", "from_model": "sonnet", "to_model": "opus"}])
        self.assertIsNone(ts.history("code+tests", 3, self.logs))
        self.log("mcp", [{"tool": "task_review", "task": "b:2", "task_type": "code+tests"},
                         {"tool": "task_review", "task": "b:3", "task_type": "docs"}])
        self.log("escalations", [{"task": "b:1", "reason": "skip-up: wide", "from_model": "haiku", "to_model": "sonnet"}])
        self.assertAlmostEqual(ts.history("code+tests", 3, self.logs), 1 / 3)

    def test_answer_combines_signals(self):
        a = ts.answer(self.root, SECTION, "b:2", TH, self.logs)
        self.assertEqual((a["files"], a["lines"], a["task_type"]), (3, 400, "code"))
        self.assertEqual(a["parts"], {"size": 13, "risk": 0, "tests": 0, "history": 0, "total": 13, "truncated": False})
        self.assertEqual((a["score"], a["tier"]), (13, "haiku"))
        self.assertEqual((a["skip"], a["review"]), (["src/app.py"], ["src/util/**"]))

    def test_answer_reads_history_min_tasks_from_thresholds(self):
        self.log("dispatch", [{"task": "b:%d" % i, "tier": "sonnet"} for i in range(2)])
        self.log("mcp", [{"tool": "task_review", "task": "b:%d" % i, "task_type": "code"} for i in range(2)])
        self.log("escalations", [{"task": "b:0", "reason": "failed twice"}])
        base = ts.answer(self.root, SECTION, "b:2", thresholds.load(), self.logs)
        self.assertIsNone(base["history"])
        seen = ts.answer(self.root, SECTION, "b:2", {"history": {"min_tasks": 2}}, self.logs)
        self.assertEqual(seen["history"], 0.5)
        self.assertEqual(seen["parts"]["history"], 15)
        self.assertEqual(seen["score"], base["score"] + 15)

    def test_answer_wires_risk_and_tier_end_to_end(self):
        self.put("package.json", 1)
        for i in range(5):
            self.put("src/big/f%d.py" % i, 100)
        sec = ("## Task 3: wide\nGoal: g\nScope:\n- package.json\n- src/big/**\nDone:\n"
               "- `python3 -m pytest -q tests` passes\n")
        a = ts.answer(self.root, sec, "b:3", {"history": {"min_tasks": 3}}, self.logs)
        self.assertGreater(a["parts"]["risk"], 0)
        self.assertEqual(a["parts"]["total"], 43)
        self.assertEqual(a["tier"], ts.tier(a["parts"]["total"]))
        self.assertEqual(a["tier"], "sonnet")

    def test_runs_test_recognises_commands_not_prose(self):
        for cmd in ("python3 -m pytest -q x", "pnpm test", "npm test", "swift test", "go test ./..."):
            sec = "## Task 1: d\nScope:\n- a.py\nDone:\n- `%s` passes\n" % cmd
            self.assertTrue(ts.runs_test(sec), cmd)
        for line in ("docs describe the test plan", "`ls -la` lists the files"):
            sec = "## Task 1: d\nScope:\n- a.md\nDone:\n- %s\n" % line
            self.assertFalse(ts.runs_test(sec), line)

    def test_task_type_tests_only_and_mixed_docs_code(self):
        self.assertEqual(ts.task_type(["tests/test_a.py", "tests/test_b.py"]), "tests")
        self.assertEqual(ts.task_type(["docs/x.md", "src/a.py"]), "code+docs")

    def test_history_counts_only_tasks_that_were_dispatched(self):
        # A task_review answer for a task that never ran (asked, then abandoned) is not history.
        self.log("mcp", [{"tool": "task_review", "task": "b:%d" % i, "task_type": "code"} for i in range(4)])
        self.log("dispatch", [{"task": "b:0", "tier": "sonnet"}, {"task": "b:1", "tier": "sonnet", "phase": "return"}])
        self.log("escalations", [{"task": "b:0", "reason": "failed twice"}, {"task": "b:3", "reason": "failed"}])
        self.assertIsNone(ts.history("code", 3, self.logs))
        self.assertEqual(ts.history("code", 2, self.logs), 0.5)

    def test_test_words_match_whole_words(self):
        for line, want in (("the toxicity check passes", False), ("`tox -e py` passes", True),
                           ("pytester notes are tidy", False), ("`make test` passes", True),
                           ("make testing docs", False), ("`go test ./...` passes", True)):
            sec = "## Task 1: d\nScope:\n- a.py\nDone:\n- %s\n" % line
            self.assertEqual(ts.runs_test(sec), want, line)

    def test_task_type_tests_by_path_parts_not_substring(self):
        for globs, want in ((["src/contest.py"], "code"), (["src/latest/**"], "code"), (["src/testing/x.py"], "code"),
                            (["tests/**"], "tests"), (["pkg/test/x.go"], "tests"), (["src/test_a.py"], "tests"),
                            (["pkg/foo_test.go"], "tests"), (["**/test_*.py"], "tests"), (["src/attest_x.py"], "code")):
            self.assertEqual(ts.task_type(globs), want, globs)

    def test_scope_size_walks_only_the_literal_prefix(self):
        for i in range(20):
            self.put("elsewhere/f%02d.py" % i, 1)
        with mock.patch.object(ts, "MAX_FILES", 5):
            self.assertEqual(ts.scope_size(self.root, ["src/app.py", "src/util/**"]), (3, 400, False))
            self.assertEqual(ts.scope_size(self.root, ["elsewhere/*.py"])[2], True)

    def test_truncated_walk_is_reported_in_parts(self):
        for i in range(8):
            self.put("src/util/z%d.py" % i, 1)
        with mock.patch.object(ts, "MAX_FILES", 5):
            a = ts.answer(self.root, SECTION, "b:2", TH, self.logs)
        self.assertIs(a["parts"]["truncated"], True)
        self.assertIs(ts.answer(self.root, SECTION, "b:2", TH, self.logs)["parts"]["truncated"], False)

    def test_scope_never_leaves_the_root(self):
        self.assertEqual(ts.scope_size(os.path.join(self.root, "src", "util"), ["../app.py", "/etc/hosts", "../*.py"]),
                         (0, 0, False))


class CliTest(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp())
        os.makedirs(os.path.join(self.root, ".orchestrate"))
        os.makedirs(os.path.join(self.root, ".git"))
        with open(os.path.join(self.root, ".git", "HEAD"), "w") as f:
            f.write("ref: refs/heads/feat/x\n")
        self.plan = os.path.join(self.root, ".orchestrate", "PLAN.md")
        with open(self.plan, "w") as f:
            f.write(SECTION)
        self.logs = os.path.join(self.root, "logs")
        p = mock.patch.dict(os.environ, {"JEV_LOG_DIR": self.logs, "JEV_THRESHOLDS": os.path.join(self.root, "t.json")})
        p.start()
        self.addCleanup(p.stop)

    def test_answer_prints_entry_and_logs_verdict(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(task_review.main(["task_review.py", "answer", self.plan, "2"]), 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["task"], "feat/x:2")
        self.assertEqual(out["review_version"], 1)
        self.assertEqual(out["entry"], {"skip": ["src/app.py"], "review": ["src/util/**"], "tier": "haiku", "score": 3})
        self.assertEqual(out["log_dispatch"], {"score": 3, "score_tier": "haiku", "task_type": "code"})
        with open(os.path.join(self.logs, "mcp.jsonl")) as f:
            rec = json.loads(f.readline())
        self.assertEqual((rec["tool"], rec["question"], rec["provider"], rec["task"], rec["task_type"]),
                         ("task_review", "task_review", "local", "feat/x:2", "code"))
        self.assertEqual(rec["answer"], {"skip": 1, "review": 1, "tier": "haiku"})
        self.assertIn("wall_ms", rec)

    def test_entry_round_trips_through_active_json(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            task_review.main(["task_review.py", "answer", self.plan, "2"])
        out = json.loads(buf.getvalue())
        with open(os.path.join(self.root, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": ["2"], "review_version": out["review_version"], "review": {"2": out["entry"]}}, f)
        self.assertEqual(task_review.edit_verdict(self.root, "Write", {"file_path": "src/app.py", "content": "x = 1\n"}),
                         ("skip", "task_review"))

    def test_usage_and_missing_task(self):
        self.assertEqual(task_review.main(["task_review.py"]), 2)
        self.assertEqual(task_review.main(["task_review.py", "answer", self.plan, "9"]), 1)
        self.assertEqual(task_review.main(["task_review.py", "answer", self.plan + ".nope", "2"]), 1)

    def _mcp_lines(self):
        try:
            with open(os.path.join(self.logs, "mcp.jsonl")) as f:
                return [json.loads(x) for x in f if x.strip()]
        except OSError:
            return []

    def test_success_logs_exactly_one_verdict_record(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(task_review.main(["task_review.py", "answer", self.plan, "2"]), 0)
        recs = self._mcp_lines()
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual((r["score"], r["score_tier"], r["confidence"], r["shadow_provider"]), (3, "haiku", 1.0, "none"))
        self.assertTrue(r["reasons"])
        self.assertIn("size:3", r["reasons"])

    def test_failures_log_nothing(self):
        err = io.StringIO()
        with mock.patch.object(sys, "stderr", err):
            self.assertEqual(task_review.main(["task_review.py"]), 2)
            self.assertEqual(task_review.main(["task_review.py", "answer", self.plan, "9"]), 1)
            self.assertEqual(task_review.main(["task_review.py", "answer", self.plan + ".nope", "2"]), 1)
        self.assertEqual(self._mcp_lines(), [])


if __name__ == "__main__":
    unittest.main()
