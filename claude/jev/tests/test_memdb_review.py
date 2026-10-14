"""Review round 1: store file privacy, per-project task key, namespace lookup without a git subprocess."""
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memdb
import projns


def git(*args, cwd):
    subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=t"] + list(args), cwd=str(cwd), check=True,
                   capture_output=True)


def mode(p):
    return stat.S_IMODE(os.stat(p).st_mode)


class MemDbReviewTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "sub", "dryas.db")
        p = mock.patch.dict(os.environ, {"DRYAS_DB": self.path})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("DRYAS_NO_FTS", None)
        old = os.umask(0o022)  # a typical user umask: files would be 0644 without the fix
        self.addCleanup(os.umask, old)

    def write(self, conn, ns="p"):
        with memdb.tx(conn):
            conn.execute("INSERT INTO memory (ns, kind, title, body, hash, created) VALUES (?, 'outcome', 't', 'b', ?, 1.0)",
                         (ns, memdb.content_hash("t", "b")))

    @unittest.skipUnless(os.name == "posix", "POSIX file modes")
    def test_wal_and_shm_are_private(self):
        conn = memdb.connect()
        self.addCleanup(conn.close)
        self.write(conn)
        for suffix in ("", "-wal", "-shm"):
            self.assertTrue(os.path.exists(self.path + suffix), suffix)
            self.assertEqual(mode(self.path + suffix), 0o600, suffix)

    @unittest.skipUnless(os.name == "posix", "POSIX file modes")
    def test_open_store_is_tightened_on_reconnect(self):
        conn = memdb.connect()
        self.write(conn)
        conn.close()
        os.chmod(self.path, 0o644)  # portable-ok: test sets a loose POSIX mode; skipped unless os.name is posix
        conn = memdb.connect()
        self.addCleanup(conn.close)
        self.write(conn)
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(self.path + suffix):
                self.assertEqual(mode(self.path + suffix), 0o600, suffix)
        self.assertEqual(mode(self.path), 0o600)

    def test_same_task_id_in_two_namespaces_keeps_two_rows(self):
        conn = memdb.connect()
        self.addCleanup(conn.close)
        for ns in ("alpha", "beta", "beta"):
            with memdb.tx(conn):
                conn.execute("INSERT INTO tasks (task_id, ns, title) VALUES ('main:1', ?, ?) "
                             "ON CONFLICT(ns, task_id) DO UPDATE SET title = excluded.title", (ns, ns + "-t"))
        rows = conn.execute("SELECT ns, title FROM tasks WHERE task_id = 'main:1' ORDER BY ns").fetchall()
        self.assertEqual([tuple(r) for r in rows], [("alpha", "alpha-t"), ("beta", "beta-t")])


class ProjNsNoSubprocessTest(unittest.TestCase):
    def test_worktree_and_main_resolve_without_subprocess(self):
        repo = Path(tempfile.mkdtemp()) / "myrepo"
        repo.mkdir()
        git("init", "-q", cwd=repo)
        git("commit", "-q", "--allow-empty", "-m", "i", cwd=repo)
        git("worktree", "add", "-q", ".worktrees/wt", "-b", "wt", cwd=repo)
        wt = repo / ".worktrees" / "wt"
        sub = wt / "deep" / "er"
        sub.mkdir(parents=True)
        with mock.patch("subprocess.run", side_effect=AssertionError("no subprocess expected")):
            for start in (repo, wt, sub):
                self.assertEqual(projns.project_ns(str(start)), "myrepo", start)
                self.assertEqual(os.path.realpath(projns.main_root(str(start))), os.path.realpath(str(repo)), start)

    def test_plain_dir_without_git_returns_basename(self):
        d = Path(tempfile.mkdtemp()) / "plain dir"
        d.mkdir()
        self.assertEqual(projns.project_ns(str(d)), "plain_dir")
        self.assertIsNone(projns.main_root(str(d)))


if __name__ == "__main__":
    unittest.main()
