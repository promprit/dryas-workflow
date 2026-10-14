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
        self.assertEqual(start["harness"], ["claude", "codex"])

    def test_hook_files_route_events(self):
        root = os.path.dirname(os.path.dirname(JEV))
        with open(os.path.join(root, "claude", "hooks", "hooks.json"), encoding="utf-8") as f:
            h = json.load(f)["hooks"]
        cmds = lambda ev: " ".join(x["command"] for m in h.get(ev, []) for x in m["hooks"])
        for ev, kind in (("PostToolUse", "post"), ("PostToolUseFailure", "post"), ("SubagentStop", "subagent-stop"),
                         ("SessionStart", "session-start"), ("SessionEnd", "session-end"), ("PreCompact", "precompact")):
            self.assertIn("chain.py\" " + kind, cmds(ev), ev)
        with open(os.path.join(root, "codex", "hooks", "hooks.json"), encoding="utf-8") as f:
            cx = json.load(f)["hooks"]
        self.assertIn("session-start --harness codex", " ".join(x["command"] for m in cx["SessionStart"] for x in m["hooks"]))
