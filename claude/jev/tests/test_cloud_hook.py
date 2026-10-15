import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

JEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = ("import json, os, sys\n"
         "keys = ('CLAUDE_PLUGIN_ROOT', 'DRYAS_DATA_ROOT', 'DRYAS_NOTES_DIR', 'PYTHONDONTWRITEBYTECODE')\n"
         "print(json.dumps(dict(argv=sys.argv[1:], **{k: os.environ.get(k) for k in keys})))\n")


class CloudHookTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.copy = os.path.join(self.base, "repo", ".dryas")
        self.jev = os.path.join(self.copy, "jev")
        os.makedirs(self.jev)
        shutil.copy(os.path.join(JEV, "cloud_hook.py"), self.jev)
        self.home = os.path.join(self.base, "home")
        os.makedirs(self.home)

    def put(self, name, code):
        with open(os.path.join(self.jev, name), "w", encoding="utf-8") as f:
            f.write(code)

    def run_hook(self, *args, **env):
        e = {"PATH": os.environ.get("PATH", ""), "HOME": self.home, "USERPROFILE": self.home,
             "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
        e.update(env)
        p = subprocess.run([sys.executable, os.path.join(self.jev, "cloud_hook.py")] + list(args), input="{}",
                           capture_output=True, text=True, env=e, timeout=60)
        return p.returncode, p.stdout

    def test_env_points_at_the_copy(self):
        self.put("probe.py", PROBE)
        rc, out = self.run_hook("probe.py", "pretool", "x", CLAUDE_CODE_REMOTE="true", DRYAS_DATA_ROOT="elsewhere")
        self.assertEqual(rc, 0)
        got = json.loads(out)
        self.assertEqual(got["CLAUDE_PLUGIN_ROOT"], self.copy)
        self.assertEqual(got["DRYAS_DATA_ROOT"], os.path.join(self.copy, "state"))
        self.assertEqual(got["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertIsNone(got["DRYAS_NOTES_DIR"])
        self.assertEqual(got["argv"], ["pretool", "x"])
        self.assertTrue(os.path.isdir(os.path.join(self.copy, "state")))

    def test_notes_dir_is_set_when_the_repo_keeps_notes(self):
        os.makedirs(os.path.join(self.copy, "memory", "notes"))
        self.put("probe.py", PROBE)
        rc, out = self.run_hook("probe.py", CLAUDE_CODE_REMOTE="true")
        self.assertEqual(json.loads(out)["DRYAS_NOTES_DIR"], os.path.join(self.copy, "memory", "notes"))

    def test_quiet_on_a_machine_with_dryas_installed(self):
        os.makedirs(os.path.join(self.home, ".dryas"))
        open(os.path.join(self.home, ".dryas", "chain.local.json"), "w").close()
        self.put("probe.py", PROBE)
        self.assertEqual(self.run_hook("probe.py"), (0, ""))
        self.assertFalse(os.path.exists(os.path.join(self.copy, "state")))
        self.assertNotEqual(self.run_hook("probe.py", DRYAS_CLOUD_HOOKS="1")[1], "")
        self.assertNotEqual(self.run_hook("probe.py", CLAUDE_CODE_REMOTE="true")[1], "")
        self.assertEqual(self.run_hook("probe.py", CLAUDE_CODE_REMOTE="true", DRYAS_CLOUD_HOOKS="0"), (0, ""))

    def test_internal_error_asks_for_pretool(self):
        self.put("chain.py", "raise RuntimeError('boom')\n")
        rc, out = self.run_hook("chain.py", "pretool", CLAUDE_CODE_REMOTE="true")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertEqual(self.run_hook("chain.py", "session-end", CLAUDE_CODE_REMOTE="true"), (0, ""))

    def test_only_scripts_beside_it_run(self):
        for name in ("../x.py", "missing.py", "cloud_hook.py", "chain"):
            self.assertEqual(self.run_hook(name, "pretool", CLAUDE_CODE_REMOTE="true"), (0, ""), name)

    def test_exit_code_of_the_script_is_kept(self):
        self.put("probe.py", "import sys\nsys.exit(3)\n")
        self.assertEqual(self.run_hook("probe.py", CLAUDE_CODE_REMOTE="true")[0], 3)

    # Added beyond the plan: gaps a wrong implementation could still pass.

    def test_absolute_and_nested_names_are_refused(self):
        outside = os.path.join(self.base, "evil.py")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("print('ran')\n")
        os.makedirs(os.path.join(self.jev, "sub"))
        self.put(os.path.join("sub", "x.py"), "print('ran')\n")
        for name in (outside, "sub/x.py", "../../evil.py", ""):
            self.assertEqual(self.run_hook(name, CLAUDE_CODE_REMOTE="true"), (0, ""), name)

    def test_no_arguments_is_a_quiet_no_op(self):
        self.assertEqual(self.run_hook(CLAUDE_CODE_REMOTE="true"), (0, ""))

    def test_missing_chain_asks_for_pretool(self):
        rc, out = self.run_hook("chain.py", "pretool", CLAUDE_CODE_REMOTE="true")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_runs_without_install_and_flags_are_parsed_loosely(self):
        self.put("probe.py", PROBE)
        self.assertNotEqual(self.run_hook("probe.py")[1], "")
        self.assertEqual(self.run_hook("probe.py", DRYAS_CLOUD_HOOKS="0"), (0, ""))
        os.makedirs(os.path.join(self.home, ".dryas"))
        open(os.path.join(self.home, ".dryas", "chain.local.json"), "w").close()
        self.assertNotEqual(self.run_hook("probe.py", CLAUDE_CODE_REMOTE=" TRUE ")[1], "")
        self.assertEqual(self.run_hook("probe.py", CLAUDE_CODE_REMOTE="false"), (0, ""))
        self.assertEqual(self.run_hook("chain.py", "pretool"), (0, ""))  # quiet means no ask either

    def test_stdin_main_guard_and_sibling_imports(self):
        self.put("helper.py", "VALUE = 'sib'\n")
        self.put("probe.py", "import sys, helper\n"
                             "if __name__ == '__main__':\n"
                             "    print(helper.VALUE + ':' + sys.stdin.read())\n")
        e = {"PATH": os.environ.get("PATH", ""), "HOME": self.home, "USERPROFILE": self.home,
             "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""), "CLAUDE_CODE_REMOTE": "true"}
        p = subprocess.run([sys.executable, os.path.join(self.jev, "cloud_hook.py"), "probe.py"],
                           input='{"tool_name": "Bash"}', capture_output=True, text=True, env=e, timeout=60)
        self.assertEqual((p.returncode, p.stdout.strip()), (0, 'sib:{"tool_name": "Bash"}'))

    def test_blocking_exit_code_two_is_kept(self):
        self.put("chain.py", "import sys\nsys.stderr.write('blocked')\nsys.exit(2)\n")
        self.assertEqual(self.run_hook("chain.py", "pretool", CLAUDE_CODE_REMOTE="true"), (2, ""))

    def test_main_returns_without_running_when_quiet(self):
        sys.path.insert(0, self.jev)
        self.addCleanup(sys.path.remove, self.jev)
        import importlib
        mod = importlib.import_module("cloud_hook")
        self.addCleanup(sys.modules.pop, "cloud_hook", None)
        old = os.environ.get("DRYAS_CLOUD_HOOKS")
        os.environ["DRYAS_CLOUD_HOOKS"] = "0"
        try:
            self.assertFalse(mod.wanted())
            self.assertEqual(mod.main(["cloud_hook.py", "chain.py", "pretool"]), 0)
        finally:
            if old is None:
                os.environ.pop("DRYAS_CLOUD_HOOKS")
            else:
                os.environ["DRYAS_CLOUD_HOOKS"] = old
        self.assertEqual(mod.ASK["hookSpecificOutput"]["permissionDecision"], "ask")

    # Follow-up: a partial write must not break the pretool JSON, and sys.exit("msg") acts as in Python.

    def run_full(self, *args):
        e = {"PATH": os.environ.get("PATH", ""), "HOME": self.home, "USERPROFILE": self.home,
             "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""), "CLAUDE_CODE_REMOTE": "true"}
        p = subprocess.run([sys.executable, os.path.join(self.jev, "cloud_hook.py")] + list(args), input="{}",
                           capture_output=True, text=True, env=e, timeout=60)
        return p.returncode, p.stdout, p.stderr

    def test_partial_output_then_crash_gives_only_ask(self):
        self.put("chain.py", "import sys\nsys.stdout.write('{\"hookSpecificOutput\": {\"permissionDec')\n"
                             "print('more')\nraise RuntimeError('boom')\n")
        rc, out, _ = self.run_full("chain.py", "pretool")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), json.loads(json.dumps(self.ask())))

    def ask(self):
        sys.path.insert(0, self.jev)
        try:
            import importlib
            sys.modules.pop("cloud_hook", None)
            return importlib.import_module("cloud_hook").ASK
        finally:
            sys.path.remove(self.jev)
            sys.modules.pop("cloud_hook", None)

    def test_output_of_a_good_run_is_written_unchanged(self):
        self.put("chain.py", "import sys\nsys.stdout.write('{\"a\": 1}')\nprint()\nsys.stdout.write('tail')\n")
        self.assertEqual(self.run_full("chain.py", "pretool")[:2], (0, '{"a": 1}\ntail'))

    def test_exit_two_keeps_its_output(self):
        self.put("chain.py", "import sys\nprint('reason')\nsys.stderr.write('blocked')\nsys.exit(2)\n")
        self.assertEqual(self.run_full("chain.py", "pretool"), (2, "reason\n", "blocked"))

    def test_exit_codes_follow_python(self):
        for code, rc in (("'bad thing'", 1), ("None", 0), ("0", 0), ("5", 5), ("False", 0), ("True", 1)):
            self.put("probe.py", "import sys\nprint('out')\nsys.exit(%s)\n" % code)
            got = self.run_full("probe.py")
            self.assertEqual(got[:2], (rc, "out\n"), code)
        self.put("probe.py", "import sys\nsys.exit('bad thing')\n")
        self.assertEqual(self.run_full("probe.py")[2].strip(), "bad thing")
        self.assertEqual(self.run_full("probe.py", "pretool")[:2], (1, ""))


if __name__ == "__main__":
    unittest.main()
