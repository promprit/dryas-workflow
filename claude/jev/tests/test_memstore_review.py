import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memdb
import memstore
from test_memstore import fts5_here


class ReviewCases:
    NO_FTS = "1"

    def setUp(self):
        p = mock.patch.dict(os.environ, {"DRYAS_DB": os.path.join(tempfile.mkdtemp(), "d.db"), "DRYAS_NO_FTS": self.NO_FTS})
        p.start()
        self.addCleanup(p.stop)
        self.c = memdb.connect()
        self.addCleanup(self.c.close)
        self.assertEqual(self.c.fts, self.NO_FTS != "1")

    def put(self, title, body, **kw):
        return memstore.store(self.c, "proj", title, body, **kw)

    def count(self, table="memory"):
        return self.c.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]

    def test_secret_in_tags_or_commit_is_refused(self):
        cases = {"tags": {"tags": ["sk-ant-api03-abcdefghijklmnopqrstuvwx"]},
                 "commit": {"commit": "ghp_abcdefghijklmnopqrstuvwxyz0123"},
                 "task_id": {"task_id": "ghp_abcdefghijklmnopqrstuvwxyz0123"}}
        for why, kw in cases.items():
            with self.assertRaises(memstore.Rejected, msg=why):
                self.put("deploy", "plain prose", **kw)
        self.assertEqual(self.count(), 0)

    def test_text_equal_to_archive_row_stores_a_new_row(self):
        a = self.put("cmd", "git status ran fine", kind="archive")
        b = self.put("cmd", "git status ran fine")
        self.assertTrue(b["stored"])
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual([x["id"] for x in memstore.search(self.c, "proj", "status")["results"]], [b["id"]])

    def test_same_top_ten_beyond_the_old_candidate_cut(self):
        ids = []
        for i in range(300):
            body = "alpha " + ("filler " * 40 if i >= 150 else "")
            ids.append(self.put("row%d" % i, body, created=1000.0 + i)["id"])
        got = [x["id"] for x in memstore.search(self.c, "proj", "alpha", limit=10)["results"]]
        self.assertEqual(got, ids[:-11:-1])

    def test_non_ascii_word_is_found(self):
        a = self.put("Über refactor", "split the module")
        self.assertEqual([x["id"] for x in memstore.search(self.c, "proj", "über")["results"]], [a["id"]])

    def test_empty_query_does_not_touch(self):
        self.put("one", "body")
        memstore.search(self.c, "proj", "", session="s1")
        self.assertEqual(self.c.execute("SELECT SUM(hits) FROM memory").fetchone()[0], 0)
        self.assertEqual(self.count("access"), 0)

    def test_search_body_is_capped(self):
        self.put("big", "word " * 2000, kind="note", check_content=False)
        hit = memstore.search(self.c, "proj", "word")["results"][0]
        self.assertLessEqual(len(hit["body"]), memstore.MAX_BODY)


class LikeReviewTest(ReviewCases, unittest.TestCase):
    NO_FTS = "1"


@unittest.skipUnless(fts5_here(), "sqlite without FTS5")
class FtsReviewTest(ReviewCases, unittest.TestCase):
    NO_FTS = "0"


if __name__ == "__main__":
    unittest.main()
