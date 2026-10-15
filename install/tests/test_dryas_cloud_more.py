"""dryas cloud, second file (test_dryas_cloud.py is near 500 lines): resume after a failed write, own-skill binaries
in the confirmation, remove with kept files, and symlinked generated folders."""
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cloud_fixtures as fx
sys.path.insert(0, str(fx.ROOT / "tools"))

SETTINGS = '{\n    "permissions": {"allow": ["Bash(make test)"]},\n    "env": {"FOO": "1"}\n}\n'
FILES = {"README.md": "# demo\n", "CLAUDE.md": "# Repo rules\n\nKeep tests green.\n", ".gitignore": "node_modules/\n",
         ".claude/settings.json": SETTINGS, ".mcp.json": '{"mcpServers": {"docs": {"command": "docs-server"}}}\n'}


class Base(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.base), True)
        self.repo = fx.git_repo(self.base / "repo", FILES)
        self.cfg = self.base / "no-config"

    def cli(self, *args):
        return fx.run_cli(list(args) + ["--repo", str(self.repo), "--claude-dir", str(self.cfg)])

    def ok(self, *args):
        rc, out = self.cli(*args)
        self.assertEqual(rc, 0, out)
        fx.commit_all(self.repo)
        return out

    def man(self):
        return json.loads((self.repo / ".dryas/manifest.json").read_text(encoding="utf-8"))

    def failing(self, name, *args):
        """Run the CLI with every os.replace onto a file called `name` failing as a full disk."""
        import dryas_cloud as dc
        real = os.replace

        def replace(src, dst):
            if Path(dst).name == name:
                raise OSError(28, "No space left on device")
            real(src, dst)

        with unittest.mock.patch.object(dc.os, "replace", replace):
            return self.cli(*args)


class ResumeTest(Base):
    def test_init_resumes_after_a_failed_write(self):
        # defect: the files a failed init wrote count as clashes (or as the repo's own config), so it cannot resume
        before = fx.snapshot(self.repo)
        rc, out = self.failing("gate.py", "init", "--yes")
        self.assertEqual(rc, 1, out)
        self.assertIn("No space left on device", out)
        self.assertTrue((self.repo / ".claude/skills/plan/SKILL.md").is_file())
        self.assertIn("written before the error:", out)
        self.assertIn(".claude/settings.json", out)
        self.assertIn("re-run the same command to resume", out)
        self.assertIn("git clean -fd -- ", out)
        out = self.ok("init", "--yes")
        self.assertNotIn("already in the repo", out)
        self.assertEqual(self.cli("check")[0], 0)
        self.ok("remove", "--yes")
        self.assertEqual(fx.snapshot(self.repo), before)  # the config records hold the true originals

    def test_init_still_clashes_on_different_content(self):
        self.assertEqual(self.failing("gate.py", "init", "--yes")[0], 1)
        skill = self.repo / ".claude/skills/plan/SKILL.md"
        skill.write_text("ours\n", encoding="utf-8")
        rc, out = self.cli("init", "--yes", "--force")
        self.assertEqual(rc, 1, out)
        self.assertIn("already in the repo and not written by Dryas: .claude/skills/plan", out)
        self.assertEqual(skill.read_text(encoding="utf-8"), "ours\n")

    def test_a_skill_folder_with_a_file_dryas_does_not_copy_still_clashes(self):
        extra = self.repo / ".claude/skills/plan/notes.md"
        extra.parent.mkdir(parents=True)
        extra.write_text("our notes\n", encoding="utf-8")
        fx.commit_all(self.repo)
        rc, out = self.cli("init", "--yes")
        self.assertEqual(rc, 1, out)
        self.assertIn("not written by Dryas: .claude/skills/plan", out)

    def test_update_resumes_after_a_failed_write(self):
        # defect: files a failed update already wrote are taken for hand edits and kept at the new bytes
        self.ok("init", "--yes")
        rc, out = self.failing("CLAUDE.md", "update", "--yes", "--persist-memory")
        self.assertEqual(rc, 1, out)
        self.assertIn(".dryas/memory/notes/.gitkeep", out)
        self.assertIn("--force", out)
        out = self.ok("update", "--yes", "--persist-memory")
        self.assertNotIn("kept hand-edited", out)
        self.assertTrue(self.man()["options"]["persist_memory"])
        self.assertEqual(self.cli("check")[0], 0)


class OwnBinaryTest(Base):
    def test_a_changed_binary_needs_confirming_again(self):
        # defect: the confirmation covers only secret-shaped text, so a swapped binary is copied without review
        self.cfg = self.base / "cfg"
        fx.own_skill(self.cfg, "kit", "---\nname: kit\ndescription: d\n---\nUse the logo.\n")
        logo = self.cfg / "skills/kit/logo.png"
        logo.write_bytes(b"\x89PNG\xff\xfe one")
        self.ok("init", "--yes", "--with-own", "kit", "--confirm-own", "kit")
        copy = self.repo / ".claude/skills/kit/logo.png"
        self.assertEqual(copy.read_bytes(), b"\x89PNG\xff\xfe one")
        self.assertIn("Nothing to change.", self.ok("update", "--yes"))
        logo.write_bytes(b"\x89PNG\xff\xfe two")
        out = self.ok("update", "--yes")
        self.assertIn("kept .claude/skills/kit/logo.png, could not rebuild: binary file logo.png", out)
        self.assertEqual(copy.read_bytes(), b"\x89PNG\xff\xfe one")
        self.ok("update", "--yes", "--confirm-own", "kit")
        self.assertEqual(copy.read_bytes(), b"\x89PNG\xff\xfe two")


class RemoveKeptTest(Base):
    def test_remove_keeps_a_manifest_for_what_it_kept(self):
        # defect: remove deletes the manifest while keeping hand-edited files, so nothing can finish the removal
        before = fx.snapshot(self.repo)
        self.ok("init", "--yes")
        skill = self.repo / ".claude/skills/plan/SKILL.md"
        skill.write_text("my plan\n", encoding="utf-8")
        fx.commit_all(self.repo)
        out = self.ok("remove", "--yes")
        self.assertIn("kept hand-edited .claude/skills/plan/SKILL.md", out)
        self.assertIn("remove --force", out)
        self.assertEqual(sorted(self.man()["files"]), [".claude/skills/plan/SKILL.md"])
        self.assertNotIn("<!-- dryas:start -->", (self.repo / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertEqual((self.repo / ".claude/settings.json").read_text(encoding="utf-8"), SETTINGS)
        self.assertIn("Nothing to change.", self.ok("remove", "--yes"))
        self.ok("remove", "--yes", "--force")
        self.assertEqual(fx.snapshot(self.repo), before)


class SymlinkTrashTest(Base):
    def test_a_generated_folder_linked_outside_stops_remove(self):
        # defect: remove reports removing .dryas/state or a __pycache__ that leads out of the repo and silently skips it
        outside = self.base / "outside"
        (outside / "keep").mkdir(parents=True)
        (outside / "keep/data").write_text("x\n", encoding="utf-8")
        self.ok("init", "--yes")
        for rel in (".dryas/state", ".dryas/jev/__pycache__"):
            link = self.repo / rel
            link.symlink_to(outside / "keep", target_is_directory=True)
            rc, out = self.cli("remove", "--yes")
            self.assertEqual(rc, 1, (rel, out))
            self.assertIn("%s would be written outside the repo" % rel, out)
            self.assertTrue((self.repo / ".dryas/manifest.json").is_file())
            self.assertEqual((outside / "keep/data").read_text(encoding="utf-8"), "x\n")
            link.unlink()

    def test_a_generated_folder_linked_inside_is_unlinked(self):
        self.ok("init", "--yes")
        target = self.repo / ".dryas-elsewhere"
        target.mkdir()
        (target / "data").write_text("x\n", encoding="utf-8")
        (self.repo / ".dryas/state").symlink_to(target, target_is_directory=True)
        fx.commit_all(self.repo)  # git ignores .dryas/state/ only as a folder, so it tracks the link
        self.ok("remove", "--yes")
        self.assertFalse(os.path.lexists(str(self.repo / ".dryas/state")))
        self.assertEqual((target / "data").read_text(encoding="utf-8"), "x\n")


if __name__ == "__main__":
    unittest.main()
