import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate
import local_judge

T = {"deny_safe_below": 0.2, "min_confidence": 0.7, "ask_risk": "destructive"}


def decision(cmd):
    d = gate.decide(local_judge.gate_answers("Bash", cmd, True)["answers"], T)
    return d[0] if d else "none"


class LocalJudgeCasesTest(unittest.TestCase):
    def check(self, expected, cmds):
        for cmd in cmds:
            self.assertEqual(decision(cmd), expected, cmd)

    def test_sql_drop_needs_an_object_name(self):
        self.check("none", ['echo "drop table" > notes.md'])
        self.check("ask", ["psql -c 'DROP TABLE users'", 'psql -c "DROP TABLE IF EXISTS users"',
                           "sqlite3 a.db 'drop database [app]'", "psql -c 'truncate table logs'"])

    def test_plus_refspec_force_push_asks(self):
        self.check("ask", ["git push origin +main"])
        self.check("none", ["git push origin main", 'git commit -m "a + b"',
                            "git push origin feat --follow-tags"])

    def test_git_clean_dry_run_gets_no_decision(self):
        self.check("none", ["git clean -n -f", "git clean -nf", "git clean --dry-run -fd"])
        self.check("ask", ["git clean -fd", "git clean -fdx"])

    def test_whole_user_home_is_denied_but_subfolders_are_not(self):
        self.check("deny", ["rm -rf /Users/someone", "rm -rf /home/someone/"])
        self.check("none", ["rm -rf /Users/someone/projects/tmp", "rm -rf /home/someone/tmp", "rm -rf /tmp/x"])

    def test_everyday_commands_checked_by_hand(self):
        self.check("none", ["rm -rf ./node_modules/.cache", "git push origin HEAD:refs/heads/x",
                            "git log --format=%H", "rm -r ~/projects/tmp"])


if __name__ == "__main__":
    unittest.main()
