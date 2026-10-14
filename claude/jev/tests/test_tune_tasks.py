import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tune_tasks as tt

TH = {"review": {"task_skip": False, "min_tasks": 2, "max_false_skip_rate": 0.01},
      "dispatch": {"scored_tier": False, "min_tasks": 2}}


def d(task, tier, role="coder", attempt=1, **kw):
    return dict({"task": task, "tier": tier, "role": role, "attempt": attempt}, **kw)


DISPATCH = [
    d("b:1", "haiku", "tester", 1, tokens=1000, duration_ms=10000, ts="2026-10-01T10:00:00+0700"),
    d("b:1", "sonnet", "coder", 2, tokens=5000, duration_ms=60000, score=45, score_tier="sonnet"),
    d("b:2", "haiku", tokens=2000, duration_ms=20000, score=10, score_tier="haiku", ts="2026-10-02T10:00:00+0700"),
    d("b:2", "sonnet", attempt=2, tokens=6000, duration_ms=50000),
    d("b:3", "sonnet", tokens=4000, duration_ms=40000, score=70, score_tier="opus"),
]
ESC = [{"task": "b:1", "reason": "skip-up: wide", "from_model": "haiku", "to_model": "sonnet"},
       {"task": "b:2", "reason": "failed done", "from_model": "haiku", "to_model": "sonnet"}]
GATE = [
    {"tool": "Bash", "decision": "none", "provider": "jev", "task": "b:1", "latency_ms": 300, "cost": 0.001},
    {"tool": "Write", "decision": "ask", "provider": "jev", "task": "b:1", "latency_ms": 200, "cost": 0.001,
     "task_review": "skip", "false_skip": True},
    {"tool": "Edit", "decision": "none", "provider": "local", "tasks": ["b:2", "b:3"], "local_ms": 2.0,
     "shadow_provider": "jev", "shadow_decision": "none", "shadow_cost": 0.002, "task_review": "skip",
     "false_skip": False},
    {"tool": "Edit", "decision": "skipped", "via": "local_file", "task": "b:3"},
    {"tool": "Write", "decision": "deny", "provider": "local", "task": "b:9", "local_ms": 1.0},
    "not a record",
]
MCP = [{"tool": "task_review", "task": "b:3", "score": 5, "score_tier": "haiku"}]
REVIEW = [{"task": "b", "round": 1, "critical": 1, "important": 2, "minor": 0},
          {"task": "b", "round": 2, "critical": 0, "important": 0, "minor": 1},
          {"task": "c", "round": 1, "critical": 0, "important": 0, "minor": 0}]


class TuneTasksTest(unittest.TestCase):
    def setUp(self):
        self.rows = tt.rows(GATE, DISPATCH, ESC, MCP)
        self.s = tt.summary(self.rows, GATE, REVIEW)

    def test_rows_per_task(self):
        r1, r2, r3 = self.rows["b:1"], self.rows["b:2"], self.rows["b:3"]
        self.assertEqual((r1["start_tier"], r1["final_tier"], r1["tokens"], r1["duration_ms"]), ("sonnet", "sonnet", 6000, 70000))
        self.assertEqual((r1["jev_calls"], r1["gate_wait_ms"], r1["escalated"]), (2, 500, False))
        self.assertAlmostEqual(r1["judge_spend"], 0.002)
        self.assertEqual((r2["start_tier"], r2["final_tier"], r2["wasted_tokens"], r2["escalated"]), ("haiku", "sonnet", 2000, True))
        self.assertEqual((r2["jev_calls"], r2["gate_wait_ms"], r2["would_skip"], r2["false_skips"]), (1, 2.0, 1, 0))
        self.assertEqual((r3["score"], r3["score_tier"]), (70, "opus"))  # the dispatch record wins over the mcp record
        self.assertEqual(r1["first_ts"], "2026-10-01T10:00:00+0700")
        self.assertNotIn("b:9", self.rows)

    def test_summary(self):
        s = self.s
        self.assertEqual(s["per_task"]["tokens"], 6000)
        self.assertEqual(s["by_tier"]["haiku"], {"tasks": 1, "tokens_median": 8000.0, "tokens_p90": 8000.0,
                                                 "duration_ms_median": 70000.0, "duration_ms_p90": 70000.0})
        self.assertEqual(s["wasted_tokens"], 2000)
        self.assertEqual((s["edits"], s["deny_per_edit"], s["ask_per_edit"]), (4, 0.25, 0.25))
        self.assertEqual(s["escalation_rate"], round(1 / 3, 4))
        self.assertEqual(s["review_findings_median"], 2.0)
        self.assertEqual(s["score_buckets"], {"0-29": {"tasks": 1, "escalated": 1}, "30-59": {"tasks": 1, "escalated": 0},
                                              "60-100": {"tasks": 1, "escalated": 0}})
        self.assertEqual((s["score_accuracy"], s["tier_accuracy"]), (round(1 / 3, 4), round(2 / 3, 4)))
        self.assertEqual((s["review_tasks"], s["would_skip_edits"], s["false_skip_tasks"], s["false_skip_rate"]),
                         (3, 3, 1, round(1 / 3, 4)))

    def test_p90_is_nearest_rank(self):
        self.assertEqual(tt._p90([float(i) for i in range(1, 11)]), 9.0)
        self.assertEqual(tt._p90([5.0]), 5.0)
        self.assertIsNone(tt._p90([]))

    def test_lines_render_every_metric(self):
        text = "\n".join(tt.lines(self.s))
        for part in ("- Per task (median over 3 tasks): executor tokens 6000", "- Start tier haiku (1 tasks)",
                     "- Tokens of failed attempts (escalation waste): 2000", "- Edits: deny rate 25.0%, ask rate 25.0% (4 edits)",
                     "- Escalation rate per task (skip-ups excluded): 33.3%", "- Review findings per reviewed branch (median): 2.0",
                     "- Score buckets (tasks, escalated): 0-29 1/1", "- Task review: 3 tasks, 3 would-skip edits, false-skip tasks 1"):
            self.assertIn(part, text)

    def test_empty_logs(self):
        s = tt.summary(tt.rows([], [], [], []), [], [])
        self.assertEqual((s["tasks"], s["escalation_rate"], s["false_skip_rate"]), (0, None, None))
        self.assertTrue(all("n/a" in l or "none" in l or ": 0" in l or "0 tasks" in l for l in tt.lines(s)))
        self.assertEqual(tt.proposals(s, TH), [])

    def test_task_skip_proposed_only_on_evidence_and_reversible(self):
        s = dict(self.s, review_tasks=100, false_skip_rate=0.0)
        self.assertEqual([(p["key"], p["new"]) for p in tt.proposals(s, TH)], [("review.task_skip", True)])
        on = dict(TH, review=dict(TH["review"], task_skip=True))
        self.assertEqual([(p["key"], p["new"]) for p in tt.proposals(dict(s, false_skip_rate=0.05), on)],
                         [("review.task_skip", False)])
        self.assertEqual(tt.proposals(dict(s, review_tasks=1), TH), [])

    def test_scored_tier_proposed_when_score_predicts_better(self):
        s = dict(self.s, review_tasks=0, scored_tasks=60, score_accuracy=0.8, tier_accuracy=0.6)
        self.assertEqual([(p["key"], p["new"]) for p in tt.proposals(s, TH)], [("dispatch.scored_tier", True)])
        self.assertEqual(tt.proposals(dict(s, score_accuracy=0.5), TH), [])
        on = dict(TH, dispatch=dict(TH["dispatch"], scored_tier=True))
        self.assertEqual([(p["key"], p["new"]) for p in tt.proposals(dict(s, score_accuracy=0.5), on)],
                         [("dispatch.scored_tier", False)])


def _many(n, bad):
    """n dispatched tasks, each with one skip edit; the first `bad` tasks had a false skip."""
    dsp = [d("t:%d" % i, "sonnet", tokens=100, duration_ms=10) for i in range(n)]
    gate = [{"tool": "Edit", "decision": "none", "task": "t:%d" % i, "task_review": "skip", "false_skip": i < bad}
            for i in range(n)]
    return tt.summary(tt.rows(gate, dsp, [], []), gate, [])


class TuneTasksEdgeTest(unittest.TestCase):
    def test_task_skip_needs_rate_under_limit_over_enough_tasks(self):
        over = _many(200, 10)  # 5% > 1%
        self.assertEqual(over["review_tasks"], 200)
        self.assertEqual(tt.proposals(over, TH), [])
        ok = _many(200, 1)  # 0.5% <= 1%
        self.assertEqual([(p["key"], p["new"]) for p in tt.proposals(ok, TH)], [("review.task_skip", True)])
        at = _many(100, 1)  # exactly 1%
        self.assertEqual([(p["key"], p["new"]) for p in tt.proposals(at, TH)], [("review.task_skip", True)])

    def test_scored_tier_needs_min_tasks(self):
        s = dict(self.base(), scored_tasks=1, score_accuracy=0.9, tier_accuracy=0.1)
        self.assertEqual(tt.proposals(s, TH), [])
        s["scored_tasks"] = 2
        self.assertEqual([p["key"] for p in tt.proposals(s, TH)], ["dispatch.scored_tier"])

    def base(self):
        return dict(tt.summary({}, [], []))

    def test_zero_denominators_with_tasks(self):
        dsp = [d("z:1", "sonnet")]  # no tokens, no edits, no review records, no escalations
        s = tt.summary(tt.rows([], dsp, [], []), [], [])
        self.assertEqual((s["tasks"], s["edits"], s["review_tasks"]), (1, 0, 0))
        self.assertEqual((s["deny_per_edit"], s["ask_per_edit"], s["false_skip_rate"], s["score_accuracy"]),
                         (None, None, None, None))
        self.assertEqual(s["escalation_rate"], 0.0)
        text = "\n".join(tt.lines(s))
        self.assertIn("deny rate n/a, ask rate n/a", text)
        self.assertIn("executor tokens n/a", text)
        self.assertEqual(tt.proposals(s, TH), [])

    def test_malformed_records_skipped_without_corrupting_rows(self):
        junk = ["x", 7, None, [1, 2], {"task": ["a"], "tier": ["haiku"], "tokens": "many", "duration_ms": "slow"},
                {"task": "b:1", "tier": {"x": 1}, "role": ["coder"], "tokens": "NaN", "duration_ms": -5,
                 "score": "high", "score_tier": ["opus"], "ts": 5},
                {"tasks": "b:1", "tool": ["Edit"], "task_review": ["skip"], "latency_ms": "x", "cost": "free"},
                {"task": 3, "reason": None}, {"tool": "task_review", "task": ["b:1"], "score": "x"}]
        clean = tt.rows(GATE, DISPATCH, ESC, MCP)
        rows = tt.rows(GATE + junk, DISPATCH + junk, ESC + junk, MCP + junk)
        self.assertEqual(rows["b:1"]["tokens"], clean["b:1"]["tokens"])
        for t in ("b:2", "b:3"):
            self.assertEqual(rows[t], clean[t])
        self.assertEqual(rows["b:1"]["start_tier"], "sonnet")
        s = tt.summary(rows, GATE + junk, REVIEW + junk + [{"task": "b", "critical": "many"}])
        self.assertEqual((s["edits"], s["tasks"]), (4, 3))
        self.assertTrue(tt.lines(s))

    def test_p90_of_several_tasks_is_not_max(self):
        dsp = [d("p:%d" % i, "haiku", tokens=100 * (i + 1), duration_ms=1000 * (i + 1)) for i in range(10)]
        dsp.append(d("p:10", "haiku", tokens=100000, duration_ms=1000000))
        s = tt.summary(tt.rows([], dsp, [], []), [], [])
        # 11 tasks: nearest rank ceil(0.9*11)=10 -> the 10th smallest, not the 100000 outlier
        self.assertEqual(s["by_tier"]["haiku"]["tokens_p90"], 1000.0)
        self.assertEqual(s["by_tier"]["haiku"]["duration_ms_p90"], 10000.0)


if __name__ == "__main__":
    unittest.main()
