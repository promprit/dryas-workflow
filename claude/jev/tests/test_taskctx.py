import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import taskctx


class TaskCtxTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, ".orchestrate"))
        os.makedirs(os.path.join(self.root, "src"))

    def active(self, data):
        with open(os.path.join(self.root, ".orchestrate", "active.json"), "w") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))

    def git_dir(self, head="ref: refs/heads/feat/x\n"):
        os.makedirs(os.path.join(self.root, ".git"))
        with open(os.path.join(self.root, ".git", "HEAD"), "w") as f:
            f.write(head)

    def git_file(self, head="ref: refs/heads/feat/wt\n"):
        gd = os.path.join(tempfile.mkdtemp(), "worktrees", "wt")
        os.makedirs(gd)
        with open(os.path.join(gd, "HEAD"), "w") as f:
            f.write(head)
        with open(os.path.join(self.root, ".git"), "w") as f:
            f.write("gitdir: %s\n" % gd)

    def test_single_task_with_branch_from_git_dir(self):
        self.git_dir()
        self.active({"active": ["3"]})
        self.assertEqual(taskctx.context(os.path.join(self.root, "src")), {"task": "feat/x:3"})

    def test_worktree_gitdir_file(self):
        self.git_file()
        self.active({"active": [2]})
        self.assertEqual(taskctx.context(self.root), {"task": "feat/wt:2"})

    def test_several_tasks(self):
        self.git_dir()
        self.active({"active": ["1", "2"]})
        self.assertEqual(taskctx.context(self.root), {"tasks": ["feat/x:1", "feat/x:2"]})

    def test_detached_head_uses_question_mark(self):
        self.git_dir("0123abcd\n")
        self.active({"active": ["1"]})
        self.assertEqual(taskctx.context(self.root), {"task": "?:1"})

    def test_nothing_active_or_malformed_is_empty(self):
        self.assertEqual(taskctx.context(tempfile.mkdtemp()), {})
        for bad in ({"active": []}, "{not json", {"active": "1"}, [1, 2]):
            self.active(bad)
            self.assertEqual(taskctx.context(self.root), {}, bad)
