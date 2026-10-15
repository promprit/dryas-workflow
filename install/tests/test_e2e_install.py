"""End to end: real install into a temp home with a fake `claude`. Claude Code: the plugin is set up in the config
dir and every plugin hook command runs through the shell Claude Code uses. Codex (fake CLI): the plugin is set up in
CODEX_HOME, its hooks are trusted and run through sh; a Codex copy install from before is migrated."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fakecli
import legacy_codex
from test_hook_shell import find_bash
REPO = HERE.parents[1]
INSTALLED = {"version": 2, "plugins": {"dryas@dryas-workflow": [{"scope": "user", "installPath": str(REPO / "claude")}]}}
# fake `claude plugin install` lists the plugin in $CLAUDE_CONFIG_DIR, as the real one does
EPILOGUE = ("import os\n"
            "if sys.argv[1:3] == ['plugin', 'install']:\n"
            "    d = os.path.join(os.environ.get('CLAUDE_CONFIG_DIR') or os.path.expanduser('~/.claude'), 'plugins'); os.makedirs(d, exist_ok=True)\n"
            "    open(os.path.join(d, 'installed_plugins.json'), 'w').write(json.dumps(%r))\n"
            "with open(%r, 'a') as f: f.write(json.dumps([sys.argv[1:3], os.environ.get('CLAUDE_CONFIG_DIR')]) + '\\n')\n")
EVENTS = {
    "PreToolUse": {"tool_name": "Write", "tool_input": {"file_path": "notes.txt", "content": "café → ok"}},
    "UserPromptSubmit": {"prompt": ""},
    "SessionStart": {"source": "startup"},
    "PreCompact": {"trigger": "manual"},
}


class E2ETest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.home.mkdir()
        fb = self.tmp / "bin"
        fakecli.make(fb, "claude", self.tmp / "calls.jsonl", outputs={"mcp list": "jev: ok\n"},
                     epilogue=EPILOGUE % (INSTALLED, str(self.tmp / "envs.jsonl")), plugin_list=True)
        fakecli.make_codex(fb, self.tmp / "codex-calls.jsonl")
        self.env = {k: v for k, v in os.environ.items() if k not in ("OPENROUTER_API_KEY", "DRYAS_DATA_ROOT", "CODEX_HOME",
                                                                   "CLAUDE_CONFIG_DIR", "CLAUDE_PLUGIN_ROOT", "DRYAS_PY")}
        self.env["CODEX_HOME"] = str(self.home / ".codex")
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home), PATH=str(fb) + os.pathsep + os.environ["PATH"],
                        JEV_LOG_DIR=str(self.tmp / "logs"), JEV_HANDOFF_DIR=str(self.tmp / "handoff"),
                        JEV_COMPACT_DIR=str(self.tmp / "compact"),
                        # CI runs the Jev suite directly; a nested run in every install multiplied its timing flakes
                        DRYAS_VERIFY_SKIP_TESTS="1")

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def installer(self, *args, yes=True, answer=""):
        """answer: stdin text for the installer's questions when run without --yes."""
        return subprocess.run([sys.executable, str(REPO / "install" / "dryas_install.py"), "run", "--repo", str(REPO)]
                              + (["--yes"] if yes else []) + ["--no-ruflo", "--no-superpowers", "--no-design"] + list(args),
                              capture_output=True, text=True, env=self.env, timeout=900, input=answer)

    def installed(self):
        """Run a plain install and fail with its output, so a CI failure shows which step broke."""
        r = self.installer()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def test_uninstall_asks_and_yes_bypasses(self):
        self.installed()
        cd = self.home / ".claude"
        u = self.installer("--uninstall", "--purge", yes=False, answer="n\n")
        self.assertEqual(u.returncode, 1, u.stdout + u.stderr)
        self.assertIn("--uninstall will remove:", u.stdout)
        self.assertIn("claude plugin uninstall dryas@dryas-workflow", u.stdout)
        self.assertIn("with --purge", u.stdout)
        self.assertIn("Proceed? [y/N]", u.stdout)
        self.assertIn("nothing removed", u.stdout)
        self.assertTrue((cd / ".dryas-plugin.json").exists())
        self.assertTrue((self.home / ".dryas" / "accounts.json").exists())
        u = self.installer("--uninstall", "--purge", yes=False, answer="y\n")
        self.assertEqual(u.returncode, 0, u.stdout + u.stderr)
        self.assertFalse((cd / ".dryas-plugin.json").exists())
        self.assertFalse((self.home / ".dryas").exists())
        self.installed()
        u = self.installer("--uninstall")  # --yes: listed, not asked
        self.assertEqual(u.returncode, 0, u.stdout + u.stderr)
        self.assertIn("--uninstall will remove:", u.stdout)
        self.assertNotIn("[y/N]", u.stdout)
        self.assertFalse((cd / ".dryas-plugin.json").exists())

    def test_plugin_setup_and_hooks_run(self):
        p = self.installer()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        cd = (self.home / ".claude").resolve()
        envs = [json.loads(l) for l in (self.tmp / "envs.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertIn([["plugin", "marketplace"], None], envs)
        self.assertIn([["plugin", "install"], None], envs)
        settings = json.loads((cd / "settings.json").read_text(encoding="utf-8"))
        self.assertNotIn("hooks", settings)
        py = settings["env"]["DRYAS_PY"]
        self.assertTrue(py)
        accounts = json.loads((self.home / ".dryas" / "accounts.json").read_text(encoding="utf-8"))
        self.assertEqual(accounts["claude_dirs"], [str(cd)])
        self.assertIn("PASS  scope lock blocks an out-of-scope write", p.stdout)
        hooks = json.loads((REPO / "claude" / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        cmds = [(ev, h["command"]) for ev, groups in hooks.items() for g in groups for h in g["hooks"]]
        self.assertTrue(cmds)
        sh = find_bash()
        if not sh:
            self.skipTest("no sh / Git Bash to run the plugin hooks")
        env = dict(self.env, CLAUDE_PLUGIN_ROOT=str(REPO / "claude").replace("\\", "/"), DRYAS_PY=py)
        for ev, cmd in cmds:
            self.assertNotIn("/bin/sh", cmd)
            event = dict(EVENTS.get(ev, {}), hook_event_name=ev, cwd=str(self.tmp), session_id="e2e")
            data = json.dumps(event, ensure_ascii=False).encode("utf-8")
            r = subprocess.run([sh, "-c", cmd], input=data, capture_output=True, env=env, timeout=120)
            self.assertEqual(r.returncode, 0, "%s: %s" % (cmd, r.stderr.decode("utf-8", "replace")))
            out = r.stdout.decode("utf-8", "replace").strip()
            if out:
                json.loads(out)

    def test_plugin_uninstall(self):
        self.installed()
        u = self.installer("--uninstall")
        self.assertEqual(u.returncode, 0, u.stdout + u.stderr)
        cd = self.home / ".claude"
        self.assertFalse((cd / ".dryas-plugin.json").exists())
        self.assertFalse((cd / "settings.json").exists())

    def codex_hooks_run(self, cdx):
        rec = json.loads((cdx / ".dryas-codex-plugin.json").read_text(encoding="utf-8"))
        root = rec["plugin_root"]
        hooks = json.loads((Path(root) / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        cmds = [(ev, h["command"]) for ev, groups in hooks.items() for g in groups for h in g["hooks"]]
        self.assertEqual(sorted(ev for ev, _ in cmds), ["PreToolUse", "SessionStart", "UserPromptSubmit"])
        sh = find_bash()
        if not sh:
            self.skipTest("no sh / Git Bash to run the plugin hooks")
        patch = "*** Begin Patch\n*** Add File: notes.txt\n+x\n*** End Patch\n"
        env = dict(self.env, PLUGIN_ROOT=root.replace("\\", "/"))
        for ev, cmd in cmds:
            event = {"hook_event_name": ev, "tool_name": "apply_patch", "tool_input": {"command": patch},
                     "cwd": str(self.tmp), "session_id": "e2e", "source": "startup", "prompt": ""}
            r = subprocess.run([sh, "-c", cmd], input=json.dumps(event).encode("utf-8"), capture_output=True, env=env,
                               timeout=120)
            self.assertEqual(r.returncode, 0, "%s: %s" % (cmd, r.stderr.decode("utf-8", "replace")))
            out = r.stdout.decode("utf-8", "replace").strip()
            if out:
                json.loads(out)

    def test_both_harnesses_install_hooks_run_and_uninstall(self):
        p = self.installer("--harness", "both")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        cdx = self.home / ".codex"
        state = json.loads((cdx / "fake_codex.json").read_text(encoding="utf-8"))
        self.assertIn("dryas@dryas-workflow", state["plugins"])
        self.assertIn("PASS  Dryas hooks trusted", p.stdout)
        self.assertIn("PASS  scope lock blocks an out-of-scope apply_patch", p.stdout)
        self.assertFalse((cdx / "AGENTS.md").exists())  # rules come from the plugin's SessionStart hook now
        self.assertFalse((self.home / ".agents" / "skills" / "orchestrate").exists())
        self.codex_hooks_run(cdx)
        self.assertIn("hooks.state", (cdx / "config.toml").read_text(encoding="utf-8"))
        cd = (self.home / ".claude").resolve()
        u = self.installer("--harness", "codex", "--uninstall")
        self.assertEqual(u.returncode, 0, u.stdout + u.stderr)
        state = json.loads((cdx / "fake_codex.json").read_text(encoding="utf-8"))
        self.assertNotIn("dryas@dryas-workflow", state["plugins"])
        self.assertNotIn("dryas-workflow", state["marketplaces"])
        self.assertFalse((cdx / ".dryas-codex-plugin.json").exists())
        self.assertNotIn("dryas", (cdx / "config.toml").read_text(encoding="utf-8"))
        accounts = json.loads((self.home / ".dryas" / "accounts.json").read_text(encoding="utf-8"))
        self.assertEqual((accounts["codex_dirs"], accounts["claude_dirs"]), ([], [str(cd)]))
        self.assertTrue((cd / ".dryas-plugin.json").exists())  # the Claude Code plugin install is untouched
        u = self.installer("--harness", "claude", "--uninstall", "--purge")
        self.assertEqual(u.returncode, 0, u.stdout + u.stderr)
        self.assertFalse((cd / ".dryas-plugin.json").exists())
        self.assertFalse((self.home / ".dryas").exists())  # no account left: purged

    def test_codex_copy_install_migrated(self):
        cdx = self.home / ".codex"
        cd = legacy_codex.legacy(self.home, cdx)
        p = self.installer("--harness", "codex")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse((cdx / ".dryas-installed.json").exists())
        self.assertEqual((cdx / "AGENTS.md").read_text(encoding="utf-8"), "mine\n")
        self.assertFalse((cdx / "hooks.json").exists())
        self.assertFalse((self.home / ".agents").exists())
        self.assertFalse((cd / ".dryas-installed.json").exists())
        calls = fakecli.calls(self.tmp / "codex-calls.jsonl")
        self.assertIn(["codex", "mcp", "remove", "jev"], calls)
        self.assertIn("PASS  no legacy Codex copy install", p.stdout)
        self.codex_hooks_run(cdx)

if __name__ == "__main__":
    unittest.main()
