import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import providers
from jev_client import JevUnavailable

LOCAL = {"answers": {"safe": {"type": "noul", "value": 0.9, "confidence": 0.9},
                     "risk": {"type": "choice", "value": "routine", "confidence": 0.9, "probabilities": {}}},
         "reasons": []}
REMOTE = {"answers": {"safe": {"type": "noul", "value": 0.1, "confidence": 0.9},
                      "risk": {"type": "choice", "value": "destructive", "confidence": 0.9, "probabilities": {}}},
          "latency_ms": 5, "input_tokens": 10, "cost": 0.00001}
NOKEY = {"OPENROUTER_API_KEY": "", "DRYAS_OPENROUTER_KEY": "", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": ""}


def th(provider="auto", shadow="auto"):
    return {"judge": {"provider": provider, "shadow": shadow}}


def down(state, questions):
    raise JevUnavailable("HTTPError 503")


class ResolveTest(unittest.TestCase):
    def test_auto_without_key_is_local_and_no_shadow(self):
        with mock.patch.dict(os.environ, NOKEY):
            self.assertEqual(providers.resolve(th(), False), ("local", "none"))

    def test_auto_with_key_is_jev_shadowed_by_local(self):
        with mock.patch.dict(os.environ, dict(NOKEY, OPENROUTER_API_KEY="k")):
            self.assertEqual(providers.resolve(th(), False), ("jev", "local"))

    def test_injected_judge_counts_as_jev(self):
        with mock.patch.dict(os.environ, NOKEY):
            self.assertEqual(providers.resolve(th(), True), ("jev", "local"))

    def test_explicit_settings_win_and_shadow_never_equals_provider(self):
        self.assertEqual(providers.resolve(th("local", "jev"), True), ("local", "jev"))
        self.assertEqual(providers.resolve(th("jev", "jev"), True), ("jev", "none"))
        self.assertEqual(providers.resolve(th("local", "none"), True), ("local", "none"))

    def test_missing_or_bad_section_is_auto(self):
        with mock.patch.dict(os.environ, NOKEY):
            self.assertEqual(providers.resolve({}, False), ("local", "none"))
            self.assertEqual(providers.resolve({"judge": "x"}, False), ("local", "none"))


class AskTest(unittest.TestCase):
    def test_jev_decides_and_local_shadows(self):
        v = providers.ask({}, {}, LOCAL, th(), lambda s, q: REMOTE)
        self.assertEqual(v["provider"], "jev")
        self.assertIs(v["answers"], REMOTE["answers"])
        self.assertEqual((v["shadow_provider"], v["shadow_answers"]), ("local", LOCAL["answers"]))
        self.assertEqual((v["latency_ms"], v["input_tokens"], v["cost"]), (5, 10, 0.00001))

    def test_jev_unavailable_falls_back_to_local(self):
        v = providers.ask({}, {}, LOCAL, th(), down)
        self.assertEqual((v["provider"], v["fallback"], v["error"], v["shadow_provider"]),
                         ("local", "local", "JevUnavailable", "none"))
        self.assertIs(v["answers"], LOCAL["answers"])
        self.assertNotIn("latency_ms", v)

    def test_local_decides_without_calling_jev(self):
        calls = []
        v = providers.ask({}, {}, LOCAL, th("local", "none"), lambda s, q: calls.append(1) or REMOTE)
        self.assertEqual((v["provider"], calls), ("local", []))
        self.assertNotIn("shadow_answers", v)

    def test_jev_shadow_when_local_decides(self):
        v = providers.ask({}, {}, LOCAL, th("local", "jev"), lambda s, q: REMOTE)
        self.assertEqual(v["provider"], "local")
        self.assertIs(v["answers"], LOCAL["answers"])
        self.assertEqual((v["shadow_provider"], v["shadow_answers"], v["shadow_cost"]), ("jev", REMOTE["answers"], 0.00001))

    def test_jev_shadow_failure_never_changes_the_decision(self):
        v = providers.ask({}, {}, LOCAL, th("local", "jev"), down)
        self.assertEqual((v["provider"], v["shadow_error"]), ("local", "JevUnavailable"))
        self.assertIs(v["answers"], LOCAL["answers"])

    def test_reasons_travel_with_local_answers(self):
        loc = dict(LOCAL, reasons=["danger:rm_root"])
        self.assertEqual(providers.ask({}, {}, loc, th("local", "none"))["reasons"], ["danger:rm_root"])
        self.assertEqual(providers.ask({}, {}, loc, th(), lambda s, q: REMOTE)["shadow_reasons"], ["danger:rm_root"])
