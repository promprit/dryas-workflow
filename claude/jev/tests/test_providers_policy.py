import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import judge_policy
import providers

LOCAL = {"answers": {"safe": {"type": "noul", "value": 0.9, "confidence": 0.9},
                     "risk": {"type": "choice", "value": "routine", "confidence": 0.9, "probabilities": {}}},
         "reasons": []}
NOKEY = {"OPENROUTER_API_KEY": "", "DRYAS_OPENROUTER_KEY": "", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": ""}


class ProvidersPolicyTest(unittest.TestCase):
    def setUp(self):
        judge_policy.clear_cache()
        self.addCleanup(judge_policy.clear_cache)
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.marked = os.path.join(self.tmp, "VOID", "Pilot")
        os.makedirs(self.marked)
        open(os.path.join(self.tmp, "VOID", ".dryas-judge"), "w").write("local\n")
        self.plain = os.path.join(self.tmp, "plain")
        os.makedirs(self.plain)

    def test_marker_beats_jev_settings_and_key(self):
        with mock.patch.dict(os.environ, dict(NOKEY, OPENROUTER_API_KEY="k")):
            for th in ({"judge": {"provider": "jev", "shadow": "jev"}}, {"judge": {"provider": "auto"}}, {}):
                for injected in (False, True):
                    self.assertEqual(providers.resolve(th, injected, self.marked), ("local", "none"))

    def test_no_marker_is_unchanged(self):
        with mock.patch.dict(os.environ, dict(NOKEY, OPENROUTER_API_KEY="k")):
            self.assertEqual(providers.resolve({}, False, self.plain), ("jev", "local"))

    def test_policy_names_project_local(self):
        self.assertEqual(providers.policy(self.marked), "project_local")
        self.assertIsNone(providers.policy(self.plain))

    def test_ask_never_calls_judge_and_reports_policy(self):
        calls = []
        out = providers.ask({}, {}, LOCAL, {"judge": {"provider": "jev"}},
                            lambda s, q: calls.append(1) or {}, cwd=self.marked)
        self.assertEqual(calls, [])
        self.assertEqual((out["provider"], out["shadow_provider"], out["judge_policy"]),
                         ("local", "none", "project_local"))
        self.assertNotIn("fallback", out)

    def test_ask_without_marker_has_no_policy_field(self):
        with mock.patch.dict(os.environ, NOKEY):
            out = providers.ask({}, {}, LOCAL, {}, cwd=self.plain)
        self.assertNotIn("judge_policy", out)


if __name__ == "__main__":
    unittest.main()
