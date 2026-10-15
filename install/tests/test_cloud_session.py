"""A simulated claude.ai/code session (owned core E): a repo set up by `dryas cloud init` runs its committed hooks
the way a cloud session does: CLAUDE_CODE_REMOTE=true, an empty HOME, no Jev opt-in. The repo path has a space."""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _d in (HERE, ROOT / "claude" / "jev"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
import cloud_fixtures as fx
import projns

PLAN = "## Task 1: a\nGoal: g\nScope:\n- src/feature/**\nDone:\n- d\n"
DISCARD = "git checkout -- ."


@unittest.skipIf(os.name == "nt", "a cloud session runs the hook commands with a POSIX shell")
class CloudSessionTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.base), True)
        self.repo = fx.git_repo(self.base / "my repo")
        self.home = self.base / "home"
        self.home.mkdir()

    def init(self, *extra):
        rc, out = fx.run_cli(["init", "--repo", str(self.repo), "--yes", "--claude-dir", str(self.base / "cfg")]
                             + list(extra))
        self.assertEqual(rc, 0, out)
        fx.commit_all(self.repo)

    def env(self, **kw):
        e = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.repo),
             "CLAUDE_CODE_REMOTE": "true", "DRYAS_PY": sys.executable, "LANG": "C.UTF-8"}
        e.update(kw)
        return e

    def event(self, **kw):
        return dict(dict(cwd=str(self.repo), session_id="s1"), **kw)

    def hook(self, event, payload, env=None):
        """Run every committed hook command of the event whose matcher fits, as Claude Code does; their stdouts."""
        settings = json.loads((self.repo / ".claude/settings.json").read_text(encoding="utf-8"))
        key = str(payload.get("tool_name") or payload.get("source") or "")
        outs = []
        for g in settings["hooks"].get(event, []):
            if g.get("matcher") and not re.fullmatch(g["matcher"], key):
                continue
            for h in g["hooks"]:
                p = subprocess.run(["sh", "-c", h["command"]], input=json.dumps(payload), capture_output=True,
                                   text=True, env=env or self.env(), cwd=str(self.repo), timeout=60)
                self.assertEqual(p.returncode, 0, p.stderr)
                outs.append(p.stdout)
        return outs

    @staticmethod
    def decision(outs):
        for o in outs:
            if o.strip():
                return json.loads(o)["hookSpecificOutput"]["permissionDecision"]
        return None

    def test_judge_is_local_and_state_stays_in_the_repo(self):
        self.init()
        env = self.env(OPENROUTER_API_KEY="not-a-real-key")  # a key is present; the cloud default ignores it
        outs = self.hook("PreToolUse", self.event(tool_name="Bash", tool_input={"command": DISCARD}), env)
        self.assertEqual(self.decision(outs), "ask")
        self.assertIn("destructive:git_checkout_discard", "".join(outs))
        log = self.repo / ".dryas/state/jev/logs/gate.jsonl"
        rec = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()][-1]
        self.assertEqual((rec["provider"], rec["decision"]), ("local", "ask"))
        for field in ("fallback", "error", "latency_ms"):
            self.assertNotIn(field, rec)  # Jev was never tried: no network
        self.assertFalse((self.home / ".dryas").exists())
        self.assertEqual(fx.git_status(self.repo), "")  # state and bytecode are git-ignored

    def test_scope_lock_and_gate_match_the_mac(self):
        self.init()
        orch = self.repo / ".orchestrate"
        orch.mkdir()
        (orch / "PLAN.md").write_text(PLAN, encoding="utf-8")
        (orch / "active.json").write_text(json.dumps({"active": ["1"]}), encoding="utf-8")
        local = self.base / "chain.local.json"
        local.write_text(json.dumps({"stages": {"pretool": {"ruflo-pre-bash": {"enabled": False}}}}), encoding="utf-8")
        mac = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.base / "mac-home"), "DRYAS_PY": sys.executable,
               "DRYAS_DATA_ROOT": str(self.base / "mac-data"), "CLAUDE_PLUGIN_ROOT": str(ROOT / "claude"),
               "JEV_CHAIN_LOCAL": str(local)}
        events = [self.event(tool_name="Write", tool_input={"file_path": str(self.repo / "src/other.py"), "content": "x"}),
                  self.event(tool_name="Write", tool_input={"file_path": str(self.repo / "src/feature/a.py"),
                                                            "content": "x"}),
                  self.event(tool_name="Bash", tool_input={"command": DISCARD})]
        cloud, plugin = [], []
        for ev in events:
            cloud.append(self.decision(self.hook("PreToolUse", ev)))
            p = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "claude/jev/chain.py"), "pretool"],
                               input=json.dumps(ev), capture_output=True, text=True, env=mac, timeout=60)
            plugin.append(self.decision([p.stdout]))
        # GOV-12: a run never asks, so the discard is denied, not asked
        self.assertEqual(cloud, ["deny", None, "deny"])
        self.assertEqual(cloud, plugin)

    def test_session_hooks_run_quietly(self):
        self.init()
        edit = {"tool_name": "Edit", "tool_input": {"file_path": str(self.repo / "README.md")}}
        for event, payload in (("SessionStart", {"source": "startup"}), ("PostToolUse", edit), ("SubagentStop", {}),
                               ("SessionEnd", {})):
            outs = self.hook(event, self.event(**payload))
            self.assertTrue(outs, event)
            self.assertEqual("".join(outs), "", event)
        self.assertTrue((self.repo / ".dryas/state/dryas.db").is_file())

    def test_memory_notes_round_trip_between_sessions(self):
        self.init("--persist-memory")
        notes = self.repo / ".dryas/memory/notes"
        self.hook("SessionStart", self.event(source="startup"))
        ns = projns.project_ns(str(self.repo))
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import memdb, memstore; "
                "memstore.store(memdb.connect(), sys.argv[2], 'Retry flaky calls', 'Use the retry helper.')")
        subprocess.run([sys.executable, "-c", code, str(self.repo / ".dryas/jev"), ns], check=True, timeout=60,
                       env=self.env(DRYAS_DATA_ROOT=str(self.repo / ".dryas/state")))
        self.hook("SessionEnd", self.event())
        written = sorted(notes.glob("*.md"))
        self.assertEqual(len(written), 1, written)
        self.assertIn("Retry flaky calls", written[0].read_text(encoding="utf-8"))
        shutil.rmtree(str(self.repo / ".dryas/state"))  # the next cloud session starts with no state
        self.hook("SessionStart", self.event(source="startup", session_id="s2"))
        db = sqlite3.connect(str(self.repo / ".dryas/state/dryas.db"))
        self.addCleanup(db.close)
        titles = [r[0] for r in db.execute("SELECT title FROM memory WHERE kind = 'note'")]
        self.assertTrue(any(t.startswith("Dryas session ") for t in titles), titles)

    def test_hooks_stay_quiet_on_a_mac_with_dryas_installed(self):
        self.init()
        (self.home / ".dryas").mkdir()
        (self.home / ".dryas" / "chain.local.json").write_text("{}", encoding="utf-8")
        env = self.env()
        del env["CLAUDE_CODE_REMOTE"]
        outs = self.hook("PreToolUse", self.event(tool_name="Bash", tool_input={"command": DISCARD}), env)
        self.assertEqual("".join(outs), "")
        self.assertFalse((self.repo / ".dryas/state").exists())

    def test_simulated_session_is_a_cloud_session(self):
        env = self.env()
        self.assertEqual(env["CLAUDE_CODE_REMOTE"], "true")
        self.assertEqual(list(self.home.iterdir()), [])  # HOME starts empty
        self.assertFalse([k for k in env if k.startswith("JEV") or k.startswith("DRYAS_DATA")])  # no Jev opt-in

    def test_scope_lock_denies_an_executor_write_to_orchestrate(self):
        self.init()
        orch = self.repo / ".orchestrate"
        orch.mkdir()
        (orch / "PLAN.md").write_text(PLAN, encoding="utf-8")
        (orch / "active.json").write_text(json.dumps({"active": ["1"]}), encoding="utf-8")
        ev = self.event(tool_name="Write", tool_input={"file_path": str(orch / "PLAN.md"), "content": "x"})
        self.assertIsNone(self.decision(self.hook("PreToolUse", ev)))  # the main session keeps the bookkeeping
        ev["agent_id"] = "executor-1"
        self.assertEqual(self.decision(self.hook("PreToolUse", ev)), "deny")

    def test_real_dryas_home_is_untouched(self):
        """A live Dryas session may write to ~/.dryas while this runs, so the check is that nothing there mentions
        this test's own session id, and that no file the hooks could write for it (a state dir) appeared."""
        real = Path.home() / ".dryas"
        sid = "untouched-" + self.base.name
        self.init()
        ev = lambda **kw: self.event(session_id=sid, **kw)  # noqa: E731
        self.hook("SessionStart", ev(source="startup"))
        self.hook("PreToolUse", ev(tool_name="Bash", tool_input={"command": DISCARD}))
        self.hook("SessionEnd", ev())
        for f in real.rglob("*") if real.exists() else []:
            if f.is_file() and f.suffix in (".jsonl", ".json", ".md"):
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                self.assertNotIn(sid, text, str(f))
        self.assertTrue((self.repo / ".dryas/state").is_dir())
        self.assertIn(sid, (self.repo / ".dryas/state/jev/logs/gate.jsonl").read_text(encoding="utf-8"))  # it did log, in the repo

    def test_single_turn_session_has_the_note_before_any_stop(self):
        self.init("--persist-memory")
        notes = self.repo / ".dryas/memory/notes"
        md = (self.repo / "CLAUDE.md").read_text(encoding="utf-8")
        cmd = re.search(r"run `([^`]*memnotes\.py export)`", md).group(1)
        self.hook("SessionStart", self.event(source="startup"))
        ns = projns.project_ns(str(self.repo))
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import memdb, memstore; "
                "memstore.store(memdb.connect(), sys.argv[2], 'Retry flaky calls', 'Use the retry helper.')")
        subprocess.run([sys.executable, "-c", code, str(self.repo / ".dryas/jev"), ns], check=True, timeout=60,
                       env=self.env(DRYAS_DATA_ROOT=str(self.repo / ".dryas/state")))
        self.assertEqual(list(notes.glob("*.md")), [])  # no Stop or SessionEnd has run yet
        p = subprocess.run(["sh", "-c", cmd], input="", capture_output=True, text=True, env=self.env(),
                           cwd=str(self.repo), timeout=60)
        self.assertEqual((p.returncode, p.stdout), (0, ""), p.stderr)
        written = sorted(notes.glob("*.md"))
        self.assertEqual(len(written), 1, written)
        self.assertIn("Retry flaky calls", written[0].read_text(encoding="utf-8"))
        self.hook("SessionEnd", self.event())  # the hook's later export overwrites the same note
        self.assertEqual(sorted(notes.glob("*.md")), written)

if __name__ == "__main__":
    unittest.main()
