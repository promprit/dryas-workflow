import os, shutil, sys, tempfile, unittest
from unittest import mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import platform_util as pu


class PlatformUtilTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def test_fwd(self):
        self.assertEqual(pu.fwd("C:\\a\\b c\\d"), "C:/a/b c/d")
        self.assertEqual(pu.fwd("/x/y"), "/x/y")

    def test_python_exe_is_forward_slash_sys_executable(self):
        self.assertEqual(pu.python_exe(), sys.executable.replace("\\", "/"))

    def _reset(self):
        pu._PYTHON_EXE = None
        self.addCleanup(setattr, pu, "_PYTHON_EXE", None)
        old = os.environ.get("DRYAS_PYTHON_PATH")
        def restore():
            if old is None:
                os.environ.pop("DRYAS_PYTHON_PATH", None)
            else:
                os.environ["DRYAS_PYTHON_PATH"] = old
        self.addCleanup(restore)

    def test_python_exe_prefers_launch_path(self):
        self._reset()
        link = self.tmp / "py3link"
        try:
            os.symlink(sys.executable, str(link))
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        os.environ["DRYAS_PYTHON_PATH"] = str(link)
        self.assertEqual(pu.python_exe(), str(link).replace("\\", "/"))

    def test_python_exe_missing_launch_path_falls_back(self):
        self._reset()
        os.environ["DRYAS_PYTHON_PATH"] = str(self.tmp / "nope")
        self.assertEqual(pu.python_exe(), sys.executable.replace("\\", "/"))

    @unittest.skipIf(os.name == "nt", "shell script stub")
    def test_python_exe_wrong_version_falls_back(self):
        self._reset()
        fake = self.tmp / "fakepy"
        fake.write_text("#!/bin/sh\necho 2.7\n")
        fake.chmod(0o755)
        os.environ["DRYAS_PYTHON_PATH"] = str(fake)
        self.assertEqual(pu.python_exe(), sys.executable.replace("\\", "/"))

    def test_space_free_without_space_is_identity(self):
        self.assertEqual(pu.space_free("/a/b"), "/a/b")

    @unittest.skipIf(os.name == "nt", "POSIX has no short names")
    def test_space_free_with_space_is_none_on_posix(self):
        self.assertIsNone(pu.space_free(str(self.tmp / "a b")))

    @unittest.skipUnless(os.name == "nt", "Windows short names")
    def test_space_free_windows_short_name_or_none(self):
        d = self.tmp / "with space"
        d.mkdir()
        got = pu.space_free(str(d))
        self.assertTrue(got is None or " " not in got)

    def test_which_and_resolve_argv(self):
        git = pu.which("git")
        self.assertTrue(git)
        self.assertEqual(pu.resolve_argv(["git", "--version"]), [git, "--version"])
        self.assertEqual(pu.resolve_argv(["no-such-tool-xyz", "a"]), ["no-such-tool-xyz", "a"])
        self.assertEqual(pu.resolve_argv([]), [])

    def test_dir_link_roundtrip(self):
        target = self.tmp / "target"
        target.mkdir()
        (target / "f.txt").write_text("x", encoding="utf-8")
        dest = self.tmp / "link"
        kind = pu.make_dir_link(str(target), str(dest))
        self.assertIn(kind, ("symlink", "junction"))
        self.assertTrue((dest / "f.txt").exists())
        self.assertTrue(pu.same_path(pu.read_dir_link(str(dest)), str(target)))
        pu.remove_path(str(dest))
        self.assertFalse(os.path.lexists(str(dest)))
        self.assertTrue((target / "f.txt").exists())

    def test_read_dir_link_of_plain_dir_is_none(self):
        self.assertIsNone(pu.read_dir_link(str(self.tmp)))

    def test_remove_path_file_and_missing(self):
        f = self.tmp / "f"
        f.write_text("x", encoding="utf-8")
        pu.remove_path(str(f))
        self.assertFalse(f.exists())
        pu.remove_path(str(f))  # missing: no error

    def test_remove_dangling_dir_link(self):
        target, link = self.tmp / "t", self.tmp / "l"
        target.mkdir()
        try:
            pu.make_dir_link(str(target), str(link))
        except OSError:
            self.skipTest("cannot create dir links")
        target.rmdir()
        pu.remove_path(str(link))
        self.assertFalse(os.path.lexists(str(link)))


class ReadRulePathTest(unittest.TestCase):
    def test_posix(self):
        self.assertEqual(pu.read_rule_path("/a/b/.dryas"), "//a/b/.dryas")

    def test_windows_drive(self):
        self.assertEqual(pu.read_rule_path("C:/Users/x/.dryas"), "//c/Users/x/.dryas")
        self.assertEqual(pu.read_rule_path("D:\\Data\\root"), "//d/Data/root")


class ClaudeEnvTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, str(self.home), True)
        env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home))
        env.pop("CLAUDE_CONFIG_DIR", None)
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)
        h = mock.patch.object(Path, "home", classmethod(lambda cls: self.home))
        h.start()
        self.addCleanup(h.stop)
        self.default = self.home / ".claude"

    def test_claude_env_default_dir_drops_var(self):
        env = pu.claude_env(self.default, {"PATH": "/bin"})
        self.assertNotIn("CLAUDE_CONFIG_DIR", env)
        self.assertEqual(env["PATH"], "/bin")

    def test_claude_env_default_dir_drops_var_from_process_env(self):
        self.assertNotIn("CLAUDE_CONFIG_DIR", pu.claude_env(self.default))

    def test_claude_env_custom_dir_sets_var(self):
        cd = self.home / "other"
        self.assertEqual(pu.claude_env(cd, {})["CLAUDE_CONFIG_DIR"], str(cd))

    def test_claude_env_user_set_var_kept_even_for_default_dir(self):
        base = {"CLAUDE_CONFIG_DIR": str(self.default)}
        self.assertEqual(pu.claude_env(self.default, base)["CLAUDE_CONFIG_DIR"], str(self.default))

    def test_claude_env_exported_other_dir_dropped_for_default_dir(self):
        base = {"CLAUDE_CONFIG_DIR": str(self.home / "elsewhere"), "PATH": "/bin"}
        self.assertNotIn("CLAUDE_CONFIG_DIR", pu.claude_env(self.default, base))

    def test_claude_env_user_set_var_uses_cd(self):
        cd = self.home / "other"
        base = {"CLAUDE_CONFIG_DIR": str(self.home / "elsewhere")}
        self.assertEqual(pu.claude_env(cd, base)["CLAUDE_CONFIG_DIR"], str(cd))

    def test_claude_env_empty_var_counts_as_unset(self):
        self.assertNotIn("CLAUDE_CONFIG_DIR", pu.claude_env(self.default, {"CLAUDE_CONFIG_DIR": ""}))

    def test_claude_env_base_arg_overrides_os_environ(self):
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.home / "x")
        self.assertNotIn("CLAUDE_CONFIG_DIR", pu.claude_env(self.default, {}))

    def test_claude_env_does_not_mutate_base(self):
        base = {"CLAUDE_CONFIG_DIR": str(self.default)}
        pu.claude_env(self.home / "other", base)
        self.assertEqual(base["CLAUDE_CONFIG_DIR"], str(self.default))

    def test_claude_global_config_default_dir(self):
        self.assertEqual(pu.claude_global_config(self.default, {}), self.home / ".claude.json")

    def test_claude_global_config_custom_dir(self):
        cd = self.home / "other"
        self.assertEqual(pu.claude_global_config(cd, {}), cd / ".claude.json")

    def _jev(self, command="python3", args=()):
        import json
        (self.home / ".claude.json").write_text(json.dumps({"mcpServers": {"jev": {"command": command, "args": list(args)}}}),
                                                encoding="utf-8")

    def test_stale_jev_returns_missing_path(self):
        missing = self.default / "jev" / "jev_mcp.py"
        self._jev(args=[str(missing)])
        self.assertEqual(pu.stale_jev(self.default, {})[0], pu.fwd(missing))

    def test_stale_jev_none_when_file_exists(self):
        f = self.default / "jev" / "jev_mcp.py"
        f.parent.mkdir(parents=True)
        f.write_text("", encoding="utf-8")
        self._jev(args=[str(f)])
        self.assertIsNone(pu.stale_jev(self.default, {}))

    def test_stale_jev_none_for_users_own_server(self):
        self._jev(args=["/opt/mine/jev_mcp.py"])
        self.assertIsNone(pu.stale_jev(self.default, {}))

    def test_stale_jev_none_without_valid_config(self):
        self.assertIsNone(pu.stale_jev(self.default, {}))
        (self.home / ".claude.json").write_text("{not json", encoding="utf-8")
        self.assertIsNone(pu.stale_jev(self.default, {}))
        (self.home / ".claude.json").write_text("[]", encoding="utf-8")
        self.assertIsNone(pu.stale_jev(self.default, {}))

    def test_stale_jev_matches_windows_backslashes(self):
        self._jev(args=["C:\\Users\\x\\.claude\\jev\\jev_mcp.py"])
        self.assertEqual(pu.stale_jev(self.default, {})[0], "C:/Users/x/.claude/jev/jev_mcp.py")

    def test_stale_jev_matches_custom_dir_named_dot_claude(self):
        missing = self.home / "work" / ".claude" / "jev" / "jev_mcp.py"
        self._jev(command=str(missing))
        self.assertEqual(pu.stale_jev(self.default, {})[0], pu.fwd(missing))

    def test_stale_jev_custom_dir_entry_in_home_config(self):
        cd = self.home / ".claude-team"
        missing = cd / "jev" / "jev_mcp.py"
        self._jev(args=[str(missing)])
        path, env = pu.stale_jev(cd, {"PATH": "/bin"})
        self.assertEqual(path, pu.fwd(missing))
        self.assertNotIn("CLAUDE_CONFIG_DIR", env)  # the entry lives in ~/.claude.json

    def test_stale_jev_custom_dir_entry_in_its_own_config(self):
        import json
        cd = self.home / ".claude-team"
        cd.mkdir()
        missing = cd / "jev" / "jev_mcp.py"
        (cd / ".claude.json").write_text(json.dumps({"mcpServers": {"jev": {"command": str(missing)}}}), encoding="utf-8")
        path, env = pu.stale_jev(cd, {})
        self.assertEqual(path, pu.fwd(missing))
        self.assertEqual(env["CLAUDE_CONFIG_DIR"], str(cd))

    def test_stale_jev_none_for_other_dirs_script(self):
        self._jev(args=[str(self.home / ".claude-other" / "jev" / "jev_mcp.py")])
        self.assertIsNone(pu.stale_jev(self.home / ".claude-team", {}))

    def test_stale_jev_regex_fallback_for_single_command_string(self):
        missing = self.default / "jev" / "jev_mcp.py"
        self._jev(command="python3 %s" % missing)
        self.assertEqual(pu.stale_jev(self.default, {})[0], pu.fwd(missing))

    def _spaced(self):
        return self.home / "John Smith" / ".claude" / "jev" / "jev_mcp.py"

    def test_stale_jev_spaced_path_existing_is_not_stale(self):
        f = self._spaced()
        f.parent.mkdir(parents=True)
        f.write_text("", encoding="utf-8")
        self._jev(args=[str(f)])
        self.assertIsNone(pu.stale_jev(self.default, {}))

    def test_stale_jev_spaced_path_missing_returns_full_path(self):
        self._jev(args=[str(self._spaced())])
        self.assertEqual(pu.stale_jev(self.default, {})[0], pu.fwd(self._spaced()))

    def test_stale_jev_quoted_spaced_path_in_command_string(self):
        self._jev(command='python3 "%s"' % self._spaced())
        self.assertEqual(pu.stale_jev(self.default, {})[0], pu.fwd(self._spaced()))


if __name__ == "__main__":
    unittest.main()
