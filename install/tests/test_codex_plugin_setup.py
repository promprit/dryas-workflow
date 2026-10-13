import io, json, os, shutil, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import fakecli
import legacy_codex
import codex_plugin_setup as cps
import codex_appserver as ca
import codex_target as ct
import dryas_install as di

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


class TrustTest(unittest.TestCase):
    def hooks(self, cdx):
        return [h for h in ca.list_hooks(dict(os.environ, CODEX_HOME=str(cdx)), str(Path.home()))
                if h["pluginId"] == cps.ID]

    def test_yes_trusts_and_records(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual({h["trustStatus"] for h in self.hooks(e.a)}, {"trusted"})
        rec = json.loads((e.a / cps.RECORD).read_text(encoding="utf-8"))
        self.assertEqual(sorted(rec["trusted"]), sorted(h["key"] for h in self.hooks(e.a)))
        self.assertEqual(rec["trusted"], {h["key"]: h["currentHash"] for h in self.hooks(e.a)})

    def test_declined_trusts_nothing(self):
        e = Env(self)
        with mock.patch.object(cps.di, "confirm", lambda *a: False):
            rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=False)
        self.assertEqual(rc, 0)
        self.assertIn("/hooks", out)
        self.assertNotIn("hooks.state", e.toml(e.a))
        self.assertEqual(json.loads((e.a / cps.RECORD).read_text(encoding="utf-8"))["trusted"], {})

    def test_asks_with_the_hook_list(self):
        e = Env(self)
        asked = []
        with mock.patch.object(cps.di, "confirm", lambda p: asked.append(p) or True):
            rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=False)
        self.assertEqual(len(asked), 1)
        self.assertIn("chain.py\" pretool --harness codex", out)

    def test_second_run_does_not_ask(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        before = e.toml(e.a)
        with mock.patch.object(cps.di, "confirm", lambda *a: self.fail("asked again")):
            quiet(cps.setup, REPO, e.a, COMPS, yes=False)
        self.assertEqual(e.toml(e.a), before)

    def test_modified_hook_is_retrusted(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        p = e.a / "config.toml"
        p.write_text(p.read_text(encoding="utf-8").replace('trusted_hash = "sha256:', 'trusted_hash = "sha256:0', 1),
                     encoding="utf-8")
        self.assertIn("modified", {h["trustStatus"] for h in self.hooks(e.a)})
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual({h["trustStatus"] for h in self.hooks(e.a)}, {"trusted"})

    def test_app_server_failure_is_a_hint_not_an_error(self):
        e = Env(self, fail=["app-server"])
        rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual(rc, 0)
        self.assertIn("/hooks", out)
        self.assertNotIn("hooks.state", e.toml(e.a))

    def test_trust_error_response_is_a_hint(self):
        e = Env(self)
        with mock.patch.dict(os.environ, {"FAKE_APPSERVER_FAIL": "config/batchWrite"}):
            rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual(rc, 0)
        self.assertIn(cps.TRUST_HINT, out)
        self.assertEqual(json.loads((e.a / cps.RECORD).read_text(encoding="utf-8"))["trusted"], {})

    def test_only_dryas_hooks_trusted(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        st = e.state(e.a)
        other = dict(st["plugins"][cps.ID])
        st["plugins"]["other@x"] = other  # same hooks under another plugin id
        (e.a / "fake_codex.json").write_text(json.dumps(st), encoding="utf-8")
        others = [h for h in ca.list_hooks(dict(os.environ, CODEX_HOME=str(e.a)), str(Path.home()))
                  if h["pluginId"] == "other@x"]
        self.assertEqual(len(others), len(self.hooks(e.a)))
        self.assertEqual({h["trustStatus"] for h in others}, {"untrusted"})  # listed, and not trusted
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertNotIn("other@x", e.toml(e.a))
        others = [h for h in ca.list_hooks(dict(os.environ, CODEX_HOME=str(e.a)), str(Path.home()))
                  if h["pluginId"] == "other@x"]
        self.assertEqual({h["trustStatus"] for h in others}, {"untrusted"})


class VerifyTest(unittest.TestCase):
    def test_pass_after_setup(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        fails, out = quiet(cps.verify, e.a, COMPS)
        self.assertEqual(fails, 0, out)
        for line in ("PASS  dryas@dryas-workflow installed and enabled", "PASS  Codex Jev MCP server listed",
                     "PASS  Dryas hooks trusted", "PASS  Dryas skills listed", "PASS  rules hook prints SessionStart JSON",
                     "PASS  scope lock blocks an out-of-scope apply_patch", "PASS  no legacy Codex copy install"):
            self.assertIn(line, out)

    def test_untrusted_fails(self):
        e = Env(self)
        with mock.patch.object(cps.di, "confirm", lambda *a: False):
            quiet(cps.setup, REPO, e.a, COMPS, yes=False)
        fails, out = quiet(cps.verify, e.a, COMPS)
        self.assertGreaterEqual(fails, 1)
        self.assertIn("FAIL  Dryas hooks trusted", out)
        self.assertIn("/hooks", out)

    def test_not_installed(self):
        e = Env(self)
        fails, out = quiet(cps.verify, e.a, COMPS)
        self.assertEqual(fails, 1)
        self.assertIn("FAIL  dryas@dryas-workflow installed and enabled", out)

    def test_app_server_failure_fails_trust_line(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        with mock.patch.dict(os.environ, {"FAKE_APPSERVER_FAIL": "hooks/list"}):
            fails, out = quiet(cps.verify, e.a, COMPS)
        self.assertEqual(fails, 1, out)
        self.assertIn("FAIL  Dryas hooks trusted", out)

    def test_missing_hook_event_fails(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        hp = Path(json.loads((e.a / cps.RECORD).read_text(encoding="utf-8"))["plugin_root"]) / "hooks" / "hooks.json"
        data = json.loads(hp.read_text(encoding="utf-8"))
        del data["hooks"]["SessionStart"]  # Codex now lists only the other two, both trusted
        hp.write_text(json.dumps(data), encoding="utf-8")
        fails, out = quiet(cps.verify, e.a, COMPS)
        self.assertEqual(fails, 1, out)
        self.assertIn("FAIL  Dryas hooks trusted", out)
        self.assertIn("missing: sessionStart", out)

    def test_expected_events_from_plugin_hooks(self):
        self.assertEqual(cps.expected_hook_events(REPO), ["preToolUse", "sessionStart", "userPromptSubmit"])

    def test_jev_off_skips_mcp_line(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, ["core"], yes=True)
        fails, out = quiet(cps.verify, e.a, ["core"])
        self.assertEqual(fails, 0, out)
        self.assertNotIn("Jev MCP", out)


class MigrationTest(unittest.TestCase):
    def legacy(self, e, cdx, claude_copy=False):
        return legacy_codex.legacy(e.home, cdx, claude_copy)

    def test_legacy_removed_and_runtime_copy_dropped(self):
        e = Env(self)
        cd = self.legacy(e, e.a)
        rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual(rc, 0, out)
        self.assertFalse((e.a / ct.RECORD).exists())
        self.assertEqual((e.a / "AGENTS.md").read_text(encoding="utf-8"), "mine\n")
        self.assertFalse((ct.skills_dir(e.home) / "orchestrate").exists())
        self.assertFalse((e.a / "hooks.json").exists())
        self.assertIn(["codex", "mcp", "remove", "jev"], e.calls())
        self.assertFalse((cd / di.RECORD).exists())
        self.assertFalse((cd / "jev" / "chain.py").exists())
        mcp_remove = e.calls().index(["codex", "mcp", "remove", "jev"])
        self.assertLess(max(i for i, c in enumerate(e.calls()) if c[1:3] == ["plugin", "add"]), mcp_remove)
        self.assertFalse((e.home / ".codex").exists())  # `codex mcp remove` ran with CODEX_HOME=<cdx>
        self.assertIn(cps.ID, e.state(e.a)["plugins"])
        fails, vout = quiet(cps.verify, e.a, COMPS)
        self.assertEqual(fails, 0, vout)
        self.assertIn("PASS  no legacy Codex copy install", vout)

    def test_live_claude_copy_install_is_kept(self):
        e = Env(self)
        with mock.patch.object(cps.migrate, "is_copy_install", lambda cd: True):
            cd = self.legacy(e, e.a, claude_copy=True)
            rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual(rc, 0)
        self.assertTrue((cd / di.RECORD).exists())
        self.assertIn("Claude Code still uses", out)

    def test_runtime_copy_kept_while_another_codex_home_uses_it(self):
        e = Env(self)
        cd = self.legacy(e, e.a)
        (e.home / ".codex").mkdir()
        (e.home / ".codex" / ct.RECORD).write_text(json.dumps({"components": ["core"]}), encoding="utf-8")
        rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual(rc, 0, out)
        self.assertFalse((e.a / ct.RECORD).exists())
        self.assertTrue((cd / "jev" / "chain.py").exists())
        self.assertIn("kept the Codex runtime copy in %s" % cd, out)

    def test_legacy_components(self):
        e = Env(self)
        self.legacy(e, e.a)
        self.assertEqual(cps.legacy_components(e.a), ["core", "jev"])
        self.assertIsNone(cps.legacy_components(e.b))

    def test_runtime_copy_state_moved_before_removal(self):
        # an older runtime copy kept Jev state in ~/.claude/jev: it reaches the data root before the copy goes
        e = Env(self)
        cd = self.legacy(e, e.a)
        (cd / "jev" / "logs").mkdir()
        (cd / "jev" / "logs" / "jev.jsonl").write_text('{"a": 1}\n', encoding="utf-8")
        shipped = json.loads((REPO / "claude" / "jev" / "thresholds.json").read_text(encoding="utf-8"))
        sec = next(k for k, v in shipped.items() if isinstance(v, dict) and v)
        key = next(iter(shipped[sec]))
        tuned = dict(shipped, **{sec: dict(shipped[sec], **{key: "tuned"})})
        (cd / "jev" / "thresholds.json").write_text(json.dumps(tuned), encoding="utf-8")
        rec = json.loads((cd / di.RECORD).read_text(encoding="utf-8"))
        rec["files"]["jev/thresholds.json"] = {}
        (cd / di.RECORD).write_text(json.dumps(rec), encoding="utf-8")
        rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual(rc, 0, out)
        self.assertFalse((cd / "jev" / "thresholds.json").exists())
        self.assertEqual(json.loads((e.root / "jev" / "thresholds.json").read_text(encoding="utf-8")),
                         {sec: {key: "tuned"}})
        self.assertEqual((e.root / "jev" / "logs" / "jev.jsonl").read_text(encoding="utf-8"), '{"a": 1}\n')

    def test_existing_data_root_state_kept(self):
        e = Env(self)
        self.legacy(e, e.a)
        (e.root / "jev" / "logs").mkdir(parents=True)
        (e.root / "jev" / "logs" / "jev.jsonl").write_text('{"keep": 1}\n', encoding="utf-8")
        (e.root / "chain.local.json").write_text(json.dumps({"stages": {"pretool": {"mine": {"x": 1}}}}),
                                                 encoding="utf-8")
        self.assertEqual(quiet(cps.setup, REPO, e.a, COMPS, yes=True)[0], 0)
        self.assertEqual((e.root / "jev" / "logs" / "jev.jsonl").read_text(encoding="utf-8"), '{"keep": 1}\n')
        loc = json.loads((e.root / "chain.local.json").read_text(encoding="utf-8"))
        self.assertEqual(loc["stages"]["pretool"]["mine"], {"x": 1})

    def test_unreadable_legacy_stops_before_any_change(self):
        for where in ("codex", "hooks", "claude"):
            e = Env(self)
            cd = self.legacy(e, e.a)
            bad = {"codex": e.a / ct.RECORD, "hooks": e.a / "hooks.json", "claude": cd / di.RECORD}[where]
            bad.write_text("[]" if where != "hooks" else "{broken", encoding="utf-8")
            rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True)
            self.assertEqual(rc, 1, where)
            self.assertIn("nothing changed", out, where)
            self.assertFalse([c for c in e.calls() if c[1:2] in (["plugin"], ["mcp"])], where)
            self.assertEqual((e.a / "AGENTS.md").read_text(encoding="utf-8"), legacy_codex.AGENTS, where)
            self.assertTrue((cd / "jev" / "chain.py").exists(), where)

    def test_rerun_after_migration_is_a_no_op(self):
        e = Env(self)
        self.legacy(e, e.a)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        n = len(e.calls())
        rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual(rc, 0)
        self.assertNotIn(["codex", "mcp", "remove", "jev"], e.calls()[n:])
        self.assertNotIn("Removing the Codex copy install", out)

    def test_resumes_after_a_failed_legacy_uninstall(self):
        e = Env(self)
        cd = self.legacy(e, e.a)
        real = ct.uninstall_codex

        def boom(*a, **k):
            raise OSError("disk went away")
        with mock.patch.object(ct, "uninstall_codex", boom):
            rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual(rc, 1)
        self.assertIn("disk went away", out)
        self.assertNotIn(cps.TOML_START, e.toml(e.a))  # config block not written
        self.assertFalse((e.root / "accounts.json").exists())
        self.assertTrue((cd / di.RECORD).exists())  # nothing after the failed step ran
        with mock.patch.object(ct, "uninstall_codex", real):
            rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        self.assertEqual(rc, 0, out)
        self.assertFalse((e.a / ct.RECORD).exists())
        self.assertFalse((cd / di.RECORD).exists())

    def test_dry_run_reports_and_changes_nothing(self):
        e = Env(self)
        cd = self.legacy(e, e.a)
        rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True, dry=True)
        self.assertEqual(rc, 0)
        self.assertIn("would remove the Codex copy install in", out)
        self.assertIn("would remove the Codex runtime copy in", out)
        self.assertTrue((e.a / ct.RECORD).exists())
        self.assertTrue((cd / di.RECORD).exists())
        self.assertNotIn(["codex", "mcp", "remove", "jev"], e.calls())


class UninstallTest(unittest.TestCase):
    def test_removes_everything_it_added(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, ["core"], yes=True)  # jev off: overlay block present
        quiet(cps.setup, REPO, e.b, COMPS, yes=True)
        rc, out = quiet(cps.uninstall, e.a)
        self.assertEqual(rc, 0)
        t = e.toml(e.a)
        self.assertNotIn("hooks.state", t)
        self.assertNotIn(cps.TOML_START, t)
        self.assertNotIn(cps.ID, e.state(e.a)["plugins"])
        self.assertNotIn(cps.MARKET, e.state(e.a)["marketplaces"])
        self.assertFalse((e.a / cps.RECORD).exists())
        acc = json.loads((e.root / "accounts.json").read_text(encoding="utf-8"))
        self.assertEqual(acc["codex_dirs"], [str(cps.ps.norm(e.b))])
        self.assertIn(cps.ID, e.state(e.b)["plugins"])  # the other CODEX_HOME is untouched

    def test_marketplace_kept_when_not_added_by_setup(self):
        e = Env(self)
        cps.di.run(["codex", "plugin", "marketplace", "add", str(REPO)], env=dict(os.environ, CODEX_HOME=str(e.a)))
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        quiet(cps.uninstall, e.a)
        self.assertIn(cps.MARKET, e.state(e.a)["marketplaces"])

    def test_nothing_to_uninstall(self):
        e = Env(self)
        self.assertEqual(quiet(cps.uninstall, e.a)[0], 0)

    def test_plugin_remove_failure_still_cleans_config(self):
        e = Env(self, fail=["plugin remove"])
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        rc, out = quiet(cps.uninstall, e.a)
        self.assertEqual(rc, 0)
        self.assertIn("warning", out)
        self.assertNotIn("hooks.state", e.toml(e.a))

    def test_user_content_kept(self):
        e = Env(self)
        e.a.mkdir()
        user = 'model = "o3"\n\n[mcp_servers.mine]\ncommand = "echo"\n\n[hooks.state."other@m:hooks/hooks.json:stop:0:0"]\n' \
               'trusted_hash = "sha256:b"\n'
        (e.a / "config.toml").write_text(user, encoding="utf-8")
        quiet(cps.setup, REPO, e.a, ["core", "jev", "ruflo"], yes=True)
        with open(e.a / "config.toml", "a", encoding="utf-8") as f:
            f.write('\n[profiles.p]\nmodel = "x"\n')  # added after setup, at the end, after our tables
        rc, out = quiet(cps.uninstall, e.a)
        self.assertEqual(rc, 0, out)
        t = e.toml(e.a)
        for kept in ('model = "o3"', "[mcp_servers.mine]", "other@m:hooks", "[profiles.p]"):
            self.assertIn(kept, t)
        self.assertNotIn("dryas", t)

    def test_codex_moved_end_marker_after_trust(self):
        # real 0.162.1: Codex writes [hooks.state] + the trust tables inside our markers (before the end marker)
        e = Env(self, py3=False)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        cfg = e.a / "config.toml"
        t = cfg.read_text(encoding="utf-8").replace(cps.TOML_END + "\n", "")
        t = t.replace('[hooks.state."', '[hooks.state]\n\n[hooks.state."', 1) + cps.TOML_END + "\n"
        cfg.write_text(t, encoding="utf-8")
        self.assertIn("[mcp_servers.jev]", t)
        rc, out = quiet(cps.uninstall, e.a)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("hooks.state", e.toml(e.a))
        self.assertNotIn("mcp_servers.jev", e.toml(e.a))
        self.assertNotIn("dryas", e.toml(e.a))

    def test_no_record_drops_stale_account_entry(self):
        e = Env(self)
        cps.ps.add_account(e.root, e.a, "codex_dirs")
        cps.ps.add_account(e.root, e.b, "codex_dirs")
        rc, out = quiet(cps.uninstall, e.a)
        self.assertEqual(rc, 0)
        acc = json.loads((e.root / "accounts.json").read_text(encoding="utf-8"))
        self.assertEqual(acc["codex_dirs"], [str(cps.ps.norm(e.b))])

    def test_bad_toml_body_type_is_a_lost_body(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, ["core"], yes=True)
        rec = json.loads((e.a / cps.RECORD).read_text(encoding="utf-8"))
        rec["toml_body"] = 5
        (e.a / cps.RECORD).write_text(json.dumps(rec), encoding="utf-8")
        rc, out = quiet(cps.uninstall, e.a)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("dryas", e.toml(e.a))  # the markers still say which tables are ours

    def test_config_write_error_keeps_record(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        real, target = open, os.path.realpath(e.a / "config.toml")  # codex_home resolves: /var is /private/var on macOS

        def fake_open(f, mode="r", *a, **k):
            if "w" in mode and os.path.realpath(f) == target:
                raise PermissionError("read-only")
            return real(f, mode, *a, **k)
        with mock.patch("builtins.open", fake_open):
            rc, out = quiet(cps.uninstall, e.a)
        self.assertEqual(rc, 1)
        self.assertIn("read-only", out)
        self.assertTrue((e.a / cps.RECORD).exists())
        self.assertIn(str(cps.ps.norm(e.a)), json.loads((e.root / "accounts.json").read_text(encoding="utf-8"))["codex_dirs"])
        rc, out = quiet(cps.uninstall, e.a)  # re-run resumes
        self.assertEqual(rc, 0, out)
        self.assertNotIn("hooks.state", e.toml(e.a))

    def test_changed_table_left_with_warning(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, ["core"], yes=True)
        cfg = e.a / "config.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("enabled = false", "enabled = true"), encoding="utf-8")
        rc, out = quiet(cps.uninstall, e.a)
        self.assertEqual(rc, 0)
        self.assertIn("was changed after Dryas setup wrote it", out)
        t = e.toml(e.a)
        self.assertIn("enabled = true", t)
        self.assertNotIn(cps.TOML_START, t)  # no markers left to claim it later

    def test_resume_after_marketplace_already_removed(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        cps.di.run(["codex", "plugin", "marketplace", "remove", cps.MARKET], env=dict(os.environ, CODEX_HOME=str(e.a)))
        n = len(e.calls())
        rc, out = quiet(cps.uninstall, e.a)
        self.assertEqual(rc, 0, out)
        self.assertNotIn(["codex", "plugin", "marketplace", "remove", cps.MARKET], e.calls()[n:])
        self.assertFalse((e.a / cps.RECORD).exists())

    def test_unreadable_record_kept(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        (e.a / cps.RECORD).write_text("[1]", encoding="utf-8")
        n = len(e.calls())
        rc, out = quiet(cps.uninstall, e.a)
        self.assertEqual(rc, 1)
        self.assertIn("nothing removed", out)
        self.assertTrue((e.a / cps.RECORD).exists())
        self.assertEqual(e.calls()[n:], [])

    def test_unreadable_accounts_left(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        (e.root / "accounts.json").write_text("{bad", encoding="utf-8")
        rc, out = quiet(cps.uninstall, e.a)
        self.assertEqual(rc, 0)
        self.assertIn("unreadable", out)
        self.assertEqual((e.root / "accounts.json").read_text(encoding="utf-8"), "{bad")

    def test_codex_cache_dir_of_ours_removed(self):
        e = Env(self)
        quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        quiet(cps.uninstall, e.a)
        self.assertFalse((e.a / "plugins" / "cache" / cps.MARKET).exists())

    def test_legacy_copy_install_removed_live_claude_copy_kept(self):
        e = Env(self)
        with mock.patch.object(cps.migrate, "is_copy_install", lambda cd: True):
            cd = legacy_codex.legacy(e.home, e.a, claude_copy=True)
            rc, out = quiet(cps.uninstall, e.a)
        self.assertEqual(rc, 0, out)
        self.assertFalse((e.a / ct.RECORD).exists())
        self.assertEqual((e.a / "AGENTS.md").read_text(encoding="utf-8"), "mine\n")
        self.assertTrue((cd / di.RECORD).exists())  # the live Claude copy install is not touched
        self.assertTrue((cd / "jev" / "chain.py").exists())

    def test_legacy_runtime_copy_state_moved_not_deleted(self):
        e = Env(self)
        cd = legacy_codex.legacy(e.home, e.a)
        (cd / "jev" / "logs").mkdir()
        (cd / "jev" / "logs" / "jev.jsonl").write_text('{"a": 1}\n', encoding="utf-8")
        rc, out = quiet(cps.uninstall, e.a)
        self.assertEqual(rc, 0, out)
        self.assertFalse((cd / di.RECORD).exists())
        self.assertEqual((e.root / "jev" / "logs" / "jev.jsonl").read_text(encoding="utf-8"), '{"a": 1}\n')

    def test_unreadable_legacy_stops(self):
        e = Env(self)
        legacy_codex.legacy(e.home, e.a)
        (e.a / ct.RECORD).write_text("[]", encoding="utf-8")
        rc, out = quiet(cps.uninstall, e.a)
        self.assertEqual(rc, 1)
        self.assertIn("nothing changed", out)
        self.assertEqual((e.a / "AGENTS.md").read_text(encoding="utf-8"), legacy_codex.AGENTS)

    def test_created_codex_home_removed_only_when_empty(self):
        for extra in (False, True):
            e = Env(self)
            e.a.mkdir()
            (e.a / cps.RECORD).write_text(json.dumps({"dir_created": True, "trusted": {}}), encoding="utf-8")
            if extra:
                (e.a / "history.jsonl").write_text("x", encoding="utf-8")
            with mock.patch.object(cps, "_say_run", lambda *a: 0):
                self.assertEqual(quiet(cps.uninstall, e.a)[0], 0)
            self.assertEqual(e.a.exists(), extra)


class LegacyProblemTest(unittest.TestCase):
    def test_element_types_checked(self):
        bad = {"skills": [1], "skill_backups": {"orchestrate": 3}, "hooks": {"hooks": [["PreToolUse", "x"]]},
               "mcp": {"jev": 1}}
        for k, v in bad.items():
            e = Env(self)
            legacy_codex.legacy(e.home, e.a)
            rec = json.loads((e.a / ct.RECORD).read_text(encoding="utf-8"))
            rec[k] = v
            (e.a / ct.RECORD).write_text(json.dumps(rec), encoding="utf-8")
            self.assertIn(str(e.a / ct.RECORD), cps.legacy_problem(e.a, e.home), k)

    def test_skill_name_must_stay_in_skills_dir(self):
        for name in ("..", "a/b", "", ".", "a\\b", "c:x", "skill.", "skill ", ".hidden", "-x", "a b"):
            e = Env(self)
            legacy_codex.legacy(e.home, e.a)
            rec = json.loads((e.a / ct.RECORD).read_text(encoding="utf-8"))
            rec["skills"] = [name]
            (e.a / ct.RECORD).write_text(json.dumps(rec), encoding="utf-8")
            self.assertTrue(cps.legacy_problem(e.a, e.home), name)

    def test_good_record_passes(self):
        e = Env(self)
        legacy_codex.legacy(e.home, e.a)
        self.assertEqual(cps.legacy_problem(e.a, e.home), "")

    def test_any_uninstall_error_is_a_legacy_error(self):
        e = Env(self)
        legacy_codex.legacy(e.home, e.a)

        def boom(*a, **k):
            raise KeyError("x")
        with mock.patch.object(ct, "uninstall_codex", boom):
            with self.assertRaises(cps.LegacyError):
                quiet(cps.migrate_legacy, e.a, e.home)
        self.assertTrue((e.a / ct.RECORD).exists())


if __name__ == "__main__":
    unittest.main()
