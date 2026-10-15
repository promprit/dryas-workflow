import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import opencode_setup
import plugin_setup as ps
import run_cmd


class OpenCodeWiringTest(unittest.TestCase):
    def test_parse_opencode_flags(self):
        a = run_cmd.parse(["--harness", "opencode", "--opencode-dir", "/x/oc", "--tier-fast", "p/a", "--tier-frontier", "p/z"])
        self.assertEqual((a.harness, a.opencode_dir, a.tier_fast, a.tier_frontier), ("opencode", "/x/oc", "p/a", "p/z"))
        self.assertEqual(run_cmd.parse(["--harness", "all"]).harness, "all")
        self.assertIn("all", run_cmd.CLAUDE_H)
        self.assertEqual(run_cmd.OPENCODE_H, ("opencode", "all"))

    def test_main_opencode_runs_only_opencode(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": os.path.join(d, "data")}), \
                mock.patch.object(run_cmd, "preflight", return_value=[]), \
                mock.patch("codex_plugin_setup.legacy_components", return_value=None), \
                mock.patch.object(opencode_setup, "setup", return_value=0) as setup, \
                mock.patch.object(opencode_setup, "verify", return_value=0), \
                mock.patch.object(ps, "setup") as claude_setup:
            rc = run_cmd.main(["--harness", "opencode", "--yes", "--opencode-dir", os.path.join(d, "oc"),
                               "--claude-dir", os.path.join(d, "claude"), "--tier-strong", "p/big"])
        self.assertEqual(rc, 0)
        claude_setup.assert_not_called()
        args = setup.call_args[0]
        self.assertEqual(args[3], {"fast": None, "standard": None, "strong": "p/big", "frontier": None})
        self.assertEqual(args[2], run_cmd.select(run_cmd.parse(["--harness", "opencode"]), None))

    def test_opencode_setup_keeps_shared_component_choices(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": os.path.join(d, "data")}), \
                mock.patch.object(run_cmd, "preflight", return_value=[]), \
                mock.patch("codex_plugin_setup.legacy_components", return_value=None), \
                mock.patch("dryas_install.capture", return_value=(0, "1.18.32\n")), \
                mock.patch.object(opencode_setup, "verify", return_value=0):
            root, cd = Path(d) / "data", Path(d) / "claude"
            root.mkdir()
            (cd / ps.RECORD).parent.mkdir(parents=True)
            (cd / ps.RECORD).write_text(json.dumps({"components": ["core", "jev", "ruflo", "design", "superpowers"]}),
                                        encoding="utf-8")
            (root / "chain.local.json").write_text(json.dumps({"off": []}), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                rc = run_cmd.main(["--harness", "opencode", "--yes", "--opencode-dir", os.path.join(d, "oc"),
                                   "--claude-dir", str(cd)])
            self.assertEqual(rc, 0)
            off = json.loads((root / "chain.local.json").read_text(encoding="utf-8"))["off"]
            for c in ("ruflo", "design", "superpowers"):
                self.assertNotIn(c, off)

    def test_uninstall_leaves_unreadable_accounts_alone(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": os.path.join(d, "data")}):
            root, od = Path(d) / "data", Path(d) / "oc"
            root.mkdir()
            (od / "dryas").mkdir(parents=True)
            (od / opencode_setup.RECORD).write_text(json.dumps({"files": {}}), encoding="utf-8")
            (root / "accounts.json").write_bytes(b"{not json")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(opencode_setup.uninstall(od), 0)
            self.assertEqual((root / "accounts.json").read_bytes(), b"{not json")

    def test_preflight_opencode_alone_skips_ruflo_node_checks(self):
        with mock.patch.object(run_cmd.pu, "which", side_effect=lambda t: None if t in ("node", "npm") else "/bin/" + t), \
                mock.patch.object(opencode_setup, "installed_version", return_value=(1, 18, 32)):
            self.assertEqual(run_cmd.preflight(["core", "jev"], "opencode", Path("/x")), [])

    def test_other_accounts_and_purge_count_opencode(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": d}):
            Path(d, "accounts.json").write_text(json.dumps({"claude_dirs": [], "codex_dirs": [],
                                                            "opencode_dirs": ["/x/oc"]}), encoding="utf-8")
            self.assertEqual(ps.other_accounts(Path(d) / "claude"), ["/x/oc"])
            self.assertEqual(ps.other_accounts(Path(d) / "claude", od=Path("/x/oc")), [])
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertFalse(ps.purge_shared())
            self.assertIn("still used by /x/oc", buf.getvalue())

    def test_claude_uninstall_purge_keeps_data_for_opencode(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": os.path.join(d, "data")}):
            root, cd = Path(d) / "data", Path(d) / "claude"
            root.mkdir()
            cd.mkdir()
            (root / "accounts.json").write_text(json.dumps({"claude_dirs": [str(ps.norm(cd))], "codex_dirs": [],
                                                            "opencode_dirs": ["/x/oc"]}), encoding="utf-8")
            (root / "dryas.db").write_text("memory", encoding="utf-8")
            (cd / ps.RECORD).write_text(json.dumps({"settings": {}}), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf), mock.patch.object(ps, "_codex_installed", return_value=None), \
                    mock.patch.object(ps.di, "run", return_value=0):
                ps.uninstall(cd, True)
            self.assertTrue((root / "dryas.db").exists())
            self.assertIn("your OpenCode Dryas install uses it", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
