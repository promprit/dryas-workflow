import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import cloud_fixtures as fx


class EntryTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.base), True)
        self.repo = fx.git_repo(self.base / "repo")
        self.env = dict(os.environ, DRYAS_PYTHON=sys.executable, DRYAS_PY=sys.executable,
                        CLAUDE_CONFIG_DIR=str(self.base / "cfg"))

    def test_installers_route_repo_to_cloud_init(self):
        sh = (ROOT / "install/install.sh").read_text(encoding="utf-8")
        self.assertIn('exec "$c" "$REPO/tools/dryas_cloud.py" init "$@"', sh)
        self.assertIn('run --repo "$REPO" "$@"', sh)  # every other run is the plugin installer, as before
        self.assertLess(sh.index("tools/dryas_cloud.py"), sh.index('run --repo "$REPO"'))
        ps = (ROOT / "install/install.ps1").read_text(encoding="utf-8")
        self.assertIn("tools\\dryas_cloud.py", ps)
        self.assertIn("'-Repo'", ps)
        self.assertIn("run --repo $repo @args", ps)

    @unittest.skipIf(os.name == "nt", "POSIX installer")
    def test_install_sh_with_repo_runs_cloud_init(self):
        before = fx.snapshot(self.repo)
        p = subprocess.run(["sh", str(ROOT / "install/install.sh"), "--repo", str(self.repo)], capture_output=True,
                           text=True, env=self.env, timeout=300)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("dryas cloud init: ", p.stdout)
        self.assertIn("Dry run: nothing written.", p.stdout)
        self.assertEqual(fx.snapshot(self.repo), before)

    def test_wrappers_name_the_checkout_tool(self):
        sh = (ROOT / "claude/bin/dryas").read_text(encoding="utf-8")
        self.assertIn("cloud)", sh)
        self.assertIn("tools/dryas_cloud.py", sh)
        self.assertIn("memory)", sh)  # D's case stays
        cmd = (ROOT / "claude/bin/dryas.cmd").read_text(encoding="utf-8")
        self.assertIn('if /I "%~1"=="cloud" set "DRYAS_SUB=cloud"', cmd)
        self.assertIn('if "%DRYAS_SUB%"=="cloud" goto cloud', cmd)
        self.assertIn("tools\\dryas_cloud.py", cmd)

    @unittest.skipIf(os.name == "nt", "POSIX wrapper")
    def test_dryas_cloud_wrapper(self):
        p = subprocess.run(["sh", str(ROOT / "claude/bin/dryas"), "cloud", "check", "--repo", str(self.repo)],
                           capture_output=True, text=True, env=self.env, timeout=120)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn("no Dryas copy here", p.stdout)
        p = subprocess.run(["sh", str(ROOT / "claude/bin/dryas"), "nope"], capture_output=True, text=True,
                           env=self.env, timeout=60)
        self.assertEqual(p.returncode, 2)
        self.assertIn("usage:", p.stderr)
        self.assertIn("dryas cloud", p.stderr)

    @unittest.skipIf(os.name == "nt", "POSIX wrapper")
    def test_wrapper_without_a_checkout_says_so(self):
        b = self.base / "plugin" / "bin"
        b.mkdir(parents=True)
        for n in ("dryas", "dryas-py"):
            shutil.copy(str(ROOT / "claude/bin" / n), str(b / n))
        p = subprocess.run(["sh", str(b / "dryas"), "cloud", "check"], capture_output=True, text=True, env=self.env,
                           timeout=60)
        self.assertEqual(p.returncode, 2)
        self.assertIn("needs a Dryas checkout", p.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows wrapper")
    def test_dryas_cloud_wrapper_windows(self):
        p = subprocess.run(["cmd", "/c", str(ROOT / "claude/bin/dryas.cmd"), "cloud", "check", "--repo", str(self.repo)],
                           capture_output=True, text=True, env=self.env, timeout=120)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("no Dryas copy here", p.stdout)

    # ---- added: gaps a wrong implementation could still pass ----

    def _sh(self, *args, env=None):
        return subprocess.run(["sh"] + [str(a) for a in args], capture_output=True, text=True,
                              env=env or self.env, timeout=300)

    @unittest.skipIf(os.name == "nt", "POSIX installer")
    def test_install_sh_repo_path_with_spaces_and_equals_form(self):
        spaced = fx.git_repo(self.base / "my repo" / "with spaces")
        before = fx.snapshot(spaced)
        for args in (["--repo", str(spaced)], ["--repo=" + str(spaced)]):
            p = self._sh(ROOT / "install/install.sh", *args)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("dryas cloud init: ", p.stdout)
            self.assertIn("Dry run: nothing written.", p.stdout)
        self.assertEqual(fx.snapshot(spaced), before)

    @unittest.skipIf(os.name == "nt", "POSIX installer")
    def test_install_sh_repo_with_a_missing_value_fails_in_cloud_init(self):
        p = self._sh(ROOT / "install/install.sh", "--repo")
        self.assertEqual(p.returncode, 2)
        self.assertIn("--repo", p.stderr)
        self.assertIn("dryas cloud", p.stderr)  # the cloud CLI's usage, not the plugin installer

    @unittest.skipIf(os.name == "nt", "POSIX installer")
    def test_install_sh_without_repo_still_runs_the_plugin_installer(self):
        p = self._sh(ROOT / "install/install.sh", "--help")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("dryas cloud", p.stdout + p.stderr)

    @unittest.skipIf(os.name == "nt", "POSIX wrapper")
    def test_dryas_cloud_wrapper_passes_every_argument(self):
        spaced = fx.git_repo(self.base / "a b" / "repo x")
        p = self._sh(ROOT / "claude/bin/dryas", "cloud", "init", "--repo", spaced, "--prefix", "my-", "--with-design")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("my-", p.stdout)
        self.assertIn("Dry run: nothing written.", p.stdout)

    @unittest.skipIf(os.name == "nt", "POSIX wrapper")
    def test_dryas_cloud_without_a_subcommand_is_a_usage_error(self):
        p = self._sh(ROOT / "claude/bin/dryas", "cloud")
        self.assertEqual(p.returncode, 2)
        self.assertIn("usage: dryas cloud", p.stderr)
        self.assertNotIn("Traceback", p.stderr)

    @unittest.skipIf(os.name == "nt", "POSIX wrapper")
    def test_dryas_memory_still_works_beside_cloud(self):
        db = self.base / "m.db"
        p = self._sh(ROOT / "claude/bin/dryas", "memory", "--db", db, "stats")
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_cmd_cloud_block_shape(self):
        t = (ROOT / "claude/bin/dryas.cmd").read_text(encoding="utf-8")
        lines = [ln.strip() for ln in t.splitlines()]
        self.assertEqual([ln for ln in lines if ln.startswith("shift")], [])  # %0 stays; nothing is collected or shifted
        i_plain, i_cloud = lines.index(":plain"), lines.index(":cloud")
        self.assertLess(i_plain, i_cloud)
        between = [ln for ln in lines[i_plain + 1:i_cloud] if ln]
        self.assertEqual(between[-1], "exit /b %ERRORLEVEL%")  # :plain never falls into :cloud
        self.assertTrue(between[0].startswith("python -X utf8"))
        self.assertLess(t.index("goto cloud"), t.index(":envpy"))  # dispatch precedes both launcher blocks
        block = "\n".join(lines[i_cloud:])
        self.assertEqual(block.count('.py" %*'), 4)  # all four launchers pass the whole original line
        self.assertNotIn("%1", block)
        self.assertEqual(block.count("exit /b %ERRORLEVEL%"), 4)
        for label in (":cloudenv", ":cloudpy", ":cloudpy3"):
            self.assertIn(label, lines)
        order = [block.index(n) for n in ("DRYAS_PY", "where py ", "where python3", "\npython -X")]
        self.assertEqual(order, sorted(order))
        self.assertIn("exit /b 2", block)
        usage = [ln for ln in lines if ln.startswith("echo usage:")][0]
        self.assertIn("dryas memory", usage)
        self.assertIn("dryas cloud", usage)

    def test_sh_wrapper_usage_names_both_and_case_order(self):
        sh = (ROOT / "claude/bin/dryas").read_text(encoding="utf-8")
        self.assertLess(sh.index("cloud)"), sh.index("*)"))
        usage = [ln for ln in sh.splitlines() if ln.strip().startswith("*)")][0]
        self.assertIn("dryas memory", usage)
        self.assertIn("dryas cloud", usage)

    def test_install_ps1_routes_and_renames_the_flag(self):
        ps = (ROOT / "install/install.ps1").read_text(encoding="utf-8")
        for needle in ("'-Repo'", "'--repo'", "StartsWith('--repo=')", "tools\\dryas_cloud.py", "init @fwd"):
            self.assertIn(needle, ps)
        self.assertIn("'-Repo') { '--repo' }", ps)  # -Repo is forwarded as --repo
        self.assertLess(ps.index("init @fwd"), ps.index("run --repo $repo @args"))  # cloud branch comes first

    @unittest.skipUnless(os.name == "nt", "Windows wrapper")
    def test_dryas_cloud_windows_spaces_and_many_arguments(self):
        spaced = fx.git_repo(self.base / "a b" / "repo x")
        p = subprocess.run(["cmd", "/c", str(ROOT / "claude/bin/dryas.cmd"), "cloud", "init", "--repo", str(spaced),
                            "--prefix", "my-", "--with-design"], capture_output=True, text=True, env=self.env,
                           timeout=300)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("Dry run: nothing written.", p.stdout)
        self.assertIn("my-", p.stdout)

    @unittest.skipUnless(os.name == "nt", "Windows wrapper")
    def test_dryas_cloud_windows_without_a_subcommand(self):
        p = subprocess.run(["cmd", "/c", str(ROOT / "claude/bin/dryas.cmd"), "cloud"], capture_output=True, text=True,
                           env=self.env, timeout=120)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("usage: dryas cloud", p.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows wrapper")
    def test_dryas_memory_windows_does_not_fall_into_cloud(self):
        db = self.base / "m.db"
        p = subprocess.run(["cmd", "/c", str(ROOT / "claude/bin/dryas.cmd"), "memory", "--db", str(db), "stats"],
                           capture_output=True, text=True, env=self.env, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn("dryas cloud", p.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows installer")
    def test_install_ps1_repo_with_spaces(self):
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if not ps:
            self.skipTest("no PowerShell")
        spaced = fx.git_repo(self.base / "my repo" / "x y")
        before = fx.snapshot(spaced)
        p = subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "install/install.ps1"),
                            "-Repo", str(spaced)], capture_output=True, text=True, env=self.env, timeout=300)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("Dry run: nothing written.", p.stdout)
        self.assertEqual(fx.snapshot(spaced), before)


class CmdShapeTest(unittest.TestCase):
    """dryas.cmd must forward every argument, not just %1..%9 (interrogate A3/B8)."""

    def setUp(self):
        self.text = (ROOT / "claude/bin/dryas.cmd").read_bytes().decode("utf-8")

    def test_forwards_with_percent_star(self):
        t = self.text
        self.assertNotRegex(t, r"%\d %\d")  # no %2 %3 ... lists
        self.assertNotIn("%9", t)
        self.assertNotIn("DRYAS_ARGS", t)  # no collector variable
        self.assertNotIn(":collect", t)
        self.assertNotIn("goto collect", t)
        self.assertFalse([ln for ln in t.splitlines() if ln.strip().startswith("shift")])
        self.assertEqual(t.count('.py" %*'), 8)  # memory x4 and cloud x4 launchers forward the original line

    def test_setlocal_first(self):
        self.assertEqual(self.text.splitlines()[:2], ["@echo off", "setlocal"])  # variables never leak into the caller

    def test_crlf_and_lookup_order_kept(self):
        raw = (ROOT / "claude/bin/dryas.cmd").read_bytes()
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))
        order = [self.text.index(n) for n in ("DRYAS_PY", "where py ", "where python3", "\npython -X")]
        self.assertEqual(order, sorted(order))

    @unittest.skipUnless(os.name == "nt", "Windows wrapper")
    def test_cmd_twelve_arguments_with_spaced_path_and_trailing_yes(self):
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(base), True)
        spaced = fx.git_repo(base / "a b" / "repo x")
        env = dict(os.environ, DRYAS_PYTHON=sys.executable, DRYAS_PY=sys.executable,
                   CLAUDE_CONFIG_DIR=str(base / "cfg"))
        args = ["init", "--repo", str(spaced), "--prefix", "my-", "--with-design", "--persist-memory", "--force",
                "--claude-dir", str(base / "cd"), "--with-design", "--force", "--yes"]  # 12 arguments, --yes last
        self.assertEqual(len(args), 12)
        p = subprocess.run(["cmd", "/c", str(ROOT / "claude/bin/dryas.cmd"), "cloud"] + args,
                           capture_output=True, text=True, env=env, timeout=300)
        self.assertNotIn("unrecognized", p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows wrapper")
    def test_cmd_empty_argument_then_yes(self):
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(base), True)
        repo = fx.git_repo(base / "repo")
        env = dict(os.environ, DRYAS_PYTHON=sys.executable, DRYAS_PY=sys.executable, CLAUDE_CONFIG_DIR=str(base / "cfg"))
        p = subprocess.run(["cmd", "/c", str(ROOT / "claude/bin/dryas.cmd"), "cloud", "init", "--repo", str(repo),
                            "--prefix", "", "--yes"], capture_output=True, text=True, env=env, timeout=300)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue((repo / ".dryas" / "manifest.json").exists())  # --yes after the empty argument still arrived

    @unittest.skipUnless(os.name == "nt", "Windows wrapper")
    def test_cmd_repo_path_with_ampersand(self):
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(base), True)
        repo = fx.git_repo(base / "a&b" / "repo")
        env = dict(os.environ, DRYAS_PYTHON=sys.executable, DRYAS_PY=sys.executable, CLAUDE_CONFIG_DIR=str(base / "cfg"))
        p = subprocess.run(["cmd", "/c", str(ROOT / "claude/bin/dryas.cmd"), "cloud", "init", "--repo", str(repo)],
                           capture_output=True, text=True, env=env, timeout=300)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("Dry run: nothing written.", p.stdout)
        self.assertNotIn("is not recognized", p.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows wrapper")
    def test_cmd_ampersand_in_a_quoted_argument_is_not_a_cmd_error(self):
        p = subprocess.run(["cmd", "/c", str(ROOT / "claude/bin/dryas.cmd"), "cloud", "init", "--prefix", "a&b-"],
                           capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, DRYAS_PYTHON=sys.executable, DRYAS_PY=sys.executable))
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)  # argparse rejects the prefix
        self.assertIn("--prefix takes up to 20 characters", p.stderr)
        self.assertNotIn("is not recognized", p.stderr)


if __name__ == "__main__":
    unittest.main()
