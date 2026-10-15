import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import dryas_install as di
import plugin_setup as ps
import test_plugin_setup as tps

ROOT = HERE.parents[1]
HINT = "OPENROUTER_API_KEY in your shell profile"


class WreviewFixTest(unittest.TestCase):
    def test_orchestrate_allows_both_memory_tool_sets(self):
        fm = (ROOT / "claude/skills/orchestrate/SKILL.md").read_text(encoding="utf-8").split("---", 2)[1]
        for t in ("memory_search", "memory_store", "swarm_init"):
            self.assertIn("mcp__plugin_dryas_jev__" + t, fm)
            self.assertIn("mcp__plugin_ruflo-core_ruflo__" + t, fm)

    def test_yes_skips_legacy_items_dryas_did_not_install(self):
        cd = Path(tempfile.mkdtemp())
        (cd / "plugins").mkdir()
        (cd / "plugins" / "installed_plugins.json").write_text(
            json.dumps({"plugins": {"ruflo-core@ruflo": [{}]}}), encoding="utf-8")
        root = Path(tempfile.mkdtemp())
        p = mock.patch.object(ps, "data_root", lambda: root)
        p.start()
        self.addCleanup(p.stop)
        with mock.patch("shutil.which", lambda n: "/usr/bin/" + n):
            items = ps.legacy_items(cd, {}, last_account=True)
        self.assertTrue(any("ruflo-core@ruflo" in i[0] for i in items))
        with mock.patch.object(di, "run", side_effect=AssertionError("ran a user-installed item")):
            out = tps._out(lambda: self.assertEqual(ps.run_legacy(items, yes=True, cd=cd), 0))
        self.assertIn("claude plugin uninstall ruflo-core@ruflo", out)

    def _setup(self, providers):
        e = tps.Env(self)
        tps._patch_env(self, {k: "" for k in ("OPENROUTER_API_KEY", "DRYAS_OPENROUTER_KEY")})
        return tps._out(lambda: ps.setup(ROOT, e.a, tps.COMPS, yes=True, key="", flowobserve=False,
                                         providers=providers))

    def test_key_note_only_when_judge_is_jev(self):
        self.assertIn(HINT, self._setup({"judge": "jev"}))
        out = self._setup({"judge": "local"})
        self.assertNotIn(HINT, out)
        self.assertIn("local judge in use", out)


if __name__ == "__main__":
    unittest.main()
