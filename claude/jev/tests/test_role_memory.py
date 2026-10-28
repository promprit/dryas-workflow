import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jev_mcp
import memory_mcp

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FIXTURE = os.path.join(ROOT, "install", "tests", "fixtures", "role-lessons.jsonl")


def call(name, args):
    resp = jev_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})
    res = resp["result"]
    return json.loads(res["content"][0]["text"]), res["isError"]


class RoleMemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "proj")
        self.other = os.path.join(self.tmp, "other")
        os.makedirs(self.proj)
        os.makedirs(self.other)
        self.thr = os.path.join(self.tmp, "thr.json")
        self.logs = os.path.join(self.tmp, "logs")
        p = mock.patch.dict(os.environ, {"DRYAS_DB": os.path.join(self.tmp, "d.db"), "JEV_LOG_DIR": self.logs,
                                         "CLAUDE_PROJECT_DIR": self.proj, "JEV_SESSION_ID": "s1",
                                         "JEV_THRESHOLDS": self.thr})
        p.start()
        self.addCleanup(p.stop)

    def log_lines(self):
        p = os.path.join(self.logs, "memory.jsonl")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def store_from(self, folder, ns, body, title="t"):
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": folder}):
            return call("memory_store", {"namespace": ns, "title": title, "body": body})

    def test_role_search_caps_and_logs(self):
        for n in range(5):
            self.store_from(self.proj, "role-builder", "use Edit not heredocs %d" % n, title="l%d" % n)
        out, _ = call("memory_search", {"namespace": "role-builder", "query": "Edit heredocs", "task": "feat/x:3"})
        self.assertLessEqual(len(out["results"]), 3)
        self.assertGreater(len(out["results"]), 0)
        self.assertLessEqual(sum(len(r["body"]) for r in out["results"]), 600)
        lines = self.log_lines()
        self.assertEqual(len(lines), 1)
        rec = lines[0]
        self.assertEqual((rec["stage"], rec["ok"], rec["task"], rec["role"]), ("role-lessons", True, "feat/x:3", "builder"))
        self.assertEqual(rec["lesson_ids"], [str(r["id"]) for r in out["results"]])

    def test_repo_lessons_first(self):
        self.store_from(self.other, "role-builder", "use Edit not heredocs elsewhere", title="o")
        self.store_from(self.proj, "role-builder", "use Edit not heredocs here", title="p")
        out, _ = call("memory_search", {"namespace": "role-builder", "query": "Edit heredocs"})
        self.assertEqual(out["results"][0]["title"], "p")

    def test_store_tags_repo(self):
        self.store_from(self.proj, "role-reviewer-spec", "check the plan Done line first")
        out, _ = call("memory_list", {"namespace": "role-reviewer-spec"})
        self.assertIn("repo:proj", out["results"][0]["tags"])

    def test_empty_role_namespace_logs_empty_ids(self):
        out, _ = call("memory_search", {"namespace": "role-devils-advocate", "query": "anything", "task": "b:1"})
        self.assertEqual(out["results"], [])
        lines = self.log_lines()
        self.assertEqual((len(lines), lines[0]["lesson_ids"], lines[0]["ok"]), (1, [], True))

    def test_no_task_no_log(self):
        self.store_from(self.proj, "role-builder", "use Edit not heredocs")
        call("memory_search", {"namespace": "role-builder", "query": "Edit"})
        self.assertEqual(self.log_lines(), [])

    def test_budget_keeps_whole_lessons(self):
        self.store_from(self.proj, "role-builder", "alpha " + "y" * 94, title="b")
        self.store_from(self.proj, "role-builder", "alpha alpha alpha alpha " + "x" * 565, title="a")
        out, _ = call("memory_search", {"namespace": "role-builder", "query": "alpha", "task": "b:1"})
        self.assertEqual([len(r["title"]) + len(r["body"]) for r in out["results"]], [590])
        self.assertEqual(self.log_lines()[0]["lesson_ids"], [str(out["results"][0]["id"])])

    def test_response_is_lean(self):
        for n in range(5):
            self.store_from(self.proj, "role-builder", "use Edit not heredocs %d " % n + "x" * 150, title="l%d" % n)
        out, _ = call("memory_search", {"namespace": "role-builder", "query": "Edit heredocs"})
        self.assertGreater(len(out["results"]), 0)
        for r in out["results"]:
            self.assertEqual(set(r), {"id", "title", "body"})
        self.assertLessEqual(len(json.dumps(out["results"])), 900)

    def test_only_returned_lessons_are_touched(self):
        for n in range(6):
            self.store_from(self.proj, "role-builder", "use Edit not heredocs %d" % n, title="l%d" % n)
        out, _ = call("memory_search", {"namespace": "role-builder", "query": "Edit heredocs"})
        self.assertLessEqual(len(out["results"]), 3)
        got = {r["id"] for r in out["results"]}
        with sqlite3.connect(os.environ["DRYAS_DB"]) as db:
            hits = dict(db.execute("SELECT id, hits FROM memory WHERE ns = 'role-builder'").fetchall())
        self.assertEqual(len(hits), 6)
        for i, h in hits.items():
            self.assertEqual(h, 1 if i in got else 0)

    def test_project_folder_named_role_is_not_a_role(self):
        folder = os.path.join(self.tmp, "role-builder")
        os.makedirs(folder)
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": folder}):
            for n in range(6):
                call("memory_store", {"title": "t%d" % n, "body": "gamma lesson %d" % n})
            out, _ = call("memory_search", {"query": "gamma", "limit": 5, "task": "b:1"})
            self.assertEqual(len(out["results"]), 5)
            rows, _ = call("memory_list", {})
            self.assertFalse(any(t.startswith("repo:") for r in rows["results"] for t in r["tags"]))
            with open(self.thr, "w") as f:
                json.dump({"memory": {"role_lessons": False}}, f)
            out, _ = call("memory_store", {"title": "x", "body": "still stored"})
            self.assertIs(out["stored"], True)
        self.assertEqual(self.log_lines(), [])

    def test_unknown_role_slug_is_plain(self):
        for n in range(5):
            self.store_from(self.proj, "role-reviewer_spec", "gamma lesson %d" % n)
        out, _ = call("memory_search", {"namespace": "role-reviewer_spec", "query": "gamma", "limit": 5, "task": "b:1"})
        self.assertEqual(len(out["results"]), 5)
        self.assertEqual(self.log_lines(), [])

    def test_role_store_caps_length(self):
        out, err = self.store_from(self.proj, "role-builder", "x" * 600, title="t")
        self.assertEqual((out["stored"], out["reason"], err), (False, "role lessons are at most 600 characters", True))
        out, err = self.store_from(self.proj, "role-builder", "x" * 599, title="t")
        self.assertIs(out["stored"], True)

    def test_role_store_single_repo_tag(self):
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.proj}):
            call("memory_store", {"namespace": "role-builder", "title": "t", "body": "b", "tags": ["repo:evil", "keep"]})
        out, _ = call("memory_list", {"namespace": "role-builder"})
        self.assertEqual(sorted(out["results"][0]["tags"]), ["keep", "repo:proj"])

    def test_switch_off_only_on_false(self):
        self.store_from(self.proj, "role-builder", "use Edit not heredocs")
        with open(self.thr, "w") as f:
            json.dump({"memory": {"role_lessons": "false"}}, f)
        out, _ = call("memory_search", {"namespace": "role-builder", "query": "Edit"})
        self.assertEqual(len(out["results"]), 1)
        with open(self.thr, "w") as f:
            json.dump({"memory": {"role_lessons": False}}, f)
        out, _ = call("memory_search", {"namespace": "role-builder", "query": "Edit", "task": "b:1"})
        self.assertEqual((out["results"], out["role_lessons"]), ([], "off"))
        self.assertEqual(self.log_lines(), [])
        out, _ = self.store_from(self.proj, "role-builder", "another lesson")
        self.assertIs(out["stored"], False)

    def test_project_namespace_unchanged(self):
        for n in range(6):
            call("memory_store", {"namespace": "proj", "title": "t%d" % n, "body": "gamma lesson %d" % n})
        out, _ = call("memory_search", {"namespace": "proj", "query": "gamma", "limit": 5, "task": "b:1"})
        self.assertEqual(len(out["results"]), 5)
        self.assertEqual(self.log_lines(), [])

    def test_fixture_matches_record(self):
        self.store_from(self.proj, "role-builder", "use Edit not heredocs")
        call("memory_search", {"namespace": "role-builder", "query": "Edit", "task": "b:1"})
        rec = self.log_lines()[0]
        rec.pop("cwd", None)
        with open(FIXTURE, encoding="utf-8") as f:
            lines = [x for x in f if x.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(set(json.loads(lines[0])), set(rec))
        self.assertEqual((rec["stage"], rec["ok"]), ("role-lessons", True))
        self.assertIn(rec["role"], memory_mcp.ROLE_SLUGS)
        self.assertIsInstance(rec["task"], str)
        self.assertIsInstance(rec["lesson_ids"], list)
        self.assertTrue(all(isinstance(i, str) for i in rec["lesson_ids"]))


if __name__ == "__main__":
    unittest.main()
