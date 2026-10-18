import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
JEV = os.path.dirname(HERE)
sys.path.insert(0, JEV)
import chain

CHAIN = os.path.join(JEV, "chain.py")


def run_chain(kind, event, config, harness=None, env_extra=None):
    env = dict(os.environ, JEV_CHAIN_CONFIG=config, JEV_CHAIN_LOCAL=os.path.join(os.path.dirname(config), "none.json"))
    env.update(env_extra or {})
    argv = [sys.executable, CHAIN, kind] + (["--harness", harness] if harness else [])
    t0 = time.monotonic()
    p = subprocess.run(argv, input=json.dumps(event), capture_output=True, text=True, env=env, timeout=30)
    return p, time.monotonic() - t0


class ObserveTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.out = os.path.join(self.d, "ran.txt")

    def config(self, kind, stages):
        p = os.path.join(self.d, "chain.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({kind: stages}, f)
        return p

    def stage(self, name, code, **kw):
        s = {"name": name, "component": "memory", "observe": True, "timeout": 2,
             "cmd": [sys.executable, "-c", code, self.out]}
        s.update(kw)
        return s

    def test_post_kind_runs_mem_edit_and_prints_nothing(self):
        code = "import sys;open(sys.argv[1],'a').write(sys.stdin.read()[:40]+'\\n');print('junk')"
        cfg = self.config("post", [self.stage("mem-edit", code, match="Write|Edit|MultiEdit|NotebookEdit")])
        p, _ = run_chain("post", {"tool_name": "Edit", "tool_input": {"file_path": "a.py"}}, cfg)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
        with open(self.out, encoding="utf-8") as f:
            self.assertIn("Edit", f.read())

    def test_match_filters_tools(self):
        code = "import sys;open(sys.argv[1],'a').write('x')"
        cfg = self.config("post", [self.stage("mem-edit", code, match="Write|Edit")])
        run_chain("post", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, cfg)
        self.assertFalse(os.path.exists(self.out))

    def test_hung_observe_stage_does_not_block(self):
        hang = "import time;time.sleep(30)"
        crash = "raise SystemExit(3)"
        write = "import sys;open(sys.argv[1],'a').write('ok')"
        cfg = self.config("session-end", [self.stage("hang", hang), self.stage("crash", crash),
                                          self.stage("after", write)])
        p, secs = run_chain("session-end", {"session_id": "s"}, cfg)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
        self.assertLess(secs, 10)  # hang is cut at its 2 s timeout; generous bound for a loaded runner
        with open(self.out, encoding="utf-8") as f:
            self.assertEqual(f.read(), "ok")

    def test_disabled_and_harness_filtered(self):
        write = "import sys;open(sys.argv[1],'a').write('x')"
        cfg = self.config("session-start", [self.stage("off", write, enabled=False),
                                            self.stage("claude-only", write)])
        run_chain("session-start", {}, cfg, harness="codex")
        self.assertFalse(os.path.exists(self.out))

    def test_unknown_kind_is_a_noop(self):
        cfg = self.config("post", [])
        p, _ = run_chain("nonsense", {}, cfg)
        self.assertEqual((p.returncode, p.stdout), (0, ""))


class ShippedChainTest(unittest.TestCase):
    def test_memory_stages_shipped(self):
        with open(os.path.join(JEV, "chain.json"), encoding="utf-8") as f:
            c = json.load(f)
        want = {("post", "mem-edit", "edit"), ("subagent-stop", "mem-task", "task"),
                ("session-start", "mem-session-start", "session-start"),
                ("session-end", "mem-session-end", "session-end"), ("precompact", "mem-session-end", "session-end")}
        got = set()
        for kind in chain.OBSERVE_KINDS:
            for s in c.get(kind, []):
                if s.get("component") == "memory":
                    self.assertTrue(s.get("observe"))
                    self.assertLessEqual(s.get("timeout"), 2)
                    self.assertTrue(s["cmd"][3].endswith("memhooks.py"), s["cmd"])
                    got.add((kind, s["name"], s["cmd"][4]))  # [$PY, -X, utf8, memhooks.py, stage, (mode)]
        self.assertEqual(got, want)
        pre = [s for s in c["precompact"] if s["name"] == "mem-session-end"][0]
        self.assertEqual(pre["cmd"][-1], "auto")  # summary only: never a full consolidation inside PreCompact
        start = [s for s in c["session-start"] if s["name"] == "mem-session-start"][0]
        self.assertEqual(start["harness"], ["claude", "opencode"])
        self.assertNotIn("codex", start["harness"])

    def test_hook_files_route_events(self):
        root = os.path.dirname(os.path.dirname(JEV))
        with open(os.path.join(root, "claude", "hooks", "hooks.json"), encoding="utf-8") as f:
            h = json.load(f)["hooks"]
        cmds = lambda ev: " ".join(x["command"] for m in h.get(ev, []) for x in m["hooks"])
        for ev, kind in (("PostToolUse", "post"), ("PostToolUseFailure", "post"), ("SubagentStop", "subagent-stop"),
                         ("SessionStart", "session-start"), ("SessionEnd", "session-end"), ("PreCompact", "precompact"),
                         ("Stop", "stop")):
            self.assertIn("chain.py\" " + kind, cmds(ev), ev)
        with open(os.path.join(root, "codex", "hooks", "hooks.json"), encoding="utf-8") as f:
            cx = json.load(f)["hooks"]
        for ev in cx:
            self.assertNotIn("session-start", " ".join(x["command"] for m in cx[ev] for x in m["hooks"]), ev)


class StopRouteTest(unittest.TestCase):
    def test_stop_event_runs_mem_notes(self):
        """Stop must reach the shipped mem-notes stage: hooks.json routes it, chain.py runs it as observe-only."""
        root = os.path.dirname(os.path.dirname(JEV))
        with open(os.path.join(root, "claude", "hooks", "hooks.json"), encoding="utf-8") as f:
            stop = " ".join(x["command"] for m in json.load(f)["hooks"].get("Stop", []) for x in m["hooks"])
        self.assertIn("chain.py\" stop", stop)
        with open(os.path.join(JEV, "chain.json"), encoding="utf-8") as f:
            shipped = json.load(f)["stop"]
        self.assertEqual([s["name"] for s in shipped], ["mem-notes"])
        d = tempfile.mkdtemp()
        out = os.path.join(d, "ran.txt")
        stage = dict(shipped[0], cmd=[sys.executable, "-c", "import sys;open(sys.argv[1],'a').write('ran');print('noise')",
                                      out])
        stage.pop("requires_path", None)
        cfg = os.path.join(d, "chain.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"stop": [stage]}, f)
        p, _ = run_chain("stop", {"session_id": "s", "hook_event_name": "Stop"}, cfg)
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        with open(out, encoding="utf-8") as f:
            self.assertEqual(f.read(), "ran")


BRIDGE_STAGE = {"name": "bridge-deliver", "harness": ["claude"], "component": "core", "inproc": "bridge_deliver",
                "context": True, "cmd": ["$PY", "-X", "utf8", "$CD/jev/bridge_deliver.py"], "timeout": 1}


class BridgeStageTest(unittest.TestCase):
    SID = "66666666-6666-4666-8666-666666666666"

    def setUp(self):
        self.d = tempfile.mkdtemp()
        root = os.path.join(self.d, "data")
        self.box = os.path.join(root, "inbox", self.SID)
        os.makedirs(self.box)
        with open(os.path.join(self.box, "1792000000000-00000001.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "id": "m-000000000001", "ts": "2026-10-18T12:34:56Z",
                       "from": {"sessionId": "77777777-7777-4777-8777-777777777777", "name": "sender",
                                "account": ".claude-two", "cwd": "/w"},
                       "to": self.SID, "reply_to": None, "text": "ping"}, f)
        self.env = {"DRYAS_DATA_ROOT": root, "JEV_LOG_DIR": os.path.join(self.d, "logs")}

    def config(self, kind, stages):
        p = os.path.join(self.d, "chain.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({kind: stages}, f)
        return p

    def ev(self, name, **kw):
        e = {"session_id": self.SID, "hook_event_name": name, "tool_name": "Bash", "tool_input": {"command": "ls"}}
        e.update(kw)
        return e

    def test_post_context_stage_prints_additional_context(self):
        p, _ = run_chain("post", self.ev("PostToolUse"), self.config("post", [BRIDGE_STAGE]), env_extra=self.env)
        self.assertEqual(p.returncode, 0)
        hso = json.loads(p.stdout)["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "PostToolUse")
        self.assertIn("ping", hso["additionalContext"])

    def test_post_failure_event_name_kept(self):
        p, _ = run_chain("post", self.ev("PostToolUseFailure"), self.config("post", [BRIDGE_STAGE]), env_extra=self.env)
        self.assertEqual(json.loads(p.stdout)["hookSpecificOutput"]["hookEventName"], "PostToolUseFailure")

    def test_plain_observe_stage_still_prints_nothing(self):
        noisy = {"name": "noisy", "component": "memory", "observe": True, "timeout": 2,
                 "cmd": [sys.executable, "-c", "print('junk')"]}
        p, _ = run_chain("post", self.ev("PostToolUse"), self.config("post", [noisy, BRIDGE_STAGE]), env_extra=self.env)
        self.assertNotIn("junk", p.stdout)
        self.assertIn("ping", p.stdout)

    def test_unknown_inproc_with_context_ignored(self):
        rogue = dict(BRIDGE_STAGE, name="rogue", inproc="memhooks")
        p, _ = run_chain("post", self.ev("PostToolUse"), self.config("post", [rogue]), env_extra=self.env)
        self.assertEqual(p.stdout, "")
        self.assertEqual(len([n for n in os.listdir(self.box) if n.endswith(".json")]), 1)

    def test_prompt_runs_inproc(self):
        p, _ = run_chain("prompt", self.ev("UserPromptSubmit", prompt="hi"), self.config("prompt", [BRIDGE_STAGE]),
                         env_extra=self.env)
        hso = json.loads(p.stdout)["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "UserPromptSubmit")
        self.assertIn("ping", hso["additionalContext"])

    def test_codex_harness_skips_stage(self):
        p, _ = run_chain("prompt", self.ev("UserPromptSubmit", prompt="hi"), self.config("prompt", [BRIDGE_STAGE]),
                         harness="codex", env_extra=self.env)
        self.assertNotIn("ping", p.stdout)

    def test_inproc_prompt_stage_never_blocks(self):
        ev = self.ev("UserPromptSubmit", prompt="hi")
        with mock.patch.object(chain, "_inproc", return_value='{"decision": "block", "reason": "x"}'):
            out = chain.prompt(ev, json.dumps(ev), [BRIDGE_STAGE])
        self.assertNotIn("decision", out)
        self.assertIn("block", out["hookSpecificOutput"]["additionalContext"])

    def test_raising_inproc_stage_is_skipped(self):
        ev = self.ev("PostToolUse")
        with mock.patch.object(chain, "_inproc", side_effect=RuntimeError("boom")):
            self.assertEqual(chain.observe(ev, json.dumps(ev), [BRIDGE_STAGE], "post"), [])
            self.assertIsNone(chain.prompt(ev, json.dumps(ev), [BRIDGE_STAGE]))
