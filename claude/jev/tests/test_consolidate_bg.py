import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import consolidate_bg as bg
import memdb


class LockTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def test_second_run_exits_while_locked(self):
        fd = bg.acquire(self.root)
        self.assertIsNotNone(fd)
        self.assertIsNone(bg.acquire(self.root))
        bg.release(self.root, fd)
        fd2 = bg.acquire(self.root)
        self.assertIsNotNone(fd2)
        bg.release(self.root, fd2)

    def test_stale_lock_is_taken_over(self):
        fd = bg.acquire(self.root)
        os.close(fd)  # crashed run: fd gone, file left behind
        old = time.time() - bg.STALE_S - 5
        os.utime(os.path.join(self.root, bg.LOCK_NAME), (old, old))
        fd2 = bg.acquire(self.root)
        self.assertIsNotNone(fd2)
        bg.release(self.root, fd2)


class PendingTest(unittest.TestCase):
    def test_mark_list_clear(self):
        conn = memdb.connect(os.path.join(tempfile.mkdtemp(), "d.db"))
        bg.mark_pending(conn, "repo")
        bg.mark_pending(conn, "repo")
        self.assertEqual(bg.pending(conn), ["repo"])
        bg.clear_pending(conn, "repo")
        self.assertEqual(bg.pending(conn), [])
        conn.close()


class SpawnTest(unittest.TestCase):
    def test_spawn_is_detached_and_silent(self):
        with mock.patch("subprocess.Popen") as P:
            self.assertTrue(bg.spawn("repo"))
        args, kw = P.call_args
        self.assertTrue(args[0][-2:] == ["--ns", "repo"] and "consolidate" in args[0] and "memcli.py" in args[0][args[0].index("consolidate") - 1])
        self.assertIn("stdin", kw)
        if os.name == "nt":
            self.assertTrue(kw.get("creationflags"))
        else:
            self.assertTrue(kw.get("start_new_session"))

    def test_spawn_failure_returns_false(self):
        with mock.patch("subprocess.Popen", side_effect=OSError("no")):
            self.assertFalse(bg.spawn(None))


class HookTest(unittest.TestCase):
    """mem-session-end marks and spawns on a skip; mem-session-start retries pending work."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, {"DRYAS_DB": os.path.join(self.d, "d.db"), "DRYAS_DATA_ROOT": self.d,
                                         "JEV_LOG_DIR": self.d})
        p.start()
        self.addCleanup(p.stop)

    def test_skip_marks_and_spawns(self):
        import memhooks
        with mock.patch.object(memhooks.memlearn, "consolidate", return_value={"skipped": "deadline"}), \
                mock.patch.object(memhooks.consolidate_bg, "spawn", return_value=True) as sp:
            conn = memdb.connect()
            out = memhooks.on_session_end(conn, {"session_id": "s", "cwd": self.d}, None, time.monotonic())
            self.assertEqual(out["consolidate_skipped"], "deadline")
            self.assertEqual(bg.pending(conn), [memhooks.projns.project_ns(self.d)])
            conn.close()
        sp.assert_called_once()

    def test_session_start_retries_pending_once_unlocked(self):
        import memhooks
        conn = memdb.connect()
        bg.mark_pending(conn, "repo")
        with mock.patch.object(memhooks.consolidate_bg, "spawn", return_value=True) as sp:
            memhooks.on_session_start(conn, {"session_id": "s2", "cwd": self.d})
        sp.assert_called_once_with("repo")
        conn.close()
