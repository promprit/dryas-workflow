import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate

AL = ["ls", "cat", "head", "tail", "wc", "pwd", "git status", "git diff", "git log", "git show",
      "pytest", "python3 -m pytest", "cd", "grep"]
CWD = "/x"

SKIP = {
    "cd /x && git status 2>&1 | tail -3": 3,
    "cd x&&git status": 2,
    "ls; pwd": 2,
    "ls || pwd": 2,
    "git status >/dev/null": 1,
    "git status 2>/dev/null && ls": 2,
    "git status 2>&1": 1,
    "cd 'my dir' && ls": 2,
    "cd \"a'b\" && ls": 2,
    "grep -rn foo . | head -5": 2,
    "cd x\t&&\tls": 2,
    "ls;ls;ls;ls;ls;ls;ls;ls": 8,
    "cd /x && python3 -m pytest -q 2>&1 | tail -1": 3,
    "cd /x/sub && ls": 2,
    "cd /x && git status": 2,
}

JUDGE = [
    "ls | sh", "cd /x && git push", "grep -r x . > out.txt", 'git log --format="%h|%s"', "cat a; rm -rf b",
    "ls &", "cat <(ls)", "ls >(cat)", "ls >| f", "ls &> f", "ls |& cat", "ls \\; pwd", "ls\npwd", "ls\rpwd",
    "ls;;pwd", "ls &&", "; ls", "ls;ls;ls;ls;ls;ls;ls;ls;ls", "ls '2>&1'", "ls >/dev/nullx", "ls 2>&1x",
    "ls >& /dev/null", "", "   ", "ls；rm -rf x", "ls $'a;b'", 'ls "$(rm x)"', "ls `rm x`", "ls $(pwd)",
    "cat <<EOF", "ls 'unclosed && pwd", "git status --output=x && ls", "git -c core.pager=sh log && ls",
    "ls 2>&1 &", "FOO=1 ls && pwd",
    "ls # x; pwd",
    "ls ${x:=--output=f} && git log $x", "git diff {--output=Y,HEAD} && ls", "git diff ${x:---output=Y} && ls",
    "git diff $'--output=Y' && ls", "\x0bls && pwd", "ls\xa0 && pwd", "ls\x00 && pwd", "ls * && pwd",
    "cd ~ && ls", "cd /tmp && pytest", "cd .. && ls", "cd - && ls", "cd && ls", "cd a && cd ../.. && ls",
    "cd -P a && ls",
]

FORBIDDEN = set(";&|<>()`\\\n\r")


def _no_cdpath(test):
    """Remove CDPATH for the test's duration; the developer's shell may set it."""
    patcher = mock.patch.dict(os.environ)
    patcher.start()
    test.addCleanup(patcher.stop)
    os.environ.pop("CDPATH", None)


class SplitTest(unittest.TestCase):
    def setUp(self):
        _no_cdpath(self)

    def test_skip_cases(self):
        for cmd, n in SKIP.items():
            self.assertEqual(gate.allowlisted_compound(cmd, AL, CWD), (True, n), repr(cmd))

    def test_judge_cases(self):
        for cmd in JUDGE:
            self.assertEqual(gate.allowlisted_compound(cmd, AL, CWD)[0], False, repr(cmd))

    def test_skipped_parts_are_clean_and_allowlisted(self):
        for cmd in SKIP:
            parts = gate.split_compound(cmd)
            self.assertIsNotNone(parts, repr(cmd))
            for p in parts:
                self.assertTrue(gate.allowlisted(p, AL), (cmd, p))
                self.assertFalse(FORBIDDEN & set(p), (cmd, p))
                self.assertNotIn("$(", p, (cmd, p))
            rest = cmd
            for tok in ("2>/dev/null", "2>&1", ">/dev/null"):
                rest = rest.replace(tok, "")
            for p in parts:
                self.assertIn(p, rest, (cmd, p))

    def test_split_returns_parts(self):
        self.assertEqual(gate.split_compound("cd /x && git status 2>&1 | tail -3"), ["cd /x", "git status", "tail -3"])
        self.assertIsNone(gate.split_compound("ls;" * 9 + "ls"))


class RunTest(unittest.TestCase):
    def setUp(self):
        _no_cdpath(self)
        self.tmp = tempfile.mkdtemp()
        os.environ["JEV_LOG_DIR"] = os.path.join(self.tmp, "logs")
        os.environ["JEV_SSD_ROOT"] = self.tmp
        self.calls = []

    def thresholds(self, **gate_cfg):
        p = os.path.join(self.tmp, "th.json")
        with open(p, "w") as f:
            json.dump({"gate": dict({"allowlist": AL}, **gate_cfg)}, f)
        os.environ["JEV_THRESHOLDS"] = p

    def judge(self, state, questions):
        self.calls.append(state)
        return {"answers": {"safe": {"type": "noul", "value": 0.9, "confidence": 0.9},
                            "risk": {"type": "choice", "value": "routine", "confidence": 0.9, "probabilities": {}}},
                "latency_ms": 1, "input_tokens": 1, "cost": 0.0}

    def bash(self, cmd):
        return {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": self.tmp}

    def records(self):
        with open(os.path.join(self.tmp, "logs", "gate.jsonl")) as f:
            return [json.loads(l) for l in f]

    def test_compound_skip_logs_parts(self):
        self.thresholds()
        self.assertIsNone(gate.run(self.bash("cd x && ls | head -1"), judge_fn=self.judge))
        self.assertEqual(self.calls, [])
        rec = self.records()[-1]
        self.assertEqual((rec["decision"], rec["parts"]), ("skipped", 3))

    def test_single_skip_has_no_parts_field(self):
        self.thresholds()
        gate.run(self.bash("ls"), judge_fn=self.judge)
        self.assertNotIn("parts", self.records()[-1])

    def test_kill_switch_judges_compound(self):
        self.thresholds(compound=False)
        gate.run(self.bash("cd x && ls"), judge_fn=self.judge)
        self.assertEqual(len(self.calls), 1)
        gate.run(self.bash("ls"), judge_fn=self.judge)
        self.assertEqual(len(self.calls), 1)  # single allowlisted command still skipped

    def test_single_expansion_now_judged(self):
        self.thresholds()
        gate.run(self.bash("git diff ${x:---output=f}"), judge_fn=self.judge)
        self.assertEqual(len(self.calls), 1)

    def test_single_glob_now_judged(self):
        self.thresholds()
        gate.run(self.bash("ls *"), judge_fn=self.judge)
        self.assertEqual(len(self.calls), 1)

    def test_single_plain_still_skipped(self):
        self.thresholds()
        gate.run(self.bash("ls"), judge_fn=self.judge)
        self.assertEqual(self.calls, [])

    def test_cd_outside_cwd_judged(self):
        self.thresholds()
        outside = tempfile.mkdtemp()
        gate.run(self.bash("cd %s && ls" % outside), judge_fn=self.judge)
        self.assertEqual(len(self.calls), 1)

    def test_cd_inside_cwd_skipped(self):
        self.thresholds()
        os.mkdir(os.path.join(self.tmp, "sub"))
        gate.run(self.bash("cd sub && ls"), judge_fn=self.judge)
        self.assertEqual(self.calls, [])

    def test_single_backslash_now_judged(self):
        self.thresholds()
        gate.run(self.bash("ls \\foo"), judge_fn=self.judge)  # backslash is not a plain character
        self.assertEqual(len(self.calls), 1)


class CdEdgeTest(unittest.TestCase):
    def setUp(self):
        _no_cdpath(self)
        self.root = os.path.realpath(tempfile.mkdtemp())
        os.makedirs(os.path.join(self.root, "a", "b"))
        os.mkdir(os.path.join(self.root, "sub"))

    def test_cd_symlink_dotdot_escape_judged(self):
        # bash/zsh resolve l/../.. logically: l/.. is root, root/.. is outside.
        os.symlink(os.path.join(self.root, "a", "b"), os.path.join(self.root, "l"))
        self.assertFalse(gate.allowlisted_compound("cd l/../.. && pwd", AL, self.root)[0])

    def test_cd_symlink_outside_judged(self):
        outside = os.path.realpath(tempfile.mkdtemp())
        os.symlink(outside, os.path.join(self.root, "l2"))
        self.assertFalse(gate.allowlisted_compound("cd l2 && ls", AL, self.root)[0])

    def test_cd_dotdot_inside_judged(self):
        self.assertFalse(gate.allowlisted_compound("cd a/../b && ls", AL, self.root)[0])

    def test_cdpath_set_judges_cd(self):
        self.assertEqual(gate.allowlisted_compound("cd sub && ls", AL, self.root), (True, 2))
        with mock.patch.dict(os.environ, {"CDPATH": "/tmp"}):
            self.assertFalse(gate.allowlisted_compound("cd sub && ls", AL, self.root)[0])

    def test_cwd_root_skipped_only_without_cdpath(self):
        self.assertEqual(gate.allowlisted_compound("cd tmp && ls", AL, "/"), (True, 2))
        with mock.patch.dict(os.environ, {"CDPATH": ".:/x"}):
            self.assertFalse(gate.allowlisted_compound("cd tmp && ls", AL, "/")[0])

    def test_cwd_trailing_slash_skipped(self):
        self.assertEqual(gate.allowlisted_compound("cd sub && ls", AL, "/x/"), (True, 2))
