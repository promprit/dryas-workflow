import json, os, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import dryas_install as di
import plugin_setup as ps
import rea_setup as rs
import run_cmd
from test_plugin_setup import Env, REPO, COMPS, _out

RM = ["claude", "mcp", "remove", "--scope", "user", "rea"]


class ReaWiringTest(unittest.TestCase):
    def setUp(self):
        self.orig = (rs.install, di.run)
        self.calls = []

    def tearDown(self):
        rs.install, di.run = self.orig

    def test_extras_offer_mcp_remove(self):
        self.assertIn(RM, ps.extras_commands({"rea": {"version": "6.7.0", "client": "claude_code", "skill_dir": None}}, False))
        self.assertNotIn(RM, ps.extras_commands({}, False))
        self.assertNotIn(RM, ps.extras_commands({"rea": "junk"}, False))

    def test_rea_step_records_on_success(self):
        rs.install = lambda client, env, yes, dry_run, prior=None: self.calls.append((client, env, yes, dry_run)) or \
            {"version": "6.7.0", "client": client, "skill_dir": "/x/skills/reverse-engineer-anything"}
        rec = {"components": ["core"]}
        cd = Path(tempfile.mkdtemp())
        ps.rea_step(cd, ["core", "rea"], rec, yes=True, dry=False)
        self.assertEqual(rec["rea"]["skill_dir"], "/x/skills/reverse-engineer-anything")
        self.assertEqual(self.calls[0][0], "claude_code")
        self.assertEqual(self.calls[0][1], ps.child_env(cd))
        self.assertNotIn("thirdparty", rec)

    def test_rea_step_failure_drops_component(self):
        rs.install = lambda *a, **k: None
        rec = {}
        comps = ["core", "rea"]
        ps.rea_step(Path(tempfile.mkdtemp()), comps, rec, yes=True, dry=False)
        self.assertNotIn("rea", rec)
        self.assertNotIn("rea", comps)

    def test_rea_step_not_selected(self):
        rs.install = lambda *a, **k: self.fail("must not run")
        rec = {}
        ps.rea_step(Path(tempfile.mkdtemp()), ["core"], rec, yes=True, dry=False)
        self.assertEqual(rec, {})

    def test_default_dir_unsets_config_dir(self):
        saved = os.environ.get("CLAUDE_CONFIG_DIR")
        try:
            for value in (None, str(Path.home() / ".claude-other")):
                if value is None:
                    os.environ.pop("CLAUDE_CONFIG_DIR", None)
                else:
                    os.environ["CLAUDE_CONFIG_DIR"] = value
                self.assertNotIn("CLAUDE_CONFIG_DIR", ps.child_env(Path.home() / ".claude"), value)
            self.assertEqual(ps.child_env(Path.home() / ".claude-x")["CLAUDE_CONFIG_DIR"], str(Path.home() / ".claude-x"))
        finally:
            if saved is None:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = saved

    def test_remove_skill_dir(self):
        di.run = lambda argv, cwd=None, env=None: 0
        with tempfile.TemporaryDirectory() as t0:
            t = os.path.realpath(t0)
            d = Path(t) / "skills" / "reverse-engineer-anything"
            d.mkdir(parents=True)
            ps._remove_extras(Path(t), {"rea": {"skill_dir": str(d)}}, [RM])
            self.assertFalse(d.exists())

    def test_remove_skill_dir_refuses_unsafe(self):
        di.run = lambda argv, cwd=None, env=None: 0
        with tempfile.TemporaryDirectory() as t0:
            t = os.path.realpath(t0)
            real = Path(t) / "real" / "reverse-engineer-anything"
            real.mkdir(parents=True)
            link = Path(t) / "skills" / "reverse-engineer-anything"
            link.parent.mkdir()
            os.symlink(str(real), str(link))
            other = Path(t) / "skills" / "keep-me"
            other.mkdir()
            for p in (str(link), str(other)):
                ps._remove_extras(Path(t), {"rea": {"skill_dir": p}}, [RM])
            self.assertTrue(real.exists() and other.exists() and os.path.islink(str(link)))

    PRIOR = {"version": "6.7.0", "client": "claude_code", "skill_dir": "/old/reverse-engineer-anything"}

    def test_rea_step_saves_record_immediately(self):
        rs.install = lambda *a, **k: {"version": "6.7.0", "client": "claude_code", "skill_dir": "/x"}
        with tempfile.TemporaryDirectory() as t:
            rp = Path(t) / "rec.json"
            rec = {}
            ps.rea_step(Path(t), ["core", "rea"], rec, True, False, rec_path=rp)
            self.assertEqual(json.loads(rp.read_text())["rea"]["skill_dir"], "/x")

    def test_rea_step_keeps_prior_on_decline(self):
        rs.install = lambda *a, **k: None
        rec = {"rea": dict(self.PRIOR)}
        comps = ["core", "rea"]
        ps.rea_step(Path(tempfile.mkdtemp()), comps, rec, True, False)
        self.assertIn("rea", comps)
        self.assertEqual(rec["rea"], self.PRIOR)

    def test_rea_step_passes_prior(self):
        seen = []
        rs.install = lambda client, env, yes, dry_run, prior=None: seen.append(prior)
        ps.rea_step(Path(tempfile.mkdtemp()), ["rea"], {"rea": dict(self.PRIOR)}, True, False)
        ps.rea_step(Path(tempfile.mkdtemp()), ["rea"], {"rea": "junk"}, True, False)
        self.assertEqual(seen, [self.PRIOR, None])

    def _dry(self, node):
        e = Env(self)
        orig = rs.node_ok
        rs.node_ok = lambda *a, **k: node
        try:
            return _out(lambda: ps.setup(REPO, e.home / ".claude", COMPS + ["rea"], yes=True, key="", flowobserve=False, dry=True))
        finally:
            rs.node_ok = orig

    def test_dry_run_prints_rea(self):
        out = self._dry(None)
        self.assertEqual(out.count("would run: npx -y rea-agents@6.7.0 setup"), 1)

    def test_dry_run_honours_node_check(self):
        out = self._dry(rs.NODE_WARNING)
        self.assertIn(rs.NODE_WARNING, out)
        self.assertNotIn("would run: npx -y rea-agents", out)

    def test_remove_skill_outside_account_kept(self):
        di.run = lambda argv, cwd=None, env=None: 0
        with tempfile.TemporaryDirectory() as t0, tempfile.TemporaryDirectory() as o0:
            cd, d = Path(os.path.realpath(t0)), Path(os.path.realpath(o0)) / "reverse-engineer-anything"
            d.mkdir()
            ps._remove_extras(cd, {"rea": {"skill_dir": str(d)}}, [RM])
            self.assertTrue(d.exists())

    def test_on_demand_uninstall_skips_absent_user_entry_but_removes_skill(self):
        ran = []
        di.run = lambda argv, cwd=None, env=None: ran.append(argv) or 0
        with tempfile.TemporaryDirectory() as t0:
            t = os.path.realpath(t0)
            d = Path(t) / "skills" / "reverse-engineer-anything"
            d.mkdir(parents=True)
            (Path(t) / ".claude.json").write_text("{}", encoding="utf-8")  # on demand: no user-scope rea
            ps._remove_extras(Path(t), {"rea": {"skill_dir": str(d)}}, [RM])
            self.assertFalse(d.exists())
        self.assertNotIn(RM, ran)

    def test_user_scoped_uninstall_still_removes_entry(self):
        ran = []
        di.run = lambda argv, cwd=None, env=None: ran.append(argv) or 0
        with tempfile.TemporaryDirectory() as t0:
            t = os.path.realpath(t0)
            (Path(t) / ".claude.json").write_text('{"mcpServers": {"rea": {}}}', encoding="utf-8")
            ps._remove_extras(Path(t), {"rea": {"skill_dir": None}}, [RM])
        self.assertIn(RM, ran)

    def test_uninstall_listing_names_what_on_demand_removes(self):
        with tempfile.TemporaryDirectory() as t0:
            t = Path(os.path.realpath(t0))
            (t / ".claude.json").write_text("{}", encoding="utf-8")
            self.assertIn("skill folder", ps.shown_extra(t, RM))
            self.assertNotIn("claude mcp remove", ps.shown_extra(t, RM))
            (t / ".claude.json").write_text('{"mcpServers": {"rea": {}}}', encoding="utf-8")
            self.assertIn("claude mcp remove --scope user rea", ps.shown_extra(t, RM))
            other = ["claude", "plugin", "uninstall", "x@y"]
            self.assertEqual(ps.shown_extra(t, other), ps.shown(t, other))

    def test_keep_extras_removes_nothing(self):
        di.run = lambda argv, cwd=None, env=None: self.fail("ran %s" % argv)
        with tempfile.TemporaryDirectory() as t0:
            t = os.path.realpath(t0)
            d = Path(t) / "skills" / "reverse-engineer-anything"
            d.mkdir(parents=True)
            ps._remove_extras(Path(t), {"rea": {"skill_dir": str(d)}}, [])
            self.assertTrue(d.exists())

    def test_off_list_excludes_rea(self):
        self.assertIn("rea", run_cmd.NO_STAGES)
        src = (HERE.parent / "plugin_setup.py").read_text(encoding="utf-8")
        self.assertIn("NO_STAGES", src)

    def test_no_global_uninstall(self):
        for c in ps.extras_commands({"rea": {"skill_dir": None}}, True):
            self.assertNotEqual(c[:2], ["rea", "uninstall"])
            self.assertNotIn("rea-agents@6.7.0", c)


if __name__ == "__main__":
    unittest.main()
