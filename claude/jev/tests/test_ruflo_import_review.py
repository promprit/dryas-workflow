import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memcli
import memdb
import ruflo_import
from test_ruflo_import import RUFLO_SCHEMA


def make(path, rows):
    """rows: (id, key, namespace, content, tags, metadata)"""
    c = sqlite3.connect(path)
    c.execute(RUFLO_SCHEMA)
    for i, k, ns, content, tags, meta in rows:
        c.execute("INSERT INTO memory_entries (id, key, namespace, content, tags, metadata, created_at, updated_at) "
                  "VALUES (?, ?, ?, ?, ?, ?, 1791028252776, 1791028252776)", (i, k, ns, content, tags, meta))
    c.commit()
    c.close()


class ImportReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, {"DRYAS_DB": os.path.join(self.tmp, "d.db")})
        p.start()
        self.addCleanup(p.stop)
        self.c = memdb.connect()
        self.addCleanup(self.c.close)

    def src(self, name, rows):
        path = os.path.join(self.tmp, name)
        make(path, rows)
        return path

    def test_title_tags_and_metadata_are_redacted(self):
        src = self.src("a.db", [("r1", "deploy API_KEY=abcd1234efgh", "proj", "plain text",
                                 '["password=hunter22x", "ok"]', "Authorization: Bearer abcdefghijklmnop")])
        rep = ruflo_import.import_ruflo(self.c, src)
        self.assertEqual(rep["redacted"], 1)
        r = self.c.execute("SELECT title, tags, meta FROM memory").fetchone()
        for text, secret in ((r["title"], "abcd1234efgh"), (r["tags"], "hunter22x"), (r["meta"], "abcdefghijklmnop")):
            self.assertNotIn(secret, text)
            self.assertIn("[REDACTED]", text)

    def test_namespace_is_sanitized(self):
        rep = ruflo_import.import_ruflo(self.c, self.src("b.db", [("r1", "k", "my proj", "x", None, None)]))
        self.assertIn("my_proj", rep["namespaces"])
        self.assertTrue(rep["ok"])
        self.assertEqual(self.c.execute("SELECT ns FROM memory").fetchone()[0], "my_proj")

    def test_changed_row_is_updated_and_new_row_added(self):
        ruflo_import.import_ruflo(self.c, self.src("c1.db", [("1", "k1", "p", "old body", None, None)]))
        self.c.execute("UPDATE memory SET hits = 7, accessed = 5.0")
        self.c.commit()
        rep = ruflo_import.import_ruflo(self.c, self.src("c2.db", [("1", "k1", "p", "new body", '["t"]', None),
                                                                   ("2", "k2", "p", "fresh", None, None)]))
        self.assertEqual((rep["updated"], rep["new"], rep["ok"]), (1, 1, True))
        r = self.c.execute("SELECT body, tags, hits, accessed FROM memory WHERE key = '1'").fetchone()
        self.assertEqual((r["body"], json.loads(r["tags"]), r["hits"], r["accessed"]), ("new body", ["t"], 7, 5.0))
        again = ruflo_import.import_ruflo(self.c, self.src("c3.db", [("1", "k1", "p", "new body", '["t"]', None)]))
        self.assertEqual(again["updated"], 0)

    def test_forgotten_key_is_not_updated(self):
        ruflo_import.import_ruflo(self.c, self.src("d1.db", [("1", "k1", "p", "old", None, None)]))
        with memdb.tx(self.c):
            self.c.execute("DELETE FROM memory")
            self.c.execute("INSERT INTO forgotten (ns, source, key, ts) VALUES ('p', 'ruflo', '1', 1.0)")
        rep = ruflo_import.import_ruflo(self.c, self.src("d2.db", [("1", "k1", "p", "changed", None, None)]))
        self.assertEqual((rep["updated"], rep["new"], rep["ok"]), (0, 0, True))

    def test_row_dropped_from_store_is_reported_missing(self):
        with memdb.tx(self.c):
            self.c.execute("CREATE TRIGGER drop_two AFTER INSERT ON memory WHEN NEW.key = '2' "
                           "BEGIN DELETE FROM memory WHERE id = NEW.id; END")
        rep = ruflo_import.import_ruflo(self.c, self.src("e.db", [("1", "a", "p", "x", None, None),
                                                                  ("2", "b", "p", "y", None, None)]))
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["namespaces"]["p"]["missing"], 1)


class CliFailureTest(unittest.TestCase):
    def test_stats_on_unopenable_db_exits_1_with_one_line(self):
        tmp = tempfile.mkdtemp()
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = memcli.main(["--db", tmp, "stats"])
        self.assertEqual(rc, 1)
        self.assertTrue(err.getvalue().startswith("stats failed: "))
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
