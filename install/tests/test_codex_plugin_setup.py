import io, json, os, shutil, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import fakecli
import codex_plugin_setup as cps

REPO = HERE.parents[1]
COMPS = ["core", "jev"]


class Env:
    """Temp HOME and data root, two CODEX_HOMEs, the fake codex on PATH, python3 assumed fine."""

    def __init__(self, tc, fail=(), py3=True):
        self.t = Path(tempfile.mkdtemp())
        tc.addCleanup(shutil.rmtree, str(self.t), True)
        self.home, self.root = self.t / "home", self.t / "home" / ".dryas"
        self.a, self.b = self.t / "codex-a", self.t / "codex-b"
        self.log = self.t / "calls.jsonl"
        self.home.mkdir()
        fakecli.make_codex(self.t / "bin", self.log, fail)
        for p in (mock.patch.dict(os.environ, {"PATH": str(self.t / "bin") + os.pathsep + os.environ["PATH"],
                                                "HOME": str(self.home), "USERPROFILE": str(self.home),
                                                "DRYAS_DATA_ROOT": str(self.root)}),
                  mock.patch.object(cps, "python3_ok", lambda: py3)):
            p.start()
            tc.addCleanup(p.stop)
        os.environ.pop("CODEX_HOME", None)
        os.environ.pop("OPENROUTER_API_KEY", None)

    def calls(self):
        return fakecli.calls(self.log)

    def state(self, cdx):
        return json.loads((cdx / "fake_codex.json").read_text(encoding="utf-8"))

    def toml(self, cdx):
        p = cdx / "config.toml"
        return p.read_text(encoding="utf-8") if p.exists() else ""


def quiet(fn, *a, **k):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = fn(*a, **k)
    return rc, buf.getvalue()


class SetupTest(unittest.TestCase):
    def test_codex_home_resolution(self):
        with mock.patch.dict(os.environ, {"CODEX_HOME": "/cx"}):
            self.assertEqual(cps.codex_home(None), cps.ps.norm("/cx"))
            self.assertEqual(cps.codex_home("/y"), cps.ps.norm("/y"))
        env = {k: v for k, v in os.environ.items() if k != "CODEX_HOME"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(cps.codex_home(None), cps.ps.norm(Path.home() / ".codex"))

    def test_codex_version(self):
        self.assertEqual(cps.codex_version("codex-cli 0.162.1\n"), (0, 162, 1))
        self.assertIsNone(cps.codex_version("garbage"))

    def test_two_codex_homes(self):
        e = Env(self)
        for cdx in (e.a, e.b):
            self.assertEqual(quiet(cps.setup, REPO, cdx, COMPS, yes=True)[0], 0)
            self.assertIn(cps.ID, e.state(cdx)["plugins"])  # the fake keeps state under its own CODEX_HOME
            rec = json.loads((cdx / cps.RECORD).read_text(encoding="utf-8"))
            self.assertTrue(rec["plugin_root"].startswith(str(cps.ps.norm(cdx))))
            self.assertEqual(rec["components"], COMPS)
        acc = json.loads((e.root / "accounts.json").read_text(encoding="utf-8"))
        self.assertEqual(acc["codex_dirs"], [str(cps.ps.norm(e.a)), str(cps.ps.norm(e.b))])
        self.assertNotIn("claude_dirs", acc)
        self.assertTrue((e.root / "docs" / "dryas-workflow.md").is_file())
        self.assertIn("off", json.loads((e.root / "chain.local.json").read_text(encoding="utf-8")))

    def test_fresh_codex_home_not_listed_before_created(self):
        # the real CLI exits 1 on `plugin marketplace list` when CODEX_HOME does not exist yet
        e = Env(self)
        self.assertEqual(quiet(cps.setup, REPO, e.a, COMPS, yes=True)[0], 0)
        self.assertNotIn(["codex", "plugin", "marketplace", "list", "--json"], e.calls())
        self.assertTrue(json.loads((e.a / cps.RECORD).read_text(encoding="utf-8"))["dir_created"])

    def test_marketplace_added_once(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        adds = [c for c in e.calls() if c[1:4] == ["plugin", "marketplace", "add"]]
        self.assertEqual(len(adds), 1)
        self.assertEqual(len([c for c in e.calls() if c[1:3] == ["plugin", "add"]]), 2)  # re-add refreshes the cache
        self.assertTrue(json.loads((e.a / cps.RECORD).read_text(encoding="utf-8"))["marketplace_added"])

    def test_marketplace_from_other_root_stops(self):
        e = Env(self)
        other = e.t / "other-clone"
        shutil.copytree(str(REPO / ".agents"), str(other / ".agents"))
        env = dict(os.environ, CODEX_HOME=str(e.a))
        cps.di.run(["codex", "plugin", "marketplace", "add", str(other)], env=env)
        rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual(rc, 1)
        self.assertIn(str(other), out)
        self.assertFalse([c for c in e.calls() if c[1:3] == ["plugin", "add"]])

    def test_plugin_add_failure_stops_before_config(self):
        e = Env(self, fail=["plugin add"])
        self.assertEqual(quiet(cps.setup, REPO, e.a, ["core"], yes=True)[0], 1)
        self.assertNotIn(cps.TOML_START, e.toml(e.a))
        self.assertFalse((e.root / "accounts.json").exists())
        self.assertFalse((e.a / cps.RECORD).exists())

    def test_old_codex_stops(self):
        e = Env(self)
        with mock.patch.dict(os.environ, {"FAKE_CODEX_VERSION": "codex-cli 0.150.0"}):
            rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual(rc, 1)
        self.assertIn("0.162.1", out)
        self.assertFalse([c for c in e.calls() if c[1:2] == ["plugin"]])

    def test_jev_off_overlay_and_rerun_removes_it(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, ["core"], yes=True)
        self.assertIn('[plugins."dryas@dryas-workflow".mcp_servers.jev]\nenabled = false', e.toml(e.a))
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertNotIn("mcp_servers.jev", e.toml(e.a))
        self.assertNotIn(cps.TOML_START, e.toml(e.a))

    def test_python3_fallback_server(self):
        e = Env(self, py3=False)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        t = e.toml(e.a)
        self.assertIn("[mcp_servers.jev]", t)
        self.assertIn(json.dumps(cps.pu.fwd(cps.di.PY)), t)
        self.assertIn("/jev/jev_mcp.py", t)
        self.assertIn('env_vars = ["OPENROUTER_API_KEY", "DRYAS_OPENROUTER_KEY", "DRYAS_DATA_ROOT"]', t)

    def test_key_never_written(self):
        e = Env(self)
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-secret-1"}):
            quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertNotIn("sk-secret-1", e.toml(e.a))

    def test_dry_run_changes_nothing(self):
        e = Env(self)
        rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True, dry=True)
        self.assertEqual(rc, 0)
        self.assertIn("codex plugin add dryas@dryas-workflow", out)
        self.assertFalse(e.a.exists() and any(e.a.iterdir()))

    def test_toml_block_pure(self):
        self.assertEqual(cps.toml_block(["core", "jev"], "/p", "/d", {}, ""), "")
        b = cps.toml_block(["core", "jev", "ruflo"], "/p", "/d", {"RUFLO_JS": "/r.js", "OTHER": "x"}, "")
        self.assertIn('[mcp_servers.ruflo]\ncommand = "node"\nargs = ["/d/ruflo/mcp-shim/bin/cli.js", "mcp", "start"]', b)
        self.assertIn('env = { RUFLO_JS = "/r.js" }', b)
        self.assertNotIn("OTHER", b)


if __name__ == "__main__":
    unittest.main()
