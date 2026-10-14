import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import codex_plugin_setup as cps
import platform_util as pu
import plugin_setup as ps
import run_cmd

P = run_cmd.parse
UP_1X = ["core", "jev", "ruflo", "superpowers", "design", "pstack-picks"]


class SelectTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": d, "JEV_THRESHOLDS": os.path.join(d, "t.json")})
        p.start()
        self.addCleanup(p.stop)

    def test_fresh_defaults_owned_core(self):
        self.assertEqual(run_cmd.select(P([]), None), ["core", "jev", "memory", "design", "pstack-picks"])

    def test_with_flags_add_extras(self):
        self.assertEqual(run_cmd.select(P(["--with-ruflo", "--with-superpowers"]), None),
                         ["core", "jev", "memory", "ruflo", "superpowers", "design", "pstack-picks"])

    def test_upgrade_without_flags_keeps_extras_and_providers(self):
        comps = run_cmd.select(P([]), UP_1X)
        self.assertEqual(comps, UP_1X)  # memory stays off: Ruflo memory is kept
        pv = run_cmd.providers(P([]), comps, UP_1X)
        self.assertEqual(pv["memory"], "ruflo")
        self.assertIsNotNone(pv["judge"])  # the current judge.provider is recorded, never null

    def test_upgrade_of_no_jev_install_keeps_gates_off_until_judge_flag(self):
        rec = ["core", "design"]
        self.assertNotIn("jev", run_cmd.select(P([]), rec))
        self.assertIn("jev", run_cmd.select(P(["--judge", "local"]), rec))

    def test_aliases(self):
        a = P(["--no-jev"])
        self.assertIn("jev", run_cmd.select(a, None))
        self.assertEqual(run_cmd.providers(a, run_cmd.select(a, None), None)["judge"], "local")
        k = P(["--openrouter-key", "sk-x"])
        self.assertEqual(run_cmd.providers(k, run_cmd.select(k, None), None)["judge"], "jev")
        self.assertNotIn("design", run_cmd.select(P(["--no-design"]), None))
        self.assertNotIn("ruflo", run_cmd.select(P(["--no-ruflo"]), UP_1X))

    def test_memory_slot(self):
        r = run_cmd.select(P(["--memory", "ruflo"]), None)
        self.assertIn("ruflo", r)
        self.assertNotIn("memory", r)
        n = run_cmd.select(P(["--memory", "none"]), UP_1X)
        self.assertNotIn("ruflo", n)
        self.assertNotIn("memory", n)
        self.assertEqual(run_cmd.providers(P([]), ["core", "jev", "memory"], None)["memory"], "dryas")

    def test_with_and_no_same_component_is_an_error(self):
        with self.assertRaises(SystemExit):
            P(["--with-ruflo", "--no-ruflo"])


class PreflightTest(unittest.TestCase):
    def test_fresh_install_needs_no_node_and_allows_spaces(self):
        found = {"python3": "/usr/bin/python3", "git": "/usr/bin/git", "claude": "/usr/bin/claude"}
        with mock.patch.object(pu, "which", lambda n: found.get(n, "")), \
                mock.patch.object(pu, "space_free", lambda p: None):
            probs = run_cmd.preflight(run_cmd.select(P([]), None), "claude", Path("/Users/A B/.claude"))
        self.assertEqual(probs, [])

    def test_with_ruflo_still_needs_node(self):
        with mock.patch.object(pu, "which", lambda n: "" if n in ("node", "npm") else "/x/" + n):
            probs = run_cmd.preflight(run_cmd.select(P(["--with-ruflo"]), None), "claude", Path("/x/.claude"))
        self.assertTrue(any("node" in p.lower() for p in probs))


class ChainLocalProvidersTest(unittest.TestCase):
    def test_providers_recorded_and_memory_stages_toggle(self):
        root = Path(tempfile.mkdtemp())
        ps.write_chain_local(root, ["core", "jev", "memory"], None,
                             providers={"judge": None, "memory": "dryas", "process": "dryas"})
        loc = json.loads((root / "chain.local.json").read_text(encoding="utf-8"))
        self.assertEqual(loc["providers"]["memory"], "dryas")
        self.assertIn("memory", [c for c in run_cmd.OPTIONAL if c not in loc["off"]])
        ps.write_chain_local(root, ["core", "jev", "ruflo"], None,
                             providers={"judge": None, "memory": "ruflo", "process": "dryas"})
        loc = json.loads((root / "chain.local.json").read_text(encoding="utf-8"))
        self.assertIs(loc["stages"]["post"]["mem-edit"]["enabled"], False)
        self.assertIn("memory", loc["off"])


class JudgeFlagTest(unittest.TestCase):
    def test_set_judge_writes_user_thresholds(self):
        d = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": d, "JEV_THRESHOLDS": os.path.join(d, "t.json")})
        p.start()
        self.addCleanup(p.stop)
        ps.set_judge("local")
        ps.set_judge(None)
        sys.path.insert(0, str(HERE.parent.parent / "claude" / "jev"))
        import thresholds
        self.assertEqual(thresholds.load()["judge"]["provider"], "local")


class CodexTomlTest(unittest.TestCase):
    def test_codex_toml_has_no_ruflo_by_default(self):
        self.assertNotIn("mcp_servers.ruflo", cps.toml_block(run_cmd.select(P([]), None), "/p", "/d", {}, "python3"))
