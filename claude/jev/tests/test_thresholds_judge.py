import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import thresholds


class JudgeThresholdsTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "t.json")
        p = mock.patch.dict(os.environ, {"JEV_THRESHOLDS": self.path})
        p.start()
        self.addCleanup(p.stop)

    def write(self, data):
        with open(self.path, "w") as f:
            json.dump(data, f)

    def test_defaults_are_auto(self):
        self.assertEqual(thresholds.load()["judge"], {"provider": "auto", "shadow": "auto"})

    def test_valid_values_load(self):
        self.write({"judge": {"provider": "local", "shadow": "jev"}})
        self.assertEqual(thresholds.load()["judge"], {"provider": "local", "shadow": "jev"})

    def test_invalid_values_fall_back(self):
        self.write({"judge": {"provider": "remote", "shadow": 3}})
        self.assertEqual(thresholds.load()["judge"], {"provider": "auto", "shadow": "auto"})

    def test_validate_messages(self):
        self.assertIsNone(thresholds.validate("judge.provider", "jev"))
        self.assertIsNone(thresholds.validate("judge.shadow", "none"))
        self.assertIn("must be one of", thresholds.validate("judge.provider", "remote"))
        self.assertIn("must be one of", thresholds.validate("judge.shadow", "always"))
