import io, json, sys, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import plugin_setup as ps
import test_plugin_setup as base

REPO = base.REPO
COMPS = base.COMPS
UPDATE = [["claude", "plugin", "marketplace", "update", "dryas-workflow"], ["claude", "plugin", "update", "dryas@dryas-workflow"]]


def _repo_ver():
    return json.loads((REPO / "claude" / ".claude-plugin" / "plugin.json").read_text())["version"]


def _installed(version):
    rec = json.loads(json.dumps(base.INSTALLED))
    rec["plugins"]["dryas@dryas-workflow"][0]["version"] = version
    return rec


def _run(fn):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = fn()
    return rc, buf.getvalue()


class UpgradeTest(unittest.TestCase):
    def env(self, version, fail=()):
        p = mock.patch.object(base, "INSTALLED", _installed(version))  # the fake `plugin install` records this version
        p.start()
        self.addCleanup(p.stop)
        e = base.Env(self)
        if fail:
            base.fakecli.make(e.bin, "claude", e.log, fail=fail, epilogue=e.epilogue, plugin_list=True)
        return e

    def argvs(self, e):
        return [c for c in e.calls() if c[1:3] in (["plugin", "update"], ["plugin", "marketplace"]) and "update" in c]

    def test_stale_install_is_updated(self):
        e = self.env("1.0.0")
        self.assertNotEqual(ps.repo_version(REPO), "1.0.0")
        rc, _ = _run(lambda: ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False))
        self.assertEqual(rc, 0)
        calls = e.calls()
        self.assertEqual(self.argvs(e), UPDATE)
        install = next(i for i, c in enumerate(calls) if c[1:3] == ["plugin", "install"] and c[3] == ps.ID)
        self.assertLess(install, calls.index(UPDATE[0]))
        self.assertLess(calls.index(UPDATE[0]), calls.index(UPDATE[1]))

    def test_current_install_is_not_updated(self):
        e = self.env(_repo_ver())
        rc, _ = _run(lambda: ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False))
        self.assertEqual(rc, 0)
        self.assertEqual(self.argvs(e), [])

    def test_failed_update_stops_setup(self):
        e = self.env("1.0.0", fail=["plugin update"])
        rc, out = _run(lambda: ps.setup(REPO, e.a, COMPS, yes=True, key="", flowobserve=False))
        self.assertNotEqual(rc, 0)
        self.assertIn("error:", out)
        self.assertIn("plugin update", out)
        self.assertFalse((e.a / "settings.json").exists())

    def test_verify_flags_version_mismatch(self):
        for version, status in (("1.0.0", "FAIL"), (_repo_ver(), "PASS")):
            e = self.env(version)
            rec = _installed(version)
            rec["plugins"]["dryas@dryas-workflow"][0]["installPath"] = str(REPO / "claude")
            (e.a / "plugins").mkdir(parents=True)
            (e.a / "plugins" / "installed_plugins.json").write_text(json.dumps(rec))
            with mock.patch.object(ps.di, "run", lambda argv, cwd=None, env=None: 0):
                _, out = _run(lambda: ps.verify(e.a, COMPS))
            self.assertIn(status + "  installed version matches this repo", out)
            if status == "FAIL":
                self.assertIn("run install/install.sh again, then restart Claude Code", out)

    def test_repo_version_reads_plugin_json(self):
        self.assertEqual(ps.repo_version(REPO), _repo_ver())
        self.assertEqual(ps.repo_version(REPO / "no-such-folder"), "")


if __name__ == "__main__":
    unittest.main()
