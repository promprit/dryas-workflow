import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import memdb
import memhooks
import memstore

HOOK = os.path.join(HERE, "memhooks.py")


def git(*args, cwd):
    subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=t"] + list(args), cwd=str(cwd), check=True,
                   capture_output=True)


class MemHooksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.proj, ".git"))
        with open(os.path.join(self.proj, ".git", "HEAD"), "w") as f:
            f.write("ref: refs/heads/feat/b\n")
        self.notes = os.path.join(self.tmp, "notes")
        os.makedirs(self.notes)
        self.logs = os.path.join(self.tmp, "logs")
        p = mock.patch.dict(os.environ, {"DRYAS_DB": os.path.join(self.tmp, "d.db"), "JEV_LOG_DIR": self.logs,
                                         "DRYAS_NOTES_DIR": self.notes, "CLAUDE_PROJECT_DIR": self.proj})
        p.start()
        self.addCleanup(p.stop)

    def event(self, **kw):
        e = {"session_id": "s1", "cwd": self.proj}
        e.update(kw)
        return e

    def run_stage(self, stage, event, *rest):
        return memhooks.run(stage, event, list(rest), time.monotonic())

    def db(self):
        c = memdb.connect()
        self.addCleanup(c.close)
        return c

    def activate(self, *ids):
        os.makedirs(os.path.join(self.proj, ".orchestrate"), exist_ok=True)
        with open(os.path.join(self.proj, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": list(ids)}, f)

    def write_note(self, name, text):
        p = os.path.join(self.notes, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def log_lines(self):
        try:
            with open(os.path.join(self.logs, "memory.jsonl"), encoding="utf-8") as f:
                return [json.loads(l) for l in f]
        except FileNotFoundError:
            return []

    def edit_event(self, ok=True, rel="src/a.py"):
        return self.event(tool_name="Edit", tool_input={"file_path": os.path.join(self.proj, rel)},
                          tool_response={"success": ok})

    def test_one_row_per_edit_failure_flagged(self):
        f = os.path.join(self.proj, "src", "a.py")
        self.assertTrue(self.run_stage("edit", self.event(tool_name="Edit", tool_input={"file_path": f},
                                                          tool_response={"success": True})))
        self.run_stage("edit", self.event(tool_name="Write", tool_input={"file_path": f},
                                          tool_response={"success": False, "error": "x"}))
        self.run_stage("edit", self.event(hook_event_name="PostToolUseFailure", tool_name="Edit", tool_input={"file_path": f}))
        self.assertFalse(self.run_stage("edit", self.event(tool_name="Bash", tool_input={"command": "ls"})))
        rows = [tuple(r) for r in self.db().execute("SELECT ns, session, task_id, file, ok FROM edits ORDER BY rowid")]
        self.assertEqual(rows, [("proj", "s1", None, "src/a.py", 1), ("proj", "s1", None, "src/a.py", 0),
                                ("proj", "s1", None, "src/a.py", 0)])

    def test_edit_carries_the_active_task(self):
        self.activate("2")
        self.run_stage("edit", self.edit_event())
        self.assertEqual(self.db().execute("SELECT task_id FROM edits").fetchone()[0], "feat/b:2")

    def test_several_active_tasks_in_either_taskctx_shape(self):
        for ctx in ({"task": "feat/b:1", "co_tasks": ["feat/b:2"]}, {"tasks": ["feat/b:1", "feat/b:2"]}):
            with mock.patch.object(memhooks.taskctx, "context", return_value=ctx):
                self.assertEqual(memhooks._task_ids(self.proj), ["feat/b:1", "feat/b:2"], ctx)
                self.run_stage("edit", self.edit_event())
                self.assertEqual(self.run_stage("task", self.event()), 2)
        self.assertEqual([r[0] for r in self.db().execute("SELECT task_id FROM edits")], [None, None])

    def test_edit_paths_agree_across_worktrees(self):
        repo = Path(self.tmp) / "myrepo"
        repo.mkdir()
        git("init", "-q", cwd=repo)
        git("commit", "-q", "--allow-empty", "-m", "i", cwd=repo)
        git("worktree", "add", "-q", ".worktrees/wt", "-b", "wt", cwd=repo)
        for root in (repo, repo / ".worktrees" / "wt"):
            self.run_stage("edit", self.event(cwd=str(root), tool_name="Edit",
                                              tool_input={"file_path": str(root / "pkg" / "m.py")}))
        rows = [tuple(r) for r in self.db().execute("SELECT ns, file FROM edits")]
        self.assertEqual(rows, [("myrepo", "pkg/m.py"), ("myrepo", "pkg/m.py")])

    def test_task_closed_with_tiers_and_plan_title(self):
        self.activate("3")
        with open(os.path.join(self.proj, ".orchestrate", "PLAN.md"), "w") as f:
            f.write("## Task 3: Fix the router\n\nGoal: x\nScope:\n- claude/jev/route.py\nDone:\n- tests pass\n")
        os.makedirs(self.logs)
        with open(os.path.join(self.logs, "dispatch.jsonl"), "w") as f:
            for rec in ({"task": "feat/b:3", "tier": "haiku", "attempt": 1}, {"task": "feat/b:9", "tier": "opus"},
                        {"task": "feat/b:3", "tier": "sonnet", "attempt": 2}):
                f.write(json.dumps(rec) + "\n")
            f.write("not json\n")
        self.assertEqual(self.run_stage("task", self.event()), 1)
        r = self.db().execute("SELECT * FROM tasks WHERE task_id = 'feat/b:3'").fetchone()
        self.assertEqual((r["ns"], r["title"], json.loads(r["scope"]), r["tier_start"], r["tier_end"], r["outcome"]),
                         ("proj", "Fix the router", ["claude/jev/route.py"], "haiku", "sonnet", "returned"))
        self.assertIsNotNone(r["ended"])
        self.assertEqual(json.loads(r["meta"]), {"dispatches": 2})

    def test_task_without_active_tasks_does_nothing(self):
        self.assertEqual(self.run_stage("task", self.event()), 0)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 0)

    def test_session_start_end_and_compaction_summary(self):
        self.run_stage("session-start", self.event())
        self.run_stage("edit", self.edit_event())
        self.run_stage("edit", self.edit_event(ok=False))
        self.run_stage("session-end", self.event(), "manual")
        r = self.db().execute("SELECT ns, started, ended, summary FROM sessions WHERE id = 's1'").fetchone()
        self.assertEqual((r["ns"], r["ended"]), ("proj", None))
        self.assertIsNotNone(r["started"])
        self.assertEqual(r["summary"], "2 edits (1 failed) in 1 files; 0 tasks closed; 0 memories stored")
        self.run_stage("session-end", self.event())
        self.assertIsNotNone(self.db().execute("SELECT ended FROM sessions WHERE id = 's1'").fetchone()[0])

    def test_session_end_consolidates(self):
        for ok in (True, True, False):
            self.run_stage("edit", self.edit_event(ok=ok))
        out = self.run_stage("session-end", self.event())
        self.assertEqual(out["consolidated"]["patterns"], 1)
        self.assertEqual(self.db().execute("SELECT key FROM patterns WHERE kind = 'file_fail'").fetchone()[0], "src/a.py")

    def test_note_import_searchable_and_unchanged_skipped(self):
        self.write_note("MEMORY.md", "- [Gate retry](gate.md) - retry once\n")
        gate = self.write_note("gate.md", "---\nname: gate-retry\ntype: feedback\n---\nRetry the gate once on timeout.\n")
        self.assertEqual(self.run_stage("session-start", self.event()),
                         {"indexed": 2, "unchanged": 0, "skipped": 0, "removed": 0})
        hit = memstore.search(self.db(), "proj", "retry timeout")["results"][0]
        self.assertEqual((hit["title"], hit["kind"], hit["source"]), ("gate-retry", "note", "claude-memory"))
        self.assertEqual(self.run_stage("session-start", self.event())["unchanged"], 2)
        self.write_note("gate.md", "---\nname: gate-retry\n---\nRetry twice now.\n")
        st = os.stat(gate)
        os.utime(gate, (st.st_atime, st.st_mtime + 10))
        self.assertEqual(self.run_stage("session-start", self.event()),
                         {"indexed": 1, "unchanged": 1, "skipped": 0, "removed": 0})
        os.remove(gate)
        self.assertEqual(self.run_stage("session-start", self.event())["removed"], 1)

    def test_oversized_and_unreadable_notes_are_counted(self):
        self.write_note("big.md", "x" * (memhooks.NOTE_MAX_BYTES + 1))
        with open(os.path.join(self.notes, "bad.md"), "wb") as f:
            f.write(b"\xff\xfe\x00bad")
        self.assertEqual(self.run_stage("session-start", self.event()),
                         {"indexed": 0, "unchanged": 0, "skipped": 2, "removed": 0})

    def test_notes_dir_from_claude_projects(self):
        projects = os.path.join(self.tmp, "projects")
        enc = "".join(ch if ch.isalnum() else "-" for ch in os.path.abspath(self.proj))
        os.makedirs(os.path.join(projects, enc, "memory"))
        with mock.patch.dict(os.environ, {"JEV_PROJECTS_DIR": projects}):
            os.environ.pop("DRYAS_NOTES_DIR")
            self.assertEqual(memhooks.notes_dir(self.proj), os.path.join(projects, enc, "memory"))

    def test_main_never_fails_and_logs_one_line(self):
        for stage, data in (("edit", b"not json"), ("bogus", b"{}"), ("edit", b"[1, 2]")):
            p = subprocess.run([sys.executable, HOOK, stage], input=data, capture_output=True, timeout=10)
            self.assertEqual((p.returncode, p.stdout), (0, b""), stage)
        self.assertEqual([r["error"] for r in self.log_lines()], ["JSONDecodeError", "ValueError", "ValueError"])

    def test_locked_store_exits_zero_within_budget(self):
        holder = memdb.connect()
        holder.execute("BEGIN IMMEDIATE")
        self.addCleanup(holder.close)
        self.addCleanup(holder.execute, "ROLLBACK")
        data = json.dumps(self.edit_event()).encode("utf-8")
        t0 = time.monotonic()
        p = subprocess.run([sys.executable, HOOK, "edit"], input=data, capture_output=True, timeout=10)
        self.assertLess(time.monotonic() - t0, 2.0)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(self.log_lines()[-1]["error"], "OperationalError")
