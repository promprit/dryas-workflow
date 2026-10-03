import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
REPO_INSTALL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_INSTALL))
import dryas_install as di
import ruflo_helpers as rh

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
        return di.install(self.repo, self.cd, comps, home=self.home, force=kw.get("force", False), dry=kw.get("dry", False))

    def snapshot(self):
        return sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*"))

    def test_full_install_record_and_files(self):
        self.install(["core", "jev", "ruflo"])
        rec = json.loads((self.cd / ".dryas-installed.json").read_text())
        self.assertIn("agents/executor.md", rec["files"])
        self.assertTrue((self.cd / "ruflo/run.sh").stat().st_mode & 0o100)
        self.assertTrue((self.cd / "docs/dryas-workflow.md").exists())
        s = json.loads((self.cd / "settings.json").read_text())
        self.assertEqual(s["env"]["DRYAS_DATA_ROOT"], str(self.home / ".dryas"))
        self.assertTrue((self.home / ".dryas").is_dir())
        self.assertIn(["claude", "mcp", "add", "--scope", "user", "jev", "--", "/usr/bin/python3", str(self.cd / "jev/jev_mcp.py")], self.calls)

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
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(str(link)), str(self.dist))
        rec = json.loads((self.cd / ".dryas-installed.json").read_text())
        self.assertIn("ruflo/mcp-shim/dist", rec["files"])
        di.uninstall(self.cd)
        self.assertFalse(os.path.lexists(str(link)))
        self.assertFalse((self.cd / "ruflo").exists())
        self.assertTrue(self.dist.is_dir())

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

    def test_dry_run_writes_nothing(self):
        self.install(["core", "jev", "ruflo"], dry=True)
        self.assertEqual(self.snapshot(), [".claude"])
        self.assertEqual(self.calls, [])

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

class ShellTest(unittest.TestCase):
    def test_space_in_home_refuses_ruflo(self):
        home = Path(tempfile.mkdtemp()) / "Jane Doe"; home.mkdir()
        sh = REPO_INSTALL / "install.sh"
        p = subprocess.run(["/bin/sh", str(sh), "--preflight-only"], capture_output=True, text=True, env=dict(os.environ, HOME=str(home)))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("--no-ruflo", p.stdout + p.stderr)
        p = subprocess.run(["/bin/sh", str(sh), "--preflight-only", "--no-ruflo"], capture_output=True, text=True, env=dict(os.environ, HOME=str(home)))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

if __name__ == "__main__":
    unittest.main()
