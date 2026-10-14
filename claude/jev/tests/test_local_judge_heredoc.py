import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import local_judge


def decision(cmd):
    return local_judge.gate_answers("Bash", cmd, True)["decision"] or "none"


JEV_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Copied from test_local_judge_parity.py: a backtracking `re` match holds the GIL, so the call
# runs in a child process killed after the limit; the child times the call itself.
_CHILD = (
    "import json, sys, time\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import local_judge\n"
    "cmd = sys.stdin.read()\n"
    "start = time.perf_counter()\n"
    "res = local_judge.gate_answers('Bash', cmd, True)\n"
    "secs = time.perf_counter() - start\n"
    "print(json.dumps({'secs': secs, 'res': res}))\n"
)


def _timed(cmd, limit=2.0):
    """Return (hung, box) where box has 'secs' and 'res', or 'err' if the child failed."""
    try:
        p = subprocess.run([sys.executable, "-c", _CHILD, JEV_DIR], input=cmd, capture_output=True,
                           text=True, timeout=limit)
    except subprocess.TimeoutExpired:
        return True, {}
    if p.returncode != 0:
        return False, {"err": AssertionError(p.stderr.strip()[-2000:])}
    return False, json.loads(p.stdout)


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
                self.assertLess(box["secs"], 0.25, "%s took %.3f s" % (name, box["secs"]))


if __name__ == "__main__":
    unittest.main()
