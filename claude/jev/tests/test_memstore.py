import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memdb
import memstore


def fts5_here():
    c = sqlite3.connect(":memory:")
    try:
        c.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        return True
    except sqlite3.Error:
        return False
    finally:
        c.close()


class StoreCases:
    NO_FTS = "1"

    def setUp(self):
        p = mock.patch.dict(os.environ, {"DRYAS_DB": os.path.join(tempfile.mkdtemp(), "d.db"), "DRYAS_NO_FTS": self.NO_FTS})
        p.start()
        self.addCleanup(p.stop)
        self.c = memdb.connect()
        self.addCleanup(self.c.close)
        self.assertEqual(self.c.fts, self.NO_FTS != "1")

    def put(self, title, body, ns="proj", **kw):
        return memstore.store(self.c, ns, title, body, **kw)

    def ids(self, query, ns="proj", **kw):
        return [x["id"] for x in memstore.search(self.c, ns, query, **kw)["results"]]

    def test_stored_row_comes_back_and_other_ns_is_empty(self):
        r = self.put("gate retry", "Worked: retry the hook once. Failed: a longer timeout.", task_id="b:1", commit="abc123")
        self.assertTrue(r["stored"])
        hit = memstore.search(self.c, "proj", "hook retry")["results"][0]
        self.assertEqual((hit["id"], hit["task_id"], hit["commit"], hit["kind"]), (r["id"], "b:1", "abc123", "outcome"))
        self.assertIn("matched 2 of 2 terms", hit["reason"])
        self.assertEqual(self.ids("hook retry", ns="other"), [])

    def test_mem4_refusals(self):
        cases = {"secret": ("deploy", "ran it with PASSWORD=hunter2hunter2 set"),
                 "diff": ("patch", "diff --git a/x.py b/x.py\n@@ -1,2 +1,2 @@\n-a\n+b"),
                 "size": ("big", "x" * (memstore.MAX_BODY + 1)),
                 "title": ("t" * (memstore.MAX_TITLE + 1), "fine"),
                 "empty": ("", "  ")}
        for why, (t, b) in cases.items():
            with self.assertRaises(memstore.Rejected, msg=why):
                self.put(t, b)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM memory").fetchone()[0], 0)

    def test_prose_about_tokens_is_stored(self):
        self.assertTrue(self.put("auth", "fix token: refresh flow; the password field is now masked")["stored"])

    def test_duplicate_returns_existing_id(self):
        a = self.put("T", "same body")
        self.assertEqual(self.put("t", "same   body"), {"id": a["id"], "stored": False, "duplicate": True})

    def test_archive_left_out_unless_asked(self):
        a = self.put("cmd", "git status ran fine", kind="archive")
        self.assertEqual(self.ids("status"), [])
        self.assertEqual(self.ids("status", include_archive=True), [a["id"]])

    def test_ranking_terms_first_then_graph_rank(self):
        a = self.put("alpha", "router cache")
        b = self.put("bravo", "router only")
        c = self.put("charlie", "router again")
        with memdb.tx(self.c):
            self.c.execute("INSERT INTO patterns VALUES ('proj', 'rank', ?, '0.5', 3, 1.0)", (str(c["id"]),))
        res = memstore.search(self.c, "proj", "router cache", limit=3)["results"]
        self.assertEqual([x["id"] for x in res], [a["id"], c["id"], b["id"]])
        self.assertIn("graph rank 1.00", res[1]["reason"])

    def test_prefix_match_is_the_same_on_both_backends(self):
        a = self.put("tests", "testing the gate")
        self.assertEqual(self.ids("test"), [a["id"]])
        self.assertEqual(self.ids("esting"), [])

    def test_query_syntax_characters_are_plain_words(self):
        a = self.put("quote", 'fixed the "NEAR" parser (fts) - café AND bar*')
        for q in ('"NEAR"', "fts)", "AND", "bar*", "-café", "NOT OR", "'; DROP TABLE memory; --", "^", ""):
            self.assertIsInstance(memstore.search(self.c, "proj", q)["results"], list, q)
        self.assertEqual(self.ids("near parser"), [a["id"]])
        self.assertEqual(self.ids("café"), [a["id"]])

    def test_empty_query_returns_most_recent(self):
        self.put("old", "one", created=1.0)
        b = self.put("new", "two", created=2.0)
        res = memstore.search(self.c, "proj", "", limit=1)["results"]
        self.assertEqual([x["id"] for x in res], [b["id"]])
        self.assertEqual(res[0]["reason"], "most recent (no search terms)")

    def test_patterns_come_with_reasons(self):
        with memdb.tx(self.c):
            self.c.executemany("INSERT INTO patterns VALUES (?, ?, ?, ?, ?, 1.0)", [
                ("proj", "file_fail", "claude/jev/gate.py", "0.2500", 8),
                ("proj", "coedit", "claude/jev/gate.py|claude/jev/route.py", "", 3),
                ("proj", "tier", "fix", "sonnet", 4),
                ("proj", "rank", "1", "0.4", 2),
                ("other", "file_fail", "claude/jev/gate.py", "0.9", 9)])
        pats = memstore.search(self.c, "proj", "gate fix")["patterns"]
        self.assertEqual([p["reason"] for p in pats], [
            "claude/jev/gate.py: 25% of 8 edits failed",
            "fix tasks finished at tier sonnet (4 tasks)",
            "claude/jev/gate.py and claude/jev/route.py were edited together in 3 tasks"])

    def test_search_counts_use_and_records_access(self):
        a = self.put("alpha", "beta")
        memstore.search(self.c, "proj", "alpha", session="s1")
        row = self.c.execute("SELECT hits, accessed FROM memory WHERE id = ?", (a["id"],)).fetchone()
        self.assertEqual(row["hits"], 1)
        self.assertIsNotNone(row["accessed"])
        self.assertEqual([tuple(r) for r in self.c.execute("SELECT session, memory_id FROM access")], [("s1", a["id"])])

    def test_list_and_forget(self):
        a = self.put("one", "first", created=1.0)
        b = self.put("two", "second", created=2.0)
        self.assertEqual([x["id"] for x in memstore.list_entries(self.c, "proj")], [b["id"], a["id"]])
        self.assertEqual(memstore.forget(self.c, "other", a["id"]), "not found")
        self.assertEqual(memstore.forget(self.c, "proj", a["id"]), "forgotten")
        self.assertEqual([x["id"] for x in memstore.list_entries(self.c, "proj")], [b["id"]])
        self.assertEqual(memstore.forget(self.c, "proj", a["id"]), "not found")

    def test_notes_cannot_be_forgotten(self):
        n = memstore.store(self.c, "proj", "note", "from MEMORY.md", kind="note", source="claude-memory",
                           key="/x/MEMORY.md", check_content=False)
        self.assertEqual(memstore.forget(self.c, "proj", n["id"]), "note")

    def test_forgotten_keyed_row_is_remembered(self):
        r = memstore.store(self.c, "proj", "imported", "row", source="ruflo", key="entry_1", check_content=False)
        memstore.forget(self.c, "proj", r["id"])
        self.assertEqual([tuple(x) for x in self.c.execute("SELECT ns, source, key FROM forgotten")],
                         [("proj", "ruflo", "entry_1")])

    def test_read_only_store_still_searches(self):
        a = self.put("alpha", "beta")
        self.c.execute("PRAGMA user_version = 99")
        self.c.close()
        ro = memdb.connect()
        self.addCleanup(ro.close)
        self.assertTrue(ro.readonly)
        self.assertEqual([x["id"] for x in memstore.search(ro, "proj", "alpha")["results"]], [a["id"]])

    def test_concurrent_writers_lose_nothing(self):
        # Transactions must not lose writes. Writers wait generously for the lock: the default 1.5 s busy timeout is
        # a hook-latency budget (a busy store fails fast, MEM-5), and a slow CI runner can exceed it under contention.
        path = os.environ["DRYAS_DB"]
        errors = []

        def work(n):
            try:
                c = memdb.connect(path, busy_ms=60000)
                try:
                    for i in range(25):
                        memstore.store(c, "proj", "w%d-%d" % (n, i), "body %d %d" % (n, i))
                finally:
                    c.close()
            except Exception as e:  # a dead worker must fail the test with its reason, not a short count
                errors.append("writer %d: %r" % (n, e))

        threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM memory").fetchone()[0], 100)


class LikeStoreTest(StoreCases, unittest.TestCase):
    NO_FTS = "1"


@unittest.skipUnless(fts5_here(), "sqlite without FTS5")
class FtsStoreTest(StoreCases, unittest.TestCase):
    NO_FTS = "0"
