"""One test per row of the spec's sub-project B parity table (Ruflo today -> Dryas 2.0), plus the migration."""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))
import jev_mcp
import local_judge
import memdb
import memhooks
import ruflo_import
from test_ruflo_import import make_source


def call(name, args):
    resp = jev_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})
    res = resp["result"]
    return json.loads(res["content"][0]["text"]), res["isError"]


class MemoryParityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.proj, ".git"))
        with open(os.path.join(self.proj, ".git", "HEAD"), "w") as f:
            f.write("ref: refs/heads/feat/b\n")
        self.notes = os.path.join(self.tmp, "notes")
        os.makedirs(self.notes)
        p = mock.patch.dict(os.environ, {"DRYAS_DB": os.path.join(self.tmp, "d.db"), "JEV_LOG_DIR": os.path.join(self.tmp, "logs"),
                                         "DRYAS_NOTES_DIR": self.notes, "CLAUDE_PROJECT_DIR": self.proj,
                                         "JEV_SESSION_ID": "s1"})
        p.start()
        self.addCleanup(p.stop)

    def hook(self, stage, *rest, **event):
        e = {"session_id": "s1", "cwd": self.proj}
        e.update(event)
        return memhooks.run(stage, e, list(rest), time.monotonic())

    def db(self):
        c = memdb.connect()
        self.addCleanup(c.close)
        return c

    def edit(self, rel, ok=True, session="s1"):
        self.hook("edit", session_id=session, tool_name="Edit",
                  tool_input={"file_path": os.path.join(self.proj, rel)}, tool_response={"success": ok})

    def test_row_memory_search(self):
        a, _ = call("memory_store", {"title": "gate retry", "body": "Worked: retry once.", "namespace": "proj"})
        out, err = call("memory_search", {"query": "retry", "namespace": "proj"})
        self.assertFalse(err)
        self.assertEqual(out["results"][0]["id"], a["id"])
        self.assertTrue(out["results"][0]["reason"])
        self.assertEqual(call("memory_search", {"query": "retry", "namespace": "elsewhere"})[0]["results"], [])

    def test_row_memory_store(self):
        for body in ("token=abcd1234efgh5678 was the fix", "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b"):
            out, err = call("memory_store", {"title": "t", "body": body})
            self.assertEqual((err, out["stored"]), (True, False), body)
        out, err = call("memory_store", {"title": "router", "body": "Worked: cache.", "task_id": "feat/b:1", "commit": "abc1234"})
        self.assertFalse(err)
        r = self.db().execute('SELECT task_id, "commit" FROM memory WHERE id = ?', (out["id"],)).fetchone()
        self.assertEqual(tuple(r), ("feat/b:1", "abc1234"))

    def test_row_swarm_init(self):
        out, err = call("swarm_init", {"topology": "hierarchical"})
        self.assertFalse(err)
        self.assertIsNotNone(self.db().execute("SELECT 1 FROM tasks WHERE task_id = ?", (out["swarmId"],)).fetchone())

    def test_row_pre_bash_danger_scan(self):
        # Ruflo pre-bash's own cases; A1 owns the rest of the danger list and its negative cases
        for cmd in ("rm -rf /", "format c:", "del /s /q c:\\", ":(){ :|:& };:"):
            self.assertIsNotNone(local_judge.danger(cmd), cmd)

    def test_row_post_edit(self):
        self.edit("a.py")
        self.edit("a.py", ok=False)
        self.assertEqual([r[0] for r in self.db().execute("SELECT ok FROM edits ORDER BY rowid")], [1, 0])

    def test_row_post_task(self):
        os.makedirs(os.path.join(self.proj, ".orchestrate"))
        with open(os.path.join(self.proj, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": ["1"]}, f)
        self.assertEqual(self.hook("task"), 1)
        q = "SELECT outcome, ended FROM tasks WHERE task_id = 'feat/b:1'"
        self.assertEqual(tuple(self.db().execute(q).fetchone()), (None, None))
        with open(os.path.join(self.proj, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": []}, f)
        self.hook("task")
        r = self.db().execute(q).fetchone()
        self.assertEqual(r[0], "done")
        self.assertIsNotNone(r[1])

    def test_row_session_restore_end_precompact(self):
        self.hook("session-start")
        self.hook("session-end", "auto")
        r = self.db().execute("SELECT started, ended, summary FROM sessions WHERE id = 's1'").fetchone()
        self.assertEqual((r["ended"], r["summary"]), (None, "0 edits (0 failed) in 0 files; 0 tasks closed; 0 memories stored"))
        self.hook("session-end")
        self.assertIsNotNone(self.db().execute("SELECT ended FROM sessions WHERE id = 's1'").fetchone()[0])

    def test_row_auto_memory_import(self):
        with open(os.path.join(self.notes, "rule.md"), "w", encoding="utf-8") as f:
            f.write("---\nname: worktree-rule\n---\nOne agent per worktree.\n")
        self.assertEqual(self.hook("session-start")["indexed"], 1)
        out, _ = call("memory_search", {"query": "worktree agent"})
        self.assertEqual(out["results"][0]["title"], "worktree-rule")
        self.assertEqual(self.hook("session-start")["unchanged"], 1)

    def test_row_session_end_consolidate(self):
        call("memory_store", {"title": "gate", "body": "gate note"})
        call("memory_store", {"title": "route", "body": "route note"})
        for s in ("s1", "s2"):
            with mock.patch.dict(os.environ, {"JEV_SESSION_ID": s}):
                call("memory_search", {"query": "note", "limit": 2})
            self.edit("gate.py", session=s)
            self.edit("route.py", session=s)
        self.edit("gate.py", ok=False, session="s2")
        out = self.hook("session-end", session_id="s2")
        self.assertGreaterEqual(out["consolidated"]["ranked"], 2)
        res, _ = call("memory_search", {"query": "gate"})
        self.assertIn("gate.py and route.py were edited together in 2 tasks", [p["reason"] for p in res["patterns"]])

    def test_migration_import_ruflo(self):
        src = os.path.join(self.tmp, "agentdb-memory.db")
        make_source(src)
        c = self.db()
        self.assertTrue(ruflo_import.import_ruflo(c, src)["ok"])
        self.assertEqual(call("memory_search", {"query": "ls", "namespace": "commands"})[0]["results"], [])
        out, _ = call("memory_search", {"query": "ls", "namespace": "commands", "include_archive": True})
        self.assertEqual(out["results"][0]["title"], "cmd-1")
