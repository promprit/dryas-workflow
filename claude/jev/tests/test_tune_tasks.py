import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import task_score
import tune
import tune_tasks as tt

TH = {"review": {"task_skip": False, "min_tasks": 2, "max_false_skip_rate": 0.01},
      "dispatch": {"scored_tier": False, "min_tasks": 2}}


def th(**kw):
    out = {k: dict(v) for k, v in TH.items()}
    for key, value in kw.items():
        section, name = key.split("__")
        out[section][name] = value
    return out


def d(task, tier, role="coder", attempt=1, **kw):
    return dict({"task": task, "tier": tier, "role": role, "attempt": attempt}, **kw)


DISPATCH = [
    d("b:1", "haiku", "tester", 1, tokens=1000, duration_ms=10000, ts="2026-10-01T10:00:00+0700"),
    d("b:1", "sonnet", "coder", 2, tokens=5000, duration_ms=60000, score=45, score_tier="sonnet", task_type="code"),
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
MCP = [{"tool": "task_review", "task": "b:3", "score": 5, "score_tier": "haiku", "task_type": "docs"}]
REVIEW = [{"task": "b", "round": 1, "critical": 1, "important": 2, "minor": 0},
          {"task": "b", "round": 2, "critical": 0, "important": 0, "minor": 1},
          {"task": "c", "round": 1, "critical": 0, "important": 0, "minor": 0}]


class TuneTasksTest(unittest.TestCase):
    def setUp(self):
        self.rows = tt.rows(GATE, DISPATCH, ESC, MCP)
        self.s = tt.summary(self.rows, GATE, REVIEW, TH)

    def test_rows_per_task(self):
        r1, r2, r3 = self.rows["b:1"], self.rows["b:2"], self.rows["b:3"]
        self.assertEqual((r1["start_tier"], r1["final_tier"], r1["tokens"], r1["duration_ms"]), ("sonnet", "sonnet", 6000, 70000))
        self.assertEqual((r1["jev_calls"], r1["gate_wait_ms"], r1["escalated"]), (2, 500, False))
        self.assertAlmostEqual(r1["judge_spend"], 0.002)
        self.assertEqual((r2["start_tier"], r2["final_tier"], r2["wasted_tokens"], r2["escalated"]), ("haiku", "sonnet", 2000, True))
        self.assertEqual((r2["jev_calls"], r2["gate_wait_ms"]), (1, 2.0))
        self.assertEqual((r3["score"], r3["score_tier"]), (70, "opus"))  # the dispatch record wins over the mcp record
        self.assertEqual((r1["task_type"], r2["task_type"], r3["task_type"]), ("code", None, "docs"))
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
        self.assertEqual(s["score_starts"], {"tasks": 2, "escalation_rate": 0.5, "tokens_median": 7000.0})
        self.assertEqual(s["question_starts"], {"tasks": 1, "escalation_rate": 0.0, "tokens_median": 4000.0})
        self.assertEqual((s["scored_tasks"], s["shadow_helps"], s["shadow_hurts"]), (3, 0, 1))
        self.assertEqual((s["skip_tasks"], s["skip_edits"], s["false_skips"], s["false_skip_rate"]), (3, 2, 1, 0.5))

    def test_p90_is_nearest_rank(self):
        self.assertEqual(tt._p90([float(i) for i in range(1, 11)]), 9.0)
        self.assertEqual(tt._p90([5.0]), 5.0)
        self.assertIsNone(tt._p90([]))

    def test_lines_render_every_metric(self):
        text = "\n".join(tt.lines(self.s))
        for part in ("- Per task (median over 3 tasks): executor tokens 6000", "- Start tier haiku (1 tasks)",
                     "- Tokens of failed attempts (escalation waste): 2000", "- Edits: deny rate 25.0%, ask rate 25.0% (4 edits)",
                     "- Escalation rate per task (skip-ups excluded): 33.3%", "- Review findings per reviewed branch (median): 2.0",
                     "- Score buckets (tasks, escalated): 0-29 1/1",
                     "- Start tier from the score: 2 tasks, escalation 50.0%, tokens median 7000; from the tier questions: "
                     "1 tasks, escalation 0.0%, tokens median 4000",
                     "- Score in shadow (3 scored tasks): would help 0, would hurt 1 (ON needs helps >= 2 x hurts and helps >= 1)",
                     "- Task review: false-skip rate 50.0% (1 of 2 judged would-skip edits, 3 tasks), enforced skips 0, "
                     "would-skip edits 2"):
            self.assertIn(part, text)

    def test_empty_logs(self):
        s = tt.summary(tt.rows([], [], [], []), [], [], TH)
        self.assertEqual((s["tasks"], s["escalation_rate"], s["false_skip_rate"]), (0, None, None))
        self.assertTrue(all("n/a" in l or "none" in l or ": 0" in l or "0 tasks" in l or "0 scored tasks" in l or "no evidence" in l
                            for l in tt.lines(s)))
        self.assertEqual(tt.proposals(s, TH), [])


def skip_edit(task, false=False, ts="2026-10-01T10:00:00+0700", **kw):
    """A would-skip edit judged by Jev (the provider that can answer deny or ask on a file edit)."""
    return dict({"tool": "Edit", "decision": "ask" if false else "none", "provider": "jev", "latency_ms": 100,
                 "task": task, "task_review": "skip", "false_skip": false, "ts": ts}, **kw)


def summary(gate, n, th_=TH):
    dsp = [d("t:%d" % i, "sonnet", tokens=100, duration_ms=10) for i in range(n)]
    return tt.summary(tt.rows(gate, dsp, [], []), gate, [], th_)


def _many(n, bad):
    """n dispatched tasks, each with one judged would-skip edit; the first `bad` tasks had a false skip."""
    return summary([skip_edit("t:%d" % i, i < bad) for i in range(n)], n)


class EvidenceTest(unittest.TestCase):
    def test_no_would_skip_means_no_evidence(self):
        # 100 tasks whose edits all needed review: nothing was ever going to be skipped, so nothing shows the
        # skip is safe. The old rule counted them as 0% false skips and proposed turning the skip on.
        gate = [dict(skip_edit("t:%d" % i), task_review="review") for i in range(100)]
        s = summary(gate, 100)
        self.assertIsNone(s["false_skip_rate"])
        self.assertEqual(tt.proposals(s, TH), [])
        self.assertIn("no evidence", "\n".join(tt.lines(s)))

    def test_only_edits_jev_judged_are_evidence(self):
        gate = [dict(skip_edit("t:0"), provider="local", latency_ms=None),  # local alone cannot say deny/ask on edits
                dict(skip_edit("t:1"), provider="local", shadow_provider="jev", shadow_error="timeout"),
                {"tool": "Edit", "decision": "skipped", "via": "task_review", "task": "t:2", "task_review": "skip"},
                dict(skip_edit("t:3"), provider="local", shadow_provider="local", shadow_decision="none"),
                skip_edit("t:4"), dict(skip_edit("t:5", True), provider="local", shadow_provider="jev",
                                       shadow_decision="ask")]
        s = summary(gate, 6)
        self.assertEqual((s["skip_tasks"], s["skip_edits"], s["false_skips"], s["false_skip_rate"]), (2, 2, 1, 0.5))
        self.assertEqual(s["enforced_skips"], 1)

    def test_local_file_skips_are_population_not_evidence(self):
        # Task 14 shape: an edit local_file skips inside a task carries the task verdict but no judge answer.
        gate = [{"tool": "Edit", "decision": "skipped", "via": "local_file", "task": "t:%d" % i, "task_review": "skip",
                 "task_review_why": "plain", "ts": "2026-10-01T10:00:00+0700"} for i in range(100)]
        s = summary(gate, 100)
        self.assertEqual((s["would_skip_edits"], s["skip_edits"], s["skip_tasks"], s["false_skip_rate"]), (100, 0, 0, None))
        self.assertEqual(tt.proposals(s, TH), [])
        self.assertIn("- Task review: no evidence (0 tasks with judged would-skip edits, need 2), enforced skips 0, "
                      "would-skip edits 100", "\n".join(tt.lines(s)))

    def test_below_min_tasks_is_no_evidence_not_zero(self):
        s = summary([skip_edit("t:0"), skip_edit("t:0")], 1)
        self.assertEqual((s["skip_tasks"], s["skip_edits"], s["false_skip_rate"]), (1, 2, None))
        self.assertEqual(tt.proposals(s, TH), [])
        self.assertIn("Task review: no evidence (1 tasks with judged would-skip edits, need 2)", "\n".join(tt.lines(s)))

    def test_rate_is_false_skips_over_judged_would_skip_edits(self):
        s = summary([skip_edit("t:0"), skip_edit("t:0"), skip_edit("t:1", True), skip_edit("t:1")], 2)
        self.assertEqual(s["false_skip_rate"], 0.25)

    def test_task_skip_on_needs_rate_under_limit_over_enough_tasks(self):
        self.assertEqual(tt.proposals(_many(200, 10), TH), [])  # 5% > 1%
        for n, bad in ((200, 1), (100, 1)):  # 0.5% and exactly 1%
            self.assertEqual([(p["key"], p["new"]) for p in tt.proposals(_many(n, bad), TH)], [("review.task_skip", True)])

    def test_on_without_enforcement_yet_goes_off_on_rate(self):
        on = th(review__task_skip=True)
        self.assertEqual([(p["key"], p["new"]) for p in tt.proposals(_many(100, 5), on)], [("review.task_skip", False)])
        self.assertEqual(tt.proposals(_many(100, 1), on), [])

    def enforced(self, after_false):
        before = [skip_edit("t:%d" % i, i == 0, ts="2026-10-01T10:00:00+0700") for i in range(3)]
        skipped = [{"tool": "Edit", "decision": "skipped", "via": "task_review", "task": "t:%d" % i,
                    "task_review": "skip", "ts": "2026-10-0%dT10:00:00+0700" % (5 + i)} for i in range(3)]
        after = [skip_edit("t:1", after_false, ts="2026-10-09T10:00:00+0700")]
        return summary(before + skipped + after, 3, th(review__task_skip=True))

    def test_enforced_freezes_evidence_and_a_later_false_skip_turns_it_off(self):
        s = self.enforced(True)
        self.assertEqual((s["enforced_since"], s["frozen_rate"], s["frozen_tasks"], s["false_skips_since"]),
                         ("2026-10-05T10:00:00+0700", round(1 / 3, 4), 3, 1))
        self.assertIn("- Task review: enforced since 2026-10-05T10:00:00+0700; evidence frozen at 33.3% over 3 tasks; "
                      "false skips in judged edits since: 1; enforced skips 3", "\n".join(tt.lines(s)))
        on = th(review__task_skip=True)
        self.assertEqual([(p["key"], p["new"]) for p in tt.proposals(s, on)], [("review.task_skip", False)])

    def test_enforced_without_a_later_false_skip_proposes_nothing(self):
        s = self.enforced(False)
        self.assertEqual(s["false_skips_since"], 0)
        self.assertEqual(tt.proposals(s, th(review__task_skip=True)), [])

    def test_never_on_from_enforced_data(self):
        gate = [{"tool": "Edit", "decision": "skipped", "via": "task_review", "task": "t:%d" % i, "task_review": "skip",
                 "false_skip": False, "provider": "jev", "ts": "2026-10-05T10:00:00+0700"} for i in range(100)]
        s = summary(gate, 100)
        self.assertEqual((s["enforced_skips"], s["skip_tasks"], s["false_skip_rate"]), (100, 0, None))
        self.assertEqual(tt.proposals(s, TH), [])


def scored(task, start, score_tier, escalated, tokens=1000):
    return task, d(task, start, score=50, score_tier=score_tier, tokens=tokens), escalated


def scored_summary(cases):
    dsp = [c[1] for c in cases]
    esc = [{"task": c[0], "reason": "failed done", "from_model": "a", "to_model": "b"} for c in cases if c[2]]
    return tt.summary(tt.rows([], dsp, esc, []), [], [], TH)


class ScoredTierTest(unittest.TestCase):
    def test_starts_split_by_score_and_tier_questions(self):
        s = scored_summary([scored("a", "haiku", "haiku", True, 100), scored("b", "sonnet", "sonnet", False, 300),
                            scored("c", "sonnet", "haiku", False, 500), ("u", d("u", "opus", tokens=700), False)])
        self.assertEqual(s["score_starts"], {"tasks": 2, "escalation_rate": 0.5, "tokens_median": 200.0})
        self.assertEqual(s["question_starts"], {"tasks": 2, "escalation_rate": 0.0, "tokens_median": 600.0})

    def test_on_when_score_in_shadow_starts_lower_on_easy_and_higher_on_hard_tasks(self):
        s = scored_summary([scored("a", "sonnet", "haiku", False), scored("b", "sonnet", "opus", True),
                            scored("c", "sonnet", "haiku", True)])
        self.assertEqual((s["shadow_helps"], s["shadow_hurts"]), (2, 1))
        p = tt.proposals(s, TH)
        self.assertEqual([(x["key"], x["new"]) for x in p], [("dispatch.scored_tier", True)])
        self.assertIn("would have started lower on 1 tasks that did not escalate and higher on 1 that did", p[0]["why"])

    def test_no_on_when_score_in_shadow_hurts_as_often_as_it_helps(self):
        s = scored_summary([scored("a", "sonnet", "haiku", False), scored("b", "sonnet", "haiku", True),
                            scored("c", "sonnet", "opus", False), scored("d", "sonnet", "opus", True)])
        self.assertEqual((s["shadow_helps"], s["shadow_hurts"]), (2, 2))
        self.assertEqual(tt.proposals(s, TH), [])

    def test_on_needs_a_margin_helps_at_least_twice_hurts(self):
        three_two = scored_summary([scored("a", "sonnet", "haiku", False), scored("b", "sonnet", "haiku", False),
                                    scored("c", "sonnet", "opus", True), scored("d", "sonnet", "haiku", True),
                                    scored("e", "sonnet", "opus", False)])
        self.assertEqual((three_two["shadow_helps"], three_two["shadow_hurts"]), (3, 2))
        self.assertEqual(tt.proposals(three_two, TH), [])
        four_two = scored_summary([scored("a", "sonnet", "haiku", False), scored("b", "sonnet", "haiku", False),
                                   scored("c", "sonnet", "opus", True), scored("f", "sonnet", "opus", True),
                                   scored("d", "sonnet", "haiku", True), scored("e", "sonnet", "opus", False)])
        self.assertEqual((four_two["shadow_helps"], four_two["shadow_hurts"]), (4, 2))
        p = tt.proposals(four_two, TH)
        self.assertEqual([(x["key"], x["new"]) for x in p], [("dispatch.scored_tier", True)])
        self.assertIn("helps 4, hurts 2", p[0]["why"])

    def test_zero_helps_never_turns_on_even_with_zero_hurts(self):
        s = dict(scored_summary([scored("a", "sonnet", "sonnet", False), scored("b", "sonnet", "sonnet", False)]))
        s.update(scored_tasks=2, shadow_helps=0, shadow_hurts=0)
        self.assertEqual(tt.proposals(s, TH), [])

    def test_on_needs_min_scored_tasks(self):
        s = scored_summary([scored("a", "sonnet", "haiku", False)])
        self.assertEqual(tt.proposals(s, TH), [])
        self.assertEqual(tt.proposals(s, th(dispatch__min_tasks=1))[0]["new"], True)

    def test_off_when_scored_starts_escalate_more_than_question_starts(self):
        on = th(dispatch__scored_tier=True)
        worse = scored_summary([scored("a", "haiku", "haiku", True), scored("b", "haiku", "haiku", False),
                                scored("c", "sonnet", "haiku", False), scored("e", "opus", "sonnet", False)])
        self.assertEqual([(p["key"], p["new"]) for p in tt.proposals(worse, on)], [("dispatch.scored_tier", False)])
        same = scored_summary([scored("a", "haiku", "haiku", True), scored("b", "haiku", "haiku", False),
                               scored("c", "sonnet", "haiku", True), scored("e", "opus", "sonnet", False)])
        self.assertEqual(tt.proposals(same, on), [])
        few = scored_summary([scored("a", "haiku", "haiku", True), scored("b", "haiku", "haiku", False),
                              scored("c", "sonnet", "haiku", False)])  # one question start: no baseline
        self.assertEqual(tt.proposals(few, on), [])


class CodexTierTest(unittest.TestCase):
    def test_model_names_map_to_their_tier_and_unknown_names_are_skipped(self):
        for name, tier in (("claude-haiku-4-5", "haiku"), ("gpt-sonnet-x", "sonnet"), ("Opus-5", "opus"),
                           ("fable", "fable"), ("sonnet", "sonnet")):
            self.assertEqual(tt._tier(name), tier, name)
        for name in ("gpt-5-codex", "", None, 3, "o3"):
            self.assertIsNone(tt._tier(name), name)

    def test_codex_named_dispatch_lands_in_tier_stats(self):
        t = tt.tiers([d("x", "claude-haiku-4-5"), d("y", "gpt-5-codex")])
        self.assertEqual((t["x"]["start"], t["y"]["start"]), ("haiku", None))


class TiersTest(unittest.TestCase):
    def test_start_is_first_coder_else_first_attempt_one_final_is_highest(self):
        t = tt.tiers([d("x", "sonnet", "tester", 2), d("x", "haiku", "reviewer", 1),
                      d("y", "haiku", "tester", 1), d("y", "sonnet", "coder", 2), d("y", "opus", "coder", 3),
                      d("z", "haiku", attempt="1"), d("z", "fable", "coder", 1, phase="return")])
        self.assertEqual(t["x"], {"start": "haiku", "final": "sonnet", "attempt": 2})
        self.assertEqual(t["y"], {"start": "sonnet", "final": "opus", "attempt": 3})
        self.assertEqual(t["z"], {"start": "haiku", "final": "haiku", "attempt": 1})

    def test_rows_and_delivery_use_the_same_start_tier(self):
        dsp = [d("x", "sonnet", "tester", 2), d("x", "haiku", "reviewer", 1)]
        self.assertEqual(tt.rows([], dsp, [], [])["x"]["start_tier"], "haiku")
        self.assertEqual(tune.delivery(dsp, [], [], [], [])["haiku_tasks"], 1)

    def test_wasted_tokens_are_attempts_followed_by_a_higher_attempt_of_the_role(self):
        dsp = [d("w", "haiku", "coder", 1, tokens=100), d("w", "haiku", "reviewer", 1, tokens=10),
               d("w", "haiku", "reviewer", 1, tokens=20),  # two reviewers on one attempt: not a failed attempt
               d("w", "sonnet", "coder", 2, tokens=300), d("w", "sonnet", "tester", 3, tokens=40)]
        self.assertEqual(tt.rows([], dsp, [], [])["w"]["wasted_tokens"], 100)


class ReturnPhaseTest(unittest.TestCase):
    def test_usage_joins_from_return_records(self):
        dsp = [d("r", "haiku"), d("r", "haiku", phase="return", tokens=900, duration_ms=5000),
               d("r", "sonnet", attempt=2, tokens=50), d("r", "sonnet", attempt=2, phase="return", tokens=700)]
        row = tt.rows([], dsp, [], [])["r"]
        self.assertEqual((row["tokens"], row["duration_ms"], row["wasted_tokens"]), (1600, 5000, 900))

    def test_dispatch_counts_ignore_return_records(self):
        dsp = [d("a", "haiku"), d("a", "haiku", phase="return", tokens=10), d("b", "sonnet", phase="return", tokens=5)]
        self.assertEqual(sorted(tt.rows([], dsp, [], [])), ["a"])
        dl = tune.delivery(dsp, [{"task": "a"}], [], [], [])
        self.assertEqual((dl["tasks_dispatched"], dl["haiku_tasks"], dl["scope_per_task"]), (1, 1, 1.0))


class SharedScoreTablesTest(unittest.TestCase):
    def test_rank_and_buckets_come_from_task_score(self):
        self.assertIs(tt.RANK, task_score.RANK)
        self.assertIs(tt.bucket, task_score.bucket)


class TuneTasksEdgeTest(unittest.TestCase):
    def test_zero_denominators_with_tasks(self):
        dsp = [d("z:1", "sonnet")]  # no tokens, no edits, no review records, no escalations
        s = tt.summary(tt.rows([], dsp, [], []), [], [], TH)
        self.assertEqual((s["tasks"], s["edits"], s["skip_tasks"]), (1, 0, 0))
        self.assertEqual((s["deny_per_edit"], s["ask_per_edit"], s["false_skip_rate"]), (None, None, None))
        self.assertEqual(s["escalation_rate"], 0.0)
        text = "\n".join(tt.lines(s))
        self.assertIn("deny rate n/a, ask rate n/a", text)
        self.assertIn("executor tokens n/a", text)
        self.assertEqual(tt.proposals(s, TH), [])

    def test_malformed_records_skipped_without_corrupting_rows(self):
        junk = ["x", 7, None, [1, 2], {"task": ["a"], "tier": ["haiku"], "tokens": "many", "duration_ms": "slow"},
                {"task": "b:1", "tier": {"x": 1}, "role": ["coder"], "tokens": "NaN", "duration_ms": -5,
                 "score": "high", "score_tier": ["opus"], "ts": 5, "task_type": 3},
                {"tasks": "b:1", "tool": ["Edit"], "task_review": ["skip"], "latency_ms": "x", "cost": "free", "ts": 1},
                {"task": 3, "reason": None}, {"tool": "task_review", "task": ["b:1"], "score": "x"}]
        clean = tt.rows(GATE, DISPATCH, ESC, MCP)
        rows = tt.rows(GATE + junk, DISPATCH + junk, ESC + junk, MCP + junk)
        self.assertEqual(rows["b:1"]["tokens"], clean["b:1"]["tokens"])
        for t in ("b:2", "b:3"):
            self.assertEqual(rows[t], clean[t])
        self.assertEqual(rows["b:1"]["start_tier"], "sonnet")
        s = tt.summary(rows, GATE + junk, REVIEW + junk + [{"task": "b", "critical": "many"}], TH)
        self.assertEqual((s["edits"], s["tasks"]), (4, 3))
        self.assertTrue(tt.lines(s))

    def test_p90_of_several_tasks_is_not_max(self):
        dsp = [d("p:%d" % i, "haiku", tokens=100 * (i + 1), duration_ms=1000 * (i + 1)) for i in range(10)]
        dsp.append(d("p:10", "haiku", tokens=100000, duration_ms=1000000))
        s = tt.summary(tt.rows([], dsp, [], []), [], [], TH)
        # 11 tasks: nearest rank ceil(0.9*11)=10 -> the 10th smallest, not the 100000 outlier
        self.assertEqual(s["by_tier"]["haiku"]["tokens_p90"], 1000.0)
        self.assertEqual(s["by_tier"]["haiku"]["duration_ms_p90"], 10000.0)


if __name__ == "__main__":
    unittest.main()
