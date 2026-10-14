import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import taskctx


def make_root(path, ids, git=True):
    os.makedirs(os.path.join(path, ".orchestrate"), exist_ok=True)
    with open(os.path.join(path, ".orchestrate", "active.json"), "w") as f:
        json.dump({"active": ids}, f)
    if git:
        os.makedirs(os.path.join(path, ".git"), exist_ok=True)
        with open(os.path.join(path, ".git", "HEAD"), "w") as f:
            f.write("ref: refs/heads/feat/x\n")


class TaskCtxPathsTest(unittest.TestCase):
    def setUp(self):
        self.base = os.path.realpath(tempfile.mkdtemp())

    def test_symlinked_cwd_resolves_to_real_root(self):
        real = os.path.join(self.base, "real")
        make_root(real, ["3"])
        os.makedirs(os.path.join(real, "src"))
        other = os.path.join(self.base, "elsewhere")
        os.makedirs(other)
        link = os.path.join(other, "link")
        os.symlink(os.path.join(real, "src"), link)
        self.assertEqual(taskctx.context(link), {"task": "feat/x:3"})

    def test_stale_ancestor_active_json_is_ignored(self):
        make_root(self.base, ["9"], git=False)
        repo = os.path.join(self.base, "repo")
        os.makedirs(os.path.join(repo, ".git"))
        os.makedirs(os.path.join(repo, "src"))
        self.assertEqual(taskctx.context(os.path.join(repo, "src")), {})

    def test_nested_worktree_root_with_own_active_wins(self):
        make_root(self.base, ["1"])
        inner = os.path.join(self.base, "wt")
        make_root(inner, ["7"])
        os.makedirs(os.path.join(inner, "src"))
        self.assertEqual(taskctx.context(os.path.join(inner, "src")), {"task": "feat/x:7"})


if __name__ == "__main__":
    unittest.main()
