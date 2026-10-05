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

    SMOKE_PLAN = "## Task 1: a\nGoal: g\nScope:\n- src/feature/**\nDone:\n- d\n"

    def _worktree(self):
        wt = os.path.join(self.tmp, "wt")
        os.makedirs(os.path.join(wt, ".orchestrate"))
        with open(os.path.join(wt, ".orchestrate", "PLAN.md"), "w", encoding="utf-8") as f:
            f.write(self.SMOKE_PLAN)
        with open(os.path.join(wt, ".orchestrate", "active.json"), "w", encoding="utf-8") as f:
            json.dump({"active": ["1"]}, f)
        return wt

    def test_load_stages_filters_by_harness(self):
        cfg = os.path.join(self.tmp, "chain.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"pretool": [{"name": "c", "cmd": ["x"]}, {"name": "both", "cmd": ["x"], "harness": ["claude", "codex"]}]}, f)
        os.environ["JEV_CHAIN_CONFIG"] = cfg
        try:
            self.assertEqual([s["name"] for s in chain.load_stages("pretool")], ["c", "both"])
            self.assertEqual([s["name"] for s in chain.load_stages("pretool", "codex")], ["both"])
        finally:
            del os.environ["JEV_CHAIN_CONFIG"]

    def test_codex_patch_denies_out_of_scope_file(self):
        code = ("import sys,json;e=json.load(sys.stdin);p=e['tool_input']['file_path'];"
                "print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'deny',"
                "'permissionDecisionReason':'out: '+p}}) if p.startswith('out/') else '')")
        patch = "*** Begin Patch\n*** Update File: src/ok.py\n@@\n-a\n+b\n*** Add File: out/bad.py\n+x\n*** End Patch\n"
        ev = {"tool_name": "apply_patch", "tool_input": {"command": patch}, "cwd": self.tmp}
        out = chain.pretool_codex(ev, [stage("lock", code, harness=["claude", "codex"], per_file=True)])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("out/bad.py", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_codex_unparseable_patch_denied(self):
        out = chain.pretool_codex({"tool_name": "apply_patch", "tool_input": {"command": "garbage"}}, [])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("[codex-patch]", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_codex_patch_outside_worktree_denied_by_real_scope_lock(self):
        wt = self._worktree()
        lock = {"name": "scope-lock", "cmd": [sys.executable, os.path.join(HERE, "scope_lock.py")],
                "match": "Edit|Write|MultiEdit|NotebookEdit", "harness": ["claude", "codex"], "per_file": True}
        ok = "*** Begin Patch\n*** Update File: src/feature/a.py\n+x\n*** End Patch\n"
        self.assertIsNone(chain.pretool_codex({"tool_name": "apply_patch", "tool_input": {"command": ok}, "cwd": wt}, [lock]))
        bad = ("*** Begin Patch\n*** Update File: src/feature/a.py\n+x\n"
               "*** Update File: ../../etc/evil\n+y\n*** End Patch\n")
        out = chain.pretool_codex({"tool_name": "apply_patch", "tool_input": {"command": bad}, "cwd": wt}, [lock])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("evil", out["hookSpecificOutput"]["permissionDecisionReason"])
        other = "*** Begin Patch\n*** Add File: src/other.py\n+x\n*** End Patch\n"
        out = chain.pretool_codex({"tool_name": "apply_patch", "tool_input": {"command": other}, "cwd": wt}, [lock])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def _counter(self, name, then=""):
        p = os.path.join(self.tmp, name)
        code = ("import sys,json;e=json.load(sys.stdin);open(%r,'a').write(e['tool_input']['file_path']+'\\n');" % p) + then
        return p, code

    def _lines(self, p):
        if not os.path.exists(p):
            return []
        with open(p) as f:
            return f.read().splitlines()

    def test_codex_per_file_deny_on_first_stops_further_runs(self):
        cnt, code = self._counter("cnt", "print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse',"
                                         "'permissionDecision':'deny','permissionDecisionReason':'no'}}))")
        later, later_code = self._counter("later")
        patch = "*** Begin Patch\n" + "".join("*** Add File: f%d.py\n+x\n" % i for i in range(5)) + "*** End Patch\n"
        out = chain.pretool_codex({"tool_name": "apply_patch", "tool_input": {"command": patch}, "cwd": self.tmp},
                                  [stage("lock", code, per_file=True), stage("gate", later_code)])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("[lock] no", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(self._lines(cnt), ["f0.py"])
        self.assertEqual(self._lines(later), [])

    def test_codex_scope_lock_name_is_per_file_without_flag(self):
        code = ("import sys,json;e=json.load(sys.stdin);p=e['tool_input']['file_path'];"
                "print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'deny',"
                "'permissionDecisionReason':'out: '+p}}) if p == 'out/bad.py' else '')")
        patch = "*** Begin Patch\n*** Update File: src/ok.py\n+b\n*** Add File: out/bad.py\n+x\n*** End Patch\n"
        out = chain.pretool_codex({"tool_name": "apply_patch", "tool_input": {"command": patch}}, [stage("scope-lock", code)])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("out/bad.py", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_codex_observers_run_once_on_pass1_deny(self):
        obs, obs_code = self._counter("obs", "print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse',"
                                              "'permissionDecision':'ask','permissionDecisionReason':'o'}}))")
        gate, gate_code = self._counter("gate")
        patch = "*** Begin Patch\n*** Add File: a.py\n+1\n*** Add File: b.py\n+2\n*** End Patch\n"
        out = chain.pretool_codex({"tool_name": "apply_patch", "tool_input": {"command": patch}},
                                  [stage("lock", decision("deny", "no"), per_file=True), stage("gate", gate_code),
                                   stage("obs", obs_code, observe=True)])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("[lock] no", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(self._lines(obs), ["a.py"])
        self.assertEqual(self._lines(gate), [])

    def test_codex_non_per_file_stage_runs_once(self):
        cnt, code = self._counter("cnt")
        seen = os.path.join(self.tmp, "seen.json")
        code += "open(%r,'w').write(json.dumps(e))" % seen
        lock, lock_code = self._counter("lock")
        patch = "*** Begin Patch\n*** Add File: a.py\n+1\n*** Update File: b.py\n+2\n*** Delete File: c.py\n*** End Patch\n"
        out = chain.pretool_codex({"tool_name": "apply_patch", "tool_input": {"command": patch}, "cwd": self.tmp},
                                  [stage("lock", lock_code, per_file=True), stage("gate", code, match="Bash|Write|Edit")])
        self.assertIsNone(out)
        self.assertEqual(self._lines(lock), ["a.py", "b.py", "c.py"])
        self.assertEqual(self._lines(cnt), ["a.py"])
        with open(seen) as f:
            e = json.load(f)
        self.assertEqual(e["tool_name"], "Write")
        self.assertEqual(e["tool_input"], {"file_path": "a.py", "content": patch})
        self.assertEqual(e["cwd"], self.tmp)

    def test_codex_strictest_decision_across_passes(self):
        ask = stage("lock", decision("ask", "hm"), per_file=True)
        deny = stage("gate", decision("deny", "no"))
        patch = "*** Begin Patch\n*** Add File: a.py\n+1\n*** Add File: b.py\n+2\n*** End Patch\n"
        ev = {"tool_name": "apply_patch", "tool_input": {"command": patch}}
        out = chain.pretool_codex(ev, [ask, deny])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("[gate] no", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(chain.pretool_codex(ev, [ask])["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_codex_non_patch_runs_all_stages_once(self):
        cnt = os.path.join(self.tmp, "c")
        code = "import sys;sys.stdin.read();open(%r,'a').write('x\\n')" % cnt
        out = chain.pretool_codex(self.ev, [stage("a", code, per_file=True), stage("b", code)])
        self.assertIsNone(out)
        self.assertEqual(self._lines(cnt), ["x", "x"])

    def test_main_exports_harness_to_stages(self):
        cfg = os.path.join(self.tmp, "chain.json")
        code = ("import os,sys,json;sys.stdin.read();print(json.dumps({'hookSpecificOutput':{'hookEventName':"
                "'UserPromptSubmit','additionalContext':'h='+os.environ.get('DRYAS_HARNESS','')}}))")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"prompt": [{"name": "p", "cmd": [sys.executable, "-c", code], "harness": ["claude", "codex"]},
                                  {"name": "claude-only", "cmd": [sys.executable, "-c", code.replace("h=", "c=")]}]}, f)
        env = dict(os.environ, JEV_CHAIN_CONFIG=cfg)
        p = subprocess.run([sys.executable, os.path.join(HERE, "chain.py"), "prompt", "--harness", "codex"],
                           input=json.dumps({"prompt": "x"}), capture_output=True, text=True, env=env)
        ctx = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(ctx, "h=codex")

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

    def test_main_exits_zero_on_garbage_stdin(self):
        cfg = os.path.join(self.tmp, "chain.json")
        with open(cfg, "w") as f:
            json.dump({"pretool": []}, f)
        env = dict(os.environ, JEV_CHAIN_CONFIG=cfg)
        p = subprocess.run([sys.executable, os.path.join(HERE, "chain.py"), "pretool"], input="not json",
                           capture_output=True, text=True, env=env)
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
