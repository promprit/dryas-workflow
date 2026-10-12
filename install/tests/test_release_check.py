"""release_check.py against the plugin in this repo (a config dir whose installed_plugins.json points at <repo>/claude)
with a fake `claude`, and against the Codex plugin set up by codex_plugin_setup with the fake `codex`."""
import contextlib, io, json, os, shutil, subprocess, sys, tempfile, unittest
from unittest import mock
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fakecli
import codex_plugin_setup as cps
from test_codex_plugin_setup import Env, quiet
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools"))
import release_check


class ReleaseCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.home.mkdir()
        fb = self.tmp / "bin"
        self.fb = fb
        fakecli.make(fb, "claude", self.tmp / "calls.jsonl", outputs={"mcp list": "jev: ok\n"}, plugin_list=True)
        self.env = {k: v for k, v in os.environ.items() if k not in release_check.KEY_VARS + (
            "DRYAS_DATA_ROOT", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "CLAUDE_PLUGIN_ROOT", "DRYAS_PY", "JEV_CHAIN_LOCAL")}
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home), PATH=str(fb) + os.pathsep + os.environ["PATH"],
                        CODEX_HOME=str(self.home / ".codex"), DRYAS_DATA_ROOT=str(self.tmp / "data"),
                        JEV_LOG_DIR=str(self.tmp / "logs"), JEV_HANDOFF_DIR=str(self.tmp / "handoff"),
                        JEV_COMPACT_DIR=str(self.tmp / "compact"))
        self.cd = self.tmp / "claude-a"
        self.plugin(self.cd, REPO / "claude")

    def plugin(self, cd, root):
        (cd / "plugins").mkdir(parents=True)
        data = {"version": 2, "plugins": {"dryas@dryas-workflow": [{"scope": "user", "installPath": str(root)}]}}
        (cd / "plugins" / "installed_plugins.json").write_text(json.dumps(data), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def run_check(self, *dirs):
        argv = []
        for d in dirs or (self.cd,):
            argv += ["--claude-dir", str(d)]
        buf = io.StringIO()
        real = shutil.which
        no_codex = lambda t, *a, **k: None if t == "codex" else real(t, *a, **k)  # Codex: CodexPluginReleaseCheckTest
        with mock_env(self.env), contextlib.redirect_stdout(buf), mock.patch.object(release_check.shutil, "which", no_codex):
            rc = release_check.main(argv + ["--codex-dir", str(self.home / ".codex")])
        return rc, buf.getvalue()

    def test_all_pass(self):
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("FAIL", out)
        self.assertIn("PASS  dryas plugin installed", out)
        self.assertIn("PASS  plugin hooks run (PreToolUse)", out)
        self.assertIn("PASS  plugin hooks run (SessionStart)", out)
        self.assertIn("PASS  plugin hooks run (UserPromptSubmit)", out)
        self.assertIn("PASS  plugin hooks run (PreCompact)", out)
        self.assertIn("PASS  Scope lock (claude)", out)
        self.assertIn("SKIP  dryas plugin installed (Codex)  (codex not on PATH)", out)
        self.assertIn("SKIP  Jev route", out)
        self.assertIn("PASS  plugin manifests valid", out)
        self.assertIn("Manual checks (needs the app open):", out)
        self.assertIn("5. In each account's Claude Code, run /plugin", out)
        self.assertIn("6. Run /tune and /handoff once in each account", out)
        self.assertIn("type $dryas:orchestrate in the TUI", out)

    def test_hooks_leave_no_state_behind(self):
        def files():
            return sorted(str(p) for d in ("logs", "data", "handoff", "compact") for p in (self.tmp / d).rglob("*"))
        before = files()
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)
        self.assertEqual(files(), before)

    def test_api_key_matches_jev_client(self):
        sys.path.insert(0, str(REPO / "claude" / "jev"))
        import jev_client
        cases = [{}, {"OPENROUTER_API_KEY": "a"}, {"OPENROUTER_API_KEY": " ", "DRYAS_OPENROUTER_KEY": "d"},
                 {"DRYAS_OPENROUTER_KEY": "${user_config.openrouter_key}", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": "p"},
                 {"CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": "${x}"}, {"OPENROUTER_API_KEY": "a", "DRYAS_OPENROUTER_KEY": "d"},
                 {"DRYAS_OPENROUTER_KEY": " d ", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": "p"}]
        for env in cases:
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(release_check.api_key(env), jev_client.api_key(), env)

    def test_missing_plugin_fails_per_dir(self):
        empty = self.tmp / "claude-b"
        empty.mkdir()
        rc, out = self.run_check(self.cd, empty)
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL  dryas plugin installed", out)
        self.assertIn("PASS  plugin hooks run (PreToolUse)", out)  # the first dir is still checked
        self.assertIn(str(empty), out)

    def test_reports_fail_for_broken_hook(self):
        root = self.tmp / "broken-plugin"
        (root / "hooks").mkdir(parents=True)
        cmd = '"${DRYAS_PY:-python3}" -X utf8 "${CLAUDE_PLUGIN_ROOT}/jev/missing_hook.py"'
        hooks = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": cmd, "timeout": 5}]}]}}
        (root / "hooks" / "hooks.json").write_text(json.dumps(hooks), encoding="utf-8")
        cd = self.tmp / "claude-c"
        self.plugin(cd, root)
        rc, out = self.run_check(cd)
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL  plugin hooks run (PreToolUse)", out)

    def test_jev_route_sees_plugin_option_key(self):
        self.env["CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY"] = "${user_config.openrouter_key}"
        rc, out = self.run_check()
        self.assertIn("SKIP  Jev route", out)  # an unexpanded option is no key
        self.assertEqual(release_check.api_key({"DRYAS_OPENROUTER_KEY": " k "}), "k")
        self.assertEqual(release_check.api_key({"OPENROUTER_API_KEY": " ", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": "p"}), "p")

    def test_ruflo_helpers_in_data_root(self):
        (self.cd / ".dryas-plugin.json").write_text(json.dumps({"components": ["core", "ruflo"]}), encoding="utf-8")
        (self.tmp / "data").mkdir(exist_ok=True)
        rc, out = self.run_check()
        self.assertIn("FAIL  Ruflo helpers in data root", out)
        hh = self.tmp / "data" / "ruflo" / "helpers"
        hh.mkdir(parents=True)
        (hh / "hook-handler.cjs").write_text("", encoding="utf-8")
        rc, out = self.run_check()
        self.assertIn("PASS  Ruflo helpers in data root", out)
        self.assertIn("PASS  Ruflo helper runs silently", out)

    def test_read_from_folder_preferred(self):
        """[C1] a directory marketplace runs the plugin from the clone, not the installPath cache snapshot."""
        cd = self.tmp / "claude-d"
        self.plugin(cd, self.tmp / "cache" / "dryas" / "1.0.0")  # a stale cache path that does not exist
        self.env["FAKE_READ_FROM"] = str(REPO / "claude")
        rc, out = self.run_check(cd)
        self.assertEqual(rc, 0, out)
        self.assertIn("PASS  dryas plugin installed  (%s)" % (REPO / "claude"), out)
        self.assertIn("PASS  dryas loads without errors", out)

    def test_load_errors_fail(self):
        self.env["FAKE_PLUGIN_ERRORS"] = json.dumps(["Dependency superpowers is not installed"])
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL  dryas loads without errors  (Dependency superpowers is not installed)", out)

    def test_plugin_list_failure_falls_back(self):
        fakecli.make(self.fb, "claude", self.tmp / "calls.jsonl", fail=["plugin list"], plugin_list=True)
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        self.assertIn("PASS  dryas plugin installed  (%s)" % (REPO / "claude"), out)  # installed_plugins.json
        self.assertIn("FAIL  dryas loads without errors", out)

    def test_jev_route_sandboxed_chain_local(self):
        seen = {}

        def fake_run(argv, **kw):
            p = kw["env"].get("JEV_CHAIN_LOCAL", "")
            seen["local"] = Path(p).read_text(encoding="utf-8") if p and Path(p).is_file() else None
            seen["logs"] = kw["env"].get("JEV_LOG_DIR")
            return subprocess.CompletedProcess(argv, 0, "Jev route: x", "")
        rep = release_check.Report()
        with mock.patch.object(release_check.subprocess, "run", fake_run), contextlib.redirect_stdout(io.StringIO()):
            release_check.jev_route(rep, REPO / "claude" / "jev" / "chain.py", {"OPENROUTER_API_KEY": "k"})
        self.assertEqual(seen["local"], "{}")
        self.assertTrue(seen["logs"])

    def test_ruflo_helper_runs_with_existing_data_root(self):
        (self.cd / ".dryas-plugin.json").write_text(json.dumps({"components": ["core", "ruflo"]}), encoding="utf-8")
        seen = {}
        real = subprocess.run

        def fake_run(argv, **kw):
            if "helper" in argv:
                seen["dir"] = Path(kw["env"]["DRYAS_DATA_ROOT"]).is_dir()
            return real(argv, **kw)
        run_root = self.tmp / "run-data"
        rep = release_check.Report()
        with mock.patch.object(release_check.subprocess, "run", fake_run), contextlib.redirect_stdout(io.StringIO()):
            release_check.ruflo(rep, self.cd, REPO / "claude", {"DRYAS_DATA_ROOT": str(self.tmp / "data")},
                                dict(os.environ, DRYAS_DATA_ROOT=str(run_root)))
        self.assertTrue(seen.get("dir"))

    def test_invalid_manifest_fails(self):
        fakecli.make(self.fb, "claude", self.tmp / "calls.jsonl", fail=["plugin validate"], plugin_list=True)
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL  plugin manifests valid", out)
        calls = [c for c in fakecli.calls(self.tmp / "calls.jsonl") if c[1:3] == ["plugin", "validate"]]
        self.assertTrue(calls)

    def test_codex_manifests_checked(self):
        self.assertEqual(release_check.codex_manifest_problems(REPO), [])
        repo = self.tmp / "repo"
        shutil.copytree(str(REPO / ".agents"), str(repo / ".agents"))
        shutil.copytree(str(REPO / "codex" / ".codex-plugin"), str(repo / "codex" / ".codex-plugin"))
        self.assertEqual(release_check.codex_manifest_problems(repo), [])
        man = repo / "codex" / ".codex-plugin" / "plugin.json"
        man.write_text(json.dumps({"name": "other"}), encoding="utf-8")
        bad = release_check.codex_manifest_problems(repo)
        self.assertTrue(any("plugin.json" in b for b in bad), bad)
        man.write_text("{broken", encoding="utf-8")
        self.assertTrue(release_check.codex_manifest_problems(repo))
        shutil.copy2(str(REPO / "codex" / ".codex-plugin" / "plugin.json"), str(man))
        (repo / ".agents" / "plugins" / "marketplace.json").write_text(json.dumps({"name": "dryas-workflow", "plugins": [
            {"name": "dryas", "source": "./elsewhere"}]}), encoding="utf-8")
        bad = release_check.codex_manifest_problems(repo)
        self.assertTrue(any("marketplace.json" in b for b in bad), bad)

    def test_bad_codex_manifest_fails_without_claude(self):
        rep = release_check.Report()
        with mock.patch.object(release_check, "codex_manifest_problems", lambda repo: ["codex/.codex-plugin/plugin.json: x"]), \
                contextlib.redirect_stdout(io.StringIO()) as buf:
            release_check.manifests(rep, None)
        self.assertIn("FAIL  plugin manifests valid", buf.getvalue())

    def test_help(self):
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(io.StringIO()):
            release_check.main(["--help"])
        self.assertEqual(cm.exception.code, 0)


class CodexPluginReleaseCheckTest(unittest.TestCase):
    """The Codex part: the plugin per --codex-dir, set up by codex_plugin_setup against the fake codex."""

    def run_check(self, e, *cdxs):
        args = ["--claude-dir", str(e.t / "no-claude")]
        for c in cdxs:
            args += ["--codex-dir", str(c)]
        return quiet(release_check.main, args)[1]

    def test_codex_lines_pass_after_setup(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, ["core", "jev"], yes=True)
        out = self.run_check(e, e.a)
        for line in ("PASS  dryas plugin installed (Codex)", "PASS  Codex hooks trusted",
                     "PASS  Codex plugin hooks run (PreToolUse)", "PASS  Codex plugin hooks run (SessionStart)",
                     "PASS  Codex plugin hooks run (UserPromptSubmit)", "PASS  Codex rules hook output",
                     "PASS  Scope lock (codex)", "PASS  legacy Codex copy install"):
            self.assertIn(line, out)
        self.assertIn("Codex: %s" % e.a, out)

    def test_each_codex_dir_checked(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, ["core", "jev"], yes=True)
        out = self.run_check(e, e.a, e.b)
        self.assertEqual(out.count("PASS  dryas plugin installed (Codex)"), 1, out)
        self.assertEqual(out.count("FAIL  dryas plugin installed (Codex)"), 1, out)
        self.assertLess(out.index("Codex: %s" % e.a), out.index("Codex: %s" % e.b))

    def test_hooks_leave_no_state_behind(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, ["core", "jev"], yes=True)
        before = sorted(str(p) for p in e.root.rglob("*"))
        self.run_check(e, e.a)
        self.assertEqual(sorted(str(p) for p in e.root.rglob("*")), before)

    def test_untrusted_and_legacy_fail(self):
        e = Env(self)
        with mock.patch.object(cps.di, "confirm", lambda *a: False):
            quiet(cps.setup, REPO, e.a, ["core", "jev"], yes=False)
        (e.a / ".dryas-installed.json").write_text("{}", encoding="utf-8")
        out = self.run_check(e, e.a)
        self.assertIn("FAIL  Codex hooks trusted", out)
        self.assertIn("run /hooks in Codex", out)
        self.assertIn("FAIL  legacy Codex copy install", out)

    def test_trust_needs_every_shipped_event(self):
        listed = [{"pluginId": release_check.PLUGIN_ID, "eventName": ev, "key": "k" + ev, "trustStatus": "trusted"}
                  for ev in ("preToolUse", "sessionStart")]
        rep = release_check.Report()
        with mock.patch.object(release_check.ca, "list_hooks", lambda *a: listed):
            out = quiet(release_check.codex_trust, rep, {})[1]
        self.assertIn("FAIL  Codex hooks trusted  (missing: UserPromptSubmit", out)

    def test_not_installed(self):
        e = Env(self)
        self.assertIn("FAIL  dryas plugin installed (Codex)", self.run_check(e, e.b))

    def test_default_codex_dir(self):
        e = Env(self)
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(e.b)}):
            out = quiet(release_check.main, ["--claude-dir", str(e.t / "no-claude")])[1]
        self.assertIn("Codex: %s" % e.b, out)


@contextlib.contextmanager
def mock_env(env):
    old = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old)


if __name__ == "__main__":
    unittest.main()
