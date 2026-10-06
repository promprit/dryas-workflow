import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import fakecli
import platform_util as pu
import run_cmd


class RunCmdTest(unittest.TestCase):
    def setUp(self):
        self.orig = (pu.which, pu.space_free)

    def tearDown(self):
        pu.which, pu.space_free = self.orig

    def test_components(self):
        self.assertEqual(run_cmd.components(run_cmd.parse(["--no-ruflo"])), ["core", "jev", "superpowers", "design", "pstack-picks"])
        self.assertEqual(run_cmd.components(run_cmd.parse([])), ["core", "jev", "ruflo", "superpowers", "design", "pstack-picks"])

    def test_preflight_missing_lists_tools(self):
        pu.which = lambda n: ""
        probs = run_cmd.preflight(["core", "ruflo"], "claude", Path("/x/.claude"))
        self.assertIn("Missing:", probs[0])
        for t in ("git", "claude", "node", "npm"):
            self.assertIn(t, probs[0])

    def test_preflight_ok(self):
        pu.which = lambda n: "/bin/" + n
        pu.space_free = lambda p: str(p)
        self.assertEqual(run_cmd.preflight(["core", "jev", "ruflo"], "claude", Path("/x/.claude")), [])

    def test_preflight_ruflo_space_refused(self):
        pu.which = lambda n: "/bin/" + n
        pu.space_free = lambda p: None
        probs = run_cmd.preflight(["core", "ruflo"], "claude", Path("/x/Ana Silva/.claude"))
        self.assertTrue(any("--no-ruflo" in p for p in probs), probs)
        self.assertEqual(run_cmd.preflight(["core", "jev"], "claude", Path("/x/Ana Silva/.claude")), [])

    def test_harness_choices(self):
        self.assertEqual(run_cmd.parse(["--harness", "both"]).harness, "both")
        with self.assertRaises(SystemExit):
            run_cmd.parse(["--harness", "nope"])

    def test_preflight_codex_needs_codex_cli_only(self):
        pu.which = lambda n: "" if n in ("codex", "claude") else "/bin/" + n
        pu.space_free = lambda p: str(p)
        self.assertIn("codex", run_cmd.preflight(["core"], "codex", Path("/x/.claude"))[0])
        self.assertNotIn("claude(", run_cmd.preflight(["core"], "codex", Path("/x/.claude"))[0])

    def test_preflight_codex_hooks_space_refused_on_windows(self):
        pu.which = lambda n: "/bin/" + n
        pu.space_free = lambda p: None
        orig = pu.IS_WINDOWS
        pu.IS_WINDOWS = True
        try:
            probs = run_cmd.preflight(["core"], "codex", Path("/x/Ana Silva/.claude"))
        finally:
            pu.IS_WINDOWS = orig
        self.assertTrue(any("--harness claude" in p for p in probs), probs)

    def test_codex_only_note(self):
        import io
        from contextlib import redirect_stdout
        import codex_target as ct
        import dryas_install as di
        saved = (di.install, ct.install_codex, ct.verify_codex, di.mapping_for, di.verify, pu.which, pu.space_free, di.confirm)
        di.confirm = lambda *a, **k: False
        di.install = lambda *a, **k: 0
        ct.install_codex = lambda *a, **k: 0
        ct.verify_codex = lambda *a, **k: 0
        di.mapping_for = lambda *a, **k: {}
        pu.which = lambda n: "/bin/" + n
        pu.space_free = lambda p: str(p)
        note = "note: superpowers and design are Claude Code plugins; skipped for Codex."
        try:
            for harness, want in (("codex", True), ("both", False)):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    run_cmd.main(["--harness", harness, "--no-ruflo"])
                self.assertEqual(note in buf.getvalue(), want, harness)
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_cmd.main(["--harness", "codex", "--no-ruflo", "--no-superpowers", "--no-design"])
            self.assertNotIn(note, buf.getvalue())
        finally:
            (di.install, ct.install_codex, ct.verify_codex, di.mapping_for, di.verify, pu.which, pu.space_free, di.confirm) = saved


class ThirdpartyWarnTest(unittest.TestCase):
    def setUp(self):
        import dryas_install as di
        self.di, self.orig = di, (di.run, di.confirm)
        di.run = lambda argv, cwd=None: 0
        di.confirm = lambda prompt: False
        self.home = Path(tempfile.mkdtemp())
        (self.home / ".claude" / "plugins").mkdir(parents=True)
        self.tested = json.loads((HERE.parent / "components.json").read_text())["superpowers"]["tested"]

    def tearDown(self):
        self.di.run, self.di.confirm = self.orig
        shutil.rmtree(str(self.home), ignore_errors=True)

    def out(self, versions):
        import io
        from contextlib import redirect_stdout
        plugins = {} if versions is None else {"superpowers@claude-plugins-official": [{"version": v} for v in versions]}
        (self.home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"plugins": plugins}))
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(run_cmd.thirdparty(["superpowers"], True, home=self.home), 0)
        return buf.getvalue()

    def test_warns_only_when_older_than_tested(self):
        o = self.out(["6.0.0"])
        self.assertIn("superpowers@claude-plugins-official is 6.0.0; Dryas Workflow is tested with %s (older than tested)" % self.tested, o)

    def test_silent_on_equal_or_newer(self):
        for v in (self.tested, "v99.0.0", "99.0.0"):
            self.assertNotIn("warning", self.out([v]), v)

    def test_silent_on_unparseable(self):
        for vs in (["abc"], ["6.0.0-beta"], ["6.0.0", "weird"], ["unknown"]):
            self.assertNotIn("warning", self.out(vs), vs)

    def test_skill_v_prefix_and_newest_wins(self):
        self.assertNotIn("warning", self.out(["skill-v99.0.0"]))
        self.assertNotIn("warning", self.out(["1.0.0", "99.0.0"]))
        self.assertIn("older than tested", self.out(["1.0.0", "2.0.0"]))

    def test_ruflo_plugin_compared_to_plugin_tested(self):
        import io
        from contextlib import redirect_stdout
        table = json.loads((HERE.parent / "components.json").read_text())
        self.assertEqual(table["ruflo"]["plugin_tested"], "0.2.6")
        self.assertEqual(table["superpowers"]["plugin_tested"], "6.4.2")
        self.assertEqual(table["design"]["plugin_tested"], "4.5.0")
        (self.home / ".claude" / "plugins" / "installed_plugins.json").write_text(
            json.dumps({"plugins": {"ruflo-core@ruflo": [{"version": "0.2.6"}]}}))
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(run_cmd.thirdparty(["ruflo"], True, home=self.home), 0)
        self.assertNotIn("older than tested", buf.getvalue())

    def test_unparseable_tested_never_warns(self):
        import io
        from contextlib import redirect_stdout
        table = json.loads((HERE.parent / "components.json").read_text())
        table["superpowers"]["plugin_tested"] = "4.6.0-rc1"
        tp = self.home / "components.json"
        tp.write_text(json.dumps(table))
        (self.home / ".claude" / "plugins" / "installed_plugins.json").write_text(
            json.dumps({"plugins": {"superpowers@claude-plugins-official": [{"version": "1.0.0"}]}}))
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(run_cmd.thirdparty(["superpowers"], True, home=self.home, table_path=tp), 0)
        self.assertNotIn("warning", buf.getvalue())

    def test_warns_when_not_installed(self):
        self.assertIn("superpowers@claude-plugins-official is not installed", self.out(None))


class WrapperTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "Jane Doe"
        self.home.mkdir()
        fb = self.tmp / "bin"
        for n in ("claude", "node", "npm", "git"):
            fakecli.make(fb, n, self.tmp / "calls.jsonl")
        path = [str(fb), os.path.dirname(sys.executable)]
        if os.name == "nt":
            sysroot = os.environ.get("SystemRoot", r"C:\Windows")
            path += [sysroot + r"\System32", sysroot + r"\System32\WindowsPowerShell\v1.0"]
        else:
            path += ["/usr/bin", "/bin"]
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home), PATH=os.pathsep.join(path))

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def wrapper(self, *args):
        if os.name == "nt":
            argv = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE.parent / "install.ps1")]
        else:
            argv = ["/bin/sh", str(HERE.parent / "install.sh")]
        return subprocess.run(argv + list(args), capture_output=True, text=True, env=self.env, timeout=120)

    def test_preflight_only(self):
        p = self.wrapper("--preflight-only", "--no-ruflo")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("preflight ok", p.stdout)

    @unittest.skipIf(os.name == "nt", "Windows usually has an 8.3 short name for the space")
    def test_space_in_home_refuses_ruflo(self):
        p = self.wrapper("--preflight-only")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("--no-ruflo", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
