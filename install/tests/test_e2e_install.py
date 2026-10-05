"""End to end: real install into a temp home with a fake `claude`, then run every installed hook command
through the OS shells with a sample event, then uninstall."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fakecli
REPO = HERE.parents[1]
EVENTS = {
    "PreToolUse": {"tool_name": "Write", "tool_input": {"file_path": "notes.txt", "content": "café → ok"}},
    "UserPromptSubmit": {"prompt": ""},
    "SessionStart": {"source": "startup"},
    "PreCompact": {"trigger": "manual"},
}


def shells():
    out = [None]  # None = the OS default shell via shell=True (sh on POSIX, cmd on Windows)
    if os.name == "nt":
        git_bash = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Git", "bin", "bash.exe")
        if os.path.isfile(git_bash):
            out.append(git_bash)
    return out


class E2ETest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.home.mkdir()
        fb = self.tmp / "bin"
        fakecli.make(fb, "claude", self.tmp / "calls.jsonl", outputs={"mcp list": "jev: ok\n"})
        fakecli.make(fb, "codex", self.tmp / "calls.jsonl", outputs={"mcp list": "jev\n"})
        self.env = {k: v for k, v in os.environ.items() if k not in ("OPENROUTER_API_KEY", "DRYAS_DATA_ROOT", "CODEX_HOME")}
        self.env["CODEX_HOME"] = str(self.home / ".codex")
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home), PATH=str(fb) + os.pathsep + os.environ["PATH"],
                        JEV_LOG_DIR=str(self.tmp / "logs"), JEV_HANDOFF_DIR=str(self.tmp / "handoff"),
                        JEV_COMPACT_DIR=str(self.tmp / "compact"))

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def installer(self, *args):
        return subprocess.run([sys.executable, str(REPO / "install" / "dryas_install.py"), "run", "--repo", str(REPO),
                               "--yes", "--no-ruflo", "--no-superpowers", "--no-design"] + list(args),
                              capture_output=True, text=True, env=self.env, timeout=900)

    def test_install_hooks_run_and_uninstall(self):
        p = self.installer()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        cd = self.home / ".claude"
        settings = json.loads((cd / "settings.json").read_text(encoding="utf-8"))
        cmds = [(ev, h["command"]) for ev, groups in settings["hooks"].items() for g in groups for h in g["hooks"]]
        self.assertTrue(cmds)
        for ev, cmd in cmds:
            self.assertNotIn("/bin/sh", cmd)
            event = dict(EVENTS.get(ev, {}), hook_event_name=ev, cwd=str(self.tmp), session_id="e2e")
            data = json.dumps(event, ensure_ascii=False).encode("utf-8")
            for sh in shells():
                argv = cmd if sh is None else [sh, "-c", cmd]
                r = subprocess.run(argv, shell=sh is None, input=data, capture_output=True, env=self.env, timeout=120)
                self.assertEqual(r.returncode, 0, "%s via %s: %s" % (cmd, sh or "default shell",
                                                                     r.stderr.decode("utf-8", "replace")))
                out = r.stdout.decode("utf-8", "replace").strip()
                if out:
                    json.loads(out)
        u = self.installer("--uninstall")
        self.assertEqual(u.returncode, 0, u.stdout + u.stderr)
        self.assertFalse((cd / ".dryas-installed.json").exists())
        self.assertFalse((cd / "settings.json").exists())

    def test_both_harnesses_install_hooks_run_and_uninstall(self):
        p = self.installer("--harness", "both")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        cdx = self.home / ".codex"
        self.assertTrue((cdx / "AGENTS.md").exists())
        self.assertTrue((self.home / ".agents" / "skills" / "orchestrate" / "SKILL.md").exists())
        hooks = json.loads((cdx / "hooks.json").read_text(encoding="utf-8"))
        cmds = [h["command"] for groups in hooks["hooks"].values() for g in groups for h in g["hooks"]]
        self.assertTrue(cmds)
        patch = "*** Begin Patch\n*** Add File: notes.txt\n+x\n*** End Patch\n"
        event = {"hook_event_name": "PreToolUse", "tool_name": "apply_patch", "tool_input": {"command": patch},
                 "cwd": str(self.tmp), "session_id": "e2e"}
        data = json.dumps(event).encode("utf-8")
        for cmd in cmds:
            r = subprocess.run(cmd, shell=True, input=data, capture_output=True, env=self.env, timeout=120)
            self.assertEqual(r.returncode, 0, "%s: %s" % (cmd, r.stderr.decode("utf-8", "replace")))
        u = self.installer("--harness", "both", "--uninstall")
        self.assertEqual(u.returncode, 0, u.stdout + u.stderr)
        self.assertFalse((cdx / ".dryas-installed.json").exists())
        self.assertFalse((self.home / ".agents" / "skills" / "orchestrate").exists())


if __name__ == "__main__":
    unittest.main()
