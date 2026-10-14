import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate
import local_judge as lj

NOKEY = {"OPENROUTER_API_KEY": "", "DRYAS_OPENROUTER_KEY": "", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": ""}

ASK = {
    "git_checkout_discard": [
        "git checkout -- .", "git checkout .", "git checkout -- src/a.py", "git checkout main -- a.py",
        "git checkout HEAD -- 'src/a b.py'", 'git checkout -- "."', "git 'checkout' -- .", '"git" checkout .',
        "git -C sub checkout -- .", "cd x && git checkout -- .", "sudo git checkout -- .",
        "sh -c 'git checkout -- .'", "/usr/bin/git checkout .",
        "git checkout -f -- .", "env -i git checkout .", "git checkout -- a;git stash clear", "git checkout -B x ."],
    "git_restore_discard": [
        "git restore .", "git restore src/a.py", "git restore -- .", "git restore --worktree a.py",
        "git restore --staged --worktree a.py", "git restore -SW a.py", "git restore --source HEAD~1 a.py",
        "git restore -s main .", "git restore 'a b.py'", 'git restore "."', "env GIT_DIR=.git git restore .",
        "git restore -W .", "command git restore .", "git --git-dir=x restore ."],
    "git_stash_drop": [
        "git stash clear", "git stash drop", "git stash drop stash@{1}", "git stash drop -q",
        "git -c x=y stash clear", 'bash -c "git stash drop"', "git status && git stash clear",
        "git stash 'clear'", "sudo -u root git stash clear", "git -C sub stash drop", "git stash  drop"],
}
NONE = [
    "git checkout main", "git checkout -b feat", "git checkout -b feat origin/main", "git checkout -- ",
    "git checkout -b new .x", "git checkout", "git switch main",
    "git restore --staged a.py", "git restore -S a.py", "git restore --staged .", "git restore",
    "git restore --staged",
    "git stash", "git stash list", "git stash pop", "git stash show -p", "git stash push -m drop",
    "git commit -m 'git checkout -- .'", "echo git restore .", "grep -r 'git stash clear' .",
    "git log -- .", "git diff -- .",
]


class LocalJudgeDiscardTest(unittest.TestCase):
    def test_discarding_work_asks(self):
        for name, cmds in ASK.items():
            for cmd in cmds:
                res = lj.gate_answers("Bash", cmd, True)
                self.assertEqual((res["decision"], res["reasons"]), ("ask", ["destructive:" + name]), cmd)

    def test_never_denies_or_allows(self):
        for cmd in [c for cmds in ASK.values() for c in cmds]:
            self.assertIsNone(lj.danger(cmd), cmd)
            self.assertNotEqual(lj.gate_answers("Bash", cmd, True)["decision"], "deny", cmd)

    def test_keeping_work_gets_no_decision(self):
        for cmd in NONE:
            self.assertIsNone(lj.gate_answers("Bash", cmd, True)["decision"], cmd)

    def test_long_inputs_stay_linear(self):
        for cmd in ("git checkout " + "-- " * 20000 + ".", "git restore " + "a " * 30000,
                    "git stash " + "'x' " * 15000):
            t0 = time.monotonic()
            lj.gate_answers("Bash", cmd, True)
            self.assertLess(time.monotonic() - t0, 2.0, cmd[:40])

    def test_gate_without_key_asks(self):
        tmp = tempfile.mkdtemp()
        env = dict(NOKEY, JEV_LOG_DIR=os.path.join(tmp, "logs"), JEV_SSD_ROOT=tmp,
                   JEV_THRESHOLDS=os.path.join(tmp, "t.json"))
        with mock.patch.dict(os.environ, env):
            out = gate.run({"tool_name": "Bash", "tool_input": {"command": "git restore ."}, "cwd": tmp})
            with open(os.path.join(tmp, "logs", "gate.jsonl")) as f:
                rec = [json.loads(l) for l in f][-1]
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertIn("destructive:git_restore_discard", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual((rec["provider"], rec["decision"]), ("local", "ask"))


if __name__ == "__main__":
    unittest.main()
