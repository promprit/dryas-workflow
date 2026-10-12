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
FOREIGN = ('\n[mcp_servers.x]\ncommand = "echo"\nargs = ["hi"]\n\n[hooks.state]\n\n'
           '[hooks.state."dryas@dryas-workflow:hooks/hooks.json:session_start:0:0"]\ntrusted_hash = "sha256:ab"\n')


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
        rec = json.loads((e.a / cps.RECORD).read_text(encoding="utf-8"))  # kept so uninstall can undo the marketplace
        self.assertTrue(rec["marketplace_added"] and rec["dir_created"])
        self.assertEqual(rec["components"], [])
        self.assertNotIn("plugin_root", rec)

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
        self.assertIn("command = %s" % cps.ct._q(cps.pu.fwd(cps.di.PY)), t)
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

    def test_codex_tables_inside_block_are_kept(self):
        # real 0.162.1: `codex mcp add` and hook trust writes land after our last table, before the end marker
        e = Env(self)
        quiet(cps.setup, REPO, e.a, ["core"], yes=True)
        cfg = e.a / "config.toml"
        cfg.write_text(e.toml(e.a).replace(cps.TOML_END, FOREIGN.strip("\n") + "\n" + cps.TOML_END), encoding="utf-8")
        self.assertEqual(quiet(cps.setup, REPO, e.a, ["core"], yes=True)[0], 0)
        t = e.toml(e.a)
        inner = t.split(cps.TOML_START)[1].split(cps.TOML_END)[0]
        self.assertEqual(inner, '\n[plugins."dryas@dryas-workflow".mcp_servers.jev]\nenabled = false\n')
        self.assertEqual(t.count(FOREIGN.strip("\n")), 1)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)  # block removed, Codex's tables stay
        self.assertNotIn(cps.TOML_START, e.toml(e.a))
        self.assertNotIn("mcp_servers.jev", e.toml(e.a))
        self.assertEqual(e.toml(e.a).count(FOREIGN.strip("\n")), 1)

    def test_lost_record_no_duplicate_block(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, ["core"], yes=True)
        (e.a / cps.RECORD).unlink()
        cfg = e.a / "config.toml"
        cfg.write_text(e.toml(e.a).replace(cps.TOML_END, FOREIGN.strip("\n") + "\n" + cps.TOML_END), encoding="utf-8")
        quiet(cps.setup, REPO, e.a, ["core"], yes=True)
        t = e.toml(e.a)
        self.assertEqual((t.count(cps.TOML_START), t.count(cps.TOML_END), t.count("mcp_servers.jev]")), (1, 1, 1))
        self.assertEqual(t.count("[mcp_servers.x]"), 1)
        (e.a / cps.RECORD).unlink()
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)  # lost record and Jev back on: the block still goes
        self.assertNotIn(cps.TOML_START, e.toml(e.a))
        self.assertIn("[mcp_servers.x]", e.toml(e.a))

    def test_marker_dropped_by_codex(self):
        # real 0.162.1: `codex mcp add y` after our [mcp_servers.jev] drops the start marker (comment before that table)
        e = Env(self, py3=False)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        cfg = e.a / "config.toml"
        t = e.toml(e.a).replace(cps.TOML_START + "\n", "").replace(
            cps.TOML_END, '\n[mcp_servers.y]\ncommand = "echo"\n' + cps.TOML_END)
        cfg.write_text(t, encoding="utf-8")
        self.assertEqual(quiet(cps.setup, REPO, e.a, COMPS, yes=True)[0], 0)
        t = e.toml(e.a)
        self.assertEqual((t.count(cps.TOML_START), t.count(cps.TOML_END), t.count("[mcp_servers.jev]")), (1, 1, 1))
        self.assertIn('[mcp_servers.y]\ncommand = "echo"', t.split(cps.TOML_START)[0])
        (e.a / cps.RECORD).unlink()  # lost record too, and only the start marker left
        cfg.write_text(e.toml(e.a).replace(cps.TOML_END + "\n", ""), encoding="utf-8")  # lone start marker
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual(e.toml(e.a).count("[mcp_servers.jev]"), 1)

    def test_foreign_table_with_our_name_not_overwritten(self):
        e = Env(self, py3=False)
        e.a.mkdir()
        (e.a / "config.toml").write_text('[mcp_servers.jev]\ncommand = "mine"\n', encoding="utf-8")
        rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual(rc, 2)
        self.assertIn("[mcp_servers.jev], not written by Dryas setup", out)
        self.assertIn("error:", out.strip().splitlines()[-1])
        self.assertFalse((e.root / "accounts.json").exists())
        self.assertEqual(e.toml(e.a).count("[mcp_servers.jev]"), 1)
        self.assertIn('command = "mine"', e.toml(e.a))
        self.assertNotIn(cps.TOML_START, e.toml(e.a))

    def test_ruflo_branch(self):
        e = Env(self)
        dist = e.t / "npm" / "ruflo" / "node_modules" / "@claude-flow" / "cli" / "dist"
        dist.mkdir(parents=True)
        det = {"RUFLO_BIN": "", "RUFLO_JS": str(e.t / "npm" / "ruflo" / "bin" / "ruflo.js"), "RUFLO_NODE_FALLBACK": "",
               "RUFLO_NODE_MODULES": str(e.t / "npm" / "ruflo" / "node_modules"), "RUFLO_CLI_DIST": str(dist)}
        with mock.patch.object(cps.di, "detect", lambda: dict(det)):
            self.assertEqual(quiet(cps.setup, REPO, e.a, COMPS + ["ruflo"], yes=True)[0], 0)
        t = e.toml(e.a)
        self.assertIn("[mcp_servers.ruflo]", t)
        self.assertIn("RUFLO_JS = %s" % cps.ct._q(det["RUFLO_JS"]), t)
        self.assertTrue((e.root / "ruflo" / "mcp-shim" / "bin" / "cli.js").is_file())
        self.assertIsNotNone(cps.pu.read_dir_link(str(e.root / "ruflo" / "mcp-shim" / "dist")))
        shutil.rmtree(str(dist))
        with mock.patch.object(cps.di, "detect", lambda: dict(det)):
            rc, out = quiet(cps.setup, REPO, e.b, COMPS + ["ruflo"], yes=True)
        self.assertEqual(rc, 0)
        self.assertIn("warning", out)
        self.assertNotIn("mcp_servers.ruflo", e.toml(e.b))

    def test_user_table_with_our_name_near_block_survives(self):
        # like `codex mcp add ruflo -- ...` after a core-only setup: Codex puts it right before our end marker
        e = Env(self)
        quiet(cps.setup, REPO, e.a, ["core"], yes=True)
        user = '[mcp_servers.ruflo]\ncommand = "mine"\n'
        (e.a / "config.toml").write_text(e.toml(e.a).replace(cps.TOML_END, "\n" + user + cps.TOML_END), encoding="utf-8")
        self.assertEqual(quiet(cps.setup, REPO, e.a, ["core"], yes=True)[0], 0)
        self.assertIn(user, e.toml(e.a))
        self.assertEqual(quiet(cps.setup, REPO, e.a, COMPS, yes=True)[0], 0)
        self.assertIn(user, e.toml(e.a))

    def test_changed_recorded_table_is_left(self):
        e = Env(self, py3=False)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        t = e.toml(e.a)
        start = t.index("[mcp_servers.jev]")
        end = t.index(cps.TOML_END)
        mine = '[mcp_servers.jev]\ncommand = "mine"\n'
        (e.a / "config.toml").write_text(t[:start] + mine + t[end:], encoding="utf-8")
        rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual(rc, 2)
        self.assertIn("was changed after Dryas setup wrote it", out)
        self.assertIn(mine, e.toml(e.a))
        with mock.patch.object(cps, "python3_ok", lambda: True):  # nothing to write: warned, left, setup goes on
            rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual(rc, 0)
        self.assertIn("was changed after Dryas setup wrote it", out)
        self.assertIn(mine, e.toml(e.a))

    def test_owned_tables_and_rewrite_pure(self):
        ov = ("plugins", cps.ID, "mcp_servers", "jev")
        ovh = '[plugins."dryas@dryas-workflow".mcp_servers.jev]'
        body = ovh + "\nenabled = false"
        x = '[mcp_servers.x]\ncommand = "echo"\n'
        text = "a = 1\n\n" + cps.TOML_START + "\n" + body + "\n\n" + x + cps.TOML_END + "\n"
        self.assertEqual(cps.owned_tables(text, body), ({ov}, []))
        self.assertEqual(cps.owned_tables(text, ""), (set(), []))  # a record owns only what it lists
        self.assertEqual(cps.owned_tables(text.replace("false", "true"), body), (set(), [ov]))
        self.assertEqual(cps.owned_tables(text.replace("enabled = false", "enabled  =  false # c"), body), ({ov}, []))
        self.assertEqual(cps.owned_tables(text, None), ({ov}, []))  # lost record: our headers inside the markers
        self.assertEqual(cps.owned_tables(text.replace(cps.TOML_START + "\n", ""), None)[0], set())  # x before end
        self.assertEqual(cps.owned_tables("[mcp_servers.jev]\nc = 1\n" + cps.TOML_END + "\n", None)[0],
                         {("mcp_servers", "jev")})
        self.assertEqual(cps.owned_tables("[mcp_servers.jev]\nc = 1\n", None)[0], set())
        new = cps.rewrite_config(text, "[mcp_servers.ruflo]\ncommand = \"node\"", {ov})
        self.assertEqual(new, "a = 1\n\n" + x + "\n" + cps.TOML_START + '\n[mcp_servers.ruflo]\ncommand = "node"\n' +
                         cps.TOML_END + "\n")
        self.assertEqual(cps.rewrite_config(text, "", {ov}), "a = 1\n\n" + x)
        self.assertEqual(cps.rewrite_config(cps.TOML_START + "\n" + body + "\n" + cps.TOML_END + "\n", "", {ov}), "")
        sub = ("[mcp_servers.ruflo]\ncommand = 1\n\n# keep\n[mcp_servers.ruflo.env]\nA = 1\n"
               "[[mcp_servers.ruflo.list]]\nb = 2\n\n[z]\nm = [\n  [1],\n]\ns = \"\"\"\n[mcp_servers.ruflo]\n\"\"\"\n")
        self.assertEqual(cps.rewrite_config(sub, "", {("mcp_servers", "ruflo")}),
                         "# keep\n[z]\nm = [\n  [1],\n]\ns = \"\"\"\n[mcp_servers.ruflo]\n\"\"\"\n")

    def test_norm_header(self):
        self.assertEqual(cps.norm_header(' [ mcp_servers . "jev" ]  # c\n'), (("mcp_servers", "jev"), False))
        self.assertEqual(cps.norm_header("[[a.'b c']]"), (("a", "b c"), True))
        self.assertEqual(cps.norm_header('[plugins."dryas@dryas-workflow".mcp_servers.jev]'),
                         (("plugins", "dryas@dryas-workflow", "mcp_servers", "jev"), False))
        for bad in ("a = [1]", "[a]]", "[a = 1]", "# [a]", "[]"):
            self.assertIsNone(cps.norm_header(bad), bad)

    def test_nothing_to_do_leaves_file(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        cfg, raw = t / "config.toml", "a=1\r\n\r\n\r\n# >>> dryas plugin >>>\r\n"
        cfg.write_bytes(raw.encode("utf-8"))
        rec = {}
        self.assertTrue(cps.write_config_block(cfg, "", rec))
        self.assertEqual(cfg.read_bytes(), raw.encode("utf-8"))
        self.assertFalse(rec["toml"])

    def test_toml_block_pure(self):
        self.assertEqual(cps.toml_block(["core", "jev"], "/p", "/d", {}, ""), "")
        b = cps.toml_block(["core", "jev", "ruflo"], "/p", "/d", {"RUFLO_JS": "/r.js", "OTHER": "x"}, "")
        self.assertIn('[mcp_servers.ruflo]\ncommand = "node"\nargs = ["/d/ruflo/mcp-shim/bin/cli.js", "mcp", "start"]', b)
        self.assertIn('env = { RUFLO_JS = "/r.js" }', b)
        self.assertNotIn("OTHER", b)


if __name__ == "__main__":
    unittest.main()
