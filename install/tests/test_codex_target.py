"""Legacy Codex copy install: uninstall only (install_codex is gone). The legacy state is built by hand."""
import io, json, os, shutil, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import codex_target as ct
import legacy_codex


class CodexTargetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.cdx = self.home / ".codex"
        self.calls = []

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def run_fake(self, argv):
        self.calls.append(argv)
        return 0

    def rec(self):
        return json.loads((self.cdx / ct.RECORD).read_text(encoding="utf-8"))

    def save(self, rec):
        (self.cdx / ct.RECORD).write_text(json.dumps(rec), encoding="utf-8")

    def uninstall(self):
        with redirect_stdout(io.StringIO()):
            return ct.uninstall_codex(self.cdx, self.home, self.run_fake)

    def test_uninstall_removes_everything(self):
        legacy_codex.legacy(self.home, self.cdx)
        self.assertEqual(self.uninstall(), 0)
        self.assertEqual((self.cdx / "AGENTS.md").read_text(encoding="utf-8"), "mine\n")
        self.assertFalse((self.cdx / "hooks.json").exists())
        self.assertFalse(ct.skills_dir(self.home).exists())  # emptied ~/.agents/skills and ~/.agents go too
        self.assertFalse((self.cdx / ct.RECORD).exists())
        self.assertEqual(self.calls, [["codex", "mcp", "remove", "jev"]])

    def test_uninstall_restores_user_files_byte_identical(self):
        legacy_codex.legacy(self.home, self.cdx)
        user_hook = {"type": "command", "command": "mine"}
        hp = self.cdx / "hooks.json"
        data = json.loads(hp.read_text(encoding="utf-8"))
        data["hooks"]["Stop"] = [{"hooks": [user_hook]}]
        hp.write_text(json.dumps(data), encoding="utf-8")
        user_toml = 'model = "x"\n'
        (self.cdx / "config.toml").write_text(user_toml + "\n" + ct.TOML_START + '\n[mcp_servers.jev]\ncommand = "p"\n'
                                              + ct.TOML_END + "\n", encoding="utf-8")
        rec = self.rec()
        rec.update(toml=True, toml_created=False, toml_sep="\n", mcp={"jev": "toml"})
        self.save(rec)
        self.uninstall()
        self.assertEqual((self.cdx / "config.toml").read_text(encoding="utf-8"), user_toml)
        self.assertEqual(json.loads(hp.read_text(encoding="utf-8")), {"hooks": {"Stop": [{"hooks": [user_hook]}]}})
        self.assertEqual(self.calls, [])  # a TOML-registered server is not removed with the CLI

    def test_toml_block_created_file_removed(self):
        legacy_codex.legacy(self.home, self.cdx)
        (self.cdx / "config.toml").write_text(ct.TOML_START + '\n[mcp_servers.jev]\ncommand = "p"\n' + ct.TOML_END + "\n",
                                              encoding="utf-8")
        rec = self.rec()
        rec.update(toml=True, toml_created=True, mcp={"jev": "toml"})
        self.save(rec)
        self.uninstall()
        self.assertFalse((self.cdx / "config.toml").exists())

    def test_backed_up_user_skill_restored(self):
        legacy_codex.legacy(self.home, self.cdx)
        b = self.cdx / ".dryas-backup-1" / "skills" / "orchestrate"
        b.mkdir(parents=True)
        (b / "SKILL.md").write_text("MINE", encoding="utf-8")
        rec = self.rec()
        rec["skill_backups"] = {"orchestrate": str(b)}
        self.save(rec)
        self.uninstall()
        self.assertEqual((ct.skills_dir(self.home) / "orchestrate" / "SKILL.md").read_text(encoding="utf-8"), "MINE")
        self.assertFalse((self.cdx / ".dryas-backup-1").exists())

    def test_resume_keeps_a_skill_restored_by_the_interrupted_run(self):
        legacy_codex.legacy(self.home, self.cdx)
        b = self.cdx / ".dryas-backup-1" / "skills" / "orchestrate"
        b.mkdir(parents=True)
        (b / "SKILL.md").write_text("MINE", encoding="utf-8")
        rec = self.rec()
        rec["skill_backups"] = {"orchestrate": str(b)}
        self.save(rec)
        with mock.patch.object(ct.sm, "unmerge", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                self.uninstall()
        self.assertTrue((self.cdx / ct.RECORD).exists())  # the record goes last: a re-run resumes
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(ct.uninstall_codex(self.cdx, self.home, self.run_fake), 0)
        self.assertIn("kept %s" % (ct.skills_dir(self.home) / "orchestrate"), buf.getvalue())
        self.assertEqual((ct.skills_dir(self.home) / "orchestrate" / "SKILL.md").read_text(encoding="utf-8"), "MINE")
        self.assertFalse((self.cdx / ct.RECORD).exists())

    def test_no_record_is_a_no_op(self):
        self.assertEqual(self.uninstall(), 0)
        self.assertEqual(self.calls, [])

    def test_codex_home_env(self):
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(self.tmp / "ch")}):
            self.assertEqual(ct.codex_dir(), self.tmp / "ch")


if __name__ == "__main__":
    unittest.main()
