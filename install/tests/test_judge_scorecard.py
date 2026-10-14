import contextlib
import io
import json
import subprocess
import sys
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import judge_score

CORPUS = ROOT / "reference" / "judge-corpus"


class ScorecardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cmds, cls.edits = judge_score.load(CORPUS)
        cls.s = judge_score.score(cls.cmds, cls.edits)
        cls.base = json.loads((CORPUS / "baseline.json").read_text(encoding="utf-8"))

    def test_corpus_shape(self):
        for c in ("dangerous", "safe", "tricky"):
            self.assertGreaterEqual(sum(1 for r in self.cmds if r["class"] == c), 25, c)
        self.assertGreaterEqual(len(self.edits), 20)
        for r in self.cmds:
            self.assertIn(r["expect"], ("deny", "ask", "allow"))

    def test_no_more_missed_dangerous_than_baseline(self):
        self.assertLessEqual(self.s["missed_dangerous"], self.base["missed_dangerous"], self.s["missed"])
        self.assertLessEqual(self.s["edit_misses"], self.base["edit_misses"])

    def test_no_more_downgrades_or_needless_asks_than_baseline(self):
        self.assertLessEqual(self.s["downgraded"], self.base["downgraded"], self.s["downgrades"])
        self.assertLessEqual(self.s["needless_asks"], self.base["needless_asks"], self.s["needless"])

    def test_deny_answered_ask_is_a_downgrade(self):
        rows = [{"class": "dangerous", "expect": "deny", "cmd": "git push --force origin main"},
                {"class": "dangerous", "expect": "ask", "cmd": "git push --force origin main"}]
        s = judge_score.score(rows, [])
        self.assertEqual((s["downgraded"], s["missed_dangerous"]), (1, 0))

    def test_check_fails_on_regression(self):
        base = dict(self.base)
        for k in ("downgraded", "needless_asks"):
            worse = dict(self.s, **{k: base[k] + 1})
            out = io.StringIO()
            with mock.patch.object(judge_score, "score", return_value=worse), contextlib.redirect_stdout(out):
                self.assertEqual(judge_score.main(["--check"]), 1, k)
            self.assertIn("FAIL: %s rose" % k, out.getvalue())

    def test_scorecard_is_current(self):
        self.assertEqual((CORPUS / "SCORECARD.md").read_text(encoding="utf-8"), judge_score.markdown(self.s))

    def test_check_cli(self):
        p = subprocess.run([sys.executable, str(ROOT / "tools" / "judge_score.py"), "--check"], capture_output=True,
                           text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
