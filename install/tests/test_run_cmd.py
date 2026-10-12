import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import fakecli
import platform_util as pu
import run_cmd
REPO_ROOT = HERE.parents[1]


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
        stubs = MainStubs(self)
        note = "note: superpowers and design are Claude Code plugins; skipped for Codex."
        for harness, want in (("codex", True), ("both", False)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_cmd.main(["--harness", harness, "--no-ruflo"])
            self.assertEqual(note in buf.getvalue(), want, harness)
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_cmd.main(["--harness", "codex", "--no-ruflo", "--no-superpowers", "--no-design"])
        self.assertNotIn(note, buf.getvalue())
        self.assertTrue(stubs.log)


class MainStubs(object):
    """Stub every step run_cmd.main drives; self.log records (step, args, kwargs)."""

    def __init__(self, tc):
        from unittest import mock
        import codex_target as ct
        import dryas_install as di
        import migrate
        import plugin_setup as ps
        self.log = []
        self.copy = False  # what migrate.is_copy_install reports

        def rec(name, rc=0):
            return lambda *a, **k: self.log.append((name, a, k)) or rc
        self.tmp = Path(tempfile.mkdtemp())
        tc.addCleanup(shutil.rmtree, str(self.tmp), True)
        patches = [mock.patch.object(di, "install", rec("di.install")), mock.patch.object(di, "uninstall", rec("di.uninstall")),
                   mock.patch.object(di, "mapping_for", lambda *a, **k: {}), mock.patch.object(di, "confirm", lambda *a: False),
                   mock.patch.object(ct, "install_codex", rec("ct.install_codex")),
                   mock.patch.object(ct, "uninstall_codex", rec("ct.uninstall_codex")),
                   mock.patch.object(ct, "verify_codex", rec("ct.verify_codex")),
                   mock.patch.object(ct, "codex_dir", lambda: self.tmp / ".codex"),
                   mock.patch.object(migrate, "migrate", rec("migrate")),
                   mock.patch.object(migrate, "is_copy_install", lambda cd: self.copy),
                   mock.patch.object(ps, "setup", rec("ps.setup")), mock.patch.object(ps, "verify", rec("ps.verify")),
                   mock.patch.object(ps, "uninstall", rec("ps.uninstall")),
                   mock.patch.object(pu, "which", lambda n: "/bin/" + n), mock.patch.object(pu, "space_free", lambda p: str(p)),
                   mock.patch.dict(os.environ, {"HOME": str(self.tmp), "USERPROFILE": str(self.tmp),
                                                "DRYAS_DATA_ROOT": str(self.tmp / "data"), "OPENROUTER_API_KEY": "sk-env"})]
        for p in patches:
            p.start()
            tc.addCleanup(p.stop)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)  # restored by the patch.dict above

    def steps(self):
        return [n for n, a, k in self.log]

    def call(self, name):
        return [(a, k) for n, a, k in self.log if n == name][0]


class MainTest(unittest.TestCase):
    def main(self, *args):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_cmd.main(list(args))
        self.out = buf.getvalue()
        return rc

    def test_claude_dir_migrate_then_setup_then_verify(self):
        st = MainStubs(self)
        st.copy = True
        cd = st.tmp / "acct"
        self.assertEqual(self.main("--claude-dir", str(cd), "--no-ruflo", "--flowobserve", "--yes"), 0)
        self.assertEqual(st.steps(), ["migrate", "ps.setup", "ps.verify"])
        a, k = st.call("migrate")
        self.assertEqual([Path(x) for x in a], [cd.resolve(), st.tmp / "data"])
        a, k = st.call("ps.setup")
        self.assertEqual(a[1], cd.resolve())
        self.assertEqual(k, {"yes": True, "key": "sk-env", "flowobserve": True, "dry": False})

    def test_key_flag_and_default_dir(self):
        st = MainStubs(self)
        self.main("--openrouter-key", "sk-flag", "--no-ruflo")
        a, k = st.call("ps.setup")
        self.assertEqual(a[1], (st.tmp / ".claude").resolve())
        self.assertEqual(k["key"], "sk-flag")
        self.assertFalse(k["flowobserve"])

    def test_no_copy_install_no_migration(self):
        st = MainStubs(self)
        self.assertEqual(self.main("--no-ruflo"), 0)
        self.assertEqual(st.steps(), ["ps.setup", "ps.verify"])

    def test_dry_run_skips_migration_and_verify(self):
        st = MainStubs(self)
        st.copy = True
        self.assertEqual(self.main("--dry-run", "--no-ruflo"), 0)
        self.assertEqual(st.steps(), ["ps.setup"])
        self.assertTrue(st.call("ps.setup")[1]["dry"])
        self.assertIn("would migrate the copy install in %s" % (st.tmp / ".claude").resolve(), self.out)

    def _codex_record(self, st, comps):
        (st.tmp / ".codex").mkdir()
        (st.tmp / ".codex" / ".dryas-installed.json").write_text(json.dumps({"components": comps}))

    def test_claude_only_migration_keeps_existing_codex(self):
        st = MainStubs(self)
        st.copy = True
        self._codex_record(st, ["core", "jev"])
        self.assertEqual(self.main("--no-ruflo"), 0)
        self.assertEqual(st.steps(), ["migrate", "ps.setup", "di.install", "ct.install_codex", "ps.verify",
                                      "ct.verify_codex"])
        self.assertEqual(st.call("ct.verify_codex")[0][2], ["core", "jev"])
        a, k = st.call("di.install")
        self.assertEqual((a[1], a[2], k["claude"]), (st.tmp / ".claude", ["core", "jev"], False))
        self.assertIn("Codex keeps working", self.out)

    def test_kept_codex_ruflo_is_preflighted(self):
        st = MainStubs(self)
        st.copy = True
        self._codex_record(st, ["core", "ruflo"])
        from unittest import mock
        seen = []
        with mock.patch.object(run_cmd, "preflight", lambda *a: seen.append(a) or ["stop"]):
            self.assertEqual(self.main("--no-ruflo"), 1)
        self.assertIn("ruflo", seen[0][0])
        self.assertIn(st.tmp / ".claude", seen[0][3])

    def test_unreadable_record_stops(self):
        st = MainStubs(self)
        (st.tmp / ".claude").mkdir()
        (st.tmp / ".claude" / ".dryas-installed.json").write_text("{broken")
        self.assertEqual(self.main("--no-ruflo"), 1)
        self.assertEqual(st.steps(), [])
        self.assertIn("cannot be read", self.out)

    def test_claude_only_other_dir_leaves_codex_alone(self):
        st = MainStubs(self)
        st.copy = True
        self._codex_record(st, ["core", "jev"])
        self.main("--no-ruflo", "--claude-dir", str(st.tmp / "acct"))
        self.assertNotIn("di.install", st.steps())

    def test_setup_failure_after_migration_still_installs_codex(self):
        st = MainStubs(self)
        st.copy = True
        import plugin_setup as ps
        from unittest import mock
        with mock.patch.object(ps, "setup", lambda *a, **k: 3):
            self.assertEqual(self.main("--no-ruflo", "--harness", "both"), 3)
        self.assertEqual(st.steps(), ["migrate", "di.install", "ct.install_codex"])
        self.assertIn("Your copy install was migrated", self.out)
        self.assertIn("plugin setup failed", self.out)

    def test_codex_ruflo_paths_include_copy_dir(self):
        st = MainStubs(self)
        from unittest import mock
        seen = []
        with mock.patch.object(run_cmd, "preflight", lambda *a: seen.append(a) or []):
            self.main("--harness", "both", "--no-ruflo")
        self.assertEqual(seen[0][2], st.tmp / ".claude")
        self.assertIn(st.tmp / ".claude", seen[0][3])
        self.assertIn(REPO_ROOT / "claude", seen[0][3])

    def test_codex_keeps_runtime_copy_in_home_claude(self):
        st = MainStubs(self)
        self.assertEqual(self.main("--harness", "codex", "--no-ruflo", "--claude-dir", str(st.tmp / "acct")), 0)
        self.assertEqual(st.steps(), ["di.install", "ct.install_codex", "ct.verify_codex"])
        a, k = st.call("di.install")
        self.assertEqual(a[1], st.tmp / ".claude")
        self.assertIs(k["claude"], False)

    def test_claude_uninstall_touches_only_that_dir(self):
        st = MainStubs(self)
        cd = st.tmp / "acct"
        self.assertEqual(self.main("--uninstall", "--purge", "--claude-dir", str(cd)), 0)
        self.assertEqual(st.steps(), ["ps.uninstall"])
        self.assertEqual(st.call("ps.uninstall")[0], (cd.resolve(), True))

    def test_both_uninstall(self):
        st = MainStubs(self)
        self.main("--uninstall", "--harness", "both")
        self.assertEqual(st.steps(), ["ct.uninstall_codex", "di.uninstall", "ps.uninstall"])
        self.assertEqual(st.call("di.uninstall")[0], (st.tmp / ".claude",))

    def test_setup_failure_stops(self):
        st = MainStubs(self)
        import plugin_setup as ps
        from unittest import mock
        with mock.patch.object(ps, "setup", lambda *a, **k: 3):
            self.assertEqual(self.main("--no-ruflo", "--harness", "both"), 3)
        self.assertNotIn("di.install", st.steps())

    def test_ruflo_space_checks_data_root_and_plugin(self):
        from unittest import mock
        seen = []
        with mock.patch.object(pu, "which", lambda n: "/bin/" + n), \
                mock.patch.object(pu, "space_free", lambda p: seen.append(str(p)) or str(p)), \
                mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": "/d/root"}):
            self.assertEqual(run_cmd.preflight(["core", "ruflo"], "claude", Path("/x/.claude"), [Path("/r/claude")]), [])
        self.assertIn(str(Path("/d/root")), seen)
        self.assertIn(str(Path("/r/claude")), seen)
        self.assertNotIn(str(Path("/x/.claude")), seen)  # the Codex copy dir matters only to the Codex check


class ThirdpartyWarnTest(unittest.TestCase):
    def setUp(self):
        import dryas_install as di
        self.di, self.orig = di, (di.run, di.confirm)
        self.ran = []
        di.run = lambda argv, cwd=None, env=None: self.ran.append((argv, env)) or 0
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
            self.assertEqual(run_cmd.thirdparty(["superpowers"], True, claude_dir=self.home / ".claude"), 0)
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
            self.assertEqual(run_cmd.thirdparty(["ruflo"], True, claude_dir=self.home / ".claude"), 0)
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
            self.assertEqual(run_cmd.thirdparty(["superpowers"], True, claude_dir=self.home / ".claude", table_path=tp), 0)
        self.assertNotIn("warning", buf.getvalue())

    def test_warns_when_not_installed(self):
        self.assertIn("superpowers@claude-plugins-official is not installed", self.out(None))

    def test_skips_superpowers_commands_and_passes_env(self):
        import io
        from contextlib import redirect_stdout
        (self.home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"plugins": {}}))
        env = {"CLAUDE_CONFIG_DIR": str(self.home / ".claude")}
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(run_cmd.thirdparty(["superpowers", "design"], True, self.home / ".claude", env), 0)
        self.assertTrue(self.ran)
        self.assertFalse(any("superpowers@claude-plugins-official" in argv for argv, _ in self.ran))
        self.assertTrue(all(e is env for _, e in self.ran))
        self.assertIn("superpowers@claude-plugins-official is not installed", buf.getvalue())


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
