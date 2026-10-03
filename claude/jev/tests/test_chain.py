import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import chain


def stage(name, code, **kw):
    d = {"name": name, "cmd": [sys.executable, "-c", code]}
    d.update(kw)
    return d


def emit(obj):
    return "import sys,json;sys.stdin.read();print(json.dumps(%r))" % (obj,)


def decision(d, reason="r"):
    return emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": d, "permissionDecisionReason": reason}})


class ChainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["JEV_LOG_DIR"] = os.path.join(self.tmp, "logs")
        self.ev = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
        self.raw = json.dumps(self.ev)

    def marker(self, name):
        p = os.path.join(self.tmp, name)
        return p, "import sys;sys.stdin.read();open(%r,'w').write('x')" % p

    def test_no_stages_no_decision(self):
        self.assertIsNone(chain.pretool(self.ev, self.raw, []))

    def test_deny_skips_later_stages_but_runs_observers(self):
        later, later_code = self.marker("later")
        obs, obs_code = self.marker("obs")
        out = chain.pretool(self.ev, self.raw, [stage("a", decision("deny", "nope")), stage("b", later_code), stage("o", obs_code, observe=True)])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("[a] nope", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertFalse(os.path.exists(later))
        self.assertTrue(os.path.exists(obs))

    def test_ask_then_deny_escalates_to_deny(self):
        out = chain.pretool(self.ev, self.raw, [stage("a", decision("ask")), stage("b", decision("deny"))])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_ask_alone(self):
        out = chain.pretool(self.ev, self.raw, [stage("a", decision("ask"))])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_allow_is_ignored(self):
        self.assertIsNone(chain.pretool(self.ev, self.raw, [stage("a", decision("allow"))]))

    def test_exit2_is_deny(self):
        code = "import sys;sys.stdin.read();sys.stderr.write('blocked by x');sys.exit(2)"
        out = chain.pretool(self.ev, self.raw, [stage("a", code)])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("blocked by x", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_observer_decision_ignored(self):
        self.assertIsNone(chain.pretool(self.ev, self.raw, [stage("o", decision("deny"), observe=True)]))

    def test_match_filters_tools(self):
        ev = {"tool_name": "Read"}
        self.assertIsNone(chain.pretool(ev, json.dumps(ev), [stage("a", decision("deny"), match="Bash|Write|Edit")]))

    def test_requires_path_missing_skips(self):
        self.assertIsNone(chain.pretool(self.ev, self.raw, [stage("a", decision("deny"), requires_path="/Volumes/__no_such_ssd__")]))

    def test_timeout_stage_ignored(self):
        code = "import time,sys;sys.stdin.read();time.sleep(5)"
        self.assertIsNone(chain.pretool(self.ev, self.raw, [stage("slow", code, timeout=1)]))

    def test_missing_binary_ignored(self):
        st = {"name": "gone", "cmd": ["/nonexistent/bin"]}
        self.assertIsNone(chain.pretool(self.ev, self.raw, [st]))

    def test_prompt_concatenates_json_and_plain(self):
        a = emit({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "Jev route: swarm (0.82)"}})
        b = "import sys;sys.stdin.read();print('ruflo: 2 similar tasks')"
        out = chain.prompt({}, "{}", [stage("a", a), stage("b", b)])
        self.assertEqual(out["hookSpecificOutput"]["additionalContext"], "Jev route: swarm (0.82)\nruflo: 2 similar tasks")

    def test_prompt_observer_output_ignored(self):
        b = "import sys;sys.stdin.read();print('noise')"
        self.assertIsNone(chain.prompt({}, "{}", [stage("o", b, observe=True)]))

    def test_prompt_block_passes_through(self):
        out = chain.prompt({}, "{}", [stage("a", emit({"decision": "block", "reason": "no"}))])
        self.assertEqual(out, {"decision": "block", "reason": "no"})

    def test_main_end_to_end_logs_calls(self):
        cfg = os.path.join(self.tmp, "chain.json")
        with open(cfg, "w") as f:
            json.dump({"pretool": [stage("a", decision("ask"))]}, f)
        env = dict(os.environ, JEV_CHAIN_CONFIG=cfg)
        p = subprocess.run([sys.executable, os.path.join(HERE, "chain.py"), "pretool"], input=self.raw, capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"], "ask")
        with open(os.path.join(self.tmp, "logs", "calls.jsonl")) as f:
            self.assertEqual(json.loads(f.readline())["tool"], "Bash")

    def test_main_bad_stdin_exits_zero(self):
        p = subprocess.run([sys.executable, os.path.join(HERE, "chain.py"), "pretool"], input="not json", capture_output=True, text=True,
                           env=dict(os.environ, JEV_CHAIN_CONFIG="/nonexistent.json"))
        self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_deny_followed_by_bad_utf8_observer(self):
        # Deny from first stage, then observer writes non-UTF-8 bytes. Deny should not be lost.
        code = "import sys;sys.stdin.read();sys.stdout.buffer.write(b'\\xff\\xfe')"
        out = chain.pretool(self.ev, self.raw, [stage("a", decision("deny", "nope")), stage("o", code, observe=True)])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("[a] nope", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_bad_hookuspecificoutput_not_dict(self):
        # Stage outputs {"hookSpecificOutput": "notadict"} (not a dict). Should not crash, no decision.
        code = "import sys,json;sys.stdin.read();print(json.dumps({'hookSpecificOutput': 'notadict'}))"
        out = chain.pretool(self.ev, self.raw, [stage("a", code)])
        self.assertIsNone(out)

    def test_bad_cmd_type_and_timeout_dont_lose_deny(self):
        # First stage has bad cmd type, second has bad timeout type. Later deny stage should still apply.
        out = chain.pretool(self.ev, self.raw, [stage("bad_cmd", "dummy", cmd="not-a-list"), stage("bad_timeout", "dummy", timeout="x"), stage("d", decision("deny", "final"))])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("[d] final", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_wrapper_missing_chain_exits_zero(self):
        # Test that if chain.py is missing, the wrapper still exits 0. Set HOME to empty temp dir.
        cfg = os.path.join(self.tmp, "chain.json")
        with open(cfg, "w") as f:
            json.dump({"pretool": []}, f)
        env = dict(os.environ, HOME=self.tmp, JEV_CHAIN_CONFIG=cfg)
        p = subprocess.run(["/bin/sh", os.path.join(HERE, "hooks", "pretool-chain.sh")], input="{}", capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")

    def test_disabled_stage_skipped(self):
        st = stage("a", decision("deny"))
        st["enabled"] = False
        self.assertIsNone(chain.pretool(self.ev, self.raw, [st]))

    def test_requires_path_env_expanded(self):
        d = tempfile.mkdtemp()
        os.environ["DRYAS_TEST_ROOT"] = d
        try:
            out = chain.pretool(self.ev, self.raw, [stage("a", decision("deny"), requires_path="$DRYAS_TEST_ROOT")])
            self.assertIsNotNone(out)
        finally:
            del os.environ["DRYAS_TEST_ROOT"]

    def test_requires_path_unset_var_skips(self):
        os.environ.pop("DRYAS_UNSET_VAR", None)
        self.assertIsNone(chain.pretool(self.ev, self.raw, [stage("a", decision("deny"), requires_path="$DRYAS_UNSET_VAR")]))

    def test_expand(self):
        os.environ["DRYAS_X"] = "/a b"
        try:
            self.assertEqual(chain._expand("$DRYAS_X/c"), "/a b/c")
            self.assertEqual(chain._expand("${DRYAS_X}/c"), "/a b/c")
            self.assertIsNone(chain._expand("$DRYAS_NOPE/c"))
            self.assertEqual(chain._expand("~/x"), os.path.expanduser("~/x"))
        finally:
            del os.environ["DRYAS_X"]


if __name__ == "__main__":
    unittest.main()


class ChainWatchTest(unittest.TestCase):
    def test_route_and_context_watch_lines_both_survive(self):
        ctx = lambda t: emit({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": t}})
        out = chain.prompt({}, "{}", [stage("jev-route", ctx("Jev route: swarm (0.82)")),
                                      stage("context-watch", ctx("Context 63% — run /handoff")),
                                      stage("observer", emit({"x": 1}), observe=True)])
        c = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Jev route: swarm (0.82)", c)
        self.assertIn("Context 63% — run /handoff", c)
        self.assertLess(c.index("Jev route"), c.index("Context 63%"))

    def test_real_chain_json_order(self):
        with open(os.path.join(HERE, "chain.json"), encoding="utf-8") as f:
            names = [s["name"] for s in json.load(f)["prompt"]]
        self.assertEqual(names, ["jev-route", "context-watch", "flowobserve"])


CHAIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_chain(tmp, raw, stages):
    cfg = os.path.join(tmp, "chain.json")
    with open(cfg, "w") as f:
        json.dump({"pretool": stages}, f)
    env = dict(os.environ, JEV_CHAIN_CONFIG=cfg, JEV_LOG_DIR=os.path.join(tmp, "logs"))
    env.pop("JEV_SESSION_ID", None)
    env.pop("JEV_CWD", None)
    return subprocess.run([sys.executable, os.path.join(CHAIN_DIR, "chain.py"), "pretool"], input=raw, capture_output=True, text=True, env=env)


class ChainSessionEnvTest(unittest.TestCase):
    def test_stage_sees_session_env_and_calls_log_has_session(self):
        tmp = tempfile.mkdtemp()
        seen = os.path.join(tmp, "seen")
        probe = os.path.join(tmp, "probe.py")
        with open(probe, "w") as f:
            f.write("import os,sys\nsys.stdin.read()\nopen(%r,'w').write(os.environ.get('JEV_SESSION_ID','')+'|'+os.environ.get('JEV_CWD',''))\n" % seen)
        raw = json.dumps({"session_id": "s-42", "cwd": "/Users/p/app", "tool_name": "Bash", "hook_event_name": "PreToolUse"})
        p = _run_chain(tmp, raw, [{"name": "probe", "cmd": [sys.executable, probe], "observe": True}])
        self.assertEqual(p.returncode, 0)
        self.assertEqual(open(seen).read(), "s-42|/Users/p/app")
        rec = json.loads(open(os.path.join(tmp, "logs", "calls.jsonl")).readline())
        self.assertEqual(rec["session_id"], "s-42")

    def test_non_string_session_is_ignored(self):
        tmp = tempfile.mkdtemp()
        p = _run_chain(tmp, json.dumps({"session_id": 7, "tool_name": "Bash"}), [])
        self.assertEqual(p.returncode, 0)
        rec = json.loads(open(os.path.join(tmp, "logs", "calls.jsonl")).readline())
        self.assertNotIn("session_id", rec)
