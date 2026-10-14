import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import thresholds


class TaskThresholdsTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "t.json")
        p = mock.patch.dict(os.environ, {"JEV_THRESHOLDS": self.path})
        p.start()
        self.addCleanup(p.stop)

    def write(self, data):
        with open(self.path, "w") as f:
            json.dump(data, f)

    def test_switches_default_off_with_spec_defaults(self):
        th = thresholds.load()
        self.assertEqual(th["review"], {"task_skip": False, "min_tasks": 50, "max_false_skip_rate": 0.01})
        self.assertEqual(th["history"], {"min_tasks": 30})
        self.assertEqual(th["baseline"], {"until": ""})
        self.assertIs(th["dispatch"]["scored_tier"], False)
        self.assertEqual(th["dispatch"]["min_tasks"], 50)
        self.assertEqual(th["dispatch"]["min_confidence"], 0.7)  # existing keys unchanged

    def test_valid_overrides_load(self):
        self.write({"review": {"task_skip": True, "min_tasks": 80, "max_false_skip_rate": 0.02},
                    "dispatch": {"scored_tier": True, "min_tasks": 60}, "history": {"min_tasks": 40},
                    "baseline": {"until": "2026-11-01"}})
        th = thresholds.load()
        self.assertEqual(th["baseline"]["until"], "2026-11-01")
        self.assertEqual(th["review"], {"task_skip": True, "min_tasks": 80, "max_false_skip_rate": 0.02})
        self.assertEqual((th["dispatch"]["scored_tier"], th["dispatch"]["min_tasks"]), (True, 60))
        self.assertEqual(th["history"]["min_tasks"], 40)

    def test_bad_values_fall_back_to_defaults(self):
        self.write({"review": {"task_skip": "yes", "min_tasks": 0, "max_false_skip_rate": 1.5},
                    "dispatch": {"scored_tier": 1, "min_tasks": True}, "history": {"min_tasks": -3},
                    "baseline": {"until": "soon"}})
        th = thresholds.load()
        self.assertEqual(th["baseline"]["until"], "")
        self.assertEqual(th["review"], {"task_skip": False, "min_tasks": 50, "max_false_skip_rate": 0.01})
        self.assertEqual((th["dispatch"]["scored_tier"], th["dispatch"]["min_tasks"]), (False, 50))
        self.assertEqual(th["history"]["min_tasks"], 30)

    def test_validate_messages(self):
        self.assertIsNone(thresholds.validate("review.task_skip", True))
        self.assertIsNone(thresholds.validate("review.max_false_skip_rate", 0))
        self.assertIsNone(thresholds.validate("history.min_tasks", 30))
        self.assertIn("[1, 100000]", thresholds.validate("dispatch.min_tasks", 0))
        self.assertIn("[0.0, 1.0]", thresholds.validate("review.max_false_skip_rate", 2.0))
        self.assertIn("Type mismatch", thresholds.validate("dispatch.scored_tier", "true"))
        self.assertIsNone(thresholds.validate("baseline.until", "2026-11-01"))
        self.assertIsNone(thresholds.validate("baseline.until", ""))
        self.assertIn("YYYY-MM-DD", thresholds.validate("baseline.until", "next week"))


if __name__ == "__main__":
    unittest.main()
