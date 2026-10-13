"""--uninstall / --purge list what they remove and ask (bypassed by --yes); third-party installs are recorded by
setup and offered for removal (--keep-extras leaves them); the node/npm preflight message names --no-ruflo."""
import io, json, os, sys, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import dryas_install as di
import platform_util as pu
import plugin_setup as ps
import run_cmd
from test_plugin_setup import Env, _out
from test_run_cmd import MainStubs
REPO = HERE.parents[1]
TABLE = json.loads((HERE.parent / "components.json").read_text(encoding="utf-8"))


def _main(*args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_cmd.main(list(args))
    return rc, buf.getvalue()


def _record(cd, **extra):
    cd.mkdir(parents=True, exist_ok=True)
    rec = dict({"components": ["core", "jev"], "settings": {"env": {"DRYAS_PY": "x"}}, "settings_created": True}, **extra)
    (cd / ps.RECORD).write_text(json.dumps(rec), encoding="utf-8")
    (cd / "settings.json").write_text(json.dumps({"env": {"DRYAS_PY": "x"}}), encoding="utf-8")


class NodeMessageTest(unittest.TestCase):
    def setUp(self):
        self.orig = (pu.which, pu.space_free)
        pu.space_free = lambda p: str(p)
        import codex_plugin_setup as cps
        for p in (mock.patch.object(run_cmd, "codex_version", lambda: cps.MIN_CODEX),
                  mock.patch.object(cps, "python3_ok", lambda: True), mock.patch.object(pu, "IS_WINDOWS", False)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        pu.which, pu.space_free = self.orig

    def test_only_node_missing_names_no_ruflo(self):
        pu.which = lambda n: "" if n in ("node", "npm") else "/bin/" + n
        for harness, hint in (("claude", "Claude Code then runs without Ruflo"), ("codex", "Ruflo MCP server"),
                              ("both", "Codex without the Ruflo MCP server")):
            probs = run_cmd.preflight(["core", "ruflo"], harness, Path("/x/.claude"))
            self.assertEqual(len(probs), 1, probs)
            self.assertIn("Missing: node npm", probs[0])
            self.assertIn("Only Ruflo needs them", probs[0])
            self.assertIn("--no-ruflo", probs[0])
            self.assertIn(hint, probs[0])
        self.assertEqual(run_cmd.preflight(["core", "jev"], "claude", Path("/x/.claude")), [])

    def test_other_tools_missing_keeps_plain_message(self):
        pu.which = lambda n: "" if n in ("node", "git") else "/bin/" + n
        probs = run_cmd.preflight(["core", "ruflo"], "claude", Path("/x/.claude"))
        self.assertIn("Missing: git node", probs[0])
        self.assertNotIn("--no-ruflo", probs[0])


class UninstallConfirmTest(unittest.TestCase):
    def test_uninstall_lists_and_asks(self):
        st = MainStubs(self)
        cd = st.tmp / "acct"
        _record(cd)
        asked = []
        with mock.patch.object(di, "confirm", lambda p: asked.append(p) or False):
            rc, out = _main("--uninstall", "--claude-dir", str(cd))
        self.assertEqual((rc, st.steps()), (1, []))
        self.assertEqual(asked, ["Proceed?"])
        self.assertIn("--uninstall will remove:", out)
        self.assertIn("claude plugin uninstall dryas@dryas-workflow", out)
        self.assertIn("%s (Dryas created it)" % (cd.resolve() / "settings.json"), out)
        self.assertIn(str(cd.resolve() / ps.RECORD), out)
        self.assertIn("nothing removed", out)
        with mock.patch.object(di, "confirm", lambda p: True):
            rc, out = _main("--uninstall", "--claude-dir", str(cd))
        self.assertEqual((rc, st.steps()), (0, ["ps.uninstall"]))
        self.assertEqual(st.call("ps.uninstall"), ((cd.resolve(), False), {"extras": []}))

    def test_purge_lists_data_root_paths(self):
        st = MainStubs(self)
        cd = st.tmp / "acct"
        _record(cd)
        root = st.tmp / "data"
        (root / "jev" / "logs").mkdir(parents=True)
        (root / "docs").mkdir()
        (root / "docs" / "dryas-local.md").write_text("mine", encoding="utf-8")
        (root / "docs" / "dryas-workflow.md").write_text("ref", encoding="utf-8")
        (root / "chain.local.json").write_text("{}", encoding="utf-8")
        with mock.patch.object(di, "confirm", lambda p: False):
            rc, out = _main("--uninstall", "--purge", "--claude-dir", str(cd))
        self.assertEqual(rc, 1)
        self.assertIn("with --purge", out)
        for p in (root / "jev", root / "chain.local.json", root / "docs" / "dryas-workflow.md"):
            self.assertIn(str(p.resolve()), out)
        self.assertIn("(kept: %s)" % (root.resolve() / "docs" / "dryas-local.md"), out)
        self.assertNotIn("  %s\n" % (root.resolve() / "docs" / "dryas-local.md"), out)

    def test_yes_skips_every_question(self):
        st = MainStubs(self)
        cd = st.tmp / "acct"
        _record(cd)
        with mock.patch.object(di, "confirm", lambda p: self.fail("asked despite --yes")):
            rc, out = _main("--uninstall", "--purge", "--claude-dir", str(cd), "--yes")
        self.assertEqual((rc, st.steps()), (0, ["ps.uninstall"]))
        self.assertIn("--uninstall will remove:", out)  # still listed

    def test_nothing_recorded_asks_nothing(self):
        st = MainStubs(self)
        with mock.patch.object(di, "confirm", lambda p: self.fail("asked with nothing to remove")):
            rc, out = _main("--uninstall", "--purge", "--claude-dir", str(st.tmp / "acct"))
        self.assertEqual((rc, st.steps()), (0, ["ps.uninstall"]))

    def test_codex_line_in_plan(self):
        st = MainStubs(self)
        import codex_plugin_setup as cps
        cdx = st.tmp / ".codex"
        cdx.mkdir()
        (cdx / cps.RECORD).write_text("{}", encoding="utf-8")
        with mock.patch.object(di, "confirm", lambda p: False):
            rc, out = _main("--uninstall", "--harness", "codex")
        self.assertEqual((rc, st.steps()), (1, []))
        self.assertIn("codex plugin remove dryas@dryas-workflow", out)
        self.assertIn(str(cdx), out)


class ExtrasTest(unittest.TestCase):
    def test_setup_records_thirdparty_and_uninstall_runs_confirmed_extras(self):
        e = Env(self)
        _out(lambda: self.assertEqual(ps.setup(REPO, e.a, ["core", "jev", "design"], yes=True, key="", flowobserve=False), 0))
        rec = json.loads((e.a / ps.RECORD).read_text(encoding="utf-8"))
        self.assertEqual(rec["thirdparty"], TABLE["design"]["commands"])
        _out(lambda: self.assertEqual(ps.setup(REPO, e.a, ["core", "jev", "design"], yes=True, key="", flowobserve=False), 0))
        rec = json.loads((e.a / ps.RECORD).read_text(encoding="utf-8"))
        self.assertEqual(rec["thirdparty"], TABLE["design"]["commands"])  # a re-run does not duplicate them
        want = [["claude", "plugin", "uninstall", "impeccable@impeccable"],
                ["claude", "plugin", "uninstall", "ui-ux-pro-max@ui-ux-pro-max-skill"]]
        self.assertEqual(ps.extras_commands(rec, last_account=True), want)
        self.assertEqual(ps.extras_marketplaces(rec), ["impeccable", "ui-ux-pro-max-skill"])
        before = len(e.calls())
        out = _out(lambda: self.assertEqual(ps.uninstall(e.a, purge=False, extras=want), 0))
        calls = [c[1:] for c in e.calls()[before:]]
        self.assertIn(["plugin", "uninstall", "impeccable@impeccable"], calls)
        self.assertIn(["plugin", "uninstall", "ui-ux-pro-max@ui-ux-pro-max-skill"], calls)
        self.assertEqual(calls[0], ["plugin", "uninstall", ps.ID, "--scope", "user", "--keep-data"])
        self.assertIn("claude plugin marketplace remove impeccable", out)  # marketplaces are never removed here
        self.assertNotIn(["plugin", "marketplace", "remove", "impeccable"], calls)
        self.assertFalse((e.a / ps.RECORD).exists())

    def test_uninstall_without_extras_prints_commands(self):
        e = Env(self)
        _out(lambda: ps.setup(REPO, e.a, ["core", "jev", "design"], yes=True, key="", flowobserve=False))
        before = len(e.calls())
        out = _out(lambda: ps.uninstall(e.a, purge=False))
        calls = [c[1:] for c in e.calls()[before:]]
        self.assertEqual(len(calls), 1)  # only the dryas plugin uninstall
        self.assertIn("kept the third-party plugins setup installed; to remove them:", out)
        self.assertIn("claude plugin uninstall impeccable@impeccable", out)

    def test_npm_only_for_last_account(self):
        rec = {"thirdparty": TABLE["ruflo"]["commands"] + [["npm", "install", "-g", "ruflo"]]}
        last = ps.extras_commands(rec, last_account=True)
        self.assertEqual(last[-1], ["npm", "uninstall", "-g", "ruflo"])
        self.assertEqual(last.count(["npm", "uninstall", "-g", "ruflo"]), 1)
        self.assertEqual([c[3] for c in last[:-1]], ["ruflo-core@ruflo", "ruflo-swarm@ruflo", "ruflo-testgen@ruflo",
                                                     "ruflo-jujutsu@ruflo"])
        self.assertEqual(ps.extras_commands(rec, last_account=False), last[:-1])
        self.assertEqual(ps.extras_marketplaces(rec), ["ruflo"])
        self.assertEqual(ps.extras_commands({"thirdparty": "junk"}, True), [])
        self.assertEqual(ps.extras_commands({}, True), [])

    def test_failed_thirdparty_run_records_what_ran(self):
        e = Env(self)
        import fakecli
        fakecli.make(e.bin, "claude", e.log, epilogue=e.epilogue, plugin_list=True, fail=["plugin marketplace"])
        # the dryas marketplace add fails first: setup stops before thirdparty; record what thirdparty ran directly
        ran = []
        with mock.patch.object(di, "run", lambda argv, cwd=None, env=None: 1 if argv[3:4] == ["ui-ux-pro-max@ui-ux-pro-max-skill"] else 0):
            rc = _out(lambda: run_cmd.thirdparty(["design"], True, e.a, ran=ran))
        self.assertEqual(ran, TABLE["design"]["commands"][:3])

    def test_main_offers_extras_and_keep_extras(self):
        st = MainStubs(self)
        cd = st.tmp / "acct"
        _record(cd, thirdparty=TABLE["design"]["commands"] + [["npm", "install", "-g", "ruflo"]])
        want = [["claude", "plugin", "uninstall", "impeccable@impeccable"],
                ["claude", "plugin", "uninstall", "ui-ux-pro-max@ui-ux-pro-max-skill"], ["npm", "uninstall", "-g", "ruflo"]]
        asked = []
        with mock.patch.object(di, "confirm", lambda p: asked.append(p) or p == "Proceed?"):
            rc, out = _main("--uninstall", "--claude-dir", str(cd))
        self.assertEqual(asked, ["Proceed?", "Remove them too?"])
        self.assertEqual(st.call("ps.uninstall"), ((cd.resolve(), False), {"extras": []}))
        self.assertIn("Third-party tools setup installed", out)
        self.assertIn("npm uninstall -g ruflo", out)
        st.log.clear()
        with mock.patch.object(di, "confirm", lambda p: True):
            _main("--uninstall", "--claude-dir", str(cd))
        self.assertEqual(st.call("ps.uninstall")[1], {"extras": want})
        st.log.clear()
        _main("--uninstall", "--claude-dir", str(cd), "--yes")
        self.assertEqual(st.call("ps.uninstall")[1], {"extras": want})
        st.log.clear()
        with mock.patch.object(di, "confirm", lambda p: self.fail("asked about extras despite --keep-extras") if "them" in p else True):
            rc, out = _main("--uninstall", "--claude-dir", str(cd), "--keep-extras")
        self.assertEqual(st.call("ps.uninstall")[1], {"extras": []})
        self.assertNotIn("Remove them too?", out)

    def test_npm_kept_while_another_account_listed(self):
        st = MainStubs(self)
        cd = st.tmp / "acct"
        _record(cd, thirdparty=[["npm", "install", "-g", "ruflo"]])
        root = st.tmp / "data"
        root.mkdir()
        (root / "accounts.json").write_text(json.dumps({"claude_dirs": [str(cd.resolve()), str(st.tmp / "other")]}), encoding="utf-8")
        _main("--uninstall", "--claude-dir", str(cd), "--yes")
        self.assertEqual(st.call("ps.uninstall")[1], {"extras": []})
        (root / "accounts.json").write_text(json.dumps({"claude_dirs": [str(cd.resolve())], "codex_dirs": [str(st.tmp / ".codex")]}),
                                            encoding="utf-8")
        st.log.clear()
        _main("--uninstall", "--claude-dir", str(cd), "--yes")  # Codex still uses ruflo
        self.assertEqual(st.call("ps.uninstall")[1], {"extras": []})
        st.log.clear()
        _main("--uninstall", "--claude-dir", str(cd), "--harness", "both", "--yes")  # that Codex home goes in this run
        self.assertEqual(st.call("ps.uninstall")[1], {"extras": [["npm", "uninstall", "-g", "ruflo"]]})


if __name__ == "__main__":
    unittest.main()
