import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memdb
import memlearn


class PageRankTest(unittest.TestCase):
    def test_star_center_ranks_highest_and_sums_to_one(self):
        r = memlearn.pagerank({("c", "a"): 1, ("c", "b"): 1, ("c", "d"): 1})
        self.assertAlmostEqual(sum(r.values()), 1.0, places=6)
        self.assertEqual(max(r, key=r.get), "c")
        self.assertAlmostEqual(r["a"], r["b"], places=9)

    def test_weights_matter(self):
        r = memlearn.pagerank({("a", "b"): 5, ("a", "c"): 1})
        self.assertGreater(r["b"], r["c"])

    def test_empty_and_self_loops(self):
        self.assertEqual(memlearn.pagerank({}), {})
        self.assertEqual(memlearn.pagerank({("a", "a"): 1}), {})

    def test_task_type(self):
        self.assertEqual(memlearn.task_type("fix(gate): retry"), "fix")
        self.assertEqual(memlearn.task_type("  Feat: x"), "feat")
        self.assertEqual(memlearn.task_type("42"), "other")


class ConsolidateTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {"DRYAS_DB": os.path.join(tempfile.mkdtemp(), "d.db")})
        p.start()
        self.addCleanup(p.stop)
        self.c = memdb.connect()
        self.addCleanup(self.c.close)

    def mem(self, title, body="b", ns="proj", task_id=None, source="dryas", kind="outcome", created=1.0, hits=0, key=None):
        with memdb.tx(self.c):
            return self.c.execute(
                "INSERT INTO memory (ns, kind, title, body, task_id, source, key, hash, created, hits) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ns, kind, title, body, task_id, source, key, memdb.content_hash(title, body), created, hits)).lastrowid

    def edit(self, file, ok=1, session="s1", task=None, ns="proj"):
        with memdb.tx(self.c):
            self.c.execute("INSERT INTO edits (ns, session, task_id, file, ok, ts) VALUES (?, ?, ?, ?, ?, 1.0)",
                           (ns, session, task, file, ok))

    def access(self, session, *ids):
        with memdb.tx(self.c):
            self.c.executemany("INSERT INTO access (session, memory_id, ts) VALUES (?, ?, 1.0)", [(session, i) for i in ids])

    def pats(self, kind, ns="proj"):
        return {r[0]: (r[1], r[2]) for r in self.c.execute(
            "SELECT key, value, support FROM patterns WHERE ns = ? AND kind = ?", (ns, kind))}

    def test_two_sessions_yield_expected_rows_and_ranks(self):
        m1 = self.mem("gate fix", task_id="b:1")
        m2 = self.mem("route fix")
        self.mem("lonely")
        self.access("s1", m1, m2)
        self.access("s2", m1, m2)
        for s, t in (("s1", "b:1"), ("s2", "b:2")):
            self.edit("gate.py", session=s, task=t)
            self.edit("route.py", session=s, task=t)
        self.edit("gate.py", ok=0, session="s2", task="b:2")
        with memdb.tx(self.c):
            self.c.executemany("INSERT INTO tasks (task_id, ns, title, tier_end, ended) VALUES (?, 'proj', ?, ?, 1.0)",
                               [("b:1", "fix(gate): a", "sonnet"), ("b:2", "fix: b", "sonnet"), ("b:3", "feat: c", "opus")])
        out = memlearn.consolidate(self.c, "proj", now=100.0)
        self.assertEqual(self.pats("coedit"), {"gate.py|route.py": ("", 2)})
        self.assertEqual(self.pats("file_fail"), {"gate.py": ("0.3333", 3)})
        self.assertEqual(self.pats("tier"), {"fix": ("sonnet", 2)})
        ranks = self.pats("rank")
        self.assertEqual(set(ranks), {str(m1), str(m2)})
        self.assertGreater(float(ranks[str(m1)][0]), float(ranks[str(m2)][0]))  # m1 also links to its task's files
        self.assertEqual(out["patterns"], 5)
        self.assertEqual(out["ranked"], 2)

    def test_dedupe_keeps_oldest_merges_hits_and_access(self):
        a = self.mem("same", created=1.0, hits=2)
        b = self.mem("same", created=2.0, hits=3)
        r = self.mem("same", source="ruflo", key="e1", created=0.5)
        self.access("s1", b)
        out = memlearn.consolidate(self.c, "proj", now=100.0)
        self.assertEqual(out["deduped"], 1)
        self.assertEqual(sorted(x[0] for x in self.c.execute("SELECT id FROM memory")), sorted([a, r]))
        self.assertEqual(self.c.execute("SELECT hits FROM memory WHERE id = ?", (a,)).fetchone()[0], 5)
        self.assertEqual(self.c.execute("SELECT memory_id FROM access").fetchone()[0], a)

    def test_other_namespace_untouched(self):
        with memdb.tx(self.c):
            self.c.execute("INSERT INTO patterns VALUES ('other', 'file_fail', 'x.py', '0.5', 4, 1.0)")
        for _ in range(3):
            self.edit("y.py", ok=0, ns="other")
        memlearn.consolidate(self.c, "proj", now=100.0)
        self.assertEqual(self.pats("file_fail", ns="other"), {"x.py": ("0.5", 4)})
        self.assertEqual(self.pats("file_fail"), {})

    def test_rerun_is_stable(self):
        m1, m2 = self.mem("a"), self.mem("b")
        self.access("s1", m1, m2)
        memlearn.consolidate(self.c, "proj", now=100.0)
        first = sorted(tuple(r) for r in self.c.execute("SELECT kind, key, value, support FROM patterns"))
        memlearn.consolidate(self.c, "proj", now=200.0)
        self.assertEqual(sorted(tuple(r) for r in self.c.execute("SELECT kind, key, value, support FROM patterns")), first)

    def test_huge_task_is_capped(self):
        for t in ("b:1", "b:2"):
            for i in range(80):
                self.edit("f%02d.py" % i, task=t)
        memlearn.consolidate(self.c, "proj", now=100.0)
        self.assertEqual(len(self.pats("coedit")), 50 * 49 // 2)

    def test_old_access_is_pruned(self):
        m = self.mem("a")
        self.access("s1", m)
        memlearn.consolidate(self.c, "proj", now=1.0 + (memlearn.ACCESS_DAYS + 1) * 86400)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM access").fetchone()[0], 0)
