import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rules_inject
import tune_memory

ROWS = [dict(stage="session-end", error="ConsolidateSkipped", detail="budget", ts="2026-10-15T10:00:00+0700"),
        dict(stage="session-end", error="ConsolidateSkipped", detail="deadline", ts="2026-10-15T11:00:00+0700"),
        dict(stage="session-end", error="ConsolidateSkipped", detail="deadline", ts="2026-10-15T12:00:00+0700"),
        dict(stage="consolidate", ns="repo", ok=True, ms=3300, ts="2026-10-15T12:01:00+0700"),
        dict(stage="consolidate", ns="repo", ok=False, ms=10, ts="2026-10-15T12:02:00+0700"),
        dict(stage="edit", error="OperationalError", detail="locked", ts="2026-10-15T12:03:00+0700")]


class TuneMemoryTest(unittest.TestCase):
    def test_summary_counts(self):
        s = tune_memory.summary(ROWS)
        self.assertEqual(s, {"skipped_budget": 1, "skipped_deadline": 2, "background_runs": 1, "background_failed": 1})

    def test_lines_have_stable_labels(self):
        text = "\n".join(tune_memory.lines(tune_memory.summary(ROWS)))
        self.assertIn("- Memory consolidation skipped in hooks: 3 (budget 1, deadline 2)", text)
        self.assertIn("- Background consolidation runs: 1 ok, 1 failed", text)

    def test_empty_log(self):
        self.assertIn("- Memory consolidation skipped in hooks: 0", "\n".join(tune_memory.lines(tune_memory.summary([]))))


class WarningTest(unittest.TestCase):
    def test_repeated_skips_without_a_finished_run_warn(self):
        rows = [r for r in ROWS if r.get("ok") is not True]
        now = 1792041200.0  # 2026-10-15 ~12:13 +0700
        self.assertIn("dryas memory consolidate", rules_inject.consolidate_warning(rows, now))

    def test_a_finished_run_after_the_skips_silences_it(self):
        self.assertEqual(rules_inject.consolidate_warning(ROWS, 1792041200.0), "")
