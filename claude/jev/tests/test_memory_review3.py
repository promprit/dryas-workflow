import json
import os
import random
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import jev_mcp
import memdb
import memhooks
import memlearn

SECRET = "sk-ant-api03-" + "A1b2C3d4" * 4


def call(name, args):
    resp = jev_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})
    res = resp["result"]
    return json.loads(res["content"][0]["text"]), res["isError"]


class ReviewThreeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.proj, ".git"))
        with open(os.path.join(self.proj, ".git", "HEAD"), "w") as f:
            f.write("ref: refs/heads/feat/b\n")
        self.dbpath = os.path.join(self.tmp, "d.db")
        p = mock.patch.dict(os.environ, {"DRYAS_DB": self.dbpath, "JEV_LOG_DIR": os.path.join(self.tmp, "logs"),
                                         "CLAUDE_PROJECT_DIR": self.proj, "JEV_SESSION_ID": "s1",
                                         "DRYAS_NOTES_DIR": os.path.join(self.tmp, "none")})
        p.start()
        self.addCleanup(p.stop)
        self.now = time.time()

    def db(self):
        c = memdb.connect()
        self.addCleanup(c.close)
        return c

    def add_memories(self, c, n):
        c.executemany("INSERT INTO memory (id, ns, kind, title, hash, created) VALUES (?, 'proj', 'task', ?, ?, ?)",
                      [(i, "m%d" % i, "h%d" % i, self.now) for i in range(1, n + 1)])
        c.commit()

    def access(self, c, session, ids):
        c.executemany("INSERT INTO access (session, memory_id, ts) VALUES (?, ?, ?)",
                      [(session, i, self.now) for i in ids])
        c.commit()

    def test_pagerank_check_called_per_iteration(self):
        calls = []

        def check():
            calls.append(1)
            if len(calls) == 3:
                raise RuntimeError("stop")
        with self.assertRaises(RuntimeError):
            memlearn.pagerank({("a", "b"): 1.0, ("b", "c"): 1.0}, tol=0.0, check=check)
        self.assertEqual(len(calls), 3)

    def test_pagerank_result_unchanged_by_check(self):
        e = {("a", "b"): 1.0, ("b", "c"): 2.0}
        self.assertEqual(memlearn.pagerank(e), memlearn.pagerank(e, check=lambda: None))

    def test_deadline_interrupts_pagerank(self):
        c = self.db()
        self.add_memories(c, 3)
        self.access(c, "s", [1, 2, 3])
        c.execute("INSERT INTO patterns (ns, kind, key, value, support, updated) VALUES ('proj', 'rank', '99', 'old', 1, 0)")
        c.commit()

        def slow(edges, check=None, **kw):
            for _ in range(5):
                time.sleep(0.3)
                check()
            return {}
        t0 = time.monotonic()
        with mock.patch.object(memlearn, "pagerank", slow):
            out = memlearn.consolidate(c, "proj", now=self.now, deadline=time.monotonic() + 0.5)
        self.assertLess(time.monotonic() - t0, 1.2)
        self.assertEqual(out["skipped"], "deadline")
        rows = c.execute("SELECT key, value FROM patterns WHERE ns = 'proj'").fetchall()
        self.assertEqual([(r[0], r[1]) for r in rows], [("99", "old")])

    def test_max_edges_keeps_heaviest(self):
        c = self.db()
        self.add_memories(c, 8)
        n = 0
        for (a, b), w in (((1, 2), 5), ((3, 4), 4), ((5, 6), 3), ((7, 8), 1)):
            for _ in range(w):
                n += 1
                self.access(c, "s%d" % n, [a, b])
        with mock.patch.object(memlearn, "MAX_EDGES", 3):
            memlearn.consolidate(c, "proj", now=self.now)
        keys = {r[0] for r in c.execute("SELECT key FROM patterns WHERE kind = 'rank'")}
        self.assertTrue(keys)
        self.assertTrue(keys <= {"1", "2", "3", "4", "5", "6"}, keys)

    def test_row_caps(self):
        c = self.db()
        self.add_memories(c, 3)
        self.access(c, "s", [1, 2, 3])
        for t in ("t1", "t2"):
            c.executemany("INSERT INTO edits (ns, session, task_id, file, ok, ts) VALUES ('proj', 's', ?, ?, 1, ?)",
                          [(t, f, self.now) for f in ("a", "b", "c")])
        c.commit()
        with mock.patch.object(memlearn, "MAX_RANK_ROWS", 1), mock.patch.object(memlearn, "MAX_COEDIT_ROWS", 1):
            memlearn.consolidate(c, "proj", now=self.now)
        for kind in ("rank", "coedit"):
            self.assertEqual(c.execute("SELECT COUNT(*) FROM patterns WHERE kind = ?", (kind,)).fetchone()[0], 1, kind)

    def test_dense_store_fits_budget(self):
        c = self.db()
        rnd = random.Random(7)
        self.add_memories(c, 2000)
        c.executemany("INSERT INTO access (session, memory_id, ts) VALUES (?, ?, ?)",
                      [("a%d" % (i % 100), 1 + i, self.now) for i in range(2000)])
        c.executemany("INSERT INTO edits (ns, session, task_id, file, ok, ts) VALUES ('proj', ?, NULL, ?, ?, ?)",
                      [("e%d" % (i % 200), "f%d" % rnd.randrange(400), rnd.randrange(2), self.now - i)
                       for i in range(20000)])
        c.commit()
        t0 = time.monotonic()
        out = memlearn.consolidate(c, "proj", now=self.now, deadline=t0 + 1.2)
        took = time.monotonic() - t0
        print("dense consolidate: %.2fs %s" % (took, out.get("skipped", "completed")))
        self.assertLess(took, 2.5)  # 1.6 flaked at load average 35; measured 0.5-1.4 s

    def test_deadline_constant_leaves_headroom(self):
        self.assertEqual(memhooks.CONSOLIDATE_DEADLINE_S, 1.2)

    def test_swarm_init_redacts_before_truncating(self):
        task = "x" * 189 + " " + SECRET + "y" * 100
        scope = ["z" * 189 + " " + SECRET + "w" * 100]
        out, err = call("swarm_init", {"task": task, "scope": scope})
        self.assertFalse(err)
        r = self.db().execute("SELECT title, scope FROM tasks WHERE task_id = ?", (out["swarmId"],)).fetchone()
        for text in (r["title"], r["scope"]):
            self.assertIn("[REDACTED", text)
            self.assertNotIn(SECRET[:12], text)
            self.assertNotIn("A1b2C3d4", text)
        self.assertLessEqual(len(r["title"]), 200)
