import io, json, os, shutil, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import codex_target as ct
REPO = Path(__file__).resolve().parents[2]
PY = sys.executable.replace("\\", "/")


class CodexTargetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.cdx = self.home / ".codex"
        self.cd = self.home / ".claude"
        self.cd.mkdir(parents=True)
        self.calls = []
        self.rc = 0
        self.mapping = {"PY": PY, "CD": str(self.cd).replace("\\", "/"), "PY_SAFE": PY, "CD_SAFE": str(self.cd).replace("\\", "/"),
                        "HOME": str(self.home).replace("\\", "/"), "DRYAS_DATA_ROOT": "/d"}
        self.ruflo_env = {"DRYAS_DATA_ROOT": "/d", "RUFLO_JS": "/r.js", "RUFLO_NO_AUTO_ENABLE": "1"}

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def run_fake(self, argv):
        self.calls.append(argv)
        return self.rc

    def install(self, comps=("core", "jev", "ruflo"), **kw):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = ct.install_codex(REPO, self.cdx, self.home, list(comps), self.mapping, self.ruflo_env, self.run_fake, **kw)
        return rc, buf.getvalue()

    def uninstall(self):
        with redirect_stdout(io.StringIO()):
            return ct.uninstall_codex(self.cdx, self.home, self.run_fake)

    def test_install_creates_everything(self):
        rc, out = self.install()
        self.assertEqual(rc, 0)
        agents = (self.cdx / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("<!-- dryas:start -->", agents)
        self.assertLess(len(agents.encode("utf-8")), 8 * 1024)
        for n in ct.SKILLS:
            t = (ct.skills_dir(self.home) / n / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("{{", t)
        hooks = json.loads((self.cdx / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("--harness codex", hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"])
        self.assertIn(["codex", "mcp", "add", "jev", "--", PY, "-X", "utf8", self.mapping["CD"] + "/jev/jev_mcp.py"], self.calls)
        ruflo = [c for c in self.calls if c[:4] == ["codex", "mcp", "add", "ruflo"]][0]
        self.assertIn("DRYAS_DATA_ROOT=/d", ruflo)
        self.assertEqual(ruflo[-3:], [self.mapping["CD"] + "/ruflo/mcp-shim/bin/cli.js", "mcp", "start"])
        rec = json.loads((self.cdx / ct.RECORD).read_text(encoding="utf-8"))
        self.assertEqual(rec["mcp"], {"jev": "cli", "ruflo": "cli"})

    def test_reinstall_is_idempotent(self):
        self.install()
        snap = {p: p.read_bytes() for p in self.home.rglob("*") if p.is_file() and p.name != ct.RECORD}
        self.calls.clear()
        self.install()
        self.assertEqual({p: p.read_bytes() for p in self.home.rglob("*") if p.is_file() and p.name != ct.RECORD}, snap)
        self.assertEqual([c for c in self.calls if c[:3] == ["codex", "mcp", "add"]], [])

    def test_uninstall_restores_user_files_byte_identical(self):
        self.cdx.mkdir(parents=True)
        user = {"AGENTS.md": "MINE\n", "config.toml": 'model = "x"\n',
                "hooks.json": json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]}}, indent=2) + "\n"}
        for n, t in user.items():
            (self.cdx / n).write_text(t, encoding="utf-8")
        self.rc = 1  # codex mcp add fails -> TOML fallback
        self.install()
        self.assertIn(ct.TOML_START, (self.cdx / "config.toml").read_text(encoding="utf-8"))
        self.uninstall()
        for n, t in user.items():
            self.assertEqual((self.cdx / n).read_text(encoding="utf-8"), t, n)
        self.assertFalse((self.cdx / ct.RECORD).exists())
        for n in ct.SKILLS:
            self.assertFalse((ct.skills_dir(self.home) / n).exists())

    def test_toml_fallback_block(self):
        self.rc = 1
        self.install(("core", "jev"))
        t = (self.cdx / "config.toml").read_text(encoding="utf-8")
        self.assertIn("[mcp_servers.jev]", t)
        self.assertIn("command = %s" % json.dumps(PY), t)
        self.assertIn('args = ["-X", "utf8", %s]' % json.dumps(self.mapping["CD"] + "/jev/jev_mcp.py"), t)
        self.uninstall()
        self.assertFalse((self.cdx / "config.toml").exists())

    def test_user_mcp_table_kept(self):
        self.cdx.mkdir(parents=True)
        (self.cdx / "config.toml").write_text('[mcp_servers.jev]\ncommand = "mine"\n', encoding="utf-8")
        self.rc = 1
        rc, out = self.install(("core", "jev"))
        t = (self.cdx / "config.toml").read_text(encoding="utf-8")
        self.assertEqual(t.count("[mcp_servers.jev]"), 1)
        self.assertIn("kept your [mcp_servers.jev]", out)
        self.assertEqual([c for c in self.calls if c[:3] == ["codex", "mcp", "add"]], [])

    def test_existing_skill_kept_without_force_and_restored_after_force(self):
        mine = ct.skills_dir(self.home) / "commit" / "SKILL.md"
        mine.parent.mkdir(parents=True)
        mine.write_text("MINE", encoding="utf-8")
        rc, out = self.install()
        self.assertEqual(mine.read_text(encoding="utf-8"), "MINE")
        self.assertIn("kept your skill", out)
        self.install(force=True)
        self.assertNotEqual(mine.read_text(encoding="utf-8"), "MINE")
        self.uninstall()
        self.assertEqual(mine.read_text(encoding="utf-8"), "MINE")

    def test_superpowers_hint(self):
        rc, out = self.install()
        self.assertIn("Superpowers was not found for Codex", out)
        shutil.rmtree(str(self.home))
        self.cd.mkdir(parents=True)
        (ct.skills_dir(self.home) / "brainstorming").mkdir(parents=True)
        rc, out = self.install()
        self.assertNotIn("Superpowers was not found", out)

    def test_dry_run_writes_nothing(self):
        before = sorted(str(p) for p in self.home.rglob("*"))
        rc, out = self.install(dry=True)
        self.assertEqual(sorted(str(p) for p in self.home.rglob("*")), before)
        self.assertEqual(self.calls, [])

    def test_codex_home_env(self):
        os.environ["CODEX_HOME"] = str(self.tmp / "ch")
        try:
            self.assertEqual(ct.codex_dir(), self.tmp / "ch")
        finally:
            del os.environ["CODEX_HOME"]

    def test_changed_hook_command_replaced_on_reinstall(self):
        self.install()
        self.mapping["PY"] = PY + "2"
        self.install()
        hooks = json.loads((self.cdx / "hooks.json").read_text(encoding="utf-8"))
        pre = [h for g in hooks["hooks"]["PreToolUse"] for h in g["hooks"] if "--harness codex" in h["command"]]
        self.assertEqual(len(pre), 1)
        self.assertIn(PY + "2", pre[0]["command"])
        rec = json.loads((self.cdx / ct.RECORD).read_text(encoding="utf-8"))
        self.assertFalse([h for h in rec["hooks"]["hooks"] if PY + "2" not in h[2]])

    def test_changed_mcp_spec_removed_then_added(self):
        self.install(("core", "jev"))
        self.calls.clear()
        self.mapping["PY"] = PY + "2"
        self.install(("core", "jev"))
        self.assertEqual([c[:4] for c in self.calls], [["codex", "mcp", "remove", "jev"], ["codex", "mcp", "add", "jev"]])
        self.assertIn(PY + "2", self.calls[1])

    def test_changed_toml_spec_rewritten(self):
        self.rc = 1
        self.install(("core", "jev"))
        self.mapping["PY"] = PY + "2"
        self.install(("core", "jev"))
        t = (self.cdx / "config.toml").read_text(encoding="utf-8")
        self.assertIn(json.dumps(PY + "2"), t)
        self.assertEqual(t.count("[mcp_servers.jev]"), 1)

    def test_user_quoted_mcp_table_kept(self):
        for form in ('[mcp_servers."jev"]', "[mcp_servers.'jev']", 'mcp_servers.jev.command = "x"'):
            self.assertTrue(ct._user_has_table(form + "\n", "jev"), form)
        self.assertFalse(ct._user_has_table("[mcp_servers.jev2]\n", "jev"))

    def test_verify_flags_missing_hook_path(self):
        self.install(("core",))
        rec = json.loads((self.cdx / ct.RECORD).read_text(encoding="utf-8"))
        rec["hooks"]["hooks"].append(["PreToolUse", None, '"/nonexistent/x/py" run'])
        (self.cdx / ct.RECORD).write_text(json.dumps(rec), encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            n = ct.verify_codex(self.cdx, self.home, ["core"], lambda *a, **k: (0, ""), self.cd)
        self.assertIn("FAIL  Codex hook commands", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
