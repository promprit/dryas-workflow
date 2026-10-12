# install/tests/test_ruflo_runtime.py
import json, os, shutil, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import ruflo_runtime

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
        self.assertEqual(frag["core"]["env"]["DRYAS_PY"], "$PY")
        self.assertEqual(frag["core"]["env"]["DRYAS_DATA_ROOT"], "$DRYAS_DATA_ROOT")

    def test_ruflo_points_at_data_root(self):
        frag = json.loads((REPO / "claude" / "settings.fragment.json").read_text(encoding="utf-8"))["ruflo"]
        text = json.dumps(frag)
        self.assertNotIn("$CD/ruflo/helpers", text)
        self.assertNotIn("$CD/ruflo/mcp-shim", text)
        self.assertIn("$DRYAS_DATA_ROOT/ruflo/helpers/hook-handler.cjs", text)
        self.assertEqual(frag["env"]["RUFLO_MCP_CLI_OVERRIDE"], "$DRYAS_DATA_ROOT/ruflo/mcp-shim/bin/cli.js")


if __name__ == "__main__":
    unittest.main()
