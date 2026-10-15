import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dryas_install as di
import opencode_e2e
import opencode_setup as os_

REPO = Path(__file__).resolve().parents[2]


class OpenCodeSetupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.od = Path(self.tmp.name) / "opencode"
        self.data = Path(self.tmp.name) / "data"
        self.env = mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": str(self.data)})
        self.env.start()
        self.ver = mock.patch.object(di, "capture", return_value=(0, "1.18.32\n"))
        self.ver.start()

    def tearDown(self):
        self.ver.stop()
        self.env.stop()
        self.tmp.cleanup()

    def setup_(self, tiers=None):
        return os_.setup(REPO, self.od, ["core", "jev"], tiers or {}, yes=True)

    def test_setup_writes_tree_and_record(self):
        self.assertEqual(self.setup_(), 0)
        for rel in ("plugin/dryas.ts", "dryas/jev/chain.py", "dryas/AGENTS.md.template",
                    "skill/dryas-brainstorm/SKILL.md", "skill/dryas-orchestrate/SKILL.md",
                    "command/orchestrate.md", "agent/dryas-executor-fast.md"):
            self.assertTrue((self.od / rel).is_file(), rel)
        rec = json.loads((self.od / os_.RECORD).read_text(encoding="utf-8"))
        self.assertIn("plugin/dryas.ts", rec["files"])
        self.assertEqual(len(rec["files"]["plugin/dryas.ts"]), 64)
        acc = json.loads((self.data / "accounts.json").read_text(encoding="utf-8"))
        self.assertEqual(acc["opencode_dirs"], [str(os_.ps.norm(self.od))])

    def test_old_opencode_refused(self):
        with mock.patch.object(di, "capture", return_value=(0, "1.17.9\n")):
            self.assertEqual(self.setup_(), 1)
        self.assertFalse(self.od.exists())

    def test_tier_models_written(self):
        self.od.mkdir()
        (self.od / "opencode.json").write_text(json.dumps({"model": "p/default"}), encoding="utf-8")
        self.assertEqual(self.setup_({"fast": "p/cheap"}), 0)
        self.assertIn("model: p/cheap\n", (self.od / "agent/dryas-executor-fast.md").read_text(encoding="utf-8"))
        self.assertIn("model: p/default\n", (self.od / "agent/dryas-executor-strong.md").read_text(encoding="utf-8"))

    def test_no_model_line_without_any_model(self):
        self.assertEqual(self.setup_(), 0)
        text = (self.od / "agent/dryas-executor-fast.md").read_text(encoding="utf-8")
        self.assertNotIn("model:", text)
        self.assertNotIn("{{MODEL}}", text)

    def test_refuses_foreign_file(self):
        (self.od / "command").mkdir(parents=True)
        (self.od / "command/commit.md").write_text("mine\n", encoding="utf-8")
        self.assertEqual(self.setup_(), 1)
        self.assertEqual((self.od / "command/commit.md").read_text(encoding="utf-8"), "mine\n")
        self.assertFalse((self.od / "plugin").exists())

    def test_edited_file_kept_as_old_on_rerun(self):
        self.assertEqual(self.setup_(), 0)
        cmd = self.od / "command/commit.md"
        cmd.write_text("edited\n", encoding="utf-8")
        self.assertEqual(self.setup_(), 0)
        self.assertEqual((self.od / "command/commit.md.dryas-old").read_text(encoding="utf-8"), "edited\n")
        self.assertIn(os_.MARK, cmd.read_text(encoding="utf-8"))

    def test_uninstall_removes_unedited_keeps_edited(self):
        self.assertEqual(self.setup_(), 0)
        (self.od / "command/tune.md").write_text("edited\n", encoding="utf-8")
        self.assertEqual(os_.uninstall(self.od), 0)
        self.assertFalse((self.od / "plugin/dryas.ts").exists())
        rec = json.loads((self.od / os_.RECORD).read_text(encoding="utf-8"))
        self.assertEqual(list(rec["files"]), ["command/tune.md"])
        self.assertTrue((self.od / "command/tune.md").exists())
        acc = json.loads((self.data / "accounts.json").read_text(encoding="utf-8"))
        self.assertEqual(acc.get("opencode_dirs"), [])

    def test_uninstall_without_record_says_so(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(os_.uninstall(self.od), 0)
        self.assertIn("nothing to uninstall in", buf.getvalue())

    def test_reinstall_after_uninstall_kept_edited_file(self):
        self.assertEqual(self.setup_(), 0)
        (self.od / "command/tune.md").write_text("edited\n", encoding="utf-8")
        self.assertEqual(os_.uninstall(self.od), 0)
        rec = json.loads((self.od / os_.RECORD).read_text(encoding="utf-8"))
        self.assertEqual(list(rec["files"]), ["command/tune.md"])
        self.assertEqual(self.setup_(), 0)
        self.assertEqual((self.od / "command/tune.md.dryas-old").read_text(encoding="utf-8"), "edited\n")
        self.assertIn(os_.MARK, (self.od / "command/tune.md").read_text(encoding="utf-8"))

    def test_setup_recovers_after_interrupted_run(self):
        real, calls = Path.write_bytes, []

        def flaky(p, data):
            calls.append(p)
            if len(calls) == 3:
                raise OSError("disk full")
            return real(p, data)
        with mock.patch.object(Path, "write_bytes", flaky):
            with self.assertRaises(OSError):
                self.setup_()
        self.assertTrue(json.loads((self.od / os_.RECORD).read_text(encoding="utf-8")).get("partial"))
        self.assertEqual(self.setup_(), 0)
        self.assertNotIn("partial", json.loads((self.od / os_.RECORD).read_text(encoding="utf-8")))

    def test_dryas_old_never_overwritten(self):
        self.assertEqual(self.setup_(), 0)
        cmd = self.od / "command/commit.md"
        (self.od / "command/commit.md.dryas-old").write_text("first\n", encoding="utf-8")
        cmd.write_text("second\n", encoding="utf-8")
        self.assertEqual(self.setup_(), 0)
        self.assertEqual((self.od / "command/commit.md.dryas-old").read_text(encoding="utf-8"), "first\n")
        self.assertEqual((self.od / "command/commit.md.dryas-old.1").read_text(encoding="utf-8"), "second\n")

    def test_record_py_forward_slashes(self):
        with mock.patch.object(di, "PY", "C:\\Python312\\python.exe"):
            self.assertEqual(self.setup_(), 0)
        rec = json.loads((self.od / os_.RECORD).read_text(encoding="utf-8"))
        self.assertEqual(rec["py"], "C:/Python312/python.exe")

    def test_verify_passes_after_setup(self):
        self.assertEqual(self.setup_(), 0)
        self.ver.stop()
        try:
            self.assertEqual(os_.verify(self.od, ["core", "jev"]), 0)
        finally:
            self.ver.start()

    def test_scope_smoke_opencode(self):
        self.ver.stop()  # needs the real capture: scope_smoke runs chain.py as a subprocess
        try:
            self.assertTrue(di.scope_smoke(REPO / "claude/jev/chain.py", {}, harness="opencode"))
        finally:
            self.ver.start()


@unittest.skipIf(opencode_e2e.opencode_ok(), opencode_e2e.opencode_ok())
class InstalledEditionTest(unittest.TestCase):
    def test_installed_edition_blocks_out_of_scope_write(self):
        with tempfile.TemporaryDirectory() as d:
            srv = opencode_e2e.Server(Path(d), install=True)
            try:
                self.assertTrue((Path(d) / "xdg/config/opencode/dryas/install.json").is_file())
                orch = srv.proj / ".orchestrate"
                orch.mkdir()
                (orch / "PLAN.md").write_text("## Task 1: t\nGoal: g\nScope:\n- src/**\nDone:\n- d\n"
                                              "Failing test first: none (review)\n", encoding="utf-8")
                (orch / "active.json").write_text(json.dumps({"active": ["1"]}), encoding="utf-8")
                kids = srv.children(srv.prompt("DELEGATE"))
                self.assertEqual(len(kids), 1)
                write = [t for t in srv.tools(kids[0]) if t[0] == "write"]
                self.assertEqual(write[0][1], "error")
                self.assertIn("[scope-lock]", write[0][2])
                self.assertFalse((srv.proj / "out.txt").exists())
            finally:
                srv.close()


if __name__ == "__main__":
    unittest.main()
