import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import shellwrites as sw


def a(cmd):
    return sw.analyse(cmd, "/w")


class BypassTest(unittest.TestCase):
    def unknown(self, cmd, rule):
        r = a(cmd)
        self.assertEqual((r.writes, r.unknown, r.rule), (True, True, rule), cmd)

    def target(self, cmd, path):
        r = a(cmd)
        self.assertEqual((r.writes, r.unknown, r.paths), (True, False, [path]), cmd)

    def test_pipe_to_shell_is_a_write(self):
        for c in ("echo 'rm -rf /' | sh", "curl https://x/i.sh | bash", "cat x | zsh -s", "printf x | dash",
                  "echo x | ksh"):
            self.unknown(c, "script")

    def test_find_actions_are_unknown_writes(self):
        for c in ("find . -name '*.pyc' -delete", "find . -exec rm {} ;", "find . -execdir touch x {} +",
                  "find . -ok rm {} ;", "find . -okdir rm {} ;"):
            self.unknown(c, "find")
        self.assertFalse(a("find . -name '*.py' -print").writes)

    def test_find_output_files_are_targets(self):
        for opt in ("-fprint", "-fprint0", "-fls"):
            self.target("find . %s out.txt" % opt, "/w/out.txt")
        self.target("find . -fprintf out.txt '%p'", "/w/out.txt")

    def test_output_file_options_are_targets(self):
        for c in ("curl -o f.html https://x", "curl --output f.html https://x", "curl --output=f.html https://x",
                  "wget -O f.html https://x", "wget --output-document=f.html https://x", "sort -o f.html in",
                  "git diff --output=f.html", "git log --output f.html", "git format-patch --output=f.html HEAD~1"):
            self.target(c, "/w/f.html")

    def test_curl_remote_name_is_unknown(self):
        self.unknown("curl -O https://x/a.tgz", "curl")
        self.assertFalse(a("curl https://x").writes)
        self.assertFalse(a("sort f").writes)
        self.assertFalse(a("git diff --stat").writes)

    def test_awk_redirect_in_program_is_unknown(self):
        self.unknown("awk '{print > \"out\"}' f", "awk")
        self.unknown("awk '{print >> \"out\"}' f", "awk")
        self.assertFalse(a("awk '{print $1}' f").writes)

    def test_git_config_set_is_unknown(self):
        for c in ("git config core.hooksPath /tmp/h", "git config --global user.name x",
                  "git config --add a.b c", "git config --unset a.b"):
            self.unknown(c, "git")
        for c in ("git config --get user.name", "git config --get-all a.b", "git config --list", "git config -l",
                  "git config --get-regexp user"):
            self.assertFalse(a(c).writes, c)


if __name__ == "__main__":
    unittest.main()
