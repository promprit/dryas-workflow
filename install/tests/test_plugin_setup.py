import json, os, shutil, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import fakecli
import plugin_setup as ps

REPO = HERE.parents[1]
INSTALLED = {"version": 2, "plugins": {"dryas@dryas-workflow": [{"scope": "user", "installPath": "", "version": "1.0.0"}]}}


def _patch_env(tc, values, clear=False):
    p = mock.patch.dict(os.environ, values, clear=clear)
    p.start()
    tc.addCleanup(p.stop)


class Env:
    """Temp HOME, data root, two config dirs and a fake `claude` that records CLAUDE_CONFIG_DIR."""

    def __init__(self, tc):
        self.t = Path(tempfile.mkdtemp()).resolve()  # macOS /var -> /private/var: setup stores resolved paths
        tc.addCleanup(shutil.rmtree, str(self.t), True)
        self.home, self.root = self.t / "home", self.t / "home" / ".dryas"
        self.a, self.b = self.t / "acct-a", self.t / "acct-b"
        self.log = self.t / "calls.jsonl"
        self.bin = bin_dir = self.t / "bin"
        # fake `claude plugin install` writes installed_plugins.json into $CLAUDE_CONFIG_DIR
        self.epilogue = (
            "import os\n"
            "if sys.argv[1:3] == ['plugin', 'install'] and os.environ.get('FAKE_NO_RECORD') != '1':\n"
            "    d = os.path.join(os.environ.get('CLAUDE_CONFIG_DIR') or os.path.expanduser('~/.claude'), 'plugins'); os.makedirs(d, exist_ok=True)\n"
            "    p = os.path.join(d, 'installed_plugins.json')\n"
            "    rec = json.load(open(p)) if os.path.exists(p) else %r\n"
            "    rec['plugins']['dryas@dryas-workflow'][0]['installPath'] = %r\n"
            "    rec['plugins'].setdefault(sys.argv[3], [{'scope': 'user', 'installPath': 'x', 'version': '1'}])\n"
            "    open(p, 'w').write(json.dumps(rec))\n"
            "with open(%r, 'a') as f: f.write(json.dumps(os.environ.get('CLAUDE_CONFIG_DIR')) + '\\n')\n"
        ) % (INSTALLED, str(REPO / "claude"), str(self.t / "envs.jsonl"))
        fakecli.make(bin_dir, "claude", self.log, epilogue=self.epilogue, plugin_list=True)
        fakecli.make(bin_dir, "npm", self.log)
        _patch_env(tc, {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"], "HOME": str(self.home),
                        "USERPROFILE": str(self.home), "DRYAS_DATA_ROOT": str(self.root)})
        self.home.mkdir()

    def calls(self):
        return fakecli.calls(self.log)

    def envs(self):
        p = self.t / "envs.jsonl"
        return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


COMPS = ["core", "jev"]
SP_COMPS = ["core", "jev", "superpowers"]


def _out(fn):
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn()
    return buf.getvalue()


class SetupTest(unittest.TestCase):
    def test_claude_dir_resolution(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "/cfg"}):
            self.assertEqual(ps.claude_dir(None), Path("/cfg").resolve())
            self.assertEqual(ps.claude_dir("/x"), Path("/x").resolve())
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(ps.claude_dir(None), (Path.home() / ".claude").resolve())

    def test_two_accounts(self):
        e = Env(self)
        for cd in (e.a, e.b):
            self.assertEqual(ps.setup(REPO, cd, COMPS, yes=True, key="", flowobserve=False), 0)
        self.assertEqual(set(e.envs()), {str(e.a), str(e.b)})
        installs = [c for c in e.calls() if c[1:3] == ["plugin", "install"] and c[3] == ps.ID]
        self.assertEqual([c[3] for c in installs], ["dryas@dryas-workflow"] * 2)
        self.assertTrue(all("-y" in c and "--scope" in c for c in installs))
        for cd in (e.a, e.b):
            s = json.loads((cd / "settings.json").read_text())
            self.assertEqual(s["env"]["DRYAS_DATA_ROOT"], str(e.root).replace("\\", "/"))
            self.assertIn("DRYAS_PY", s["env"])
            self.assertTrue(any("/jev/planfile.py" in r for r in s["permissions"]["allow"]))
            self.assertIn("Read(~/.dryas/**)", s["permissions"]["allow"])
            self.assertNotIn("hooks", s)
            self.assertTrue((cd / ps.RECORD).exists())
        self.assertEqual(json.loads((e.root / "accounts.json").read_text())["claude_dirs"], [str(e.a), str(e.b)])

    def test_cd_is_installed_plugin_path(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        s = json.loads((e.a / "settings.json").read_text())
        plugin = str(REPO / "claude").replace("\\", "/")
        self.assertTrue(any(plugin + "/jev/planfile.py" in r for r in s["permissions"]["allow"]))
        self.assertFalse(any(str(e.a).replace("\\", "/") + "/jev" in r for r in s["permissions"]["allow"]))
        self.assertEqual(json.loads((e.a / ps.RECORD).read_text())["plugin_root"], str(REPO / "claude"))

    def test_cd_is_read_from_folder(self):
        """[C1] a directory marketplace loads the plugin in place: rules name readFromFolder, not the cache copy."""
        e = Env(self)
        live = e.t / "clone" / "claude"
        _patch_env(self, {"FAKE_READ_FROM": str(live)})
        self.assertEqual(ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False), 0)
        allow = json.loads((e.a / "settings.json").read_text())["permissions"]["allow"]
        self.assertTrue(any(str(live).replace("\\", "/") + "/jev/planfile.py" in r for r in allow), allow)
        self.assertFalse(any(str(REPO / "claude").replace("\\", "/") + "/jev" in r for r in allow))
        self.assertEqual(json.loads((e.a / ps.RECORD).read_text())["plugin_root"], str(live))
        self.assertEqual(ps.install_path(e.a), str(live))

    def test_install_path_falls_back_when_cli_fails(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        fakecli.make(e.bin, "claude", e.log, fail=["plugin list"], epilogue=e.epilogue, plugin_list=True)
        _patch_env(self, {"FAKE_READ_FROM": str(e.t / "elsewhere")})
        self.assertEqual(ps.install_path(e.a), str(REPO / "claude"))  # installed_plugins.json installPath

    def test_official_marketplace_added_before_install(self):
        """With superpowers selected, claude-plugins-official is added before dryas is installed: the component
        installs from it."""
        e = Env(self)
        ps.setup(REPO, e.a, SP_COMPS, yes=True, key="", flowobserve=False)
        cmds = [c[1:5] for c in e.calls()]
        off = cmds.index(["plugin", "marketplace", "add", ps.OFFICIAL_SOURCE])
        dr = cmds.index(["plugin", "install", ps.ID, "--scope"])
        self.assertLess(off, dr)

    def test_missing_dependency_installed(self):
        """An existing install whose dependency never resolved: `plugin install dryas` does not retry it."""
        e = Env(self)
        _patch_env(self, {"FAKE_MISSING_DEP": ps.SUPERPOWERS})
        self.assertEqual(ps.setup(REPO, e.a, SP_COMPS, yes=True, key="", flowobserve=False), 0)
        cmds = [c[1:4] for c in e.calls()]
        self.assertLess(cmds.index(["plugin", "install", ps.ID]), cmds.index(["plugin", "install", ps.SUPERPOWERS]))
        self.assertTrue((e.a / "settings.json").exists())

    def test_legacy_dependency_repair_respects_no_superpowers(self):
        e = Env(self)
        _patch_env(self, {"FAKE_MISSING_DEP": ps.SUPERPOWERS})
        out = _out(lambda: ps.setup(REPO, e.a, ["core", "jev"], yes=True, key="", flowobserve=False))
        self.assertFalse(any(c[1:3] == ["plugin", "install"] and ps.SUPERPOWERS in c for c in e.calls()))
        self.assertIn("an earlier install expected Superpowers; it is optional now and was not installed", out)

    def test_load_errors_stop_before_settings(self):
        e = Env(self)
        _patch_env(self, {"FAKE_PLUGIN_ERRORS": json.dumps(["Dependency superpowers is not installed"])})
        out = _out(lambda: self.assertEqual(ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False), 1))
        self.assertIn("Dependency superpowers is not installed", out)
        self.assertFalse((e.a / "settings.json").exists())
        self.assertFalse((e.root / "accounts.json").exists())

    def test_no_superpowers_note(self):
        e = Env(self)
        out = _out(lambda: ps.setup(REPO, e.a, ["core", "jev"], yes=True, key="", flowobserve=False))
        self.assertIn("Superpowers is not installed; the Dryas process skills cover the loop", out)
        self.assertFalse(any(ps.OFFICIAL_SOURCE in c for c in e.calls()))
        self.assertFalse(any(ps.SUPERPOWERS in c for c in e.calls()))
        s = json.loads((e.a / "settings.json").read_text())
        self.assertEqual(len([r for r in s["permissions"]["deny"] if r.startswith("Skill(superpowers:")]), 5)

    def test_rerun_without_superpowers_keeps_denies(self):
        """The deny rules live in core: dropping superpowers on a re-run must not turn the conflicting skills on."""
        e = Env(self)
        ps.setup(REPO, e.a, ["core", "jev", "superpowers"], yes=True, key="", flowobserve=False)
        _out(lambda: ps.setup(REPO, e.a, ["core", "jev"], yes=True, key="", flowobserve=False))
        deny = json.loads((e.a / "settings.json").read_text())["permissions"]["deny"]
        self.assertIn("Skill(superpowers:subagent-driven-development)", deny)
        self.assertEqual(len([r for r in deny if r.startswith("Skill(superpowers:")]), 5)

    def test_jev_key_hint(self):
        e = Env(self)
        _patch_env(self, {k: "" for k in ("OPENROUTER_API_KEY", "DRYAS_OPENROUTER_KEY")})
        out = _out(lambda: ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False))
        self.assertIn("set OPENROUTER_API_KEY in your shell profile", out)
        out = _out(lambda: ps.setup(REPO, e.a, COMPS, yes=True, key="sk-1", flowobserve=False))
        self.assertNotIn("OPENROUTER_API_KEY in your shell profile", out)
        _patch_env(self, {"OPENROUTER_API_KEY": "sk-2"})
        out = _out(lambda: ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False))
        self.assertNotIn("OPENROUTER_API_KEY in your shell profile", out)
        out = _out(lambda: ps.setup(REPO, e.b, ["core"], yes=True, key="", flowobserve=False))
        self.assertNotIn("OPENROUTER_API_KEY in your shell profile", out)

    def test_shared_components_warning(self):
        """[I3] chain.local.json is shared: changing the "off" set while other accounts exist warns."""
        e = Env(self)
        out = _out(lambda: ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False))
        self.assertNotIn("shared", out)  # first account: nothing to warn about
        out = _out(lambda: ps.setup(REPO, e.b, COMPS, yes=True, key="", flowobserve=False))
        self.assertNotIn("warning: component choices", out)  # same choices
        out = _out(lambda: ps.setup(REPO, e.b, ["core"], yes=True, key="", flowobserve=False))
        self.assertIn("warning: component choices", out)
        self.assertIn("jev", out)
        self.assertIn(str(e.a), out)
        out = _out(lambda: ps.setup(REPO, e.b, ["core"], yes=True, key="", flowobserve=False))
        self.assertNotIn("warning: component choices", out)

    def test_shared_components_warning_names_codex(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        cdx = e.home / ".codex"
        cdx.mkdir()
        (cdx / ".dryas-installed.json").write_text("{}")
        _patch_env(self, {"CODEX_HOME": str(cdx)})
        out = _out(lambda: ps.setup(REPO, e.a, ["core"], yes=True, key="", flowobserve=False))
        self.assertIn("warning: component choices", out)
        self.assertIn("Codex", out)

    def test_data_root_expands_user(self):
        e = Env(self)
        _patch_env(self, {"DRYAS_DATA_ROOT": "~/state"})
        self.assertEqual(ps.data_root(), e.home / "state")
        self.assertEqual(ps.di._mapping([], e.home, e.a)["DRYAS_DATA_ROOT"], str(e.home / "state").replace("\\", "/"))

    def test_native_rules_windows_form(self):
        """[I6] on Windows ${CLAUDE_PLUGIN_ROOT} may be substituted with backslashes: allow both forms."""
        root = "C:\\Users\\me\\dryas\\claude"
        fw = "C:/Users/me/dryas/claude"
        frag = {"env": {"X": fw + "/ruflo/run.py"},
                "permissions": {"allow": ["Read(~/.dryas/**)", 'Bash("%s/bin/dryas-py" "%s/jev/tune.py" report)' % (fw, fw),
                                          "mcp__plugin_dryas_jev"]}}
        out = ps.native_rules(frag, root)
        nat = 'Bash("%s/bin/dryas-py" "%s/jev/tune.py" report)' % (root, root)
        self.assertEqual(out["permissions"]["allow"], frag["permissions"]["allow"] + [nat])
        self.assertEqual(out["env"], frag["env"])
        self.assertEqual(len(frag["permissions"]["allow"]), 3)  # input untouched
        self.assertEqual(ps.native_rules(out, fw), out)  # idempotent, either spelling of the root

    def test_windows_native_rules_recorded_and_removed(self):
        e = Env(self)
        with mock.patch.object(ps.pu, "IS_WINDOWS", True):
            ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        nat = str(REPO / "claude").replace("/", "\\") + "/jev/planfile.py"
        allow = json.loads((e.a / "settings.json").read_text())["permissions"]["allow"]
        self.assertTrue(any(nat in r for r in allow), allow)
        self.assertTrue(any(nat in r for r in json.loads((e.a / ps.RECORD).read_text())["settings"]["allow"]))
        ps.uninstall(e.a, purge=False)
        self.assertFalse((e.a / "settings.json").exists())

    def test_key_passed_as_config(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="sk-1", flowobserve=False)
        inst = [c for c in e.calls() if c[1:4] == ["plugin", "install", ps.ID]][0]
        self.assertIn("--config", inst)
        self.assertIn("openrouter_key=sk-1", inst)

    def test_verification_failure_stops_before_settings(self):
        e = Env(self)
        _patch_env(self, {"FAKE_NO_RECORD": "1"})
        self.assertEqual(ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False), 1)
        self.assertFalse((e.a / "settings.json").exists())
        self.assertFalse((e.root / "accounts.json").exists())
        self.assertFalse((e.root / "chain.local.json").exists())

    def test_install_failure_stops_before_settings(self):
        e = Env(self)
        fakecli.make(e.bin, "claude", e.log, fail=["plugin install"], epilogue=e.epilogue, plugin_list=True)
        self.assertEqual(ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False), 1)
        self.assertFalse((e.a / "settings.json").exists())
        self.assertFalse((e.root / "accounts.json").exists())

    def test_chain_local_components(self):
        e = Env(self)
        ps.setup(REPO, e.a, ["core", "jev"], yes=True, key="", flowobserve=True)
        loc = json.loads((e.root / "chain.local.json").read_text())
        self.assertEqual(sorted(loc["off"]), ["design", "pstack-picks", "ruflo", "superpowers"])
        self.assertTrue(loc["stages"]["pretool"]["flowobserve"]["enabled"])
        self.assertFalse(loc["stages"]["pretool"]["ruflo-pre-bash"]["enabled"])
        self.assertNotIn("jev-gate", loc["stages"]["pretool"])

    def test_chain_local_never_lists_core_stages(self):
        chain = json.loads((REPO / "claude" / "jev" / "chain.json").read_text(encoding="utf-8"))
        core = {(ev, st["name"]) for ev, sts in chain.items() for st in sts if st.get("component") == "core"}
        self.assertIn(("pretool", "scope-lock"), core)
        self.assertIn(("prompt", "context-watch"), core)
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        for comps, fo in ((["core"], False), (["core", "jev", "ruflo"], True), (["core"], True)):
            ps.write_chain_local(t, comps, fo)
            loc = json.loads((t / "chain.local.json").read_text())
            for ev, name in core:
                self.assertNotIn(name, loc["stages"].get(ev, {}), (comps, fo))

    def test_chain_local_keeps_user_entries_and_reenables(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        (t / "chain.local.json").write_text(json.dumps({"stages": {"pretool": {"mine": {"enabled": False}}}}))
        ps.write_chain_local(t, ["core"], False)
        ps.write_chain_local(t, ["core", "jev", "ruflo"], False)
        loc = json.loads((t / "chain.local.json").read_text())
        self.assertEqual(loc["stages"]["pretool"]["mine"], {"enabled": False})
        self.assertNotIn("jev-gate", loc["stages"]["pretool"])
        self.assertNotIn("ruflo-pre-bash", loc["stages"]["pretool"])

    def test_workflow_doc_written_to_data_root(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        doc = e.root / "docs" / "dryas-workflow.md"
        self.assertEqual(doc.read_bytes(), (REPO / "docs" / "workflow.md").read_bytes())
        os.utime(str(doc), (1000000000, 1000000000))
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        self.assertEqual(doc.stat().st_mtime, 1000000000)  # unchanged content: not rewritten
        doc.write_text("stale", encoding="utf-8")
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        self.assertEqual(doc.read_bytes(), (REPO / "docs" / "workflow.md").read_bytes())

    def test_second_run_is_noop(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        before = (e.a / "settings.json").read_text()
        self.assertEqual(ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False), 0)
        self.assertEqual((e.a / "settings.json").read_text(), before)
        self.assertEqual(json.loads((e.root / "accounts.json").read_text())["claude_dirs"], [str(e.a)])

    def test_malformed_settings_stops_before_commands(self):
        e = Env(self)
        e.a.mkdir()
        (e.a / "settings.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False), 1)
        self.assertEqual(e.calls(), [])
        self.assertEqual((e.a / "settings.json").read_text(encoding="utf-8"), "{not json")

    def _ruflo_stubs(self, e, helpers=None):
        det = {"RUFLO_BIN": "/fake/ruflo", "RUFLO_JS": "/fake/ruflo.js", "RUFLO_NODE_FALLBACK": "/fake/node",
               "RUFLO_NODE_MODULES": "/fake/nm", "RUFLO_CLI_DIST": ""}
        for p in (mock.patch.object(ps.di, "detect", return_value=det),
                  mock.patch.object(ps.ruflo_runtime, "install", return_value=[str(e.root / "ruflo" / "x")])):
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(ps.ruflo_helpers, "patched_helpers", **(helpers or {"return_value": {}}))
        p.start()
        self.addCleanup(p.stop)

    def test_reconfigure_drops_ruflo(self):
        e = Env(self)
        self._ruflo_stubs(e)
        self.assertEqual(ps.setup(REPO, e.a, ["core", "jev", "ruflo"], yes=True, key="", flowobserve=False), 0)
        s = json.loads((e.a / "settings.json").read_text())
        self.assertEqual(s["env"]["RUFLO_BIN"], "/fake/ruflo")
        rec = json.loads((e.a / ps.RECORD).read_text())
        self.assertEqual(rec["data_files"], [str(e.root / "ruflo" / "x")])
        self.assertEqual(ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False), 0)
        s = json.loads((e.a / "settings.json").read_text())
        self.assertFalse([k for k in s.get("env", {}) if k.startswith(("RUFLO", "CLAUDE_FLOW"))])
        self.assertFalse([r for r in s["permissions"]["allow"] if "ruflo" in r])
        self.assertNotIn("hooks", s)
        self.assertIn("DRYAS_PY", s["env"])
        self.assertEqual(json.loads((e.a / ps.RECORD).read_text())["components"], COMPS)

    def test_ruflo_patch_error_uses_fallback(self):
        e = Env(self)
        self._ruflo_stubs(e, {"side_effect": ps.ruflo_helpers.PatchError("anchor")})
        fb = mock.patch.object(ps.di, "_ruflo_fallback", return_value=None)
        m = fb.start()
        self.addCleanup(fb.stop)
        self.assertEqual(ps.setup(REPO, e.a, ["core", "ruflo"], yes=True, key="", flowobserve=False), 1)
        m.assert_called_once()
        self.assertFalse((e.a / "settings.json").exists())
        m.return_value = {}
        self.assertEqual(ps.setup(REPO, e.a, ["core", "ruflo"], yes=True, key="", flowobserve=False), 0)

    def test_ruflo_helper_error_stops(self):
        e = Env(self)
        self._ruflo_stubs(e, {"side_effect": ps.ruflo_helpers.HelperError("no ruflo")})
        self.assertEqual(ps.setup(REPO, e.a, ["core", "ruflo"], yes=True, key="", flowobserve=False), 1)
        self.assertFalse((e.a / "settings.json").exists())

    def test_account_paths_normalized(self):
        t = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, str(t), True)
        (t / "acct").mkdir()
        ps.add_account(t, t / "acct")
        ps.add_account(t, str(t / "acct") + os.sep)
        old = os.getcwd()
        os.chdir(str(t))
        self.addCleanup(os.chdir, old)
        ps.add_account(t, Path("acct"))
        self.assertEqual(json.loads((t / "accounts.json").read_text())["claude_dirs"], [str(t / "acct")])
        self.assertEqual(ps.remove_account(t, Path(".") / "acct" / ".."  / "acct"), [])

    def test_chain_local_repairs_bad_shapes(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        (t / "chain.local.json").write_text(json.dumps({"stages": {"pretool": ["x"], "prompt": {"jev-route": 3}}}))
        ps.write_chain_local(t, ["core"], False, REPO)
        loc = json.loads((t / "chain.local.json").read_text())
        self.assertEqual(loc["stages"]["pretool"]["jev-gate"], {"enabled": False})
        self.assertEqual(loc["stages"]["prompt"]["jev-route"], {"enabled": False})

    def _fo(self, t):
        st = json.loads((t / "chain.local.json").read_text())["stages"]
        return [st[e]["flowobserve"]["enabled"] for e in ("pretool", "prompt") if "flowobserve" in st.get(e, {})]

    def test_chain_local_flowobserve_tristate(self):
        """None keeps a migrated setting (no entry -> off); True turns it on; False turns both stages off."""
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        ps.write_chain_local(t, ["core"], None, REPO)
        self.assertEqual(self._fo(t), [False, False])
        (t / "chain.local.json").write_text(json.dumps({"stages": {"pretool": {"flowobserve": {"enabled": True}}}}))
        ps.write_chain_local(t, ["core"], None, REPO)
        self.assertIs(self._fo(t)[0], True)
        (t / "chain.local.json").write_text(json.dumps({"stages": {"pretool": {"flowobserve": {"enabled": False}}}}))
        ps.write_chain_local(t, ["core"], True, REPO)
        self.assertEqual(self._fo(t), [True, True])
        ps.write_chain_local(t, ["core"], None, REPO)
        self.assertEqual(self._fo(t), [True, True])
        ps.write_chain_local(t, ["core"], False, REPO)
        self.assertEqual(self._fo(t), [False, False])

    def test_setup_flowobserve_off_overrides_on(self):
        e = Env(self)
        ps.setup(REPO, e.a, ["core", "jev"], yes=True, key="", flowobserve=True)
        self.assertEqual(self._fo(e.root), [True, True])
        ps.setup(REPO, e.a, ["core", "jev"], yes=True, key="")
        self.assertEqual(self._fo(e.root), [True, True])
        ps.setup(REPO, e.a, ["core", "jev"], yes=True, key="", flowobserve=False)
        self.assertEqual(self._fo(e.root), [False, False])

    def test_missing_workflow_doc_warns(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        ps.write_workflow_doc(t / "norepo", t / "root")
        self.assertFalse((t / "root" / "docs" / "dryas-workflow.md").exists())

    def test_accounts_key(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        ps.add_account(t, t / "c1")
        ps.add_account(t, t / "x1", "codex_dirs")
        acc = json.loads((t / "accounts.json").read_text())
        self.assertEqual((len(acc["claude_dirs"]), len(acc["codex_dirs"])), (1, 1))
        self.assertEqual(ps.remove_account(t, t / "x1", "codex_dirs"), [])
        self.assertEqual(len(json.loads((t / "accounts.json").read_text())["claude_dirs"]), 1)

    def test_remove_account(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        ps.add_account(t, Path("/a"))
        ps.add_account(t, Path("/b"))
        self.assertEqual(ps.remove_account(t, Path("/a")), [str(Path("/b").resolve())])
        self.assertEqual(json.loads((t / "accounts.json").read_text())["claude_dirs"], [str(Path("/b").resolve())])


class VerifyTest(unittest.TestCase):
    def setUp(self):
        self.e = Env(self)
        self.ran = []
        p = mock.patch.object(ps.di, "run", lambda argv, cwd=None, env=None: self.ran.append(argv) or 0)
        p.start()
        self.addCleanup(p.stop)

    def verify(self, cd):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            fails = ps.verify(cd, COMPS)
        return fails, buf.getvalue()

    def test_passes_with_plugin_installed(self):
        rec = json.loads(json.dumps(INSTALLED))
        rec["plugins"]["dryas@dryas-workflow"][0]["installPath"] = str(REPO / "claude")
        (self.e.a / "plugins").mkdir(parents=True)
        (self.e.a / "plugins" / "installed_plugins.json").write_text(json.dumps(rec))
        fails, out = self.verify(self.e.a)
        self.assertEqual(fails, 0, out)
        for name in ("dryas@dryas-workflow listed in", "dryas loads without errors", "rules hook prints SessionStart JSON",
                     "scope lock blocks an out-of-scope write"):
            self.assertIn("PASS  " + name, out)
        tests = str(REPO / "claude" / "jev" / "tests")
        self.assertTrue(any(tests in a for argv in self.ran for a in argv), self.ran)  # Jev tests of the plugin

    def _installed(self):
        rec = json.loads(json.dumps(INSTALLED))
        rec["plugins"]["dryas@dryas-workflow"][0]["installPath"] = str(REPO / "claude")
        (self.e.a / "plugins").mkdir(parents=True)
        (self.e.a / "plugins" / "installed_plugins.json").write_text(json.dumps(rec))

    def test_fails_with_load_errors(self):
        """[C2] enabled is not enough: Claude Code reports a missing dependency as an error on the plugin."""
        self._installed()
        _patch_env(self, {"FAKE_PLUGIN_ERRORS": json.dumps(["Dependency superpowers is not installed"])})
        fails, out = self.verify(self.e.a)
        self.assertEqual(fails, 1, out)
        self.assertIn("FAIL  dryas loads without errors", out)
        self.assertIn("Dependency superpowers is not installed", out)

    def test_fails_when_plugin_list_fails(self):
        self._installed()
        fakecli.make(self.e.bin, "claude", self.e.log, fail=["plugin list"], plugin_list=True)
        fails, out = self.verify(self.e.a)
        self.assertEqual(fails, 1, out)
        self.assertIn("FAIL  dryas loads without errors", out)
        self.assertIn("PASS  rules hook prints SessionStart JSON", out)  # installPath fallback still checked

    def test_fails_without_plugin(self):
        self.e.a.mkdir()
        fails, out = self.verify(self.e.a)
        self.assertGreater(fails, 0)
        self.assertIn("FAIL  dryas@dryas-workflow listed in", out)


class UninstallTest(unittest.TestCase):
    def test_one_dir_removed_other_kept(self):
        e = Env(self)
        for cd in (e.a, e.b):
            ps.setup(REPO, cd, COMPS, yes=True, key="", flowobserve=False)
        self.assertEqual(ps.uninstall(e.a, purge=True), 0)
        un = [c for c in e.calls() if c[1:3] == ["plugin", "uninstall"]]
        self.assertEqual(len(un), 1)
        self.assertIn("--keep-data", un[0])
        self.assertEqual(e.envs()[-1], str(e.a))
        s = json.loads((e.a / "settings.json").read_text()) if (e.a / "settings.json").exists() else {}
        self.assertNotIn("DRYAS_PY", s.get("env", {}))
        self.assertIn("DRYAS_PY", json.loads((e.b / "settings.json").read_text())["env"])
        self.assertEqual(json.loads((e.root / "accounts.json").read_text())["claude_dirs"], [str(e.b)])
        self.assertTrue(e.root.exists())  # another account still listed: purge refused

    def test_purge_last_account(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        ps.uninstall(e.a, purge=True)
        self.assertFalse(e.root.exists())

    def test_keep_data_without_purge(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        ps.uninstall(e.a, purge=False)
        self.assertTrue((e.root / "chain.local.json").exists())

    def test_nothing_to_uninstall(self):
        e = Env(self)
        e.a.mkdir()
        self.assertEqual(ps.uninstall(e.a, purge=False), 0)

    def test_purge_refuses_symlinked_root(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        real = e.t / "real-root"
        shutil.move(str(e.root), str(real))
        try:
            os.symlink(str(real), str(e.root))
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        ps.uninstall(e.a, purge=True)
        self.assertTrue(real.exists())


    def test_purge_never_removes_home(self):
        e = Env(self)
        with mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": str(e.home)}):
            ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
            (e.home / "mine.txt").write_text("x")
            ps.uninstall(e.a, purge=True)
        self.assertTrue((e.home / "mine.txt").exists())
        self.assertTrue((e.home / "chain.local.json").exists())

    def test_purge_keeps_foreign_files(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        (e.root / "foreign.txt").write_text("x")
        ps.uninstall(e.a, purge=True)
        self.assertTrue((e.root / "foreign.txt").exists())
        for n in ps.OWNED:
            self.assertFalse((e.root / n).exists(), n)

    def test_purge_keeps_local_notes(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        (e.root / "docs" / "dryas-local.md").write_text("mine", encoding="utf-8")
        (e.root / "jev" / "logs").mkdir(parents=True, exist_ok=True)
        (e.root / "jev" / "logs" / "calls.jsonl").write_text("{}\n")
        (e.root / "jev" / "thresholds.json").write_text("{}")
        ps.uninstall(e.a, purge=True)
        self.assertEqual((e.root / "docs" / "dryas-local.md").read_text(encoding="utf-8"), "mine")
        self.assertFalse((e.root / "docs" / "dryas-workflow.md").exists())
        self.assertFalse((e.root / "jev").exists())  # logs and /tune thresholds go with --purge
        self.assertFalse((e.root / "chain.local.json").exists())

    def test_purge_removes_real_dist_dir(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        d = e.root / "ruflo" / "mcp-shim" / "dist"
        d.mkdir(parents=True)
        (d / "x.js").write_text("x")
        self.assertEqual(ps.uninstall(e.a, purge=True), 0)
        self.assertFalse((e.root / "ruflo").exists())

    def test_purge_skipped_when_record_corrupt(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        (e.a / ps.RECORD).write_text("[1]")
        with mock.patch("sys.stdout", new_callable=__import__("io").StringIO) as out:
            self.assertEqual(ps.uninstall(e.a, purge=True), 0)
        self.assertTrue((e.root / "chain.local.json").exists())
        self.assertIn("unreadable", out.getvalue())

    def test_corrupt_record_keeps_account(self):
        """[I5] the dir may still use Dryas: it stays in accounts.json."""
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        (e.a / ps.RECORD).write_text("[1]")
        ps.uninstall(e.a, purge=False)
        self.assertEqual(json.loads((e.root / "accounts.json").read_text())["claude_dirs"], [str(e.a)])

    def test_purge_refused_while_codex_installed(self):
        """[I4] Codex uses the data root too: --purge keeps it while a Codex install exists."""
        for where in ("codex", "copy"):
            e = Env(self)
            ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
            cdx = e.t / "codex"
            _patch_env(self, {"CODEX_HOME": str(cdx)})
            rec = (cdx if where == "codex" else e.home / ".claude") / ".dryas-installed.json"
            rec.parent.mkdir(parents=True)
            rec.write_text("{}")
            out = _out(lambda: self.assertEqual(ps.uninstall(e.a, purge=True), 0))
            self.assertTrue((e.root / "chain.local.json").exists(), where)
            self.assertIn("Codex", out)
            self.assertFalse((e.a / ps.RECORD).exists())
            rec.unlink()  # Codex uninstalled earlier in the same run: its record is gone, purge goes ahead
            ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
            ps.uninstall(e.a, purge=True)
            self.assertFalse(e.root.exists(), where)

    def test_purge_refused_while_codex_listed(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        ps.add_account(e.root, e.t / "codex-home", "codex_dirs")
        out = _out(lambda: ps.uninstall(e.a, purge=True))
        self.assertTrue(e.root.exists())
        self.assertIn("Codex in %s" % (e.t / "codex-home"), out)

    def test_purge_shared_after_last_account(self):
        e = Env(self)
        ps.add_account(e.root, e.t / "codex-home", "codex_dirs")
        self.assertFalse(ps.purge_shared())
        ps.remove_account(e.root, e.t / "codex-home", "codex_dirs")
        self.assertTrue(ps.purge_shared())
        self.assertFalse(e.root.exists())

    def test_purge_shared_refusals(self):
        e = Env(self)
        _out(lambda: self.assertFalse(ps.purge_shared()))  # no accounts.json: unknown users
        ps.add_account(e.root, e.a, "claude_dirs")
        out = _out(lambda: self.assertFalse(ps.purge_shared()))
        self.assertIn("still used by %s" % e.a, out)
        ps.remove_account(e.root, e.a, "claude_dirs")
        cdx = e.t / "codex"
        cdx.mkdir()
        (cdx / ".dryas-installed.json").write_text("{}")
        _patch_env(self, {"CODEX_HOME": str(cdx)})
        out = _out(lambda: self.assertFalse(ps.purge_shared()))
        self.assertIn("Codex copy install", out)
        self.assertTrue(e.root.exists())

    def test_shared_warning_names_codex_dirs_not_the_current_one(self):
        e = Env(self)
        ps.write_chain_local(e.root, COMPS, False, REPO)
        ps.add_account(e.root, e.t / "cx-a", "codex_dirs")
        ps.add_account(e.root, e.t / "cx-b", "codex_dirs")
        out = _out(lambda: ps.write_chain_local(e.root, ["core"], False, REPO, e.t / "cx-a"))
        self.assertIn("warning: component choices", out)
        self.assertIn("Codex in %s" % (e.t / "cx-b"), out)
        self.assertNotIn(str(e.t / "cx-a"), out)

    def test_no_record_drops_stale_claude_entry(self):
        e = Env(self)
        ps.add_account(e.root, e.a, "claude_dirs")
        ps.add_account(e.root, e.b, "claude_dirs")
        _out(lambda: self.assertEqual(ps.uninstall(e.a, purge=False), 0))
        self.assertEqual(json.loads((e.root / "accounts.json").read_text())["claude_dirs"], [str(e.b)])

    def test_account_lists_of_wrong_type(self):
        e = Env(self)
        e.root.mkdir()
        (e.root / "accounts.json").write_text(json.dumps({"codex_dirs": "/x/cdx", "claude_dirs": []}))
        out = _out(lambda: self.assertFalse(ps.purge_shared()))
        self.assertIn("unreadable", out)
        self.assertTrue(e.root.exists())
        self.assertEqual(ps._codex_dirs(e.root), [])
        ps.add_account(e.root, e.a, "codex_dirs")  # a broken list is replaced, never iterated char by char
        self.assertEqual(json.loads((e.root / "accounts.json").read_text())["codex_dirs"], [str(e.a)])

    def test_purge_message_names_notes(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        (e.root / "docs" / "dryas-local.md").write_text("mine", encoding="utf-8")
        out = _out(lambda: ps.uninstall(e.a, purge=True))
        self.assertIn("kept %s (your notes)" % e.root, out)
        self.assertNotIn("did not create", out)

    def test_purge_refusal_without_cwd(self):
        e = Env(self)
        with mock.patch.object(ps.Path, "cwd", side_effect=FileNotFoundError):
            self.assertIsNone(ps._purge_refusal(e.root, e.a))

    def test_purge_refused_when_accounts_missing_or_corrupt(self):
        for corrupt in (False, True):
            e = Env(self)
            ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
            acc = e.root / "accounts.json"
            if corrupt:
                acc.write_text("{not json")
            else:
                acc.unlink()
            self.assertEqual(ps.uninstall(e.a, purge=True), 0)
            self.assertFalse((e.a / ps.RECORD).exists())
            self.assertTrue((e.root / "chain.local.json").exists())
            if corrupt:
                self.assertEqual(acc.read_text(), "{not json")

    def test_corrupt_record_leaves_settings(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        before = (e.a / "settings.json").read_text()
        (e.a / ps.RECORD).write_text("[1]")
        self.assertEqual(ps.uninstall(e.a, purge=False), 0)
        self.assertEqual((e.a / "settings.json").read_text(), before)
        self.assertTrue((e.a / ps.RECORD).exists())

    def test_non_dict_settings(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        (e.a / "settings.json").write_text("[1]")
        self.assertEqual(ps.uninstall(e.a, purge=False), 1)
        self.assertTrue((e.a / ps.RECORD).exists())
        self.assertFalse([c for c in e.calls() if c[1:3] == ["plugin", "uninstall"]])

    def test_user_keys_and_modified_values_survive(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        sp = e.a / "settings.json"
        s = json.loads(sp.read_text())
        s["theme"] = "dark"
        s["env"]["DRYAS_PY"] = "/my/python"  # user changed a recorded value
        sp.write_text(json.dumps(s))
        ps.uninstall(e.a, purge=False)
        s = json.loads(sp.read_text())
        self.assertEqual(s["theme"], "dark")
        self.assertEqual(s["env"]["DRYAS_PY"], "/my/python")

    def test_settings_kept_when_not_created_by_dryas(self):
        e = Env(self)
        e.a.mkdir()
        (e.a / "settings.json").write_text(json.dumps({"theme": "dark"}))
        ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False)
        ps.uninstall(e.a, purge=False)
        self.assertEqual(json.loads((e.a / "settings.json").read_text()), {"theme": "dark"})


class StaleJevMcpTest(unittest.TestCase):
    """The old copy install registered user-scope MCP `jev` on <config dir>/jev/jev_mcp.py; migration deleted that file."""
    REMOVE = ["claude", "mcp", "remove", "--scope", "user", "jev"]

    def _cfg(self, e, entry):
        (e.home / ".claude.json").write_text(json.dumps({"mcpServers": {"jev": entry}}), encoding="utf-8")

    def _stale(self, e):
        return {"command": "/usr/bin/python3", "args": ["-X", "utf8", str(e.home / ".claude" / "jev" / "jev_mcp.py")]}

    def _default_dir_env(self):
        _patch_env(self, {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}, clear=True)

    def _removes(self, e):
        return [i for i, c in enumerate(e.calls()) if c[:6] == self.REMOVE]

    def test_setup_removes_stale_copy_install_jev_mcp(self):
        e = Env(self)
        self._default_dir_env()
        self._cfg(e, self._stale(e))
        cd = e.home / ".claude"
        self.assertEqual(ps.setup(REPO, cd, COMPS, yes=True, key="", flowobserve=False), 0)
        rm = self._removes(e)
        self.assertEqual(len(rm), 1, e.calls())
        self.assertIsNone(e.envs()[rm[0]])  # default dir: no CLAUDE_CONFIG_DIR in the child env

    def test_setup_removes_stale_jev_for_custom_dir(self):
        e = Env(self)
        self._default_dir_env()
        cd = e.home / ".claude-team"
        self._cfg(e, {"command": "/usr/bin/python3", "args": [str(cd / "jev" / "jev_mcp.py")]})
        self.assertEqual(ps.setup(REPO, cd, COMPS, yes=True, key="", flowobserve=False), 0)
        rm = self._removes(e)
        self.assertEqual(len(rm), 1, e.calls())
        self.assertIsNone(e.envs()[rm[0]])  # the entry is in ~/.claude.json: run without CLAUDE_CONFIG_DIR

    def test_other_dirs_jev_is_kept_for_custom_dir(self):
        e = Env(self)
        self._default_dir_env()
        self._cfg(e, {"command": "python3", "args": [str(e.home / ".claude-other" / "jev" / "jev_mcp.py")]})
        self.assertEqual(ps.setup(REPO, e.home / ".claude-team", COMPS, yes=True, key="", flowobserve=False), 0)
        self.assertEqual(self._removes(e), [])

    def test_live_jev_mcp_file_is_kept(self):
        e = Env(self)
        self._default_dir_env()
        entry = self._stale(e)
        script = Path(entry["args"][-1])
        script.parent.mkdir(parents=True)
        script.write_text("", encoding="utf-8")
        self._cfg(e, entry)
        self.assertEqual(ps.setup(REPO, e.home / ".claude", COMPS, yes=True, key="", flowobserve=False), 0)
        self.assertEqual(self._removes(e), [])

    def test_users_own_jev_server_is_kept(self):
        e = Env(self)
        self._default_dir_env()
        self._cfg(e, {"command": "node", "args": ["/opt/my-jev/server.js"]})
        self.assertEqual(ps.setup(REPO, e.home / ".claude", COMPS, yes=True, key="", flowobserve=False), 0)
        self.assertEqual(self._removes(e), [])

    def test_no_global_config_is_fine(self):
        e = Env(self)
        self._default_dir_env()
        self.assertFalse((e.home / ".claude.json").exists())
        self.assertEqual(ps.setup(REPO, e.home / ".claude", COMPS, yes=True, key="", flowobserve=False), 0)
        self.assertEqual(self._removes(e), [])

    def test_dry_run_prints_remove_without_calling(self):
        e = Env(self)
        self._default_dir_env()
        self._cfg(e, self._stale(e))
        out = _out(lambda: ps.setup(REPO, e.home / ".claude", COMPS, yes=True, key="", flowobserve=False, dry=True))
        self.assertIn("claude mcp remove --scope user jev", out)
        self.assertEqual(self._removes(e), [])


if __name__ == "__main__":
    unittest.main()
