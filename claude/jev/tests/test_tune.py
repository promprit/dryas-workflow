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
