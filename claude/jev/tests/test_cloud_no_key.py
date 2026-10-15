import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jev_client


class CloudNoKeyTest(unittest.TestCase):
    """Every direct jev_client caller (PreCompact, /handoff) stays off the network in a cloud session."""

    def env(self, **kw):
        base = {"CLAUDE_CODE_REMOTE": "", "DRYAS_JUDGE": "", "OPENROUTER_API_KEY": "x",
                "DRYAS_OPENROUTER_KEY": "", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": ""}
        base.update(kw)
        p = mock.patch.dict(os.environ, base)
        p.start()
        self.addCleanup(p.stop)

    def test_cloud_session_hides_the_key(self):
        self.env(CLAUDE_CODE_REMOTE="true")
        self.assertEqual(jev_client.api_key(), "")

    def test_cloud_opt_in_keeps_the_key(self):
        self.env(CLAUDE_CODE_REMOTE="true", DRYAS_JUDGE="jev")
        self.assertEqual(jev_client.api_key(), "x")

    def test_workstation_keeps_the_key(self):
        self.env()
        self.assertEqual(jev_client.api_key(), "x")

    def test_cloud_judge_makes_no_request(self):
        self.env(CLAUDE_CODE_REMOTE="true")
        with mock.patch.object(jev_client.urllib.request, "urlopen") as urlopen:
            with self.assertRaises(jev_client.JevUnavailable):
                jev_client.judge("ctx", {"safe": {"type": "bool"}})
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
