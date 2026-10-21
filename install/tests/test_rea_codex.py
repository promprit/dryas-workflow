import json, os, shutil, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import codex_plugin_setup as cps
import dryas_install as di
import rea_setup
import run_cmd
from test_codex_plugin_setup import Env, REPO, quiet
from test_run_cmd import MainStubs

COMPS = ["core", "jev", "rea"]
REMOVE = ["codex", "mcp", "remove", "rea"]


def entry(skill_dir=None):
    return {"version": "6.7.0", "client": "codex", "skill_dir": skill_dir}


def record(cdx):
    return json.loads((cdx / cps.RECORD).read_text(encoding="utf-8"))


class ReaCodexTest(unittest.TestCase):
    def setup_with(self, e, cdx, result, comps=COMPS):
        seen = []

        def fake(client, env, yes, dry, prior=None):
            seen.append((client, env))
            return result
        with mock.patch.object(rea_setup, "install", fake):
            rc, _ = quiet(cps.setup, REPO, cdx, comps, yes=True)
        self.assertEqual(rc, 0)
        return seen

    def test_setup_runs_codex_client(self):
        e = Env(self)
        seen = self.setup_with(e, e.a, entry())
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], "codex")
        self.assertEqual(seen[0][1]["CODEX_HOME"], str(cps.ps.norm(e.a)))
        rec = record(e.a)
        self.assertEqual(rec["rea"]["client"], "codex")
        self.assertIn("rea", rec["components"])
        self.assertEqual(cps.rea_extras(e.a), [REMOVE])

    def test_setup_failure_not_recorded(self):
        e = Env(self)
        self.setup_with(e, e.a, None)
        rec = record(e.a)
        self.assertNotIn("rea", rec)
        self.assertNotIn("rea", rec["components"])
        self.assertEqual(cps.rea_extras(e.a), [])

    def test_shared_comps_not_mutated(self):
        e = Env(self)
        comps = list(COMPS)
        self.setup_with(e, e.a, None, comps)
        self.assertIn("rea", comps)

    def uninstall_with(self, e, skill_dir):
        self.setup_with(e, e.a, entry(skill_dir))
        ran = []
        real = di.run

        def run(argv, **k):
            if argv[:2] == ["codex", "mcp"]:
                ran.append((argv, k.get("env", {}).get("CODEX_HOME")))
                return 0
            return real(argv, **k)
        with mock.patch.object(di, "run", run):
            rc, out = quiet(cps.uninstall, e.a, extras=cps.rea_extras(e.a))
        self.assertEqual(rc, 0)
        return ran, out

    def test_uninstall_offers_codex_remove(self):
        e = Env(self)
        sd = e.a / "skills" / rea_setup.SKILL_NAME
        sd.mkdir(parents=True)
        (sd / "SKILL.md").write_text("x", encoding="utf-8")
        ran, _ = self.uninstall_with(e, str(sd))
        self.assertEqual(ran, [(REMOVE, str(cps.ps.norm(e.a)))])
        self.assertFalse(sd.exists())

    def test_uninstall_keeps_unsafe_skill_dir(self):
        e = Env(self)
        sd = e.a / "precious"
        sd.mkdir(parents=True)
        _, out = self.uninstall_with(e, str(sd))
        self.assertTrue(sd.exists())
        self.assertIn("remove it by hand", out)

    def test_decline_keeps_prior_record(self):
        e = Env(self)
        self.setup_with(e, e.a, entry("/old/x"))
        seen = []

        def fake(client, env, yes, dry, prior=None):
            seen.append(prior)
        with mock.patch.object(rea_setup, "install", fake):
            quiet(cps.setup, REPO, e.a, COMPS, yes=True)
        rec = record(e.a)
        self.assertEqual(seen, [entry("/old/x")])
        self.assertEqual(rec["rea"], entry("/old/x"))
        self.assertIn("rea", rec["components"])

    def test_uninstall_keeps_skill_outside_home(self):
        e = Env(self)
        sd = e.t / "agents" / "skills" / rea_setup.SKILL_NAME
        sd.mkdir(parents=True)
        _, out = self.uninstall_with(e, str(sd))
        self.assertTrue(sd.exists())
        self.assertIn("remove it by hand", out)

    def test_dry_run_prints_rea(self):
        e = Env(self)
        rc, out = quiet(cps.setup, REPO, e.a, COMPS, yes=True, dry=True)
        self.assertEqual(rc, 0)
        self.assertIn("would run: npx -y rea-agents@6.7.0 setup --client codex", out)

    def test_uninstall_without_extras_runs_nothing(self):
        e = Env(self)
        self.setup_with(e, e.a, entry())
        with mock.patch.object(di, "run", side_effect=AssertionError("no extras")) as r:
            r.side_effect = lambda argv, **k: 0 if argv[:2] != ["codex", "mcp"] else self.fail("mcp remove ran")
            rc, _ = quiet(cps.uninstall, e.a)
        self.assertEqual(rc, 0)

    def test_keep_extras_codex(self):
        st = MainStubs(self)
        cdx = st.tmp / "cx"
        cdx.mkdir()
        (cdx / cps.RECORD).write_text(json.dumps({"components": ["core"], "rea": entry()}), encoding="utf-8")
        ran = []
        with mock.patch.object(di, "run", lambda argv, **k: ran.append(argv) or 0):
            quiet(run_cmd.main, ["--uninstall", "--harness", "codex", "--keep-extras", "--yes", "--codex-dir", str(cdx)])
        a, k = st.call("cps.uninstall")
        self.assertEqual(k.get("extras"), [])
        self.assertNotIn(REMOVE, ran)

    def test_yes_passes_codex_remove(self):
        st = MainStubs(self)
        cdx = st.tmp / "cx"
        cdx.mkdir()
        (cdx / cps.RECORD).write_text(json.dumps({"components": ["core"], "rea": entry()}), encoding="utf-8")
        quiet(run_cmd.main, ["--uninstall", "--harness", "codex", "--yes", "--codex-dir", str(cdx)])
        a, k = st.call("cps.uninstall")
        self.assertEqual(k.get("extras"), [REMOVE])


if __name__ == "__main__":
    unittest.main()
