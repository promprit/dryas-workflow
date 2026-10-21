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
        self.assertEqual(run_cmd.components(run_cmd.parse(["--no-ruflo"])), ["core", "jev", "memory", "design", "pstack-picks", "rea"])
        self.assertEqual(run_cmd.components(run_cmd.parse([])), ["core", "jev", "memory", "design", "pstack-picks", "rea"])

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

    def test_preflight_codex_python3(self):
        from unittest import mock
        import codex_plugin_setup as cps
        pu.which = lambda n: "/bin/" + n
        pu.space_free = lambda p: str(p)
        with mock.patch.object(run_cmd, "codex_version", lambda: (0, 162, 1)), \
                mock.patch.object(pu, "IS_WINDOWS", False):
            for ok in (False, True):
                with mock.patch.object(cps, "python3_ok", lambda: ok):
                    probs = run_cmd.preflight(["core"], "codex", Path("/x/.claude"))
                    self.assertEqual(any("python3" in p and "3.9" in p for p in probs), not ok, probs)
            with mock.patch.object(cps, "python3_ok", lambda: False):
                self.assertEqual(run_cmd.preflight(["core"], "claude", Path("/x/.claude")), [])

    def test_preflight_windows_warns_without_python(self):
        import io
        from contextlib import redirect_stdout
        from unittest import mock
        import codex_plugin_setup as cps
        pu.space_free = lambda p: str(p)
        with mock.patch.object(run_cmd, "codex_version", lambda: (0, 162, 1)), \
                mock.patch.object(pu, "IS_WINDOWS", True), \
                mock.patch.object(cps, "python3_ok", lambda: False):
            for have in (False, True):
                pu.which = lambda n: "" if (n == "python" and not have) else "/bin/" + n
                buf = io.StringIO()
                with redirect_stdout(buf):
                    probs = run_cmd.preflight(["core"], "codex", Path("/x/.claude"))
                self.assertEqual(probs, [])
                self.assertEqual("warning: `python` is not on PATH" in buf.getvalue(), not have, buf.getvalue())

    def test_preflight_codex_version(self):
        from unittest import mock
        import codex_plugin_setup as cps
        p = mock.patch.object(cps, "python3_ok", lambda: True)
        p.start()
        self.addCleanup(p.stop)
        pu.which = lambda n: "/bin/" + n
        pu.space_free = lambda p: str(p)
        with mock.patch.object(run_cmd, "codex_version", lambda: (0, 150, 0)):
            probs = run_cmd.preflight(["core"], "codex", Path("/x/.claude"))
            self.assertTrue(any("0.162.1" in p and "0.150.0" in p for p in probs), probs)
            self.assertEqual(run_cmd.preflight(["core"], "claude", Path("/x/.claude")), [])
        with mock.patch.object(run_cmd, "codex_version", lambda: None):
            self.assertTrue(run_cmd.preflight(["core"], "both", Path("/x/.claude")))
        with mock.patch.object(run_cmd, "codex_version", lambda: (0, 162, 1)):
            self.assertEqual(run_cmd.preflight(["core", "ruflo"], "codex", Path("/x/.claude")), [])

    def test_preflight_codex_ruflo_needs_node_npm(self):
        from unittest import mock
        import codex_plugin_setup as cps
        p = mock.patch.object(cps, "python3_ok", lambda: True)
        p.start()
        self.addCleanup(p.stop)
        pu.which = lambda n: "" if n in ("node", "npm") else "/bin/" + n
        with mock.patch.object(run_cmd, "codex_version", lambda: (0, 162, 1)):
            probs = run_cmd.preflight(["core", "ruflo"], "codex", Path("/x/.claude"))
            self.assertIn("node npm", probs[0])
            self.assertEqual(run_cmd.preflight(["core"], "codex", Path("/x/.claude")), [])

    def test_codex_dir_parsed(self):
        self.assertEqual(run_cmd.parse(["--codex-dir", "/c"]).codex_dir, "/c")
        self.assertIsNone(run_cmd.parse([]).codex_dir)

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
        import codex_plugin_setup as cps
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
        patches = [mock.patch.object(di, "uninstall", rec("di.uninstall")),
                   mock.patch.object(di, "confirm", lambda *a: False),
                   mock.patch.object(cps, "setup", rec("cps.setup")), mock.patch.object(cps, "verify", rec("cps.verify")),
                   mock.patch.object(cps, "uninstall", rec("cps.uninstall")),
                   mock.patch.object(cps, "codex_home", lambda arg: Path(arg) if arg else self.tmp / ".codex"),
                   mock.patch.object(run_cmd, "codex_version", lambda: cps.MIN_CODEX),
                   mock.patch.object(cps, "python3_ok", lambda: True),
                   mock.patch.object(ct, "uninstall_codex", rec("ct.uninstall_codex")),
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
        from unittest import mock
        p = mock.patch.dict(os.environ, {"JEV_THRESHOLDS": str(st.tmp / "thresholds.json")})
        p.start()
        self.addCleanup(p.stop)
        self.assertEqual(self.main("--claude-dir", str(cd), "--no-ruflo", "--flowobserve", "--yes"), 0)
        self.assertEqual(st.steps(), ["migrate", "ps.setup", "ps.verify"])
        a, k = st.call("migrate")
        self.assertEqual([Path(x) for x in a], [cd.resolve(), st.tmp / "data"])
        a, k = st.call("ps.setup")
        self.assertEqual(a[1], cd.resolve())
        self.assertEqual(k, {"yes": True, "key": "", "flowobserve": True, "dry": False,
                             "providers": {"judge": "auto", "memory": "dryas", "process": "dryas"}})

    def test_key_flag_and_default_dir(self):
        st = MainStubs(self)
        self.main("--openrouter-key", "sk-flag", "--no-ruflo")
        a, k = st.call("ps.setup")
        self.assertEqual(a[1], (st.tmp / ".claude").resolve())
        self.assertEqual(k["key"], "sk-flag")
        self.assertIsNone(k["flowobserve"])

    def test_no_flowobserve_flag(self):
        st = MainStubs(self)
        self.main("--no-ruflo", "--no-flowobserve")
        a, k = st.call("ps.setup")
        self.assertIs(k["flowobserve"], False)

    def test_flowobserve_flags_exclusive(self):
        MainStubs(self)
        with self.assertRaises(SystemExit):
            run_cmd.parse(["--flowobserve", "--no-flowobserve"])

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

    def test_unreadable_record_stops(self):
        st = MainStubs(self)
        (st.tmp / ".claude").mkdir()
        (st.tmp / ".claude" / ".dryas-installed.json").write_text("{broken")
        self.assertEqual(self.main("--no-ruflo"), 1)
        self.assertEqual(st.steps(), [])
        self.assertIn("cannot be read", self.out)

    def test_non_dict_record_stops(self):
        for bad in ("[]", '"x"'):
            st = MainStubs(self)
            (st.tmp / ".claude").mkdir()
            (st.tmp / ".claude" / ".dryas-installed.json").write_text(bad)
            self.assertEqual(self.main("--no-ruflo"), 1, bad)
            self.assertEqual(st.steps(), [])
            self.assertIn("cannot be read", self.out)

    def test_key_not_taken_from_env(self):
        st = MainStubs(self)  # OPENROUTER_API_KEY=sk-env is set: it must not reach the plugin install argv
        self.main("--no-ruflo")
        self.assertEqual(st.call("ps.setup")[1]["key"], "")

    def test_claude_uninstall_touches_only_that_dir(self):
        st = MainStubs(self)
        cd = st.tmp / "acct"
        self.assertEqual(self.main("--uninstall", "--purge", "--claude-dir", str(cd)), 0)
        self.assertEqual(st.steps(), ["ps.uninstall"])
        self.assertEqual(st.call("ps.uninstall")[0], (cd.resolve(), True))

    def test_both_uninstall_codex_first(self):
        st = MainStubs(self)
        self.main("--uninstall", "--harness", "both")
        self.assertEqual(st.steps(), ["cps.uninstall", "ps.uninstall"])

    def test_codex_only_purge(self):
        st = MainStubs(self)
        import plugin_setup as ps
        from unittest import mock
        seen = []
        with mock.patch.object(ps, "purge_shared", lambda: seen.append(1) or True):
            self.main("--uninstall", "--purge", "--harness", "codex")
        self.assertEqual((st.steps(), seen), (["cps.uninstall"], [1]))

    def test_codex_uninstall_one_codex_home_never_claude(self):
        st = MainStubs(self)
        self.assertEqual(self.main("--uninstall", "--harness", "codex", "--codex-dir", str(st.tmp / "cx2")), 0)
        self.assertEqual(st.steps(), ["cps.uninstall"])  # no copy uninstall of ~/.claude (a live Claude install)
        self.assertEqual(st.call("cps.uninstall")[0], (st.tmp / "cx2",))

    def test_codex_uninstall_failure_stops_before_claude(self):
        st = MainStubs(self)
        import codex_plugin_setup as cps
        from unittest import mock
        with mock.patch.object(cps, "uninstall", lambda cdx: 1):
            self.assertEqual(self.main("--uninstall", "--purge", "--harness", "both"), 1)
        self.assertEqual(st.steps(), [])

    def test_setup_failure_stops(self):
        st = MainStubs(self)
        st.copy = True
        import plugin_setup as ps
        from unittest import mock
        with mock.patch.object(ps, "setup", lambda *a, **k: 3):
            self.assertEqual(self.main("--no-ruflo", "--harness", "both"), 3)
        self.assertEqual(st.steps(), ["cps.setup", "migrate"])  # no verify; Codex no longer needs ~/.claude
        self.assertIn("Your copy install was migrated", self.out)
        self.assertIn("plugin setup failed", self.out)

    def test_codex_harness_is_the_plugin(self):
        st = MainStubs(self)
        self.assertEqual(self.main("--harness", "codex", "--no-ruflo"), 0)
        self.assertEqual(st.steps(), ["cps.setup", "cps.verify"])
        a, k = st.call("cps.setup")
        self.assertEqual(a[1], st.tmp / ".codex")

    def test_codex_dir_flag(self):
        st = MainStubs(self)
        self.main("--harness", "codex", "--codex-dir", str(st.tmp / "cx2"))
        self.assertEqual(st.call("cps.setup")[0][1], st.tmp / "cx2")
        self.assertEqual(st.call("cps.verify")[0][0], st.tmp / "cx2")

    def test_both_runs_codex_first(self):
        st = MainStubs(self)
        st.copy = True
        self.assertEqual(self.main("--harness", "both", "--no-ruflo"), 0)
        self.assertEqual(st.steps(), ["cps.setup", "migrate", "ps.setup", "ps.verify", "cps.verify"])

    def test_codex_dry_run(self):
        st = MainStubs(self)
        self.assertEqual(self.main("--harness", "codex", "--dry-run"), 0)
        self.assertEqual(st.steps(), ["cps.setup"])
        self.assertTrue(st.call("cps.setup")[1]["dry"])

    def test_codex_failure_stops_before_claude(self):
        st = MainStubs(self)
        import codex_plugin_setup as cps
        from unittest import mock
        with mock.patch.object(cps, "setup", lambda *a, **k: 4):
            self.assertEqual(self.main("--harness", "both"), 4)
        self.assertNotIn("ps.setup", st.steps())
        self.assertNotIn("migrate", st.steps())

    def test_claude_only_with_legacy_codex_refuses(self):
        st = MainStubs(self)
        st.copy = True
        self._codex_record(st, ["core", "jev"])
        self.assertEqual(self.main("--claude-dir", str(st.tmp / ".claude")), 1)
        self.assertEqual(st.steps(), [])
        self.assertIn("--harness both", self.out)
        self.assertIn("--uninstall --harness codex", self.out)  # for users who dropped Codex
        self.assertIn("install.ps1", self.out)

    def test_claude_only_other_dir_ignores_legacy_codex(self):
        st = MainStubs(self)
        st.copy = True
        self._codex_record(st, ["core", "jev"])
        self.assertEqual(self.main("--claude-dir", str(st.tmp / "acct")), 0)
        self.assertEqual(st.steps(), ["migrate", "ps.setup", "ps.verify"])

    def test_legacy_components_used_without_flags(self):
        st = MainStubs(self)
        self._codex_record(st, ["core", "jev"])
        self.main("--harness", "codex")
        self.assertEqual(st.call("cps.setup")[0][2], ["core", "jev"])
        self.main("--harness", "codex", "--no-ruflo")
        last = [a for n, a, k in st.log if n == "cps.setup"][-1]
        self.assertNotIn("ruflo", last[2])
        self.assertIn("pstack-picks", last[2])

    def test_openrouter_key_ignored_for_codex(self):
        st = MainStubs(self)
        self.main("--harness", "codex", "--openrouter-key", "sk-x")
        self.assertIn("--openrouter-key is not used for Codex", self.out)
        self.assertNotIn("sk-x", json.dumps([list(map(str, a)) + [str(k)] for n, a, k in st.log]))

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
        self.tested = json.loads((HERE.parent / "components.json").read_text())["superpowers"]["plugin_tested"]

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
        self.assertEqual(table["superpowers"]["plugin_tested"], "6.4.1")
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

    def test_runs_superpowers_command_and_passes_env(self):
        import io
        from contextlib import redirect_stdout
        (self.home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"plugins": {}}))
        env = {"CLAUDE_CONFIG_DIR": str(self.home / ".claude")}
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(run_cmd.thirdparty(["superpowers", "design"], True, self.home / ".claude", env), 0)
        self.assertTrue(self.ran)
        self.assertTrue(any("superpowers@claude-plugins-official" in argv for argv, _ in self.ran))
        self.assertTrue(all(e is env for _, e in self.ran))
        self.assertIn("superpowers@claude-plugins-official is not installed", buf.getvalue())

    def test_superpowers_failure_does_not_abort(self):
        import io
        from contextlib import redirect_stdout
        self.di.run = lambda argv, cwd=None, env=None: self.ran.append((argv, env)) or (
            3 if any("superpowers@" in a for a in argv) else 0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_cmd.thirdparty(["superpowers", "design"], True, self.home / ".claude")
        self.assertEqual(rc, 0)
        self.assertIn("failed (exit 3); Superpowers is optional, Dryas setup continues", buf.getvalue())
        self.assertIn("warning:", buf.getvalue())
        table = json.loads((HERE.parent / "components.json").read_text())
        design = [list(a) for a in table["design"]["commands"]]
        self.assertTrue(all(c in [a for a, _ in self.ran] for c in design))


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
        base = {k: v for k, v in os.environ.items()
                if k not in ("DRYAS_DATA_ROOT", "CLAUDE_CONFIG_DIR", "CODEX_HOME") and not k.startswith("JEV_")}
        self.env = dict(base, HOME=str(self.home), USERPROFILE=str(self.home), PATH=os.pathsep.join(path))

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
        # 2.0: Ruflo is an optional extra, so only an explicit --with-ruflo meets the space check
        p = self.wrapper("--preflight-only", "--with-ruflo")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("--with-ruflo", p.stdout + p.stderr)

    @unittest.skipIf(os.name == "nt", "Windows usually has an 8.3 short name for the space")
    def test_space_in_home_is_fine_without_ruflo(self):
        p = self.wrapper("--preflight-only")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
