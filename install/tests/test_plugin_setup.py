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
            "    d = os.path.join(os.environ['CLAUDE_CONFIG_DIR'], 'plugins'); os.makedirs(d, exist_ok=True)\n"
            "    rec = %r\n"
            "    rec['plugins']['dryas@dryas-workflow'][0]['installPath'] = %r\n"
            "    open(os.path.join(d, 'installed_plugins.json'), 'w').write(json.dumps(rec))\n"
            "with open(%r, 'a') as f: f.write(json.dumps(os.environ.get('CLAUDE_CONFIG_DIR')) + '\\n')\n"
        ) % (INSTALLED, str(REPO / "claude"), str(self.t / "envs.jsonl"))
        fakecli.make(bin_dir, "claude", self.log, epilogue=self.epilogue)
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
        installs = [c for c in e.calls() if c[1:3] == ["plugin", "install"]]
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

    def test_key_passed_as_config(self):
        e = Env(self)
        ps.setup(REPO, e.a, COMPS, yes=True, key="sk-1", flowobserve=False)
        inst = [c for c in e.calls() if c[1:3] == ["plugin", "install"]][0]
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
        fakecli.make(e.bin, "claude", e.log, fail=["plugin install"], epilogue=e.epilogue)
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

    def test_missing_workflow_doc_warns(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        ps.write_workflow_doc(t / "norepo", t / "root")
        self.assertFalse((t / "root" / "docs" / "dryas-workflow.md").exists())

    def test_remove_account(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        ps.add_account(t, Path("/a"))
        ps.add_account(t, Path("/b"))
        self.assertEqual(ps.remove_account(t, Path("/a")), [str(Path("/b").resolve())])
        self.assertEqual(json.loads((t / "accounts.json").read_text())["claude_dirs"], [str(Path("/b").resolve())])


if __name__ == "__main__":
    unittest.main()
