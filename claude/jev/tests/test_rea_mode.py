import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import rea_mode  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))


class ReaModeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.cfg = os.path.join(self.tmp, "cfg")
        os.makedirs(self.cfg)
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, "sub"))
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self.env = {"CLAUDE_CONFIG_DIR": self.cfg, "PATH": os.environ.get("PATH", "")}
        self.calls = []

    def write_config(self, top=None, project=None):
        d = {"mcpServers": top or {}, "projects": {}}
        if project is not None:
            d["projects"][self.repo] = {"mcpServers": project}
        with open(os.path.join(self.cfg, ".claude.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def run_main(self, *argv, rc=0, cwd=None):
        def fake(cmd, cwd=None, env=None):
            self.calls.append((cmd, cwd))
            return rc
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = rea_mode.main(list(argv), env=self.env, cwd=cwd or os.path.join(self.repo, "sub"), run=fake)
        return code, buf.getvalue()

    def test_version_matches_installer(self):
        sys.path.insert(0, os.path.join(REPO, "install"))
        import rea_setup
        self.assertEqual(rea_mode.VERSION, rea_setup.VERSION)

    def test_argv(self):
        self.assertEqual(rea_mode.on_argv(), ["claude", "mcp", "add", "--scope", "local", "rea", "--",
                                              "npx", "-y", "rea-agents@" + rea_mode.VERSION, "mcp"])
        self.assertEqual(rea_mode.off_argv(), ["claude", "mcp", "remove", "--scope", "local", "rea"])

    def test_project_key_is_git_root(self):
        self.assertEqual(rea_mode.project_key(os.path.join(self.repo, "sub")), self.repo)

    def test_project_key_outside_git_is_the_folder(self):
        d = os.path.join(self.tmp, "plain")
        os.makedirs(d)
        self.assertEqual(rea_mode.project_key(d), d)

    def test_config_file_default_account(self):
        self.assertEqual(rea_mode.config_file({"HOME": "/h"}), os.path.join(os.path.expanduser("~"), ".claude.json"))
        self.assertEqual(rea_mode.config_file({"CLAUDE_CONFIG_DIR": self.cfg}), os.path.join(self.cfg, ".claude.json"))

    def test_state(self):
        sub = os.path.join(self.repo, "sub")
        self.assertEqual(rea_mode.state(self.env, sub), "off")  # no config file yet
        self.write_config(project={"rea": {"command": "npx"}})
        self.assertEqual(rea_mode.state(self.env, sub), "project")
        self.write_config(top={"rea": {"command": "npx"}})
        self.assertEqual(rea_mode.state(self.env, sub), "user")
        with open(os.path.join(self.cfg, ".claude.json"), "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertEqual(rea_mode.state(self.env, sub), "off")

    def test_on_adds_local_server_at_git_root_and_says_restart(self):
        self.write_config()
        code, out = self.run_main("on")
        self.assertEqual(code, 0)
        self.assertEqual(self.calls, [(rea_mode.on_argv(), self.repo)])
        self.assertIn("claude --continue", out)

    def test_on_when_already_on_does_nothing(self):
        self.write_config(project={"rea": {}})
        code, out = self.run_main("on")
        self.assertEqual((code, self.calls), (0, []))
        self.assertIn("already on", out)

    def test_on_when_user_scope_says_so(self):
        self.write_config(top={"rea": {}})
        code, out = self.run_main("on")
        self.assertEqual((code, self.calls), (0, []))
        self.assertIn("every session", out)

    def test_on_failure_returns_its_code(self):
        self.write_config()
        code, out = self.run_main("on", rc=3)
        self.assertEqual(code, 3)
        self.assertNotIn("claude --continue", out)

    def test_off_removes_local_server(self):
        self.write_config(project={"rea": {}})
        code, _ = self.run_main("off")
        self.assertEqual((code, self.calls), (0, [(rea_mode.off_argv(), self.repo)]))

    def test_off_when_off_does_nothing(self):
        self.write_config()
        code, out = self.run_main("off")
        self.assertEqual((code, self.calls), (0, []))
        self.assertIn("already off", out)

    def test_off_when_user_scope_names_the_command(self):
        self.write_config(top={"rea": {}})
        code, out = self.run_main("off")
        self.assertEqual(self.calls, [])
        self.assertIn("claude mcp remove --scope user rea", out)

    def test_status(self):
        self.write_config(project={"rea": {}})
        code, out = self.run_main("status")
        self.assertEqual((code, self.calls), (0, []))
        self.assertIn("on in " + self.repo, out)

    def test_leading_rea_word_is_dropped(self):
        self.write_config(project={"rea": {}})
        code, out = self.run_main("rea", "status")
        self.assertEqual(code, 0)
        self.assertIn("on in", out)

    def test_usage(self):
        code, out = self.run_main("bogus")
        self.assertEqual(code, 2)
        self.assertIn("dryas rea {on|off|status}", out)

    def test_dryas_entry_dispatches_rea(self):
        with open(os.path.join(REPO, "claude", "bin", "dryas"), encoding="utf-8") as f:
            self.assertIn("rea_mode.py", f.read())
        with open(os.path.join(REPO, "claude", "bin", "dryas.cmd"), encoding="utf-8") as f:
            self.assertIn("rea_mode.py", f.read())


if __name__ == "__main__":
    unittest.main()
