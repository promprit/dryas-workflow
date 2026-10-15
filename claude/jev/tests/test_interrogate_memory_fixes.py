"""Interrogate fixes for background consolidation (owned core D, Task 20): per-namespace runs, failure backoff,
lock heartbeat, and a warning that names the full wrapper path."""
import io
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import consolidate_bg as bg
import memcli
import memdb
import memhooks
import paths
import rules_inject


def _ts(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t))


class MemoryFixTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.db = os.path.join(self.d, "d.db")
        p = mock.patch.dict(os.environ, {"DRYAS_DB": self.db, "DRYAS_DATA_ROOT": self.d, "JEV_LOG_DIR": self.d})
        p.start()
        self.addCleanup(p.stop)
        self.conn = memdb.connect(self.db)
        self.addCleanup(self.conn.close)

    def _start(self):
        with mock.patch.object(memhooks.consolidate_bg, "spawn", return_value=True) as sp:
            memhooks.on_session_start(self.conn, {"session_id": "s", "cwd": self.d})
        return [c.args[0] for c in sp.call_args_list]

    def _cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = memcli.main(["--db", self.db, "consolidate"] + list(args))
        return rc, out.getvalue()

    # fix 1
    def test_session_start_spawns_pending_namespaces_only(self):
        bg.mark_pending(self.conn, "alpha")
        bg.mark_pending(self.conn, "beta")
        self.assertEqual(sorted(self._start()), ["alpha", "beta"])

    def test_session_start_spawns_at_most_five(self):
        for i in range(7):
            bg.mark_pending(self.conn, "ns%d" % i)
        spawned = self._start()
        self.assertEqual(len(spawned), 5)
        self.assertNotIn(None, spawned)

    def test_nothing_pending_spawns_nothing(self):
        self.assertEqual(self._start(), [])

    def test_background_run_waits_for_the_lock_instead_of_dropping_its_namespace(self):
        bg.mark_pending(self.conn, "alpha")
        fd = bg.acquire(self.d)
        threading.Timer(0.3, bg.release, (self.d, fd)).start()
        with mock.patch.object(memcli.memlearn, "consolidate",
                               return_value={"deduped": 0, "edges": 0, "ranked": 0, "patterns": 0}):
            rc, out = self._cli("--wait", "5", "--ns", "alpha")
        self.assertEqual(rc, 0)
        self.assertNotIn("already running", out)
        self.assertEqual(bg.pending(self.conn), [])

    def test_spawned_run_waits_for_the_lock(self):
        with mock.patch("subprocess.Popen") as P:
            bg.spawn("alpha")
        self.assertIn("--wait", P.call_args.args[0])

    def test_manual_run_without_wait_still_exits_at_once(self):
        fd = bg.acquire(self.d)
        self.addCleanup(bg.release, self.d, fd)
        rc, out = self._cli("--ns", "alpha")
        self.assertEqual(rc, 0)
        self.assertIn("already running", out)

    # fix 2
    def _fail(self, *args):
        with mock.patch.object(memcli.memlearn, "consolidate", side_effect=sqlite3.OperationalError("boom")):
            return self._cli(*args)

    def test_three_failed_runs_stop_the_session_start_spawn(self):
        bg.mark_pending(self.conn, "alpha")
        self._fail("--ns", "alpha")
        self._fail("--ns", "alpha")
        self.assertEqual(self._start(), ["alpha"])
        self._fail("--ns", "alpha")
        self.assertEqual(self._start(), [])
        self.assertEqual(bg.pending(self.conn), ["alpha"])  # still pending: a manual run can finish it

    def test_marker_value_counts_failures(self):
        bg.mark_pending(self.conn, "alpha")
        self._fail("--ns", "alpha")
        self._fail()  # the all-namespaces run counts too
        v = self.conn.execute("SELECT value FROM kv WHERE key = ?", (bg.PREFIX + "alpha",)).fetchone()[0]
        self.assertEqual(v.split("|")[1], "2")

    def test_a_new_skip_does_not_reset_the_backoff(self):
        bg.mark_pending(self.conn, "alpha")
        for _ in range(3):
            self._fail("--ns", "alpha")
        bg.mark_pending(self.conn, "alpha")
        self.assertEqual(self._start(), [])

    def test_success_clears_the_marker(self):
        bg.mark_pending(self.conn, "alpha")
        self._fail("--ns", "alpha")
        with mock.patch.object(memcli.memlearn, "consolidate",
                               return_value={"deduped": 0, "edges": 0, "ranked": 0, "patterns": 0}):
            self._cli("--ns", "alpha")
        self.assertEqual(bg.pending(self.conn), [])

    def test_failure_of_a_namespace_that_was_not_pending_does_not_mark_it(self):
        self._fail("--ns", "alpha")
        self.assertEqual(bg.pending(self.conn), [])

    def test_legacy_marker_without_a_count_is_still_spawned(self):
        with memdb.tx(self.conn):
            self.conn.execute("INSERT INTO kv (key, value) VALUES (?, ?)", (bg.PREFIX + "alpha", str(time.time())))
        self.assertEqual(self._start(), ["alpha"])

    def test_session_end_does_not_spawn_a_backed_off_namespace(self):
        ns = memhooks.projns.project_ns(self.d)
        bg.mark_pending(self.conn, ns)
        for _ in range(3):
            self._fail("--ns", ns)
        with mock.patch.object(memhooks.memlearn, "consolidate", return_value={"skipped": "deadline"}), \
                mock.patch.object(memhooks.consolidate_bg, "spawn", return_value=True) as sp:
            memhooks.on_session_end(self.conn, {"session_id": "s", "cwd": self.d}, None, time.monotonic())
        sp.assert_not_called()

    def test_three_failed_rows_warn_with_the_command(self):
        now = time.time()
        rows = [dict(stage="consolidate", ns="alpha", ok=False, ts=_ts(now - 30 + i)) for i in range(3)]
        line = rules_inject.consolidate_warning(rows, now)
        self.assertIn("consolidation failed 3 times for alpha", line)
        self.assertIn("`%s memory consolidate --ns alpha`" % rules_inject.wrapper(), line)
        self.assertIn("memory.jsonl", line)

    def test_a_later_success_silences_the_failure_warning(self):
        now = time.time()
        rows = [dict(stage="consolidate", ns="alpha", ok=False, ts=_ts(now - 30 + i)) for i in range(3)]
        rows.append(dict(stage="consolidate", ns="alpha", ok=True, ts=_ts(now - 10)))
        self.assertEqual(rules_inject.consolidate_warning(rows, now), "")

    def test_two_failures_do_not_warn(self):
        now = time.time()
        rows = [dict(stage="consolidate", ns="alpha", ok=False, ts=_ts(now - 30 + i)) for i in range(2)]
        self.assertEqual(rules_inject.consolidate_warning(rows, now), "")

    # fix 3
    def test_lock_is_touched_before_each_namespace(self):
        lock = os.path.join(self.d, bg.LOCK_NAME)
        ages = []

        def run(conn, ns):
            ages.append(time.time() - os.path.getmtime(lock))
            old = time.time() - 1000
            os.utime(lock, (old, old))  # a long namespace: the lock looks old by the next one
            return {"deduped": 0, "edges": 0, "ranked": 0, "patterns": 0}

        bg.mark_pending(self.conn, "alpha")
        bg.mark_pending(self.conn, "beta")
        with mock.patch.object(memcli.memlearn, "consolidate", side_effect=run):
            self._cli()
        self.assertEqual(len(ages), 2)
        self.assertLess(ages[1], 60)

    # fix 4
    def test_skip_warning_names_the_full_wrapper_path(self):
        now = time.time()
        rows = [dict(stage="session-end", error="ConsolidateSkipped", ts=_ts(now - 30 + i)) for i in range(3)]
        line = rules_inject.consolidate_warning(rows, now)
        self.assertIn("`%s memory consolidate`" % rules_inject.wrapper(), line)

    def test_windows_names_the_cmd_wrapper(self):
        now = time.time()
        rows = [dict(stage="session-end", error="ConsolidateSkipped", ts=_ts(now - 30 + i)) for i in range(3)]
        with mock.patch.object(rules_inject.os, "name", "nt"):
            line = rules_inject.consolidate_warning(rows, now)
        self.assertIn(os.path.join(paths.plugin_root(), "bin", "dryas.cmd") + " memory consolidate", line)


if __name__ == "__main__":
    unittest.main()
