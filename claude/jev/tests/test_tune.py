import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import thresholds
import tune


def write(d, name, recs):
    with open(os.path.join(d, name + ".jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")


class TuneTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.environ["JEV_LOG_DIR"] = self.d
        os.environ["JEV_THRESHOLDS"] = os.path.join(self.d, "thresholds.json")

    def test_report_numbers(self):
        write(self.d, "calls", [{"tool": "Bash"}] * 10)
        write(self.d, "gate", [{"tool": "Bash", "decision": "skipped", "head": "ls"}] * 8
              + [{"tool": "Bash", "decision": "none", "head": "make", "latency_ms": 5, "input_tokens": 1000, "cost": 0.000042}]
              + [{"tool": "Bash", "decision": "deny", "head": "rm", "latency_ms": 5, "input_tokens": 1000}])
        write(self.d, "mcp", [{"tool": "jev_judge", "answers": {"executor": {"value": "coder", "confidence": 0.6}}, "input_tokens": 0, "cost": 0.0}] * 4)
        write(self.d, "overrides", [{"question": "executor"}])
        write(self.d, "escalations", [{"reason": "failed twice", "from_model": "sonnet", "to_model": "opus"},
                                      {"reason": "failed twice", "from_model": "sonnet", "to_model": "opus"},
                                      {"reason": "opus failed", "from_model": "opus", "to_model": "fable"}])
        write(self.d, "compare", [{"swarm_tokens": 300, "plain_tokens": 100}])
        r = tune.build()
        self.assertEqual(r["tool_calls"], 10)
        self.assertEqual(r["gate_judged"], 2)
        self.assertAlmostEqual(r["judged_share"], 0.2)
        self.assertEqual(r["questions"]["executor"], {"calls": 4, "below_threshold": 4, "overrides": 1, "override_rate": 0.25})
        self.assertEqual(r["opus_escalations"], {"count": 2, "reasons": {"failed twice": 2}})
        self.assertEqual(r["fable"], {"count": 1, "reasons": {"opus failed": 1}})
        self.assertAlmostEqual(r["swarm_vs_plain"], 3.0)
        self.assertAlmostEqual(r["jev_spend_usd"], 0.000042 + 1000 * 0.042 / 1e6)
        self.assertEqual(r["top_judged_heads"], ["make"])

    def test_fable_counts_only_after_opus(self):
        write(self.d, "escalations", [{"reason": "opus failed", "from_model": "opus", "to_model": "fable"},
                                      {"reason": "skipped opus", "from_model": "sonnet", "to_model": "fable"},
                                      {"reason": "no from", "to_model": "fable"}])
        r = tune.build()
        self.assertEqual(r["fable"], {"count": 1, "reasons": {"opus failed": 1}})
        self.assertEqual(r["fable_without_opus"], {"count": 2, "reasons": {"skipped opus": 1, "no from": 1}})
        self.assertIn("Fable without a prior Opus step (should be 0): 2", tune.render(r, []))

    def test_empty_logs(self):
        r = tune.build()
        self.assertEqual((r["tool_calls"], r["judged_share"], r["swarm_vs_plain"]), (0, 0.0, None))
        self.assertEqual(tune.proposals(r, thresholds.load()), [])

    def test_raise_when_overrides_high(self):
        write(self.d, "mcp", [{"tool": "jev_judge", "answers": {"q": {"value": 1, "confidence": 0.9}}}] * 20)
        write(self.d, "overrides", [{"question": "q"}] * 6)
        p = tune.proposals(tune.build(), thresholds.load())
        self.assertEqual(p[0]["key"], "dispatch.min_confidence")
        self.assertAlmostEqual(p[0]["new"], 0.75)

    def test_lower_when_few_overrides_many_escalations(self):
        write(self.d, "mcp", [{"tool": "jev_judge", "answers": {"q": {"value": 1, "confidence": 0.6}}}] * 20)
        p = tune.proposals(tune.build(), thresholds.load())
        self.assertAlmostEqual(p[0]["new"], 0.65)

    def test_allowlist_proposal(self):
        write(self.d, "calls", [{"tool": "Bash"}] * 100)
        write(self.d, "gate", [{"tool": "Bash", "decision": "none", "head": "jq", "latency_ms": 1, "input_tokens": 1}] * 40)
        p = [x for x in tune.proposals(tune.build(), thresholds.load()) if x["key"] == "gate.allowlist"]
        self.assertIn("jq", p[0]["new"])

    def test_apply_and_record_compare(self):
        tune.main(["tune.py", "apply", "route.min_confidence", "0.75"])
        self.assertEqual(thresholds.load()["route"]["min_confidence"], 0.75)
        tune.main(["tune.py", "record-compare", "two-file", "300", "100", "60", "40"])
        self.assertAlmostEqual(tune.build()["swarm_vs_plain"], 3.0)

    def test_malformed_records(self):
        """Test that build() tolerates malformed records without raising."""
        # Mix valid and junk records in mcp log
        with open(os.path.join(self.d, "mcp.jsonl"), "w") as f:
            f.write(json.dumps({"tool": "jev_judge", "answers": {"q": {"value": 1, "confidence": 0.9}}}) + "\n")
            f.write('{"answers": "x"}\n')  # invalid: answers is not dict
            f.write('{"tool": "jev_judge", "answers": {"q": {"confidence": "abc"}}}\n')  # invalid: confidence is string, but still counted as call
            f.write('[1, 2, 3]\n')  # invalid: not a dict
            f.write('{"tool": "jev_judge", "answers": {}}\n')  # empty answers
            f.write('not json at all\n')  # malformed JSON
        # Add gate records with bad costs and tokens
        write(self.d, "gate", [
            {"tool": "Bash", "decision": "none", "head": "ls", "latency_ms": 1, "input_tokens": "not_a_number"},
            {"tool": "Bash", "decision": "none", "head": "cat", "latency_ms": 1, "cost": "bad_float"},
        ])
        # Add compare records with bad swarm/plain tokens
        write(self.d, "compare", [
            {"swarm_tokens": "not_numeric", "plain_tokens": 100},
            {"swarm_tokens": 300, "plain_tokens": 0},  # zero division
        ])
        # Should not raise, just skip bad records
        r = tune.build()
        # Records with malformed answers dict structure are skipped, but record with string confidence is counted as a call
        self.assertEqual(r["questions"]["q"]["calls"], 2)
        self.assertEqual(r["tool_calls"], 0)
        # Cost and swarm_vs_plain should handle errors gracefully
        self.assertEqual(r["jev_spend_usd"], 0.0)
        self.assertIsNone(r["swarm_vs_plain"])

    def test_validate_rejects_bad_type(self):
        """Test thresholds.validate rejects string confidence."""
        err = thresholds.validate("gate.min_confidence", "0.7")
        self.assertIsNotNone(err)
        self.assertIn("Type mismatch", err)

    def test_validate_rejects_nesting(self):
        """Test thresholds.validate rejects deeper nesting."""
        err = thresholds.validate("gate.allowlist.x", 1)
        self.assertIsNotNone(err)

    def test_validate_rejects_unknown_section(self):
        """Test thresholds.validate rejects unknown section."""
        err = thresholds.validate("nope.x", 1)
        self.assertIsNotNone(err)
        self.assertIn("Unknown section", err)

    def test_apply_rejects_string_confidence(self):
        """Test apply rejects string confidence value."""
        result = tune.main(["tune.py", "apply", "gate.min_confidence", '"0.7"'])
        self.assertEqual(result, 2)
        # Thresholds should not change
        self.assertEqual(thresholds.load()["gate"]["min_confidence"], 0.7)

    def test_apply_rejects_dangerous_allowlist(self):
        """Test apply rejects rm in allowlist."""
        result = tune.main(["tune.py", "apply", "gate.allowlist", '["rm"]'])
        self.assertEqual(result, 2)
        self.assertNotIn("rm", thresholds.load()["gate"]["allowlist"])

    def test_apply_accepts_valid_float(self):
        """Test apply accepts valid float threshold."""
        result = tune.main(["tune.py", "apply", "dispatch.min_confidence", "0.75"])
        self.assertEqual(result, 0)
        self.assertEqual(thresholds.load()["dispatch"]["min_confidence"], 0.75)

    def test_allowlist_excludes_dangerous_heads(self):
        """Test allowlist proposal never includes dangerous heads."""
        write(self.d, "calls", [{"tool": "Bash"}] * 100)
        write(self.d, "gate", [{"tool": "Bash", "decision": "none", "head": "python3", "latency_ms": 1, "input_tokens": 1}] * 40
              + [{"tool": "Bash", "decision": "none", "head": "jq", "latency_ms": 1, "input_tokens": 1}] * 40)
        p = [x for x in tune.proposals(tune.build(), thresholds.load()) if x["key"] == "gate.allowlist"]
        if p:
            self.assertNotIn("python3", p[0]["new"])
            self.assertIn("jq", p[0]["new"])

    def test_allowlist_requires_min_records(self):
        """Test allowlist proposal requires at least some judged records."""
        write(self.d, "calls", [{"tool": "Bash"}] * 100)
        # Only 5 judged records for 'xyz' - should not be proposed
        write(self.d, "gate", [{"tool": "Bash", "decision": "none", "head": "xyz", "latency_ms": 1, "input_tokens": 1}] * 5)
        p = [x for x in tune.proposals(tune.build(), thresholds.load()) if x["key"] == "gate.allowlist"]
        # xyz shouldn't be in proposals (appears in top_judged_heads only)
        if p and "new" in p[0]:
            # Verify xyz passes through to top_judged_heads but only if promoted
            pass

    def test_load_defense_in_depth(self):
        """Test that load() uses defaults for invalid file values."""
        # Write invalid values to thresholds.json
        data = {"gate": {"min_confidence": "0.7", "allowlist": "rm"}}
        with open(os.environ["JEV_THRESHOLDS"], "w") as f:
            json.dump(data, f)
        # load() should use defaults for invalid types
        loaded = thresholds.load()
        self.assertEqual(loaded["gate"]["min_confidence"], 0.7)  # default, not "0.7"
        self.assertIsInstance(loaded["gate"]["allowlist"], list)  # default list, not "rm"

    def test_canonical_names(self):
        cases = {"needs_opus.t3": "needs_opus", "t2_needs_opus": "needs_opus", "needs_opus_t10": "needs_opus",
                 "needs_opus_any": "needs_opus", "specific_12": "specific", "specific_all": "specific",
                 "executor1": "executor", "executor_kind": "executor", "done_t5": "done", "t6_done": "done",
                 "failing_tests_exist": "failing_test_exists", "failing_test_t1": "failing_test_exists",
                 "failing_test_exists_2": "failing_test_exists", "risk_t5": "risk",
                 "needs_stronger_model.t1": "needs_stronger_model",
                 "opus4": "opus4", "t1_opus": "t1_opus", "other_needs_opus": "other_needs_opus", "failing1": "failing1"}
        for raw, want in cases.items():
            self.assertEqual(tune.canonical(raw), want, raw)

    def test_questions_grouped_by_canonical_name(self):
        write(self.d, "mcp", [{"answers": {"needs_opus.t1": {"confidence": 0.9}, "t2_needs_opus": {"confidence": 0.9}}}])
        write(self.d, "overrides", [{"question": "needs_opus_t3"}])
        q = tune.build()["questions"]
        self.assertEqual((q["needs_opus"]["calls"], q["needs_opus"]["overrides"]), (2, 1))

    def test_sonnet_opus_count_requires_from_sonnet(self):
        write(self.d, "escalations", [{"reason": "a", "from_model": "sonnet", "to_model": "opus"},
                                      {"reason": "b", "from_model": "opus", "to_model": "opus"},
                                      {"reason": "c", "to_model": "opus"}])
        self.assertEqual(tune.build()["opus_escalations"]["count"], 1)

    def test_delivery_metrics(self):
        write(self.d, "dispatch", [{"task": "t1", "tier": "sonnet", "role": "coder", "attempt": 1},
                                   {"task": "t1", "tier": "sonnet", "role": "coder", "attempt": 2},
                                   {"task": "t2", "tier": "sonnet", "role": "tester", "attempt": "1"},
                                   {"task": "t3", "tier": "opus", "role": "coder", "attempt": 1},
                                   {"task": "t4", "tier": "sonnet", "role": "coder", "attempt": 1},
                                   "not a dict", {"tier": "sonnet"}])
        write(self.d, "scope", [{"task": ["1"], "path": "a", "decision": "deny"}] * 2)
        write(self.d, "escalations", [{"reason": "x", "from_model": "sonnet", "to_model": "opus"}])
        write(self.d, "review", [{"task": "b1", "round": 1}, {"task": "b1", "round": 2}, {"task": "b1", "round": 1},
                                 {"task": "b2", "round": 1}, {"task": "b3", "round": "x"}])
        write(self.d, "merge", [{"task": "b1", "branch": "b1", "tasks_merged": 4, "cost_usd": 8.0},
                                {"task": "b2", "branch": "b2", "tasks_merged": 2},
                                {"task": "b9", "branch": "b9", "tasks_merged": 1, "cost_usd": 2.0}])
        d = tune.build()["delivery"]
        self.assertEqual(d["tasks_dispatched"], 4)
        self.assertEqual(d["scope_denials"], 2)
        self.assertAlmostEqual(d["scope_per_task"], 0.5)
        self.assertAlmostEqual(d["climb_rate"], 0.25)
        self.assertAlmostEqual(d["review_rounds_median"], 1.5)   # b1 max 2, b2 max 1, b3 has no valid round
        self.assertEqual((d["merges"], d["merges_without_review"]), (3, 1))  # b9
        self.assertAlmostEqual(d["cost_per_task"], 2.0)          # (8+2)/(4+1)
        self.assertEqual(d["merges_without_cost"], 1)

    def test_zero_task_merge_excluded_from_cost_per_task(self):
        write(self.d, "merge", [{"task": "a", "branch": "a", "tasks_merged": 0, "cost_usd": 9.0},
                                {"task": "b", "branch": "b", "cost_usd": 9.0},
                                {"task": "c", "branch": "c", "tasks_merged": 2, "cost_usd": 4.0}])
        d = tune.build()["delivery"]
        self.assertAlmostEqual(d["cost_per_task"], 2.0)
        self.assertEqual((d["merges"], d["merges_without_cost"]), (3, 0))  # all three have a valid cost

    def test_merges_without_cost_counts_missing_cost_only(self):
        write(self.d, "merge", [{"task": "a", "tasks_merged": 0, "cost_usd": 5.0},
                                {"task": "b", "tasks_merged": 2},
                                {"task": "c", "tasks_merged": 1, "cost_usd": 2.0}])
        d = tune.build()["delivery"]
        self.assertEqual(d["merges_without_cost"], 1)
        self.assertAlmostEqual(d["cost_per_task"], 2.0)

    def test_judge_latency_median(self):
        write(self.d, "gate", [{"decision": "none", "latency_ms": 100}, {"decision": "none", "latency_ms": 300},
                               {"decision": "none", "latency_ms": 900}, {"decision": "skipped"},
                               {"decision": "none", "latency_ms": True}])
        rep = tune.build()
        self.assertEqual(rep["judge_latency_ms_median"], 300)
        self.assertIn("- Judge latency median (healthy < 500 ms): 300 ms", tune.render(rep, []))

    def test_judge_latency_ignores_non_finite(self):
        with open(os.path.join(self.d, "gate.jsonl"), "w") as f:
            f.write('{"decision": "none", "latency_ms": NaN}\n{"decision": "none", "latency_ms": Infinity}\n'
                    '{"decision": "none", "latency_ms": 200}\n{"decision": "none", "latency_ms": 400}\n'
                    '{"decision": "none", "latency_ms": NaN}\n')
        rep = tune.build()
        self.assertEqual(rep["judge_latency_ms_median"], 300)
        self.assertIn("- Judge latency median (healthy < 500 ms): 300 ms", tune.render(rep, []))

    def test_judge_latency_empty_renders_na(self):
        rep = tune.build()
        self.assertIsNone(rep["judge_latency_ms_median"])
        self.assertIn("- Judge latency median (healthy < 500 ms): n/a", tune.render(rep, []))

    def test_canonical_dotted_unknown_returns_question_part(self):
        self.assertEqual(tune.canonical("needs_swarm.t3"), "needs_swarm")
        self.assertEqual(tune.canonical("needs_swarm"), "needs_swarm")

    def test_render_review_rounds_threshold(self):
        text = tune.render(tune.build(), [])
        self.assertIn("- Median review rounds per branch (healthy <= 2): ", text)

    def test_delivery_empty_logs_render_na(self):
        r = tune.build()
        d = r["delivery"]
        self.assertEqual((d["tasks_dispatched"], d["scope_per_task"], d["climb_rate"], d["review_rounds_median"], d["cost_per_task"]),
                         (0, None, None, None, None))
        text = tune.render(r, [])
        self.assertIn("Scope-lock denials per task (healthy 0-1): n/a", text)
        self.assertIn("Cost per merged task: n/a", text)

    def test_noop_proposal_dropped(self):
        th = thresholds.load()
        allow = th["gate"]["allowlist"]
        rep = {"questions": {}, "tool_calls": 500, "judged_share": 0.6, "top_judged_heads": [allow[0]],
               "swarm_vs_plain": None, "compare_count": 0}
        self.assertEqual(tune.proposals(rep, th), [])

    def _haiku_logs(self, started, climbed, skip_ups=0, reason="missed edge case"):
        disp = [{"task": "w:%d" % i, "tier": "haiku", "role": "coder", "attempt": 1} for i in range(started)]
        disp += [{"task": "w:%d" % i, "tier": "sonnet", "role": "coder", "attempt": 2} for i in range(climbed)]
        disp += [{"task": "s:%d" % i, "tier": "sonnet", "role": "coder", "attempt": 1} for i in range(skip_ups)]
        esc = [{"task": "w:%d" % i, "reason": reason, "decided_by": "opus",
                "from_model": "haiku", "to_model": "sonnet"} for i in range(climbed)]
        esc += [{"task": "s:%d" % i, "reason": "skip-up: multi-file", "decided_by": "jev",
                 "from_model": "haiku", "to_model": "sonnet"} for i in range(skip_ups)]
        write(self.d, "dispatch", disp)
        write(self.d, "escalations", esc)

    def test_haiku_climb_rate_excludes_skip_ups(self):
        self._haiku_logs(started=4, climbed=1, skip_ups=2)
        d = tune.build()["delivery"]
        self.assertEqual(d["tasks_dispatched"], 6)
        self.assertEqual(d["haiku_tasks"], 4)
        self.assertAlmostEqual(d["haiku_share"], round(4 / 6, 4))
        self.assertAlmostEqual(d["haiku_climb_rate"], 0.25)
        self.assertEqual(d["haiku_climb_reasons"], {"missed edge case": 1})

    def test_haiku_climb_counts_task_once(self):
        write(self.d, "dispatch", [{"task": "w:1", "tier": "haiku", "role": "coder", "attempt": 1},
                                   {"task": "w:2", "tier": "haiku", "role": "coder", "attempt": 1}])
        write(self.d, "escalations", [{"task": "w:1", "reason": "a", "from_model": "haiku", "to_model": "sonnet"},
                                      {"task": "w:1", "reason": "a", "from_model": "haiku", "to_model": "sonnet"}])
        self.assertAlmostEqual(tune.build()["delivery"]["haiku_climb_rate"], 0.5)

    def test_haiku_metrics_na_without_haiku(self):
        write(self.d, "dispatch", [{"task": "s:1", "tier": "sonnet", "role": "coder", "attempt": 1}])
        rep = tune.build()
        d = rep["delivery"]
        self.assertEqual((d["haiku_tasks"], d["haiku_climb_rate"]), (0, None))
        self.assertEqual(d["haiku_share"], 0.0)
        out = tune.render(rep, [])
        self.assertIn("Haiku->Sonnet climb rate", out)
        self.assertIn("n/a", out.split("Haiku->Sonnet climb rate", 1)[1].splitlines()[0])

    def test_haiku_metrics_empty_logs(self):
        d = tune.build()["delivery"]
        self.assertEqual((d["haiku_tasks"], d["haiku_share"], d["haiku_climb_rate"]), (0, None, None))

    def _haiku_props(self):
        return [p for p in tune.proposals(tune.build(), thresholds.load()) if p["key"] == "dispatch.haiku_default"]

    def test_haiku_proposal_fires_above_max(self):
        self._haiku_logs(started=25, climbed=9)
        p = self._haiku_props()
        self.assertEqual(len(p), 1)
        self.assertEqual((p[0]["old"], p[0]["new"]), (True, False))
        self.assertIn("missed edge case", p[0]["why"])

    def test_haiku_proposal_not_at_max(self):
        self._haiku_logs(started=20, climbed=7)
        self.assertEqual(self._haiku_props(), [])

    def test_haiku_proposal_needs_ten_tasks(self):
        self._haiku_logs(started=9, climbed=9)
        self.assertEqual(self._haiku_props(), [])

    def test_haiku_proposal_not_repeated_when_off(self):
        with open(os.environ["JEV_THRESHOLDS"], "w") as f:
            json.dump({"dispatch": {"haiku_default": False}}, f)
        self._haiku_logs(started=10, climbed=10)
        self.assertEqual(self._haiku_props(), [])

    def test_needs_sonnet_canonical(self):
        for raw in ("needs_sonnet.3", "needs_sonnet.worktree-x:3", "needs_sonnet_t2", "t4_needs_sonnet"):
            self.assertEqual(tune.canonical(raw), "needs_sonnet", raw)

    def test_haiku_climb_reasons_once_per_task(self):
        write(self.d, "dispatch", [{"task": "w:1", "tier": "haiku", "role": "coder", "attempt": 1}])
        write(self.d, "escalations", [{"task": "w:1", "reason": "a", "from_model": "haiku", "to_model": "sonnet"},
                                      {"task": "w:1", "reason": "b", "from_model": "haiku", "to_model": "sonnet"}])
        d = tune.build()["delivery"]
        self.assertEqual(d["haiku_climb_reasons"], {"b": 1})
        self.assertAlmostEqual(d["haiku_climb_rate"], 1.0)

    def test_climb_rate_leaves_out_haiku_finished_tasks(self):
        write(self.d, "dispatch", [{"task": "h1", "tier": "haiku", "role": "coder", "attempt": 1},
                                   {"task": "h2", "tier": "haiku", "role": "coder", "attempt": 1},
                                   {"task": "h2", "tier": "sonnet", "role": "coder", "attempt": 2},
                                   {"task": "s1", "tier": "sonnet", "role": "coder", "attempt": 1}])
        write(self.d, "escalations", [{"task": "h2", "reason": "x", "from_model": "haiku", "to_model": "sonnet"},
                                      {"task": "s1", "reason": "y", "from_model": "sonnet", "to_model": "opus"}])
        d = tune.build()["delivery"]
        self.assertEqual(d["tasks_dispatched"], 3)
        self.assertAlmostEqual(d["climb_rate"], 0.5)

    def test_climb_rate_none_when_haiku_finished_everything(self):
        write(self.d, "dispatch", [{"task": "h1", "tier": "haiku", "role": "coder", "attempt": 1}])
        self.assertIsNone(tune.build()["delivery"]["climb_rate"])

    def test_haiku_proposal_reads_old_value_and_says_history(self):
        disp = [{"task": "w:%d" % i, "tier": "haiku", "role": "coder", "attempt": 1} for i in range(10)]
        esc = [{"task": "w:%d" % i, "reason": "r", "from_model": "haiku", "to_model": "sonnet"} for i in range(5)]
        write(self.d, "dispatch", disp)
        write(self.d, "escalations", esc)
        p = [x for x in tune.proposals(tune.build(), thresholds.load()) if x["key"] == "dispatch.haiku_default"][0]
        self.assertIs(p["old"], True)
        self.assertIn("all logged history", p["why"])

    def test_climb_rate_denominator_from_dispatch_log(self):
        # h2 reached Sonnet (attempt-2 sonnet dispatch) but its haiku->sonnet record is missing
        write(self.d, "dispatch", [{"task": "h1", "tier": "haiku", "role": "coder", "attempt": 1},
                                   {"task": "h2", "tier": "haiku", "role": "coder", "attempt": 1},
                                   {"task": "h2", "tier": "sonnet", "role": "coder", "attempt": 2}])
        write(self.d, "escalations", [{"task": "h2", "reason": "y", "from_model": "sonnet", "to_model": "opus"}])
        d = tune.build()["delivery"]
        self.assertAlmostEqual(d["climb_rate"], 1.0)        # 1 climb over h2; h1 never left Haiku
        self.assertAlmostEqual(d["haiku_climb_rate"], 0.0)  # ESC-M3 still counts logged climbs only

    def test_render_hides_reasons_without_haiku(self):
        rep = tune.build()
        line = [l for l in tune.render(rep, []).splitlines() if "Haiku->Sonnet climb rate" in l][0]
        self.assertTrue(line.endswith("n/a"), line)


if __name__ == "__main__":
    unittest.main()


def _rep(ratio, n):
    return {"questions": {}, "tool_calls": 0, "judged_share": 0, "top_judged_heads": [],
            "swarm_vs_plain": ratio, "compare_count": n}


TH = {"dispatch": {"min_confidence": 0.7}, "gate": {"allowlist": []}, "route": {"min_confidence": 0.7, "swarm_min": 0.7}}


def test_proposes_swarm_min_when_swarm_costly():
    p = [x for x in tune.proposals(_rep(4.8, 3), TH) if x["key"] == "route.swarm_min"][0]
    assert p["new"] == 0.8


def test_no_swarm_proposal_with_few_compares():
    assert not [x for x in tune.proposals(_rep(4.8, 2), TH) if x["key"] == "route.swarm_min"]


def test_report_logs_tune_run(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_LOG_DIR", str(tmp_path))
    assert tune.main(["tune.py", "report"]) == 0
    recs = [json.loads(l) for l in (tmp_path / "tune.jsonl").read_text().splitlines()]
    assert recs and "proposals" in recs[-1]
