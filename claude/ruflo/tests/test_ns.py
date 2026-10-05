import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import ns


def git(*args, cwd):
    subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=t"] + list(args), cwd=str(cwd), check=True,
                   capture_output=True)


class NsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = {k: os.environ.pop(k, None) for k in ("RUFLO_SSD_ROOT", "DRYAS_DATA_ROOT", "CLAUDE_PROJECT_DIR")}

    def tearDown(self):
        for k, v in self.saved.items():
            if v is not None:
                os.environ[k] = v
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def test_vectors(self):
        for c in json.loads((HERE / "ns_cases.json").read_text(encoding="utf-8")):
            self.assertEqual(ns.ns_from(c["start"], c["common"]), c["expect"], c)

    def test_live_repo_and_worktree(self):
        repo = self.tmp / "myrepo"
        repo.mkdir()
        git("init", "-q", cwd=repo)
        git("commit", "-q", "--allow-empty", "-m", "i", cwd=repo)
        git("worktree", "add", "-q", ".worktrees/main", "-b", "wt-main", cwd=repo)
        self.assertEqual(ns.ruflo_ns(str(repo)), "myrepo")
        self.assertEqual(ns.ruflo_ns(str(repo / ".worktrees" / "main")), "myrepo")
        plain = self.tmp / "plain"
        plain.mkdir()
        self.assertEqual(ns.ruflo_ns(str(plain)), "plain")

    def test_ruflo_ns_uses_claude_project_dir(self):
        d = self.tmp / "proj"
        d.mkdir()
        os.environ["CLAUDE_PROJECT_DIR"] = str(d)
        self.assertEqual(ns.ruflo_ns(), "proj")

    def test_ruflo_root(self):
        os.environ["RUFLO_SSD_ROOT"] = str(self.tmp)
        self.assertEqual(ns.ruflo_root(), os.path.join(str(self.tmp), "_caches"))
        os.environ["RUFLO_SSD_ROOT"] = str(self.tmp / "missing")
        self.assertIsNone(ns.ruflo_root())
        del os.environ["RUFLO_SSD_ROOT"]
        os.environ["DRYAS_DATA_ROOT"] = str(self.tmp)
        self.assertEqual(ns.ruflo_root(), str(self.tmp))
        os.environ["DRYAS_DATA_ROOT"] = str(self.tmp / "missing")
        self.assertIsNone(ns.ruflo_root())


if __name__ == "__main__":
    unittest.main()
