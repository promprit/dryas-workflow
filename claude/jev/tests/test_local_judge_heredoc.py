import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import local_judge
from test_local_judge_parity import _timed, assert_fast


def decision(cmd):
    return local_judge.gate_answers("Bash", cmd, True)["decision"] or "none"



class HeredocTest(unittest.TestCase):
    def check(self, cmds, want):
        for cmd in cmds:
            with self.subTest(cmd=cmd):
                self.assertEqual(decision(cmd), want, cmd)

    def test_heredoc_body_is_not_judged(self):
        body = "rm -rf /\ngit reset --hard\n"
        self.check((
            "cat > notes.md <<'EOF'\n" + body + "EOF",
            "cat > notes.md <<EOF\n" + body + "EOF",
            'cat > notes.md <<"EOF"\n' + body + "EOF",
            "cat > notes.md <<-EOF\n\t" + body.replace("\n", "\n\t") + "EOF",
            "python3 - <<'PY'\nimport os\nos.system(\"rm -rf /\")\nPY",
        ), "none")

    def test_command_around_the_heredoc_is_judged(self):
        self.check((
            "cat <<EOF\nx\nEOF\nrm -rf /",
            "bash <<EOF\nrm -rf /\nEOF",
        ), "deny")
        self.check(("cat <<EOF > x\nhi\nEOF\ngit reset --hard",), "ask")

    def test_here_string_is_not_a_heredoc(self):
        self.check(('cat <<< "rm -rf /"',), "none")
        self.check(('bash <<< "rm -rf /"',), "deny")

    def test_arithmetic_shift_is_not_a_heredoc(self):
        self.check((
            "x=$((1<<2))\nrm -rf /",
            "((x=1<<2))\nrm -rf /",
            "echo $(( (1<<2) ))\nrm -rf /",
        ), "deny")
        self.check(("(cat <<EOF\nrm -rf /\nEOF\n)",), "none")

    def test_unterminated_heredoc_is_body(self):
        self.check(("cat <<EOF\nrm -rf /",), "none")

    def test_perf(self):
        cases = (
            ("heredoc body rm -rf x7000", "cat <<EOF\n" + "rm -rf /\n" * 7000 + "EOF\n"),
            ("<<A x15000", "<<A " * 15000),
        )
        for name, cmd in cases:
            with self.subTest(case=name):
                hung, box = _timed(cmd)
                self.assertFalse(hung, name + ": still running after 2 s")
                if "err" in box:
                    raise box["err"]
                assert_fast(self, name, box)


if __name__ == "__main__":
    unittest.main()
