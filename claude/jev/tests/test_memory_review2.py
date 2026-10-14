import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import jev_mcp
import memcli
import memdb
import memhooks
import memlearn

SECRET = "sk-ant-api03-" + "A1b2C3d4" * 4


def call(name, args):
    resp = jev_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})
    res = resp["result"]
    return json.loads(res["content"][0]["text"]), res["isError"]


class ReviewTwoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.proj, ".git"))
        with open(os.path.join(self.proj, ".git", "HEAD"), "w") as f:
            f.write("ref: refs/heads/feat/b\n")
        self.logs = os.path.join(self.tmp, "logs")
        self.dbpath = os.path.join(self.tmp, "d.db")
        p = mock.patch.dict(os.environ, {"DRYAS_DB": self.dbpath, "JEV_LOG_DIR": self.logs,
                                         "CLAUDE_PROJECT_DIR": self.proj, "JEV_SESSION_ID": "s1",
                                         "DRYAS_NOTES_DIR": os.path.join(self.tmp, "none")})
        p.start()
        self.addCleanup(p.stop)

    def db(self):
        c = memdb.connect()
        self.addCleanup(c.close)
        return c

    def test_swarm_init_task_is_redacted(self):
        out, err = call("swarm_init", {"task": "deploy with " + SECRET, "scope": ["keep/*", "env " + SECRET]})
        self.assertFalse(err)
        self.assertTrue(out["swarmId"].startswith("swarm-"))
        r = self.db().execute("SELECT title, scope FROM tasks WHERE task_id = ?", (out["swarmId"],)).fetchone()
        self.assertNotIn(SECRET, r["title"] + r["scope"])
        self.assertIn("[REDACTED", r["title"])
        self.assertIn("[REDACTED", r["scope"])
        self.assertIn("keep/*", r["scope"])

    def test_on_task_title_and_scope_are_redacted(self):
        os.makedirs(os.path.join(self.proj, ".orchestrate"))
        with open(os.path.join(self.proj, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": ["3"]}, f)
        with open(os.path.join(self.proj, ".orchestrate", "PLAN.md"), "w") as f:
            f.write("## Task 3: Rotate %s\n\nGoal: x\nScope:\n- cfg/%s.py\nDone:\n- ok\n" % (SECRET, SECRET))
        memhooks.run("task", {"session_id": "s1", "cwd": self.proj}, [], time.monotonic())
        r = self.db().execute("SELECT title, scope FROM tasks").fetchone()
        self.assertNotIn(SECRET, r["title"] + r["scope"])
        self.assertIn("[REDACTED", r["title"])
        self.assertIn("[REDACTED", r["scope"])

    def test_consolidate_past_deadline_is_skipped_and_changes_nothing(self):
        c = self.db()
        c.execute("INSERT INTO patterns (ns, kind, key, value, support, updated) VALUES ('proj', 'rank', '99', '0.5', 1, 1.0)")
        c.commit()
        before = [tuple(r) for r in c.execute("SELECT * FROM patterns ORDER BY key")]
        out = memlearn.consolidate(c, "proj", deadline=time.monotonic() - 1)
        self.assertEqual(out, {"skipped": "deadline", "deduped": 0, "edges": 0, "ranked": 0, "patterns": 0})
        self.assertEqual([tuple(r) for r in c.execute("SELECT * FROM patterns ORDER BY key")], before)

    def test_only_the_newest_edits_count(self):
        c = self.db()
        now = time.time()
        for i, f in enumerate(("old.py", "mid.py", "new.py")):
            c.execute("INSERT INTO edits (ns, session, task_id, file, ok, ts) VALUES ('proj', 's', NULL, ?, 1, ?)",
                      (f, now - 100 + i))
        c.commit()
        with mock.patch.object(memlearn, "MAX_EDITS", 2), mock.patch.object(memlearn, "MIN_EDITS", 1):
            memlearn.consolidate(c, "proj", now=now)
        keys = sorted(r[0] for r in c.execute("SELECT key FROM patterns WHERE kind = 'file_fail'"))
        self.assertEqual(keys, ["mid.py", "new.py"])

    def test_session_end_over_the_gate_logs_budget_skip(self):
        c = self.db()
        out = memhooks.on_session_end(c, {"session_id": "s1", "cwd": self.proj}, None, time.monotonic() - 1.1)
        self.assertEqual(out["consolidate_skipped"], "budget")
        self.assertNotIn("consolidated", out)
        with open(os.path.join(self.logs, "memory.jsonl")) as f:
            recs = [json.loads(line) for line in f]
        self.assertTrue(any(r.get("stage") == "session-end" and r.get("error") == "ConsolidateSkipped"
                            and r.get("detail") == "budget" for r in recs))

    def test_session_end_deadline_skip_is_reported(self):
        c = self.db()
        skipped = {"skipped": "deadline", "deduped": 0, "edges": 0, "ranked": 0, "patterns": 0}
        with mock.patch.object(memhooks.memlearn, "consolidate", return_value=skipped):
            out = memhooks.on_session_end(c, {"session_id": "s1", "cwd": self.proj}, None, time.monotonic())
        self.assertEqual(out["consolidate_skipped"], "deadline")

    def test_cli_consolidate_prints_a_line_per_namespace(self):
        c = self.db()
        c.execute("INSERT INTO edits (ns, session, task_id, file, ok, ts) VALUES ('proj', 's', NULL, 'a.py', 1, ?)", (time.time(),))
        c.commit()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = memcli.main(["--db", self.dbpath, "consolidate", "--ns", "proj"])
        self.assertEqual(rc, 0)
        lines = buf.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("proj"))


if __name__ == "__main__":
    unittest.main()
