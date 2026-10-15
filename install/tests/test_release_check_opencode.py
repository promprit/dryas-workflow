import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import release_check as rc  # noqa: E402
import release_check_opencode as rco  # noqa: E402


class ReleaseCheckOpenCodeTest(unittest.TestCase):
    def test_skip_without_opencode(self):
        rep, buf = rc.Report(), io.StringIO()
        with redirect_stdout(buf):
            rco.check(rep, Path("/nope"), None, {})
        self.assertIn("SKIP", buf.getvalue())
        self.assertEqual(rep.fails, 0)

    def test_flat_tiers_warn_and_hashes_checked(self):
        with tempfile.TemporaryDirectory() as d:
            od = Path(d)
            (od / "dryas").mkdir()
            (od / "plugin").mkdir()
            (od / "plugin/dryas.ts").write_text("x", encoding="utf-8")
            (od / "agent").mkdir()
            for t in ("fast", "standard", "strong", "frontier"):
                (od / ("agent/dryas-executor-%s.md" % t)).write_text("model: p/same\n", encoding="utf-8")
            files = {"plugin/dryas.ts": hashlib.sha256(b"edited-later").hexdigest()}
            (od / "dryas/install.json").write_text(json.dumps({"files": files, "tiers": {}}), encoding="utf-8")
            rep, buf = rc.Report(), io.StringIO()
            with redirect_stdout(buf), mock.patch.object(rco.di, "capture", return_value=(0, "1.18.32\n")), \
                    mock.patch.object(rco.di, "scope_smoke", return_value=True), \
                    mock.patch.object(rco, "_mcp_connected", return_value=(True, "")), \
                    mock.patch.object(rco, "_rules_ok", return_value=True):
                rco.check(rep, od, "/usr/bin/opencode", {})
            out = buf.getvalue()
            self.assertIn("WARN  executor tiers", out)
            self.assertIn("WARN  installed files unchanged", out)
            self.assertEqual(rep.fails, 0)

    def test_mcp_check_skips_untargetable_dir(self):
        with tempfile.TemporaryDirectory() as d:
            od = Path(d) / "oc-other"
            (od / "dryas").mkdir(parents=True)
            (od / "dryas/install.json").write_text(json.dumps({"files": {}, "tiers": {}}), encoding="utf-8")
            (od / "agent").mkdir()
            rep, buf = rc.Report(), io.StringIO()
            with redirect_stdout(buf), mock.patch.object(rco.di, "capture", return_value=(0, "1.18.32\n")), \
                    mock.patch.object(rco.di, "scope_smoke", return_value=True), \
                    mock.patch.object(rco, "_mcp_connected", return_value=(True, "")) as mcp, \
                    mock.patch.object(rco, "_rules_ok", return_value=True):
                rco.check(rep, od, "/usr/bin/opencode", {})
            self.assertIn("SKIP  jev MCP server connects  (OpenCode reads <XDG_CONFIG_HOME>/opencode; "
                          "re-run with a dir named opencode)", buf.getvalue())
            mcp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
