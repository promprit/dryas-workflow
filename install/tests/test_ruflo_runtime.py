# install/tests/test_ruflo_runtime.py
import json, os, shutil, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import ruflo_runtime
import platform_util as pu

REPO = HERE.parents[1]


class RufloRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.dist = Path(tempfile.mkdtemp())
        self.helpers = {"hook-handler.cjs": (b"// h\n", 0o755), "auto-memory-hook.mjs": (b"// a\n", 0o644)}

    def tearDown(self):
        shutil.rmtree(str(self.root), ignore_errors=True)
        shutil.rmtree(str(self.dist), ignore_errors=True)

    def test_first_install_writes_helpers_shim_and_link(self):
        wrote = ruflo_runtime.install(REPO, self.root, self.helpers, str(self.dist))
        r = self.root / "ruflo"
        self.assertEqual((r / "helpers" / "hook-handler.cjs").read_bytes(), b"// h\n")
        self.assertEqual((r / "mcp-shim" / "bin" / "cli.js").read_bytes(),
                         (REPO / "claude" / "ruflo" / "mcp-shim" / "bin" / "cli.js").read_bytes())
        self.assertTrue(os.path.isdir(str(r / "mcp-shim" / "dist")))
        self.assertEqual(len(wrote), 4)

    def test_second_run_is_noop(self):
        ruflo_runtime.install(REPO, self.root, self.helpers, str(self.dist))
        self.assertEqual(ruflo_runtime.install(REPO, self.root, self.helpers, str(self.dist)), [])

    def test_changed_helper_rewritten(self):
        ruflo_runtime.install(REPO, self.root, self.helpers, str(self.dist))
        self.helpers["hook-handler.cjs"] = (b"// h2\n", 0o755)
        wrote = ruflo_runtime.install(REPO, self.root, self.helpers, str(self.dist))
        self.assertEqual([Path(w).name for w in wrote], ["hook-handler.cjs"])

    def test_relink_when_target_changes(self):
        ruflo_runtime.install(REPO, self.root, self.helpers, str(self.dist))
        other = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(other), True)
        wrote = ruflo_runtime.install(REPO, self.root, self.helpers, str(other))
        link = self.root / "ruflo" / "mcp-shim" / "dist"
        self.assertEqual(wrote, [str(link)])
        self.assertTrue(pu.same_path(pu.read_dir_link(str(link)), str(other)))

    def test_real_dist_dir_is_kept_with_warning(self):
        d = self.root / "ruflo" / "mcp-shim" / "dist"
        d.mkdir(parents=True)
        (d / "x").write_text("keep")
        ruflo_runtime.install(REPO, self.root, self.helpers, str(self.dist))
        self.assertEqual((d / "x").read_text(), "keep")

    @unittest.skipIf(os.name == "nt", "exec bit")
    def test_exec_bit_repaired(self):
        ruflo_runtime.install(REPO, self.root, self.helpers, "")
        h = self.root / "ruflo" / "helpers" / "hook-handler.cjs"
        os.chmod(str(h), 0o644)
        self.assertEqual(ruflo_runtime.install(REPO, self.root, self.helpers, ""), [])
        self.assertEqual(h.stat().st_mode & 0o777, 0o755)

    def test_no_dist_skips_link(self):
        ruflo_runtime.install(REPO, self.root, self.helpers, "")
        self.assertFalse(os.path.lexists(str(self.root / "ruflo" / "mcp-shim" / "dist")))


class FragmentTest(unittest.TestCase):
    def test_core_has_no_hooks_and_new_rules(self):
        frag = json.loads((REPO / "claude" / "settings.fragment.json").read_text(encoding="utf-8"))
        self.assertNotIn("hooks", frag["core"])
        self.assertNotIn("hooks", frag.get("jev", {}))
        allow = frag["core"]["permissions"]["allow"]
        self.assertIn("Read($DATA_RULE/**)", allow)
        self.assertIn('Bash("$CD/bin/dryas-py" "$CD/jev/planfile.py":*)', allow)
        self.assertEqual(json.loads((REPO / "claude" / "settings.fragment.json").read_text(encoding="utf-8"))["jev"]["permissions"]["allow"], ["mcp__plugin_dryas_jev"])
        self.assertEqual(frag["core"]["env"]["DRYAS_PY"], "$PY")
        self.assertEqual(frag["core"]["env"]["DRYAS_DATA_ROOT"], "$DRYAS_DATA_ROOT")

    def test_ruflo_points_at_data_root(self):
        frag = json.loads((REPO / "claude" / "settings.fragment.json").read_text(encoding="utf-8"))["ruflo"]
        text = json.dumps(frag)
        self.assertNotIn("$CD/ruflo/helpers", text)
        self.assertNotIn("$CD/ruflo/mcp-shim", text)
        self.assertIn("$DRYAS_DATA_ROOT/ruflo/helpers/hook-handler.cjs", text)
        self.assertEqual(frag["env"]["RUFLO_MCP_CLI_OVERRIDE"], "$DRYAS_DATA_ROOT/ruflo/mcp-shim/bin/cli.js")


class CodexDataRootTest(unittest.TestCase):
    def test_custom_root_reaches_codex_server_env(self):
        import codex_target, dryas_install
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(home), True)
        old = os.environ.get("DRYAS_DATA_ROOT")
        os.environ["DRYAS_DATA_ROOT"] = str(home / "custom")
        self.addCleanup(lambda: os.environ.__setitem__("DRYAS_DATA_ROOT", old) if old else os.environ.pop("DRYAS_DATA_ROOT", None))
        m = dryas_install._mapping(["core", "ruflo"], home, home / ".claude")
        env = dryas_install.ruflo_env(REPO, m)
        srv = codex_target.servers(["ruflo"], m, env)["ruflo"]
        self.assertEqual(srv[2]["DRYAS_DATA_ROOT"], m["DRYAS_DATA_ROOT"])
        self.assertIn("custom", srv[2]["DRYAS_DATA_ROOT"])
        self.assertTrue(m["DATA_RULE"].startswith("//"))

    def test_default_root_rule(self):
        import dryas_install
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(home), True)
        os.environ.pop("DRYAS_DATA_ROOT", None)
        self.assertEqual(dryas_install._mapping(["core"], home, home / ".claude")["DATA_RULE"], "~/.dryas")


if __name__ == "__main__":
    unittest.main()
