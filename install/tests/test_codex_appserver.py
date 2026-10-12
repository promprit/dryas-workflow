# install/tests/test_codex_appserver.py
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import codex_appserver as ca
import fakecli

REPO = HERE.parents[1]
ID = "dryas@dryas-workflow"


class PureTest(unittest.TestCase):
    def test_hook_entries_any_nesting(self):
        h = {"key": "k1", "pluginId": ID, "trustStatus": "untrusted", "currentHash": "sha256:a"}
        res = {"data": [{"cwd": "/x", "hooks": [h, {"no": "key"}], "warnings": []}]}
        self.assertEqual(ca.hook_entries(res), [h])
        self.assertEqual(ca.hook_entries([h]), [h])
        self.assertEqual(ca.hook_entries(None), [])

    def test_untrusted_filters_plugin_and_status(self):
        es = [{"key": "a", "pluginId": ID, "trustStatus": "trusted"},
              {"key": "b", "pluginId": ID, "trustStatus": "modified"},
              {"key": "c", "pluginId": "other@x", "trustStatus": "untrusted"},
              {"key": "d", "pluginId": ID, "trustStatus": "untrusted"}]
        self.assertEqual([e["key"] for e in ca.untrusted(es, ID)], ["b", "d"])

    def test_trust_params(self):
        p = ca.trust_params([{"key": "a", "currentHash": "sha256:1"}, {"key": "b", "currentHash": "sha256:2"}])
        self.assertEqual(p, {"edits": [{"keyPath": "hooks.state", "mergeStrategy": "upsert",
                                        "value": {"a": {"trusted_hash": "sha256:1"}, "b": {"trusted_hash": "sha256:2"}}}],
                             "reloadUserConfig": True})


class FakeCodex:
    """A CODEX_HOME with the fake codex on PATH and the dryas plugin installed from this repo."""

    def __init__(self, tc, fail=()):
        self.t = Path(tempfile.mkdtemp())
        tc.addCleanup(shutil.rmtree, str(self.t), True)
        self.cdx, self.log = self.t / "codex-home", self.t / "calls.jsonl"
        fakecli.make_codex(self.t / "bin", self.log, fail)
        self.env = dict(os.environ, CODEX_HOME=str(self.cdx),
                        PATH=str(self.t / "bin") + os.pathsep + os.environ["PATH"])
        p = mock.patch.dict(os.environ, {"PATH": self.env["PATH"]})
        p.start()
        tc.addCleanup(p.stop)

    def codex(self, *args):
        import platform_util as pu
        return subprocess.run(pu.resolve_argv(["codex"] + list(args)), env=self.env, capture_output=True, text=True)

    def install(self):
        self.codex("plugin", "marketplace", "add", str(REPO))
        return json.loads(self.codex("plugin", "add", ID, "--json").stdout)


class RunnerTest(unittest.TestCase):
    def test_list_then_trust(self):
        f = FakeCodex(self)
        f.install()
        es = ca.list_hooks(f.env, str(f.t))
        mine = ca.untrusted(es, ID)
        self.assertEqual(len(mine), 3)
        ca.write_trust(f.env, mine)
        self.assertEqual(ca.untrusted(ca.list_hooks(f.env, str(f.t)), ID), [])
        cfg = (f.cdx / "config.toml").read_text(encoding="utf-8")
        self.assertIn('[hooks.state."%s:hooks/hooks.json:pre_tool_use:0:0"]' % ID, cfg)

    def test_error_response_raises(self):
        f = FakeCodex(self)
        f.install()
        with self.assertRaises(ca.AppServerError):
            ca.list_hooks(dict(f.env, FAKE_APPSERVER_FAIL="hooks/list"), str(f.t))

    def test_silent_server_times_out(self):
        f = FakeCodex(self)
        with self.assertRaises(ca.AppServerError):
            ca.list_hooks(dict(f.env, FAKE_APPSERVER_SILENT="1"), str(f.t), timeout=2)

    def test_server_exits(self):
        f = FakeCodex(self, fail=["app-server"])
        with self.assertRaises(ca.AppServerError):
            ca.list_hooks(f.env, str(f.t))

    def test_no_codex(self):
        with self.assertRaises(ca.AppServerError):
            ca.AppServer(dict(os.environ, PATH=tempfile.mkdtemp()), argv=["codex-not-here-xyz", "app-server"])


class FakeCliTest(unittest.TestCase):
    def test_plugin_add_copies_without_symlinks_and_lists(self):
        f = FakeCodex(self)
        out = f.install()
        self.assertEqual(out["pluginId"], ID)
        root = Path(out["installedPath"])
        self.assertTrue((root / "jev" / "chain.py").is_file())
        self.assertTrue(str(root).startswith(str(f.cdx / "plugins" / "cache" / "dryas-workflow" / "dryas")))
        listed = json.loads(f.codex("plugin", "list", "--json").stdout)["installed"]
        self.assertEqual([(p["pluginId"], p["enabled"]) for p in listed], [(ID, True)])
        self.assertIn("dryas:orchestrate", f.codex("debug", "prompt-input", "hi").stdout)
        self.assertIn("jev", [s["name"] for s in json.loads(f.codex("mcp", "list", "--json").stdout)])


if __name__ == "__main__":
    unittest.main()
