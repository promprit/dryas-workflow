import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tune
import tune_window as tw


def row(day, jev, wait, tokens, escalated=False):
    return {"first_ts": "2026-10-%02dT09:00:00+0700" % day, "jev_calls": jev, "gate_wait_ms": wait,
            "tokens": tokens, "escalated": escalated}


def rows(base, cur):
    out = {"b:%d" % i: row(1 + i % 9, *base) for i in range(10)}
    out.update({"c:%d" % i: row(20 + i % 9, *cur) for i in range(10)})
    return out


class WindowTest(unittest.TestCase):
    def test_pass_when_targets_met(self):
        res = tw.check(rows((8, 900.0, 50000.0), (3, 400.0, 48000.0)), "")
        self.assertEqual([l["verdict"] for l in res["lines"]], ["PASS"] * 4)
        self.assertEqual((res["base_tasks"], res["current_tasks"], res["basis"]), (10, 10, "earlier half"))

    def test_fail_lines(self):
        res = tw.check(rows((8, 900.0, 50000.0), (5, 950.0, 51000.0, True)), "")
        self.assertEqual([l["verdict"] for l in res["lines"]], ["FAIL"] * 4)

    def test_until_date_splits_windows(self):
        r = rows((8, 900.0, 50000.0), (3, 400.0, 48000.0))
        base, cur = tw.windows(r, "2026-10-15")
        self.assertEqual((len(base), len(cur)), (10, 10))
        self.assertEqual(tw.check(r, "2026-10-15")["basis"], "before 2026-10-15")
        base, cur = tw.windows(r, "2026-10-05")
        self.assertEqual(len(base), 5)

    def test_small_windows_are_na(self):
        r = {k: v for k, v in rows((8, 900.0, 50000.0), (3, 400.0, 48000.0)).items() if k[2:] in "01234"}
        self.assertEqual({l["verdict"] for l in tw.check(r, "")["lines"]}, {"n/a"})

    def test_missing_tokens_are_na_not_zero(self):
        r = rows((8, 900.0, None), (3, 400.0, None))
        line = [l for l in tw.check(r, "")["lines"] if l["name"] == "Executor tokens per task"][0]
        self.assertEqual((line["base"], line["verdict"]), (None, "n/a"))

    def test_lines_text(self):
        text = "\n".join(tw.lines(tw.check(rows((8, 900.0, 50000.0), (3, 400.0, 48000.0)), "")))
        self.assertIn("- Done-when check (baseline earlier half: 10 tasks; current: 10 tasks; n/a below 10 each)", text)
        self.assertIn("- Done-when Jev calls per task: baseline 8, current 3 (target: at most half): PASS", text)


class TuneWiringTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, {"JEV_LOG_DIR": self.tmp, "JEV_THRESHOLDS": os.path.join(self.tmp, "t.json")})
        p.start()
        self.addCleanup(p.stop)

    def write(self, name, recs):
        with open(os.path.join(self.tmp, name + ".jsonl"), "w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")

    def test_new_lines_follow_delivery_and_precede_swarm(self):
        lines = tune.render(tune.build(self.tmp), []).splitlines()
        i = next(n for n, l in enumerate(lines) if l.startswith("- Cost per merged task:"))
        self.assertTrue(lines[i + 1].startswith("- Per task (median over 0 tasks):"))
        j = next(n for n, l in enumerate(lines) if l.startswith("- Swarm vs plain token ratio:"))
        self.assertTrue(lines[j - 1].startswith("- Done-when Escalation rate:"))

    def test_report_carries_task_numbers_and_proposals(self):
        self.write("dispatch", [{"task": "b:%d" % i, "tier": "haiku", "role": "coder", "attempt": 1, "tokens": 1000,
                                 "ts": "2026-10-%02dT09:00:00+0700" % (i + 1)} for i in range(3)])
        self.write("gate", [{"tool": "Write", "decision": "none", "provider": "local", "task": "b:%d" % i,
                             "local_ms": 1.0, "task_review": "skip", "false_skip": False} for i in range(3)])
        with open(os.environ["JEV_THRESHOLDS"], "w") as f:
            json.dump({"review": {"min_tasks": 3}}, f)
        rep = tune.build(self.tmp)
        self.assertEqual((rep["tasks"]["tasks"], rep["tasks"]["review_tasks"]), (3, 3))
        props = tune.proposals(rep, tune.thresholds.load())
        self.assertIn({"key": "review.task_skip", "old": False, "new": True}, [{k: p[k] for k in ("key", "old", "new")} for p in props])

    def test_hand_built_reports_without_task_numbers_still_render(self):
        rep = tune.build(self.tmp)
        del rep["tasks"], rep["done_check"]
        self.assertIn("PROPOSALS_JSON", tune.render(rep, tune.proposals(rep, tune.thresholds.load())))


def verdicts(res):
    return {l["name"]: l["verdict"] for l in res["lines"]}


class BoundaryTest(unittest.TestCase):
    def one(self, base, cur, name):
        return verdicts(tw.check(rows(base, cur), ""))[name]

    def test_jev_calls_exactly_half_passes_above_half_fails(self):
        self.assertEqual(self.one((8, 900.0, 5.0), (4, 400.0, 5.0), "Jev calls per task"), "PASS")
        self.assertEqual(self.one((8, 900.0, 5.0), (4.1, 400.0, 5.0), "Jev calls per task"), "FAIL")
        self.assertEqual(self.one((8, 900.0, 5.0), (4.5, 400.0, 5.0), "Jev calls per task"), "FAIL")

    def test_gate_wait_equal_nonzero_fails_zero_passes(self):
        self.assertEqual(self.one((8, 900.0, 5.0), (4, 900.0, 5.0), "Gate wait per task (ms)"), "FAIL")
        self.assertEqual(self.one((8, 0, 5.0), (4, 0, 5.0), "Gate wait per task (ms)"), "PASS")

    def test_tokens_and_escalation_equal_pass(self):
        res = verdicts(tw.check(rows((8, 900.0, 5.0), (4, 400.0, 5.0)), ""))
        self.assertEqual((res["Executor tokens per task"], res["Escalation rate"]), ("PASS", "PASS"))
        r = rows((8, 900.0, 5.0, True), (4, 400.0, 5.0, True))
        self.assertEqual(verdicts(tw.check(r, ""))["Escalation rate"], "PASS")


class WindowMinTest(unittest.TestCase):
    def test_nine_in_either_window_is_na_ten_in_both_is_verdict(self):
        full = rows((8, 900.0, 5.0), (3, 400.0, 4.0))
        for drop in ("b", "c"):
            r = {k: v for k, v in full.items() if not (k.startswith(drop) and k.endswith("9"))}
            self.assertEqual({l["verdict"] for l in tw.check(r, "2026-10-15")["lines"]}, {"n/a"}, drop)
        self.assertEqual(set(verdicts(tw.check(full, "2026-10-15")).values()), {"PASS"})


class UntilFallbackTest(unittest.TestCase):
    def test_bad_until_values_fall_back_to_earlier_half(self):
        r = rows((8, 900.0, 5.0), (3, 400.0, 4.0))
        for bad in (None, 5, ["x"], "garbage", "2026-13-99"):
            res = tw.check(r, bad)
            self.assertEqual((res["basis"], res["base_tasks"], res["current_tasks"]), ("earlier half", 10, 10), bad)

    def test_windows_alone_also_tolerates_bad_until(self):
        base, cur = tw.windows(rows((8, 900.0, 5.0), (3, 400.0, 4.0)), 5)
        self.assertEqual((len(base), len(cur)), (10, 10))

    def test_rows_without_first_ts_are_ignored(self):
        r = rows((8, 900.0, 5.0), (3, 400.0, 4.0))
        r["x"] = {"jev_calls": 99, "gate_wait_ms": 1.0, "tokens": 1.0, "escalated": True}
        r["y"] = dict(r["x"], first_ts=None)
        res = tw.check(r, "")
        self.assertEqual((res["base_tasks"], res["current_tasks"]), (10, 10))

    def test_build_with_non_string_until_in_thresholds_file(self):
        tmp = tempfile.mkdtemp()
        with open(os.path.join(tmp, "t.json"), "w") as f:
            json.dump({"baseline": {"until": 7}}, f)
        with mock.patch.dict(os.environ, {"JEV_LOG_DIR": tmp, "JEV_THRESHOLDS": os.path.join(tmp, "t.json")}):
            self.assertEqual(tune.build(tmp)["done_check"]["basis"], "earlier half")


class ZeroBaseTest(unittest.TestCase):
    def test_zero_base_values_give_verdicts_without_dividing(self):
        res = tw.check(rows((0, 0, 0.0), (0, 0, 0.0)), "")
        self.assertEqual(verdicts(res), {"Jev calls per task": "PASS", "Gate wait per task (ms)": "PASS",
                                          "Executor tokens per task": "PASS", "Escalation rate": "PASS"})
        res = tw.check(rows((0, 0, 0.0), (1, 5.0, 1.0, True)), "")
        self.assertEqual(set(verdicts(res).values()), {"FAIL"})
        self.assertTrue(tw.lines(res))

    def test_no_rows_at_all(self):
        self.assertEqual({l["verdict"] for l in tw.check({}, "")["lines"]}, {"n/a"})


class PartialReportTest(unittest.TestCase):
    def render(self, **change):
        tmp = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"JEV_LOG_DIR": tmp, "JEV_THRESHOLDS": os.path.join(tmp, "t.json")}):
            rep = tune.build(tmp)
            for k, v in change.items():
                if v == "DEL":
                    del rep[k]
                else:
                    rep[k] = v
            return tune.render(rep, tune.proposals(rep, tune.thresholds.load()))

    def test_missing_only_one_or_none_renders(self):
        for change in ({"tasks": "DEL"}, {"done_check": "DEL"}, {"tasks": None}, {"done_check": None},
                       {"tasks": None, "done_check": None}):
            out = self.render(**change)
            self.assertIn("PROPOSALS_JSON", out, change)
        self.assertNotIn("Done-when", self.render(done_check=None))
        self.assertIn("Done-when", self.render(tasks=None))
        self.assertNotIn("Per task (median", self.render(tasks=None))


if __name__ == "__main__":
    unittest.main()
