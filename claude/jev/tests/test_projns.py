import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import projns

CASES = Path(__file__).resolve().parents[2] / "ruflo" / "tests" / "ns_cases.json"


def git(*args, cwd):
    subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=t"] + list(args), cwd=str(cwd), check=True,
                   capture_output=True)


class ProjNsTest(unittest.TestCase):
    def test_shared_vectors_match_ruflo_rules(self):
        for c in json.loads(CASES.read_text(encoding="utf-8")):
            self.assertEqual(projns.ns_from(c["start"], c["common"]), c["expect"], c)

    def test_worktree_maps_to_main_repo(self):
        repo = Path(tempfile.mkdtemp()) / "myrepo"
        repo.mkdir()
        git("init", "-q", cwd=repo)
        git("commit", "-q", "--allow-empty", "-m", "i", cwd=repo)
        git("worktree", "add", "-q", ".worktrees/wt", "-b", "wt", cwd=repo)
        wt = repo / ".worktrees" / "wt"
        self.assertEqual(projns.project_ns(str(wt)), "myrepo")
        self.assertEqual(os.path.realpath(projns.main_root(str(wt))), os.path.realpath(str(repo)))
        self.assertIsNone(projns.main_root(tempfile.mkdtemp()))

    def test_sanitize(self):
        self.assertEqual(projns.sanitize("my app"), "my_app")
        self.assertEqual(projns.sanitize(""), "_unknown")
        self.assertEqual(projns.sanitize(".."), "_unknown")

    def test_project_ns_uses_claude_project_dir(self):
        plain = Path(tempfile.mkdtemp()) / "plain"
        plain.mkdir()
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(plain)}):
            self.assertEqual(projns.project_ns(), "plain")
