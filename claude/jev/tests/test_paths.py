# claude/jev/tests/test_paths.py
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths

HOME = os.path.expanduser("~")
CLEAN = {k: v for k, v in os.environ.items()
         if not k.startswith("JEV_") and k not in ("DRYAS_DATA_ROOT", "CLAUDE_CONFIG_DIR", "CLAUDE_PLUGIN_ROOT", "DRYAS_PY")}


class PathsTest(unittest.TestCase):
    def test_defaults(self):
        with mock.patch.dict(os.environ, CLEAN, clear=True):
            root = os.path.join(HOME, ".dryas")
            self.assertEqual(paths.data_root(), root)
            self.assertEqual(paths.log_dir(), os.path.join(root, "jev", "logs"))
            self.assertEqual(paths.thresholds_file(), os.path.join(root, "jev", "thresholds.json"))
            self.assertEqual(paths.handoff_dir(), os.path.join(root, "jev", "handoff"))
            self.assertEqual(paths.compact_dir(), os.path.join(root, "jev", "compact"))
            self.assertEqual(paths.chain_local(), os.path.join(root, "chain.local.json"))
            self.assertEqual(paths.accounts_file(), os.path.join(root, "accounts.json"))
            self.assertEqual(paths.ruflo_dir(), os.path.join(root, "ruflo"))
            self.assertEqual(paths.projects_dir(), os.path.join(HOME, ".claude", "projects"))
            self.assertEqual(paths.python(), sys.executable)
            self.assertTrue(os.path.isfile(os.path.join(paths.plugin_root(), "jev", "paths.py")))

    def test_data_root_override(self):
        d = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, dict(CLEAN, DRYAS_DATA_ROOT=d), clear=True):
            self.assertEqual(paths.log_dir(), os.path.join(d, "jev", "logs"))
            self.assertEqual(paths.chain_local(), os.path.join(d, "chain.local.json"))

    def test_jev_overrides_win(self):
        env = dict(CLEAN, DRYAS_DATA_ROOT="/r", JEV_LOG_DIR="/l", JEV_THRESHOLDS="/t.json", JEV_HANDOFF_DIR="/h",
                   JEV_COMPACT_DIR="/c", JEV_PROJECTS_DIR="/p", JEV_CHAIN_LOCAL="/cl.json")
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual((paths.log_dir(), paths.thresholds_file(), paths.handoff_dir(), paths.compact_dir(),
                              paths.projects_dir(), paths.chain_local()),
                             ("/l", "/t.json", "/h", "/c", "/p", "/cl.json"))

    def test_projects_dir_follows_config_dir(self):
        with mock.patch.dict(os.environ, dict(CLEAN, CLAUDE_CONFIG_DIR="/acct/team"), clear=True):
            self.assertEqual(paths.projects_dir(), os.path.join("/acct/team", "projects"))

    def test_plugin_root_and_python_from_env(self):
        with mock.patch.dict(os.environ, dict(CLEAN, CLAUDE_PLUGIN_ROOT="/plug", DRYAS_PY="/py"), clear=True):
            self.assertEqual((paths.plugin_root(), paths.python()), ("/plug", "/py"))


class ModulesUsePathsTest(unittest.TestCase):
    """Every state path in jev/ comes from paths.py (no hardcoded ~/.claude/jev)."""

    def test_no_hardcoded_claude_jev(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        hits = []
        for n in sorted(os.listdir(here)):
            if n.endswith(".py") and n != "paths.py":
                with open(os.path.join(here, n), encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if "~/.claude/jev" in line or "~/.claude/projects\")" in line:
                            hits.append("%s:%d" % (n, i))
        self.assertEqual(hits, [])

    def test_modules_delegate(self):
        import compact_keep, context_watch, handoff, handoff_paths, jevlog, thresholds
        d = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, dict(CLEAN, DRYAS_DATA_ROOT=d), clear=True):
            self.assertEqual(jevlog.log_dir(), paths.log_dir())
            self.assertEqual(handoff_paths.handoff_dir(), paths.handoff_dir())
            self.assertEqual(compact_keep.compact_dir(), paths.compact_dir())
            self.assertEqual(handoff.projects_dir(), paths.projects_dir())
            self.assertEqual(context_watch._state_dir(), os.path.join(paths.handoff_dir(), ".warned"))
            self.assertEqual(thresholds.path(), paths.thresholds_file())


class ThresholdLayersTest(unittest.TestCase):
    """DEFAULTS <- shipped jev/thresholds.json <- user file; /tune writes only the user file."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, dict(CLEAN, DRYAS_DATA_ROOT=self.d), clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_shipped_defaults_apply_without_user_file(self):
        import thresholds
        self.assertIn("cd", thresholds.load()["gate"]["allowlist"])  # "cd" is only in the shipped file

    def test_set_value_creates_user_file_and_keeps_shipped(self):
        import json, thresholds
        thresholds.set_value("gate.min_confidence", 0.8)
        with open(paths.thresholds_file(), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"gate": {"min_confidence": 0.8}})
        th = thresholds.load()
        self.assertEqual(th["gate"]["min_confidence"], 0.8)
        self.assertIn("cd", th["gate"]["allowlist"])


if __name__ == "__main__":
    unittest.main()
