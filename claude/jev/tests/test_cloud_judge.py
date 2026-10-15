import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jev_client  # noqa: F401  (imported so mock.patch can find jev_client.judge)
import providers

AUTO = {"judge": {"provider": "auto", "shadow": "auto"}}
LOCAL = {"answers": {"safe": {"value": True, "confidence": 0.9}}, "reasons": ["local"]}


class CloudJudgeTest(unittest.TestCase):
    def env(self, **kw):
        base = {"CLAUDE_CODE_REMOTE": "", "DRYAS_JUDGE": ""}
        base.update(kw)
        p = mock.patch.dict(os.environ, base)
        p.start()
        self.addCleanup(p.stop)

    def key(self, present):
        p = mock.patch.object(providers, "_has_key", return_value=present)
        p.start()
        self.addCleanup(p.stop)

    def test_auto_is_local_in_a_cloud_session_even_with_a_key(self):
        self.env(CLAUDE_CODE_REMOTE="true")
        self.key(True)
        self.assertEqual(providers.resolve(AUTO, False), ("local", "none"))

    def test_cloud_session_never_calls_jev(self):
        self.env(CLAUDE_CODE_REMOTE="TRUE")
        self.key(True)
        with mock.patch("jev_client.judge", side_effect=AssertionError("network call")):
            out = providers.ask({}, {}, LOCAL, AUTO)
        self.assertEqual((out["provider"], out["shadow_provider"]), ("local", "none"))
        self.assertEqual(out["answers"], LOCAL["answers"])
        self.assertNotIn("fallback", out)

    def test_opt_in_uses_jev(self):
        self.env(CLAUDE_CODE_REMOTE="true", DRYAS_JUDGE="jev")
        self.key(True)
        self.assertEqual(providers.resolve(AUTO, False), ("jev", "local"))

    def test_opt_in_without_a_key_stays_local(self):
        self.env(CLAUDE_CODE_REMOTE="true", DRYAS_JUDGE="jev")
        self.key(False)
        self.assertEqual(providers.resolve(AUTO, False), ("local", "none"))

    def test_explicit_provider_is_kept_in_the_cloud(self):
        self.env(CLAUDE_CODE_REMOTE="true")
        self.key(True)
        self.assertEqual(providers.resolve({"judge": {"provider": "jev", "shadow": "none"}}, False), ("jev", "none"))

    def test_outside_the_cloud_nothing_changes(self):
        self.env(CLAUDE_CODE_REMOTE="false")
        with mock.patch.object(providers, "_has_key", return_value=True):
            self.assertEqual(providers.resolve(AUTO, False), ("jev", "local"))
        with mock.patch.object(providers, "_has_key", return_value=False):
            self.assertEqual(providers.resolve(AUTO, False), ("local", "none"))
        self.assertEqual(providers.resolve(AUTO, True), ("jev", "local"))


class CloudEnvEdgeTest(unittest.TestCase):
    """Added: wrong env parsing would still pass the plan's tests (exact "true"/"jev" values only)."""

    def env(self, drop=(), **kw):
        p = mock.patch.dict(os.environ, kw)
        p.start()
        self.addCleanup(p.stop)
        for k in drop:
            os.environ.pop(k, None)
        p = mock.patch.object(providers, "_has_key", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def test_only_true_marks_a_cloud_session(self):
        for v in ("1", "yes", "on", "truex", "false", ""):
            with self.subTest(remote=v):
                self.env(CLAUDE_CODE_REMOTE=v, DRYAS_JUDGE="")
                self.assertFalse(providers._cloud_without_jev())
                self.assertEqual(providers.resolve(AUTO, False), ("jev", "local"))
        for v in ("true", "True", " TRUE ", "true\n"):
            with self.subTest(remote=v):
                self.env(CLAUDE_CODE_REMOTE=v, DRYAS_JUDGE="")
                self.assertTrue(providers._cloud_without_jev())
                self.assertEqual(providers.resolve(AUTO, False), ("local", "none"))

    def test_remote_unset_is_not_cloud(self):
        self.env(drop=("CLAUDE_CODE_REMOTE", "DRYAS_JUDGE"))
        self.assertFalse(providers._cloud_without_jev())
        self.assertEqual(providers.resolve(AUTO, False), ("jev", "local"))

    def test_judge_unset_with_a_key_stays_local(self):
        self.env(drop=("DRYAS_JUDGE",), CLAUDE_CODE_REMOTE="true")
        self.assertEqual(providers.resolve(AUTO, False), ("local", "none"))

    def test_opt_in_tolerates_case_and_spaces(self):
        for v in ("JEV", " jev ", "Jev\t"):
            with self.subTest(judge=v):
                self.env(CLAUDE_CODE_REMOTE="true", DRYAS_JUDGE=v)
                self.assertFalse(providers._cloud_without_jev())
                self.assertEqual(providers.resolve(AUTO, False), ("jev", "local"))

    def test_other_judge_values_do_not_opt_in(self):
        for v in ("local", "jevx", "1", "true"):
            with self.subTest(judge=v):
                self.env(CLAUDE_CODE_REMOTE="true", DRYAS_JUDGE=v)
                self.assertEqual(providers.resolve(AUTO, False), ("local", "none"))

    def test_explicit_jev_in_thresholds_is_kept_in_the_cloud(self):
        self.env(CLAUDE_CODE_REMOTE="true", DRYAS_JUDGE="")
        self.assertEqual(providers.resolve({"judge": {"provider": "jev", "shadow": "auto"}}, False), ("jev", "local"))
        self.assertEqual(providers.resolve({"judge": {"provider": "local", "shadow": "auto"}}, False), ("local", "none"))

    def test_injected_judge_still_decides_in_the_cloud(self):
        self.env(CLAUDE_CODE_REMOTE="true", DRYAS_JUDGE="")
        self.assertEqual(providers.resolve(AUTO, True), ("jev", "local"))


if __name__ == "__main__":
    unittest.main()
