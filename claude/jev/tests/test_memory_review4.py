import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memdb
import memlearn


class ReviewFourTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {"DRYAS_DB": os.path.join(tempfile.mkdtemp(), "d.db")})
        p.start()
        self.addCleanup(p.stop)
        self.c = memdb.connect()
        self.addCleanup(self.c.close)

    def mem(self, title, body="b", task_id=None):
        with memdb.tx(self.c):
            return self.c.execute(
                "INSERT INTO memory (ns, kind, title, body, task_id, source, hash, created) "
                "VALUES ('proj', 'outcome', ?, ?, ?, 'dryas', ?, 1.0)",
                (title, body, task_id, memdb.content_hash(title, body))).lastrowid

    def edit(self, file, session="s1", task=None):
        with memdb.tx(self.c):
            self.c.execute("INSERT INTO edits (ns, session, task_id, file, ok, ts) VALUES ('proj', ?, ?, ?, 1, 1.0)",
                           (session, task, file))

    def access(self, session, *ids):
        with memdb.tx(self.c):
            self.c.executemany("INSERT INTO access (session, memory_id, ts) VALUES (?, ?, 1.0)",
                               [(session, i) for i in ids])

    def small_store(self):
        m1, m2 = self.mem("a", task_id="t:1"), self.mem("b")
        self.access("s1", m1, m2)
        self.edit("x.py", task="t:1")
        self.edit("y.py", task="t:1")

    def patterns(self):
        return self.c.execute("SELECT kind, key, value, support FROM patterns ORDER BY kind, key").fetchall()

    def run_counting(self):
        events = []
        orig_pairs, orig_rank = memlearn._pairs, memlearn.pagerank

        def pairs(items):
            events.append("pairs")
            return orig_pairs(items)

        def rank(edges, **kw):
            events.append("rank")
            return orig_rank(edges, **kw)
        with mock.patch.object(memlearn, "_pairs", pairs), mock.patch.object(memlearn, "pagerank", rank):
            memlearn._consolidate(self.c, "proj", 2.0, lambda: events.append("check"))
        return events

    def test_check_runs_after_each_edge_phase(self):
        self.small_store()
        ev = self.run_counting()
        last_pairs = max(i for i, e in enumerate(ev) if e == "pairs")
        # co-edit phase end and memory-to-file link phase end each get a check before PageRank
        self.assertGreaterEqual(ev[last_pairs:ev.index("rank")].count("check"), 2)
        first_pairs = ev.index("pairs")
        self.assertIn("check", ev[first_pairs:last_pairs])

    def test_dedupe_checks_once_per_duplicate_group(self):
        for body in ("one", "two"):
            for _ in range(3):
                with memdb.tx(self.c):
                    self.c.execute("INSERT INTO memory (ns, kind, title, body, source, hash, created) "
                                   "VALUES ('proj', 'outcome', 't', ?, 'dryas', ?, 1.0)",
                                   (body, memdb.content_hash("t", body)))
        calls = []
        self.assertEqual(memlearn._dedupe(self.c, "proj", lambda: calls.append(1)), 4)
        self.assertEqual(len(calls), 2)

    def test_small_store_results_unchanged_by_cap_path(self):
        self.small_store()
        memlearn.consolidate(self.c, "proj", now=2.0)
        base = self.patterns()
        self.assertTrue(base)
        with mock.patch.object(memlearn, "MAX_EDGES", 10 ** 9):
            memlearn.consolidate(self.c, "proj", now=2.0)
        self.assertEqual(self.patterns(), base)

    def test_cap_keeps_heaviest_edges_by_weight_then_key(self):
        seen = {}
        orig = memlearn.pagerank

        def spy(edges, **kw):
            seen.update(edges)
            return orig(edges, **kw)
        files = ["a.py", "b.py", "c.py", "d.py"]
        for n, group in enumerate((files, files[:3], files[:2], files[:2])):
            for f in group:
                self.edit(f, session="s%d" % n)
        with mock.patch.object(memlearn, "MAX_EDGES", 3), mock.patch.object(memlearn, "pagerank", spy):
            memlearn.consolidate(self.c, "proj", now=2.0)
        self.assertEqual(sorted(seen), [("f:a.py", "f:b.py"), ("f:a.py", "f:c.py"), ("f:b.py", "f:c.py")])
        self.assertEqual(seen[("f:a.py", "f:b.py")], 4)

    def test_pair_loop_checks_on_work_done(self):
        def checks(n):
            with memdb.tx(self.c):
                self.c.execute("DELETE FROM edits")
            for i in range(n):
                self.edit("f%03d.py" % i, session="big")
            calls = []
            with mock.patch.object(memlearn, "MAX_GROUP", n), \
                    mock.patch.object(memlearn, "pagerank", lambda e, **k: {}):  # keep PageRank checks out
                memlearn._consolidate(self.c, "proj", 2.0, lambda: calls.append(1))
            return len(calls)
        small = checks(5)
        self.assertGreaterEqual(checks(320) - small, 2)  # 320 files -> 51,040 pair increments


if __name__ == "__main__":
    unittest.main()
