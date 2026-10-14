import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memdb


def fts5_here():
    c = sqlite3.connect(":memory:")
    try:
        c.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        return True
    except sqlite3.Error:
        return False
    finally:
        c.close()


class MemDbTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "sub", "dryas.db")
        p = mock.patch.dict(os.environ, {"DRYAS_DB": self.path})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("DRYAS_NO_FTS", None)

    def insert(self, conn, title="t", body="b"):
        with memdb.tx(conn):
            return conn.execute("INSERT INTO memory (ns, kind, title, body, hash, created) VALUES ('p', 'outcome', ?, ?, ?, 1.0)",
                                (title, body, memdb.content_hash(title, body))).lastrowid

    def test_creates_schema_wal_and_version(self):
        conn = memdb.connect()
        self.addCleanup(conn.close)
        self.assertEqual(memdb.db_path(), self.path)
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
        for t in ("memory", "edits", "tasks", "sessions", "patterns", "access", "forgotten", "kv"):
            self.assertIn(t, names)
        self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], memdb.SCHEMA_VERSION)
        self.assertFalse(conn.readonly)

    def test_default_path_is_under_the_data_root(self):
        root = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": root}):
            os.environ.pop("DRYAS_DB")
            self.assertEqual(memdb.db_path(), os.path.join(root, "dryas.db"))

    def test_reconnect_keeps_rows_and_migrate_is_idempotent(self):
        c = memdb.connect()
        self.insert(c)
        c.close()
        c = memdb.connect()
        self.addCleanup(c.close)
        memdb.migrate(c)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM memory").fetchone()[0], 1)

    def test_tx_rolls_back_on_error(self):
        c = memdb.connect()
        self.addCleanup(c.close)
        with self.assertRaises(RuntimeError):
            with memdb.tx(c):
                c.execute("INSERT INTO kv(key, value) VALUES ('a', 'b')")
                raise RuntimeError("boom")
        self.assertEqual(c.execute("SELECT COUNT(*) FROM kv WHERE key = 'a'").fetchone()[0], 0)

    @unittest.skipUnless(fts5_here(), "sqlite without FTS5")
    def test_fts_index_follows_insert_update_delete(self):
        c = memdb.connect()
        self.addCleanup(c.close)
        self.assertTrue(c.fts)
        mid = self.insert(c, "alpha", "bravo")

        def q(word):
            return [r[0] for r in c.execute("SELECT rowid FROM memory_fts WHERE memory_fts MATCH ?", (word,))]

        self.assertEqual(q("bravo"), [mid])
        with memdb.tx(c):
            c.execute("UPDATE memory SET body = 'charlie' WHERE id = ?", (mid,))
        self.assertEqual(q("bravo"), [])
        self.assertEqual(q("charlie"), [mid])
        with memdb.tx(c):
            c.execute("DELETE FROM memory WHERE id = ?", (mid,))
        self.assertEqual(q("charlie"), [])

    @unittest.skipUnless(fts5_here(), "sqlite without FTS5")
    def test_fts_toggle_keeps_writes_and_rebuilds(self):
        memdb.connect().close()
        with mock.patch.dict(os.environ, {"DRYAS_NO_FTS": "1"}):
            c = memdb.connect()
            self.assertFalse(c.fts)
            self.assertEqual([r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")], [])
            mid = self.insert(c, "while", "offline")
            c.close()
        c = memdb.connect()
        self.addCleanup(c.close)
        self.assertTrue(c.fts)
        self.assertEqual([r[0] for r in c.execute("SELECT rowid FROM memory_fts WHERE memory_fts MATCH 'offline'")], [mid])

    def test_without_fts_inserts_work(self):
        with mock.patch.dict(os.environ, {"DRYAS_NO_FTS": "1"}):
            c = memdb.connect()
            self.addCleanup(c.close)
            self.assertFalse(c.fts)
            self.insert(c)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM memory").fetchone()[0], 1)

    def test_newer_schema_opens_read_only(self):
        c = memdb.connect()
        self.insert(c)
        c.execute("PRAGMA user_version = 99")
        c.close()
        c = memdb.connect()
        self.addCleanup(c.close)
        self.assertTrue(c.readonly)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM memory").fetchone()[0], 1)
        with self.assertRaises(sqlite3.OperationalError):
            c.execute("INSERT INTO kv(key, value) VALUES ('x', 'y')")

    def test_unopenable_path_raises(self):
        with self.assertRaises((sqlite3.Error, OSError)):
            memdb.connect(tempfile.mkdtemp())  # a directory, not a file

    def test_content_hash_ignores_case_and_spacing(self):
        self.assertEqual(memdb.content_hash("A  b", "c\n"), memdb.content_hash("a b", " c"))
        self.assertNotEqual(memdb.content_hash("a", "b"), memdb.content_hash("a", "c"))
