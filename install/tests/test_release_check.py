"""release_check.py against a real install into a temp home with a fake `claude`."""
import contextlib, io, json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fakecli
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools"))
import release_check


class ReleaseCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.home.mkdir()
        fb = self.tmp / "bin"
        fakecli.make(fb, "claude", self.tmp / "calls.jsonl", outputs={"mcp list": "jev: ok\n"})
        self.env = {k: v for k, v in os.environ.items() if k not in ("OPENROUTER_API_KEY", "DRYAS_DATA_ROOT", "CODEX_HOME")}
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home), PATH=str(fb) + os.pathsep + os.environ["PATH"],
                        CODEX_HOME=str(self.home / ".codex"), DRYAS_DATA_ROOT=str(self.tmp / "data"),
                        JEV_LOG_DIR=str(self.tmp / "logs"), JEV_HANDOFF_DIR=str(self.tmp / "handoff"),
                        JEV_COMPACT_DIR=str(self.tmp / "compact"))
        p = subprocess.run([sys.executable, str(REPO / "install" / "dryas_install.py"), "run", "--repo", str(REPO), "--yes",
                            "--no-ruflo", "--no-superpowers", "--no-design"],
                           capture_output=True, text=True, env=self.env, timeout=900)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.cd = self.home / ".claude"

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def run_check(self):
        buf = io.StringIO()
        with mock_env(self.env), contextlib.redirect_stdout(buf):
            rc = release_check.main(["--claude-dir", str(self.cd), "--codex-dir", str(self.home / ".codex")])
        return rc, buf.getvalue()

    def test_all_pass(self):
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("FAIL", out)
        self.assertIn("PASS", out)
        self.assertIn("Scope lock", out)
        self.assertIn("Manual checks (needs the app open):", out)

    def test_reports_fail_for_broken_hook(self):
        rp = self.cd / ".dryas-installed.json"
        rec = json.loads(rp.read_text(encoding="utf-8"))
        rec["settings"]["hooks"][0][2] = "python3 /nonexistent/missing_hook.py"
        rp.write_text(json.dumps(rec), encoding="utf-8")
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL", out)

    def test_help(self):
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(io.StringIO()):
            release_check.main(["--help"])
        self.assertEqual(cm.exception.code, 0)


@contextlib.contextmanager
def mock_env(env):
    old = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old)


if __name__ == "__main__":
    unittest.main()
