import os, shutil, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import platform_util as pu


class PlatformUtilTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def test_fwd(self):
        self.assertEqual(pu.fwd("C:\\a\\b c\\d"), "C:/a/b c/d")
        self.assertEqual(pu.fwd("/x/y"), "/x/y")

    def test_python_exe_is_forward_slash_sys_executable(self):
        self.assertEqual(pu.python_exe(), sys.executable.replace("\\", "/"))

    def test_space_free_without_space_is_identity(self):
        self.assertEqual(pu.space_free("/a/b"), "/a/b")

    @unittest.skipIf(os.name == "nt", "POSIX has no short names")
    def test_space_free_with_space_is_none_on_posix(self):
        self.assertIsNone(pu.space_free(str(self.tmp / "a b")))

    @unittest.skipUnless(os.name == "nt", "Windows short names")
    def test_space_free_windows_short_name_or_none(self):
        d = self.tmp / "with space"
        d.mkdir()
        got = pu.space_free(str(d))
        self.assertTrue(got is None or " " not in got)

    def test_which_and_resolve_argv(self):
        git = pu.which("git")
        self.assertTrue(git)
        self.assertEqual(pu.resolve_argv(["git", "--version"]), [git, "--version"])
        self.assertEqual(pu.resolve_argv(["no-such-tool-xyz", "a"]), ["no-such-tool-xyz", "a"])
        self.assertEqual(pu.resolve_argv([]), [])

    def test_dir_link_roundtrip(self):
        target = self.tmp / "target"
        target.mkdir()
        (target / "f.txt").write_text("x", encoding="utf-8")
        dest = self.tmp / "link"
        kind = pu.make_dir_link(str(target), str(dest))
        self.assertIn(kind, ("symlink", "junction"))
        self.assertTrue((dest / "f.txt").exists())
        self.assertTrue(pu.same_path(pu.read_dir_link(str(dest)), str(target)))
        pu.remove_path(str(dest))
        self.assertFalse(os.path.lexists(str(dest)))
        self.assertTrue((target / "f.txt").exists())

    def test_read_dir_link_of_plain_dir_is_none(self):
        self.assertIsNone(pu.read_dir_link(str(self.tmp)))

    def test_remove_path_file_and_missing(self):
        f = self.tmp / "f"
        f.write_text("x", encoding="utf-8")
        pu.remove_path(str(f))
        self.assertFalse(f.exists())
        pu.remove_path(str(f))  # missing: no error

    def test_remove_dangling_dir_link(self):
        target, link = self.tmp / "t", self.tmp / "l"
        target.mkdir()
        try:
            pu.make_dir_link(str(target), str(link))
        except OSError:
            self.skipTest("cannot create dir links")
        target.rmdir()
        pu.remove_path(str(link))
        self.assertFalse(os.path.lexists(str(link)))


if __name__ == "__main__":
    unittest.main()
