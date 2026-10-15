import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools"))
import compare_v1


def summary(asks=0, denied=20, wrong=0, p50=100.0, lo=90.0, hi=110.0):
    return {"asks": asks, "denied_expected": denied, "denied_total_expected": 20, "wrong_denies": wrong,
            "p50_ms": p50, "range_ms": [lo, hi]}


class CompareV1Test(unittest.TestCase):
    def test_verdict_rules(self):
        v1 = summary(asks=0, denied=0)  # 1.0 never looked at shell commands
        self.assertEqual(compare_v1.verdict(v1, summary()), [])
        self.assertTrue(compare_v1.verdict(v1, summary(asks=1)))           # any prompt fails
        self.assertTrue(compare_v1.verdict(v1, summary(denied=19)))        # must catch every out-of-scope target
        self.assertTrue(compare_v1.verdict(v1, summary(wrong=1)))          # must not deny in-scope work
        self.assertTrue(compare_v1.verdict(v1, summary(p50=150.0, lo=140.0, hi=160.0)))  # slower beyond noise
        self.assertEqual(compare_v1.verdict(v1, summary(p50=105.0, lo=95.0, hi=115.0)), [])  # within noise

    def test_catches_no_less_than_v1(self):
        self.assertTrue(compare_v1.verdict(summary(denied=20), summary(denied=18)))


if __name__ == "__main__":
    unittest.main()
