import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jev_client
import judge_policy


class JevClientGuardTest(unittest.TestCase):
    def setUp(self):
        judge_policy.clear_cache()
        self.addCleanup(judge_policy.clear_cache)
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.marked = os.path.join(self.tmp, "VOID", "Pilot")
        os.makedirs(self.marked)
        open(os.path.join(self.tmp, "VOID", ".dryas-judge"), "w").write("local\n")
        p = mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k"})
        p.start()
        self.addCleanup(p.stop)

    def opener(self, *a, **k):
        raise AssertionError("network call under a marker")

    def test_state_cwd_under_marker_refuses(self):
        with self.assertRaises(jev_client.JevUnavailable) as e:
            jev_client.judge({"cwd": self.marked}, {}, opener=self.opener)
        self.assertEqual(str(e.exception), "project_local")

    def test_process_directory_under_marker_refuses(self):
        for state in ({}, {"cwd": ""}, {"cwd": None}, {"cwd": 7}, "not a dict"):
            judge_policy.clear_cache()
            with mock.patch("os.getcwd", return_value=self.marked):
                with self.assertRaises(jev_client.JevUnavailable, msg=repr(state)) as e:
                    jev_client.judge(state, {}, opener=self.opener)
            self.assertEqual(str(e.exception), "project_local", repr(state))


if __name__ == "__main__":
    unittest.main()
