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
        self.assertNotIn("superpowers", args[2])
        self.assertNotIn("design", args[2])

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
