# install/tests/test_codex_appserver.py
import json, os, shutil, subprocess, sys, tempfile, time, unittest
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

    def test_trust_params_needs_current_hash(self):
        with self.assertRaises(ca.AppServerError):
            ca.trust_params([{"key": "a", "pluginId": ID}])

    def test_trust_params_plugin_guard(self):
        es = [{"key": "a", "pluginId": ID, "currentHash": "sha256:1"},
              {"key": "b", "pluginId": "other@x", "currentHash": "sha256:2"}]
        with self.assertRaises(ca.AppServerError):
            ca.trust_params(es, plugin_id=ID)
        self.assertEqual(list(ca.trust_params(es[:1], plugin_id=ID)["edits"][0]["value"]), ["a"])


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

    def test_noise_is_ignored(self):
        f = FakeCodex(self)
        f.install()
        env = dict(f.env, FAKE_APPSERVER_NOISE="1")
        mine = ca.untrusted(ca.list_hooks(env, str(f.t)), ID)
        self.assertEqual(len(mine), 3)
        ca.write_trust(env, mine, plugin_id=ID)
        self.assertEqual(ca.untrusted(ca.list_hooks(env, str(f.t)), ID), [])

    def test_write_trust_plugin_guard(self):
        f = FakeCodex(self)
        f.install()
        es = ca.list_hooks(f.env, str(f.t))
        with self.assertRaises(ca.AppServerError):
            ca.write_trust(f.env, [dict(es[0], pluginId="other@x")], plugin_id=ID)
        self.assertNotIn("hooks.state", (f.cdx / "config.toml").read_text(encoding="utf-8"))

    def test_fake_requires_handshake(self):
        f = FakeCodex(self)
        f.install()
        with ca.AppServer(f.env, timeout=10) as s:
            with self.assertRaisesRegex(ca.AppServerError, "Not initialized"):
                s.request("hooks/list", {"cwds": [str(f.t)]})
            s.request("initialize", {"clientInfo": ca.CLIENT})
            with self.assertRaisesRegex(ca.AppServerError, "Not initialized"):
                s.request("config/batchWrite", ca.trust_params([]))
            s.notify("initialized")
            self.assertEqual(len(ca.hook_entries(s.request("hooks/list", {"cwds": [str(f.t)]}))), 3)

    def test_fake_rejects_other_batch_writes(self):
        f = FakeCodex(self)
        f.install()
        bad = [{"keyPath": "hooks", "value": {}, "mergeStrategy": "upsert"},
               {"keyPath": "hooks.state", "value": {}, "mergeStrategy": "replace"}]
        with ca.AppServer(f.env, timeout=10) as s:
            s.request("initialize", {"clientInfo": ca.CLIENT})
            s.notify("initialized")
            for e in bad:
                with self.assertRaises(ca.AppServerError):
                    s.request("config/batchWrite", {"edits": [e], "reloadUserConfig": True})

    def test_null_id_error_raises_at_once(self):
        f = FakeCodex(self)
        t0 = time.monotonic()
        with self.assertRaisesRegex(ca.AppServerError, "Parse error"):
            ca.list_hooks(dict(f.env, FAKE_APPSERVER_PARSE_ERROR="1"), str(f.t), timeout=20)
        self.assertLess(time.monotonic() - t0, 10)

    def test_exit_error_carries_stderr(self):
        f = FakeCodex(self)
        f.install()
        with self.assertRaisesRegex(ca.AppServerError, "fake crash in hooks/list"):
            ca.list_hooks(dict(f.env, FAKE_APPSERVER_CRASH="hooks/list"), str(f.t))

    def test_close_kills_a_hung_server(self):
        f = FakeCodex(self)
        s = ca.AppServer(dict(f.env, FAKE_APPSERVER_HANG="1"), timeout=1)
        s.request("initialize", {"clientInfo": ca.CLIENT})
        t0 = time.monotonic()
        s.close()
        self.assertLess(time.monotonic() - t0, 5)
        self.assertIsNotNone(s.p.poll())

    def test_session_closes_on_interrupt(self):
        f = FakeCodex(self)
        made = []
        real = ca.AppServer

        def spy(*a, **k):
            made.append(real(*a, **k))
            return made[-1]
        with mock.patch.object(ca, "AppServer", spy), \
                mock.patch.object(real, "notify", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                ca.list_hooks(f.env, str(f.t))
        self.assertIsNotNone(made[0].p.poll())

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
