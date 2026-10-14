import hashlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memcli
import memdb
import ruflo_import

RUFLO_SCHEMA = """CREATE TABLE memory_entries (id TEXT PRIMARY KEY, key TEXT NOT NULL, namespace TEXT DEFAULT 'default',
  content TEXT NOT NULL, type TEXT DEFAULT 'semantic', embedding TEXT, embedding_model TEXT DEFAULT 'local',
  embedding_dimensions INTEGER, tags TEXT, metadata TEXT, owner_id TEXT, created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL, expires_at INTEGER, last_accessed_at INTEGER, access_count INTEGER DEFAULT 0,
  status TEXT DEFAULT 'active', provenance_type TEXT DEFAULT 'unknown', UNIQUE(namespace, key))"""

ROWS = [
    ("e1", "task7-helpers", "dryas-workflow", "Task 7: verify the patch table. Worked: tester then coder.", "[0.1, 0.2]",
     '["success"]', 1791028252776, 3),
    ("e2", "flow-1", "flowobserve", "Reducer golden replay caught a field rename.", None, None, 1791028252000, 0),
    ("e3", "cmd-1", "commands", '{"command":"ls -la","exitCode":0}', None, '["success"]', 1790958703544, 0),
    ("e4", "cmd-2", "commands", '{"command":"PASSWORD=hunter2hunter2 make deploy"}', None, None, 1790958703545, 0),
    ("e5", "fb-1", "feedback", '{"success":true}', None, "not json", 1790958752930, 0),
    ("e6", "session-x", "session", '{"summary":"0 tasks"}', None, '["session-end"]', 1790959178040, 0),
]


def make_source(path, rows=ROWS):
    c = sqlite3.connect(path)
    c.execute(RUFLO_SCHEMA)
    for i, k, ns, content, emb, tags, ts, hits in rows:
        c.execute("INSERT INTO memory_entries (id, key, namespace, content, embedding, tags, created_at, updated_at, "
                  "access_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (i, k, ns, content, emb, tags, ts, ts, hits))
    c.commit()
    c.close()


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class ImportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "agentdb-memory.db")
        make_source(self.src)
        p = mock.patch.dict(os.environ, {"DRYAS_DB": os.path.join(self.tmp, "d.db")})
        p.start()
        self.addCleanup(p.stop)
        self.c = memdb.connect()
        self.addCleanup(self.c.close)

    def test_imports_every_row_and_verifies_counts(self):
        rep = ruflo_import.import_ruflo(self.c, self.src)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["new"], 6)
        self.assertEqual(rep["namespaces"]["commands"], {"source": 2, "imported": 2, "forgotten": 0})
        kinds = {r[0]: r[1] for r in self.c.execute("SELECT key, kind FROM memory")}
        self.assertEqual(kinds, {"e1": "outcome", "e2": "outcome", "e3": "archive", "e4": "archive",
                                 "e5": "archive", "e6": "archive"})
        r = self.c.execute("SELECT * FROM memory WHERE key = 'e1'").fetchone()
        self.assertEqual((r["ns"], r["title"], r["source"], r["hits"]), ("dryas-workflow", "task7-helpers", "ruflo", 3))
        self.assertAlmostEqual(r["created"], 1791028252.776, places=3)
        self.assertEqual(bytes(r["embedding"]), b"[0.1, 0.2]")
        self.assertEqual(json.loads(r["tags"]), ["success"])
        self.assertEqual(json.loads(r["meta"])["ruflo_id"], "e1")
        self.assertEqual(json.loads(self.c.execute("SELECT tags FROM memory WHERE key = 'e5'").fetchone()[0]), [])

    def test_idempotent(self):
        ruflo_import.import_ruflo(self.c, self.src)
        rep = ruflo_import.import_ruflo(self.c, self.src)
        self.assertEqual((rep["new"], rep["ok"]), (0, True))
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM memory").fetchone()[0], 6)

    def test_source_is_left_unchanged(self):
        before = sha(self.src)
        ruflo_import.import_ruflo(self.c, self.src)
        self.assertEqual(sha(self.src), before)

    def test_secrets_redacted_and_counted(self):
        rep = ruflo_import.import_ruflo(self.c, self.src)
        self.assertEqual(rep["redacted"], 1)
        body = self.c.execute("SELECT body FROM memory WHERE key = 'e4'").fetchone()[0]
        self.assertIn("[REDACTED]", body)
        self.assertNotIn("hunter2", body)

    def test_older_schema_and_odd_values(self):
        old = os.path.join(self.tmp, "old.db")
        c = sqlite3.connect(old)
        c.execute("CREATE TABLE memory_entries (id TEXT PRIMARY KEY, key TEXT, namespace TEXT, content TEXT, created_at INTEGER)")
        c.executemany("INSERT INTO memory_entries VALUES (?, ?, ?, ?, ?)",
                      [("o1", "k", "proj", "hello", 1700000000), ("o2", None, None, None, None)])
        c.commit()
        c.close()
        t0 = time.time()
        rep = ruflo_import.import_ruflo(self.c, old)
        self.assertTrue(rep["ok"])
        r1 = self.c.execute("SELECT created, ns FROM memory WHERE key = 'o1'").fetchone()
        self.assertEqual((r1["created"], r1["ns"]), (1700000000.0, "proj"))
        r2 = self.c.execute("SELECT ns, title, body, created FROM memory WHERE key = 'o2'").fetchone()
        self.assertEqual((r2["ns"], r2["title"], r2["body"]), ("default", "", ""))
        self.assertGreaterEqual(r2["created"], t0)

    def test_forgotten_rows_stay_forgotten(self):
        ruflo_import.import_ruflo(self.c, self.src)
        with memdb.tx(self.c):
            self.c.execute("DELETE FROM memory WHERE key = 'e1'")
            self.c.execute("INSERT INTO forgotten (ns, source, key, ts) VALUES ('dryas-workflow', 'ruflo', 'e1', 1.0)")
        rep = ruflo_import.import_ruflo(self.c, self.src)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["namespaces"]["dryas-workflow"], {"source": 1, "imported": 0, "forgotten": 1})
        self.assertIsNone(self.c.execute("SELECT id FROM memory WHERE key = 'e1'").fetchone())

    def test_not_a_ruflo_db_raises(self):
        other = os.path.join(self.tmp, "other.db")
        sqlite3.connect(other).close()
        with self.assertRaises(ValueError):
            ruflo_import.import_ruflo(self.c, other)
        with self.assertRaises(FileNotFoundError):
            ruflo_import.import_ruflo(self.c, os.path.join(self.tmp, "missing.db"))


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "agentdb-memory.db")
        make_source(self.src)
        p = mock.patch.dict(os.environ, {"DRYAS_DB": os.path.join(self.tmp, "d.db"), "DRYAS_DATA_ROOT": self.tmp})
        p.start()
        self.addCleanup(p.stop)

    def cli(self, *argv):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = memcli.main(list(argv))
        return rc, out.getvalue()

    def test_import_prints_counts_and_exits_zero(self):
        rc, out = self.cli("import-ruflo", "--from", self.src)
        self.assertEqual(rc, 0)
        self.assertIn("verified", out)
        self.assertIn("(archive)", next(l for l in out.splitlines() if l.startswith("commands")))

    def test_missing_source_exits_2(self):
        rc, out = self.cli("import-ruflo")  # default source under DRYAS_DATA_ROOT/ruflo does not exist
        self.assertEqual(rc, 2)
        self.assertIn("nothing to import", out)

    def test_stats(self):
        self.cli("import-ruflo", "--from", self.src)
        rc, out = self.cli("stats", "--ns", "commands")
        self.assertEqual((rc, out.split()), (0, ["commands", "archive", "2"]))
