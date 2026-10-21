import json, os, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import dryas_install as di
import plugin_setup as ps
import rea_setup as rs
import run_cmd

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
        rs.install = lambda client, env, yes, dry_run: self.calls.append((client, env, yes, dry_run)) or \
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
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "skills" / "reverse-engineer-anything"
            d.mkdir(parents=True)
            ps._remove_extras(Path(t), {"rea": {"skill_dir": str(d)}}, [RM])
            self.assertFalse(d.exists())

    def test_remove_skill_dir_refuses_unsafe(self):
        di.run = lambda argv, cwd=None, env=None: 0
        with tempfile.TemporaryDirectory() as t:
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

    def test_keep_extras_removes_nothing(self):
        di.run = lambda argv, cwd=None, env=None: self.fail("ran %s" % argv)
        with tempfile.TemporaryDirectory() as t:
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
