import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jev_mcp
import memdb


def call(name, args):
    resp = jev_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})
    res = resp["result"]
    return json.loads(res["content"][0]["text"]), res["isError"]


class MemoryMcpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj)
        p = mock.patch.dict(os.environ, {"DRYAS_DB": os.path.join(self.tmp, "d.db"), "JEV_LOG_DIR": os.path.join(self.tmp, "logs"),
                                         "CLAUDE_PROJECT_DIR": self.proj, "JEV_SESSION_ID": "s1"})
        p.start()
        self.addCleanup(p.stop)

    def test_tools_listed_after_the_jev_tools(self):
        names = [t["name"] for t in jev_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]]
        self.assertEqual(names[-5:], ["memory_search", "memory_store", "memory_list", "memory_forget", "swarm_init"])
        for old in ("jev_judge", "log_escalation", "log_override", "log_dispatch", "log_review", "log_merge"):
            self.assertIn(old, names[:-5])

    def test_ruflo_argument_names_work(self):
        out, err = call("memory_store", {"key": "task7", "value": "Worked: tester then coder", "namespace": "my app"})
        self.assertFalse(err)
        self.assertEqual((out["stored"], out["namespace"]), (True, "my_app"))
        out, _ = call("memory_search", {"query": "tester", "namespace": "my app"})
        self.assertEqual(out["results"][0]["title"], "task7")

    def test_default_namespace_is_the_project(self):
        out, _ = call("memory_store", {"title": "t", "body": "b"})
        self.assertEqual(out["namespace"], "proj")

    def test_store_needs_a_body_and_reports_refusals(self):
        out, err = call("memory_store", {"title": "x"})
        self.assertTrue(err)
        self.assertIn("body", out["reason"])
        out, err = call("memory_store", {"title": "x", "body": "diff --git a/f b/f\n@@ -1 +1 @@\n-a\n+b"})
        self.assertEqual((err, out["stored"]), (True, False))

    def test_object_value_is_stored_as_json(self):
        out, err = call("memory_store", {"key": "cfg", "value": {"retries": 2}})
        self.assertFalse(err)
        res, _ = call("memory_search", {"query": "retries"})
        self.assertEqual(json.loads(res["results"][0]["body"]), {"retries": 2})

    def test_retro_kind_is_kept(self):
        # spec D: /retro stores its outcome with kind "retro" so the next task's memory_search finds it
        out, err = call("memory_store", {"title": "retro 2026-10-14", "body": "Lesson: split PLAN.md only at line start.",
                                         "kind": "retro"})
        self.assertFalse(err)
        res, _ = call("memory_search", {"query": "lesson plan"})
        self.assertEqual((res["results"][0]["id"], res["results"][0]["kind"]), (out["id"], "retro"))
        out, _ = call("memory_store", {"title": "x", "body": "unknown kind falls back", "kind": "bogus"})
        res, _ = call("memory_list", {"kind": "outcome"})
        self.assertIn(out["id"], [r["id"] for r in res["results"]])

    def test_list_and_forget(self):
        a, _ = call("memory_store", {"title": "one", "body": "first"})
        call("memory_store", {"title": "two", "body": "second"})
        out, _ = call("memory_list", {})
        self.assertEqual(len(out["results"]), 2)
        out, err = call("memory_forget", {"id": a["id"]})
        self.assertEqual((out["forgotten"], err), (True, False))
        out, err = call("memory_forget", {"id": "abc"})
        self.assertTrue(err)

    def test_limit_and_flags_are_coerced(self):
        for i in range(3):
            call("memory_store", {"title": "row %d" % i, "body": "router note %d" % i})
        for args in ({"limit": "50"}, {"limit": True}, {"limit": -1}, {"include_archive": "yes"}):
            out, err = call("memory_search", dict(args, query="router"))
            self.assertFalse(err, args)
            self.assertLessEqual(len(out["results"]), 20)

    def test_swarm_init_opens_a_task_row(self):
        out, err = call("swarm_init", {"topology": "hierarchical", "maxAgents": 4, "task": "plan B", "scope": ["claude/jev/*"]})
        self.assertFalse(err)
        self.assertTrue(out["swarmId"].startswith("swarm-"))
        c = memdb.connect()
        self.addCleanup(c.close)
        r = c.execute("SELECT * FROM tasks WHERE task_id = ?", (out["swarmId"],)).fetchone()
        self.assertEqual((r["ns"], r["title"], json.loads(r["scope"]), json.loads(r["meta"])),
                         ("proj", "plan B", ["claude/jev/*"], {"topology": "hierarchical", "kind": "swarm"}))
        out, _ = call("swarm_init", {})
        self.assertEqual(out["topology"], "hierarchical")

    def test_degraded_when_the_store_cannot_open(self):
        with mock.patch.dict(os.environ, {"DRYAS_DB": self.tmp}):  # a directory: sqlite cannot open it
            out, err = call("memory_search", {"query": "x"})
            self.assertEqual((err, out["degraded"], out["results"]), (False, True, []))
            out, err = call("memory_store", {"title": "t", "body": "b"})
            self.assertEqual((err, out["degraded"], out["stored"]), (False, True, False))
            out, err = call("swarm_init", {"task": "t"})
            self.assertEqual((err, out["degraded"]), (False, True))
            self.assertTrue(out["swarmId"].startswith("swarm-"))
