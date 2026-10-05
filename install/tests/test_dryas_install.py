import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
REPO_INSTALL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_INSTALL))
import dryas_install as di
import ruflo_helpers as rh

REAL_DETECT = di.detect

CHAIN = {"pretool": [{"name": "scope-lock", "component": "core", "cmd": ["true"]},
                     {"name": "jev-gate", "component": "jev", "cmd": ["true"]},
                     {"name": "ruflo-pre-bash", "component": "ruflo", "cmd": ["true"]},
                     {"name": "flowobserve", "component": "flowobserve", "enabled": False, "cmd": ["true"]}],
         "prompt": []}
FRAG = {"core": {"env": {"CORE": "1"}, "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "/bin/sh \"$HOME/.claude/hooks/pretool-chain.sh\""}]}]}},
        "jev": {"permissions": {"allow": ["mcp__jev"]}},
        "ruflo": {"env": {"DRYAS_DATA_ROOT": "$DRYAS_DATA_ROOT", "RUFLO_BIN": "$RUFLO_BIN", "RUFLO_JS": "$RUFLO_JS",
                          "RUFLO_NODE_FALLBACK": "$RUFLO_NODE_FALLBACK", "RUFLO_NODE_MODULES": "$RUFLO_NODE_MODULES"}},
        "superpowers": {}}

def fixture_repo():
    r = Path(tempfile.mkdtemp())
    files = {"claude/agents/executor.md": "exec", "claude/jev/chain.json": json.dumps(CHAIN),
             "claude/jev/x.py": "print(1)", "claude/ruflo/run.sh": "#!/bin/sh\n", "claude/hooks/pretool-chain.sh": "#!/bin/sh\nexit 0\n",
             "claude/CLAUDE.md.template": "POLICY", "claude/settings.fragment.json": json.dumps(FRAG),
             "docs/workflow.md": "# W\n"}
    for rel, t in files.items():
        p = r / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(t)
    os.chmod(r / "claude/ruflo/run.sh", 0o755)
    return r

class InstallTest(unittest.TestCase):
    def setUp(self):
        self.repo = fixture_repo()
        self.home = Path(tempfile.mkdtemp()) / "Jane Doe"
        self.cd = self.home / ".claude"
        self.cd.mkdir(parents=True)
        os.environ.pop("DRYAS_DATA_ROOT", None)  # the live session sets it; tests need the $HOME/.dryas default
        self.calls = []
        self.dist = Path(tempfile.mkdtemp()) / "cli-dist"
        self.dist.mkdir()
        di.run = lambda argv: self.calls.append(argv) or 0
        di.detect = lambda: {"RUFLO_BIN": "/b/ruflo", "RUFLO_JS": "/b/ruflo.js", "RUFLO_NODE_FALLBACK": "/b/node", "RUFLO_NODE_MODULES": "/b/nm",
                             "RUFLO_CLI_DIST": str(self.dist)}
        di.confirm = lambda prompt: True
        rh.generate = lambda ruflo_bin: {n: (("".join(o for f, o, _ in rh.PATCHES if f == n) or "x\n").encode(), 0o644) for n in rh.HELPERS}

    def install(self, comps, **kw):
        return di.install(self.repo, self.cd, comps, home=self.home, force=kw.get("force", False), dry=kw.get("dry", False), yes=kw.get("yes", False))

    def snapshot(self):
        return sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*"))

    def test_full_install_record_and_files(self):
        self.install(["core", "jev", "ruflo"])
        rec = json.loads((self.cd / ".dryas-installed.json").read_text())
        self.assertIn("agents/executor.md", rec["files"])
        if os.name != "nt":
            self.assertTrue((self.cd / "ruflo/run.sh").stat().st_mode & 0o100)
        self.assertTrue((self.cd / "docs/dryas-workflow.md").exists())
        s = json.loads((self.cd / "settings.json").read_text())
        self.assertEqual(s["env"]["DRYAS_DATA_ROOT"], str(self.home / ".dryas"))
        self.assertTrue((self.home / ".dryas").is_dir())
        self.assertIn(["claude", "mcp", "add", "--scope", "user", "jev", "--", di.PY, "-X", "utf8",
                       di.pu.fwd(self.cd / "jev/jev_mcp.py")], self.calls)

    def test_no_ruflo_disables_stage_and_skips_files(self):
        self.install(["core", "jev"])
        chain = json.loads((self.cd / "jev/chain.json").read_text())
        st = {x["name"]: x for x in chain["pretool"]}
        self.assertIs(st["ruflo-pre-bash"].get("enabled"), False)
        self.assertIs(st["flowobserve"].get("enabled"), False)
        self.assertNotIn("enabled", st["jev-gate"])
        self.assertFalse((self.cd / "ruflo").exists())

    def test_existing_file_skipped_unless_force(self):
        (self.cd / "agents").mkdir()
        (self.cd / "agents/executor.md").write_text("mine")
        self.install(["core"])
        self.assertEqual((self.cd / "agents/executor.md").read_text(), "mine")
        self.install(["core"], force=True)
        self.assertEqual((self.cd / "agents/executor.md").read_text(), "exec")
        backups = list(self.cd.glob(".dryas-backup-*/agents/executor.md"))
        self.assertEqual([b.read_text() for b in backups], ["mine"])

    def test_claude_md_block_idempotent(self):
        (self.cd / "CLAUDE.md").write_text("# mine\n")
        self.install(["core"])
        self.install(["core"])
        t = (self.cd / "CLAUDE.md").read_text()
        self.assertEqual(t.count("<!-- dryas:start -->"), 1)
        self.assertTrue(t.startswith("# mine\n"))

    def test_upgrade_then_single_uninstall_restores_home(self):
        (self.cd / "CLAUDE.md").write_text("# mine\n")
        (self.cd / "settings.json").write_text(json.dumps({"env": {"MINE": "1"}}))
        before = {p: (self.home / p).read_bytes() for p in self.snapshot() if (self.home / p).is_file()}
        self.install(["core", "jev"])
        self.install(["core", "jev", "ruflo"])
        s = json.loads((self.cd / "settings.json").read_text()); s["env"]["LATER"] = "x"
        (self.cd / "settings.json").write_text(json.dumps(s))
        di.uninstall(self.cd)
        self.assertEqual((self.cd / "CLAUDE.md").read_text(), "# mine\n")
        self.assertEqual(json.loads((self.cd / "settings.json").read_text())["env"], {"MINE": "1", "LATER": "x"})
        self.assertFalse((self.cd / ".dryas-installed.json").exists())
        self.assertFalse((self.cd / "agents/executor.md").exists())
        self.assertIn(["claude", "mcp", "remove", "--scope", "user", "jev"], self.calls)
        for p, b in before.items():
            if p.endswith("settings.json"):
                continue
            self.assertEqual((self.home / p).read_bytes(), b, p)

    # --- additions beyond the plan's listed tests ---

    def test_ruflo_shim_dist_link_created_and_removed(self):
        self.install(["core", "jev", "ruflo"])
        link = self.cd / "ruflo/mcp-shim/dist"
        self.assertTrue(di.pu.same_path(di.pu.read_dir_link(str(link)), str(self.dist)))
        rec = json.loads((self.cd / ".dryas-installed.json").read_text())
        self.assertIn(rec["files"]["ruflo/mcp-shim/dist"]["link"], ("symlink", "junction"))
        self.assertIn("ruflo/mcp-shim/dist", rec["files"])
        di.uninstall(self.cd)
        self.assertFalse(os.path.lexists(str(link)))
        self.assertFalse((self.cd / "ruflo").exists())
        self.assertTrue(self.dist.is_dir())

    @unittest.skipIf(os.name == "nt", "file symlinks need admin rights on Windows")
    def test_source_symlinks_copied_as_symlinks(self):
        (self.repo / "claude/jev/hooks").mkdir(parents=True)
        (self.repo / "claude/jev/hooks/prompt-chain.sh").write_text("#!/bin/sh\n")
        os.symlink("../jev/hooks/prompt-chain.sh", str(self.repo / "claude/hooks/prompt-chain.sh"))
        self.install(["core"])
        dest = self.cd / "hooks/prompt-chain.sh"
        self.assertTrue(dest.is_symlink())
        self.assertEqual(os.readlink(str(dest)), "../jev/hooks/prompt-chain.sh")
        self.install(["core"])  # identical link: nothing to do, no error
        self.assertTrue(dest.is_symlink())

    def test_chain_and_md_rendered(self):
        chain = {"pretool": [{"name": "s", "component": "core", "cmd": ["$PY", "-X", "utf8", "$CD/jev/x.py"],
                              "requires_path": "$DRYAS_DATA_ROOT"}], "prompt": []}
        (self.repo / "claude/jev/chain.json").write_text(json.dumps(chain), encoding="utf-8")
        (self.repo / "claude/commands").mkdir(parents=True)
        (self.repo / "claude/commands/h.md").write_text('"{{PY}}" -X utf8 "{{CD}}/jev/h.py" --cwd "$PWD" café\n',
                                                         encoding="utf-8")
        self.install(["core"])
        cd = di.pu.fwd(self.cd)
        got = json.loads((self.cd / "jev/chain.json").read_text(encoding="utf-8"))["pretool"][0]
        self.assertEqual(got["cmd"], [di.PY, "-X", "utf8", cd + "/jev/x.py"])
        self.assertEqual(got["requires_path"], di.pu.fwd(self.home / ".dryas"))
        self.assertEqual((self.cd / "commands/h.md").read_text(encoding="utf-8"),
                         '"%s" -X utf8 "%s/jev/h.py" --cwd "$PWD" café\n' % (di.PY, cd))

    def test_unknown_md_token_aborts_before_any_write(self):
        (self.repo / "claude/commands").mkdir(parents=True)
        (self.repo / "claude/commands/bad.md").write_text("{{NOPE}}", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.install(["core"])
        self.assertEqual(self.snapshot(), before)

    def test_hook_problems(self):
        (self.cd / "jev").mkdir(parents=True, exist_ok=True)
        (self.cd / "jev/c.py").write_text("x", encoding="utf-8")
        ok = '"%s" -X utf8 "%s"' % (di.PY, di.pu.fwd(self.cd / "jev/c.py"))
        self.assertEqual(di.hook_problems([["PreToolUse", "*", ok]]), [])
        self.assertEqual(len(di.hook_problems([["PreToolUse", "*", '/bin/sh "/nope/x.sh"']])), 2)

    def test_detect_without_npm(self):
        orig = di.pu.which
        di.pu.which = lambda n: ""
        try:
            d = REAL_DETECT()
        finally:
            di.pu.which = orig
        self.assertEqual((d["RUFLO_JS"], d["RUFLO_CLI_DIST"], d["RUFLO_NODE_MODULES"]), ("", "", ""))

    def test_fresh_install_uninstall_leaves_home_empty_of_installer_paths(self):
        self.install(["core", "jev", "ruflo"])
        di.uninstall(self.cd)
        self.assertEqual(self.snapshot(), [".claude"])

    def test_malformed_settings_aborts_before_any_write(self):
        (self.cd / "settings.json").write_text("{bad")
        with self.assertRaises(SystemExit):
            self.install(["core", "jev"])
        self.assertEqual(self.snapshot(), [".claude", ".claude/settings.json"])
        self.assertEqual(self.calls, [])

    def test_declined_settings_writes_no_settings(self):
        di.confirm = lambda prompt: False
        self.install(["core"])
        self.assertFalse((self.cd / "settings.json").exists())
        self.assertTrue((self.cd / "agents/executor.md").exists())

    def test_yes_skips_settings_prompt(self):
        di.confirm = lambda prompt: False
        self.install(["core"], yes=True)
        self.assertTrue((self.cd / "settings.json").exists())

    def test_main_yes_flag_reaches_apply_settings(self):
        def no_prompt(prompt):
            raise AssertionError("confirm called despite --yes")
        di.confirm = no_prompt
        rc = di.main(["install", "--repo", str(self.repo), "--claude-dir", str(self.cd), "--components", "core", "--yes"])
        self.assertEqual(rc, 0)
        self.assertTrue((self.cd / "settings.json").exists())

    def test_dry_run_writes_nothing(self):
        self.install(["core", "jev", "ruflo"], dry=True)
        self.assertEqual(self.snapshot(), [".claude"])
        self.assertEqual(self.calls, [])

    def test_install_creates_missing_claude_dir_and_uninstall_removes_it(self):
        self.cd.rmdir()
        self.install(["core", "jev", "ruflo"])
        self.assertTrue(json.loads((self.cd / ".dryas-installed.json").read_text())["claude_dir_created"])
        di.uninstall(self.cd)
        self.assertFalse(self.cd.exists())

    def test_dry_run_with_missing_claude_dir_creates_nothing(self):
        self.cd.rmdir()
        self.install(["core", "jev", "ruflo"], dry=True)
        self.assertEqual(self.snapshot(), [])

    def test_uninstall_without_record(self):
        self.assertEqual(di.uninstall(self.cd), 0)

    def test_user_file_never_deleted_by_uninstall(self):
        (self.cd / "agents").mkdir()
        (self.cd / "agents/executor.md").write_text("mine")
        (self.cd / "agents/own.md").write_text("own")
        self.install(["core"])
        di.uninstall(self.cd)
        self.assertEqual((self.cd / "agents/executor.md").read_text(), "mine")
        self.assertEqual((self.cd / "agents/own.md").read_text(), "own")

    def test_force_backup_restored_on_uninstall(self):
        (self.cd / "agents").mkdir()
        (self.cd / "agents/executor.md").write_text("mine")
        self.install(["core"], force=True)
        di.uninstall(self.cd)
        self.assertEqual((self.cd / "agents/executor.md").read_text(), "mine")
        self.assertEqual(list(self.cd.glob(".dryas-backup-*")), [])

    def test_verify_smoke_logs_outside_claude_dir(self):
        envs = []
        orig = di.capture
        di.capture = lambda argv, input_text=None, env=None: envs.append(env) or (0, "")
        try:
            di.verify(self.cd, [])
        finally:
            di.capture = orig
        env = envs[-1]
        self.assertIn("JEV_LOG_DIR", env)
        self.assertFalse(Path(env["JEV_LOG_DIR"]).resolve().is_relative_to(self.cd.resolve()))
        self.assertEqual(list(self.cd.rglob("logs")), [])

    def test_upgrade_replaces_old_hooks_keeps_user_hooks(self):
        self.install(["core"])
        s = json.loads((self.cd / "settings.json").read_text(encoding="utf-8"))
        s["hooks"]["PreToolUse"].append({"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-hook"}]})
        (self.cd / "settings.json").write_text(json.dumps(s), encoding="utf-8")
        new_core = {"env": {"CORE": "1"}, "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
            {"type": "command", "command": "\"$PY\" -X utf8 \"$CD/jev/chain.py\" pretool"}]}]}}
        (self.repo / "claude/settings.fragment.json").write_text(json.dumps(dict(FRAG, core=new_core)), encoding="utf-8")
        os.unlink(str(self.repo / "claude/hooks/pretool-chain.sh"))
        self.install(["core"])
        s = json.loads((self.cd / "settings.json").read_text(encoding="utf-8"))
        cmds = [h["command"] for g in s["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertIn('"%s" -X utf8 "%s/jev/chain.py" pretool' % (di.PY, di.pu.fwd(self.cd)), cmds)
        self.assertIn("my-own-hook", cmds)
        self.assertFalse(any("/bin/sh" in c for c in cmds))
        self.assertFalse((self.cd / "hooks/pretool-chain.sh").exists())
        rec = json.loads((self.cd / ".dryas-installed.json").read_text(encoding="utf-8"))
        self.assertNotIn("hooks/pretool-chain.sh", rec["files"])
        self.assertFalse(any("/bin/sh" in h[2] for h in rec["settings"]["hooks"]))
        di.uninstall(self.cd)
        s = json.loads((self.cd / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual([h["command"] for g in s["hooks"]["PreToolUse"] for h in g["hooks"]], ["my-own-hook"])

    def test_stale_file_backup_restored(self):
        (self.cd / "hooks").mkdir(parents=True)
        (self.cd / "hooks/pretool-chain.sh").write_text("MINE", encoding="utf-8")
        self.install(["core"], force=True)
        os.unlink(str(self.repo / "claude/hooks/pretool-chain.sh"))
        self.install(["core"])
        self.assertEqual((self.cd / "hooks/pretool-chain.sh").read_text(encoding="utf-8"), "MINE")

    def test_reinstall_with_fewer_components_keeps_earlier_ones(self):
        self.install(["core", "jev", "ruflo"])
        self.install(["core"])
        s = json.loads((self.cd / "settings.json").read_text(encoding="utf-8"))
        self.assertIn("RUFLO_BIN", s["env"])
        self.assertTrue((self.cd / "ruflo/run.sh").exists())

    def test_declined_settings_keeps_old_hook_files(self):
        self.install(["core"])
        new_core = {"env": {"CORE": "1"}, "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
            {"type": "command", "command": "\"$PY\" -X utf8 \"$CD/jev/chain.py\" pretool"}]}]}}
        (self.repo / "claude/settings.fragment.json").write_text(json.dumps(dict(FRAG, core=new_core)), encoding="utf-8")
        os.unlink(str(self.repo / "claude/hooks/pretool-chain.sh"))
        di.confirm = lambda prompt: False
        self.install(["core"])
        self.assertTrue((self.cd / "hooks/pretool-chain.sh").exists())
        rec = json.loads((self.cd / ".dryas-installed.json").read_text(encoding="utf-8"))
        self.assertIn("hooks/pretool-chain.sh", rec["files"])

    def test_record_survives_exception(self):
        real, n = di._put, [0]
        def boom(*a, **k):
            n[0] += 1
            if n[0] > 1:
                raise RuntimeError("boom")
            return real(*a, **k)
        di._put = boom
        try:
            with self.assertRaises(RuntimeError):
                self.install(["core"])
        finally:
            di._put = real
        rec = json.loads((self.cd / ".dryas-installed.json").read_text(encoding="utf-8"))
        self.assertEqual(len(rec["files"]), 1)

    def test_pycache_not_installed(self):
        p = self.repo / "claude/jev/__pycache__/x.pyc"
        p.parent.mkdir(parents=True)
        p.write_bytes(b"x")
        (self.repo / "claude/jev/y.pyc").write_bytes(b"y")
        self.install(["core"])
        self.assertFalse((self.cd / "jev/__pycache__").exists())
        self.assertFalse((self.cd / "jev/y.pyc").exists())

    def test_venv_warning(self):
        import io, contextlib
        buf = io.StringIO()
        old = (sys.prefix, sys.base_prefix)
        sys.prefix, sys.base_prefix = "/venv", "/base"
        try:
            with contextlib.redirect_stdout(buf):
                self.install(["core"])
        finally:
            sys.prefix, sys.base_prefix = old
        self.assertIn("warning: installing with a virtual-environment Python", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
