import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import local_judge as lj


def one(text, first=None):
    cmds = lj.simple_commands(text)
    return [c for c in cmds if not first or c.words[:1] == [first]][0]


class RedirsTest(unittest.TestCase):
    def test_output_operators(self):
        c = one("echo a > f >> g 2>&1 &> h &>> i >| j")
        self.assertEqual(list(zip(c.rops, c.redirs)),
                         [(">", "f"), (">>", "g"), (">&", "1"), ("&>", "h"), ("&>>", "i"), (">|", "j")])

    def test_input_and_heredoc_operators(self):
        c = one("cat < in <<EOF\nbody > x\nEOF")
        self.assertEqual(list(zip(c.rops, c.redirs)), [("<", "in"), ("<<", "EOF")])
        self.assertEqual(c.here, ["body > x"])

    def test_quoted_target_is_one_word(self):
        c = one('echo hi > "my file.txt"')
        self.assertEqual((c.rops, c.redirs, c.rdyn), ([">"], ["my file.txt"], [False]))

    def test_dynamic_target(self):
        c = one('echo x > "$(pwd)/f"', "echo")
        self.assertEqual((c.rops, c.rdyn), ([">"], [True]))

    def test_arrow_in_heredoc_body_is_data(self):
        c = one("python3 - <<'EOF'\nf = lambda: a => {}\nEOF")
        self.assertEqual(c.rops, ["<<"])

    def test_too_long_raises(self):
        with self.assertRaises(ValueError):
            lj.simple_commands("a" * (lj.MAX_CHARS + 1))

    def test_public_helpers(self):
        self.assertEqual(lj.head_index(["sudo", "env", "X=1", "rm", "x"]), (3, False))
        self.assertEqual(lj.base("/bin/rm"), "rm")
        self.assertEqual(lj.shell_string(["-c", "rm x"]), "rm x")


if __name__ == "__main__":
    unittest.main()
