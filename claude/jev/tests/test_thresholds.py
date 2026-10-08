import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import thresholds


class ThresholdsTest(unittest.TestCase):
    def setUp(self):
        self.p = os.path.join(tempfile.mkdtemp(), "thresholds.json")
        os.environ["JEV_THRESHOLDS"] = self.p

    def test_defaults_when_missing(self):
        t = thresholds.load()
        self.assertEqual(t["gate"]["deny_safe_below"], 0.2)
        self.assertEqual(t["gate"]["min_confidence"], 0.7)
        self.assertIn("git status", t["gate"]["allowlist"])
        self.assertEqual(t["route"]["min_confidence"], 0.7)

    def test_file_overrides_per_key(self):
        with open(self.p, "w") as f:
            json.dump({"gate": {"min_confidence": 0.8}}, f)
        t = thresholds.load()
        self.assertEqual(t["gate"]["min_confidence"], 0.8)
        self.assertEqual(t["gate"]["deny_safe_below"], 0.2)

    def test_corrupt_file_falls_back(self):
        with open(self.p, "w") as f:
            f.write("{nope")
        self.assertEqual(thresholds.load()["gate"]["min_confidence"], 0.7)

    def test_set_value_nested(self):
        thresholds.set_value("dispatch.min_confidence", 0.75)
        self.assertEqual(thresholds.load()["dispatch"]["min_confidence"], 0.75)
        with open(self.p) as f:
            self.assertEqual(json.load(f), {"dispatch": {"min_confidence": 0.75}})

    def test_validate_accepts_valid_float(self):
        err = thresholds.validate("gate.min_confidence", 0.75)
        self.assertIsNone(err)

    def test_validate_rejects_string(self):
        err = thresholds.validate("gate.min_confidence", "0.7")
        self.assertIsNotNone(err)

    def test_validate_rejects_confidence_out_of_range(self):
        err = thresholds.validate("gate.min_confidence", 1.5)
        self.assertIsNotNone(err)
        self.assertIn("0.0, 1.0", err)

    def test_validate_rejects_nested_key(self):
        err = thresholds.validate("gate.min_confidence.x", 0.7)
        self.assertIsNotNone(err)

    def test_validate_rejects_unknown_section(self):
        err = thresholds.validate("nope.x", 0.7)
        self.assertIsNotNone(err)

    def test_validate_rejects_allowlist_string(self):
        err = thresholds.validate("gate.allowlist", "rm")
        self.assertIsNotNone(err)

    def test_validate_accepts_allowlist_list(self):
        err = thresholds.validate("gate.allowlist", ["ls", "cat"])
        self.assertIsNone(err)

    def test_validate_rejects_invalid_ask_risk(self):
        err = thresholds.validate("gate.ask_risk", "unknown")
        self.assertIsNotNone(err)

    def test_validate_accepts_valid_ask_risk(self):
        err = thresholds.validate("gate.ask_risk", "destructive")
        self.assertIsNone(err)

    def test_load_defense_in_depth(self):
        with open(self.p, "w") as f:
            json.dump({"gate": {"min_confidence": "0.7", "allowlist": "rm"}}, f)
        t = thresholds.load()
        self.assertEqual(t["gate"]["min_confidence"], 0.7)
        self.assertIsInstance(t["gate"]["allowlist"], list)

    def test_validate_allows_default_allowlist(self):
        """Test that DEFAULTS allowlist is always valid."""
        err = thresholds.validate("gate.allowlist", thresholds.DEFAULTS["gate"]["allowlist"])
        self.assertIsNone(err)

    def test_validate_allows_default_plus_new(self):
        """Test that DEFAULTS allowlist + new safe entry is valid."""
        new_allowlist = thresholds.DEFAULTS["gate"]["allowlist"] + ["jq"]
        err = thresholds.validate("gate.allowlist", new_allowlist)
        self.assertIsNone(err)

    def test_validate_rejects_dangerous_new_entry(self):
        """Test that adding a dangerous head entry is rejected."""
        new_allowlist = thresholds.DEFAULTS["gate"]["allowlist"] + ["python3 foo.py"]
        err = thresholds.validate("gate.allowlist", new_allowlist)
        self.assertIsNotNone(err)
        self.assertIn("python3", err)

    def test_validate_rejects_rm_entry(self):
        """Test that rm entry is rejected."""
        new_allowlist = thresholds.DEFAULTS["gate"]["allowlist"] + ["rm"]
        err = thresholds.validate("gate.allowlist", new_allowlist)
        self.assertIsNotNone(err)

    def test_validate_accepts_routine_ask_risk(self):
        """Test that 'routine' ask_risk is valid."""
        err = thresholds.validate("gate.ask_risk", "routine")
        self.assertIsNone(err)

    def test_validate_accepts_worth_a_look_ask_risk(self):
        """Test that 'worth_a_look' ask_risk is valid."""
        err = thresholds.validate("gate.ask_risk", "worth_a_look")
        self.assertIsNone(err)

    def test_validate_rejects_risky_ask_risk(self):
        """Test that 'risky' ask_risk is rejected."""
        err = thresholds.validate("gate.ask_risk", "risky")
        self.assertIsNotNone(err)

    def test_validate_rejects_read_only_ask_risk(self):
        """Test that 'read-only' ask_risk is rejected."""
        err = thresholds.validate("gate.ask_risk", "read-only")
        self.assertIsNotNone(err)

    def test_validate_rejects_none_of_these_ask_risk(self):
        """Test that 'none_of_these' ask_risk is rejected."""
        err = thresholds.validate("gate.ask_risk", "none_of_these")
        self.assertIsNotNone(err)

    def test_interrogate_default(self):
        self.assertEqual(thresholds.load()["interrogate"]["min_confidence"], 0.7)
        self.assertIsNone(thresholds.validate("interrogate.min_confidence", 0.8))
        self.assertIsNotNone(thresholds.validate("interrogate.min_confidence", 1.5))

    def test_gate_prescreen_default_and_validation(self):
        self.assertIs(thresholds.DEFAULTS["gate"]["prescreen"], True)
        self.assertIsNone(thresholds.validate("gate.prescreen", False))
        self.assertIsNotNone(thresholds.validate("gate.prescreen", "no"))

    def test_gate_compound_default_and_validation(self):
        self.assertIs(thresholds.DEFAULTS["gate"]["compound"], True)
        self.assertIsNone(thresholds.validate("gate.compound", False))
        self.assertIsNotNone(thresholds.validate("gate.compound", "no"))
        self.assertIsNotNone(thresholds.validate("gate.compound", 0))

    def test_haiku_defaults(self):
        t = thresholds.load()
        self.assertEqual(t["escalation"]["haiku_failures_before_sonnet"], 1)
        self.assertEqual(t["escalation"]["haiku_climb_max"], 0.35)
        self.assertIs(t["dispatch"]["haiku_default"], True)
        self.assertEqual(t["escalation"]["sonnet_failures_before_opus"], 2)
        self.assertEqual(t["escalation"]["opus_failures_before_fable"], 1)

    def test_failures_before_keys_range(self):
        for key in ("escalation.haiku_failures_before_sonnet",
                    "escalation.sonnet_failures_before_opus",
                    "escalation.opus_failures_before_fable"):
            self.assertIsNone(thresholds.validate(key, 1), key)
            self.assertIsNone(thresholds.validate(key, 5), key)
            self.assertIsNotNone(thresholds.validate(key, 0), key)
            self.assertIsNotNone(thresholds.validate(key, 6), key)
            self.assertIsNotNone(thresholds.validate(key, 1.5), key)
            self.assertIsNotNone(thresholds.validate(key, True), key)

    def test_haiku_climb_max_range(self):
        self.assertIsNone(thresholds.validate("escalation.haiku_climb_max", 0.5))
        self.assertIsNone(thresholds.validate("escalation.haiku_climb_max", 0.0))
        self.assertIsNone(thresholds.validate("escalation.haiku_climb_max", 1.0))
        self.assertIsNotNone(thresholds.validate("escalation.haiku_climb_max", 1.2))
        self.assertIsNotNone(thresholds.validate("escalation.haiku_climb_max", -0.1))
        self.assertIsNotNone(thresholds.validate("escalation.haiku_climb_max", "0.3"))

    def test_haiku_default_must_be_bool(self):
        self.assertIsNone(thresholds.validate("dispatch.haiku_default", False))
        self.assertIsNone(thresholds.validate("dispatch.haiku_default", True))
        self.assertIsNotNone(thresholds.validate("dispatch.haiku_default", 0))
        self.assertIsNotNone(thresholds.validate("dispatch.haiku_default", "false"))


class HandoffThresholdsTest(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(thresholds.DEFAULTS["handoff"]["keep_min"], 0.5)
        self.assertEqual(thresholds.DEFAULTS["context"]["warn_pct"], 0.65)

    def test_keep_min_range(self):
        self.assertIsNone(thresholds.validate("handoff.keep_min", 0.7))
        self.assertIsNotNone(thresholds.validate("handoff.keep_min", 1.5))
        self.assertIsNotNone(thresholds.validate("handoff.keep_min", -0.1))
        self.assertIsNotNone(thresholds.validate("handoff.keep_min", "x"))

    def test_warn_pct_range(self):
        self.assertIsNone(thresholds.validate("context.warn_pct", 0.5))
        self.assertIsNone(thresholds.validate("context.warn_pct", 0.1))
        self.assertIsNone(thresholds.validate("context.warn_pct", 0.95))
        self.assertIsNotNone(thresholds.validate("context.warn_pct", 0.05))
        self.assertIsNotNone(thresholds.validate("context.warn_pct", 0.99))
        self.assertIsNotNone(thresholds.validate("context.warn_pct", True))


def test_validate_rejects_nan_inf():
    for v in (float("nan"), float("inf"), float("-inf")):
        assert thresholds.validate("gate.min_confidence", v) is not None
        assert thresholds.validate("context.warn_pct", v) is not None


def test_load_nan_falls_back(tmp_path, monkeypatch):
    p = tmp_path / "thresholds.json"
    p.write_text('{"gate": {"min_confidence": NaN}, "route": {"min_confidence": 7}}')
    monkeypatch.setenv("JEV_THRESHOLDS", str(p))
    t = thresholds.load()
    assert t["gate"]["min_confidence"] == thresholds.DEFAULTS["gate"]["min_confidence"]
    assert t["route"]["min_confidence"] == thresholds.DEFAULTS["route"]["min_confidence"]


if __name__ == "__main__":
    unittest.main()
