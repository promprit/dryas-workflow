import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import opencode_session  # noqa: E402
import transcript_items  # noqa: E402
from jev_client import JevUnavailable  # noqa: E402


def user(mid, text, synthetic=False):
    return {"info": {"id": mid, "role": "user"}, "parts": [{"type": "text", "text": text, "synthetic": synthetic}]}


def tool(tool_name, call, inp, status="completed", output="ok", error=None):
    st = {"status": status, "input": inp}
    st.update({"output": output} if status == "completed" else {"error": error})
    return {"type": "tool", "tool": tool_name, "callID": call, "state": st}


def assistant(mid, *parts, text=None):
    ps = ([{"type": "text", "text": text}] if text else []) + list(parts)
    return {"info": {"id": mid, "role": "assistant"}, "parts": ps}


MESSAGES = [
    user("m1", "Please write allowed.txt"),
    assistant("m2", tool("write", "c1", {"filePath": "/p/allowed.txt", "content": "x"}), text="Writing it."),
    assistant("m3", tool("bash", "c2", {"command": "pytest -q"}, status="error", error="1 failed")),
]


def no_judge(state, questions):
    raise JevUnavailable("test")


def items_of(messages):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        for r in opencode_session.records(messages):
            f.write(json.dumps(r) + "\n")
    try:
        return transcript_items.extract_items(f.name)
    finally:
        os.unlink(f.name)


class RecordsTest(unittest.TestCase):
    def test_user_assistant_and_tool_items(self):
        items = items_of(MESSAGES)
        kinds = [it["kind"] for it in items]
        self.assertIn("user", kinds)
        self.assertIn("assistant", kinds)
        tools = [it for it in items if it["kind"] == "tool"]
        self.assertEqual([t["tool"] for t in tools], ["Write", "Bash"])
        self.assertIn("/p/allowed.txt", tools[0]["text"])
        self.assertTrue(tools[1].get("is_error"))

    def test_synthetic_and_odd_parts(self):
        msgs = [user("m1", "Dryas rules and warnings", synthetic=True), user("m2", "real prompt"),
                assistant("m3", {"type": "tool", "tool": "webfetch", "callID": "c9"},
                          tool("mystery", "c8", {"x": "short"}), tool("read", "c7", {"filePath": "/p/f"}, output="y" * 2000000)),
                {"info": "bad"}, {"parts": []}, "junk", None]
        items = items_of(msgs)
        texts = " ".join(it["text"] for it in items)
        self.assertNotIn("Dryas rules and warnings", texts)
        self.assertIn("real prompt", texts)
        self.assertEqual(opencode_session.records("not a list"), [])


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj)
        subprocess.run(["git", "init", "-q", self.proj], check=True)
        self.env = mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": os.path.join(self.tmp, "data"),
                                                "JEV_HANDOFF_DIR": os.path.join(self.tmp, "handoff"),
                                                "JEV_COMPACT_DIR": os.path.join(self.tmp, "compact")})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def ev(self):
        return {"session_id": "ses_abc", "cwd": self.proj, "messages": MESSAGES}

    def test_compact_returns_restore_context(self):
        out = opencode_session.compact(self.ev(), judge_fn=no_judge)
        self.assertIn("Handoff from previous session", out["context"])
        self.assertIn("Please write allowed.txt", out["context"])
        self.assertEqual(os.listdir(os.path.join(self.tmp, "data", "jev", "opencode")), [])  # transcript removed

    def test_compact_with_no_items_is_empty(self):
        self.assertEqual(opencode_session.compact(dict(self.ev(), messages=[]), judge_fn=no_judge), {"context": ""})

    def test_handoff_saves_and_says_new(self):
        out = opencode_session.save_handoff(self.ev(), judge_fn=no_judge)
        self.assertTrue(out["line"].startswith("Handoff saved:"), out)
        self.assertIn("/new", out["line"])
        self.assertNotIn("/clear", out["line"])
        import handoff_restore
        restored = handoff_restore.run({"cwd": self.proj, "source": "clear"})
        self.assertIn("Please write allowed.txt", restored["hookSpecificOutput"]["additionalContext"])

    def test_cli_never_fails(self):
        script = os.path.join(HERE, "..", "opencode_session.py")
        for args, stdin in ((["compact"], "not json"), (["nope"], "{}"), ([], "{}")):
            p = subprocess.run([sys.executable, script] + args, input=stdin, text=True, capture_output=True, timeout=60)
            self.assertEqual(p.returncode, 0)
            json.loads(p.stdout)


class EnginePolicyTest(unittest.TestCase):
    """OpenCode compact and handoff under a .dryas-judge marker send nothing to Jev (spec 2026-10-19 §7.3)."""
    setUp = EngineTest.setUp
    tearDown = EngineTest.tearDown
    ev = EngineTest.ev

    def boom(self, state, questions):
        raise AssertionError("Jev called under a marker")

    def mark(self):
        import judge_policy
        judge_policy.clear_cache()
        self.addCleanup(judge_policy.clear_cache)
        open(os.path.join(self.proj, ".dryas-judge"), "w").write("local\n")
        p = mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k", "JEV_LOG_DIR": os.path.join(self.tmp, "logs")})
        p.start()
        self.addCleanup(p.stop)

    def last(self, name):
        with open(os.path.join(self.tmp, "logs", name + ".jsonl")) as f:
            return [json.loads(l) for l in f][-1]

    def test_compact_under_marker_never_calls_jev(self):
        self.mark()
        out = opencode_session.compact(self.ev(), judge_fn=self.boom)
        self.assertIn("Handoff from previous session", out["context"])
        self.assertEqual((self.last("compact")["jev_ok"], self.last("compact")["judge_policy"]),
                         ("local", "project_local"))

    def test_handoff_under_marker_never_calls_jev(self):
        self.mark()
        out = opencode_session.save_handoff(self.ev(), judge_fn=self.boom)
        self.assertIn("local judge (project policy)", out["line"])
        self.assertEqual(self.last("handoff")["judge_policy"], "project_local")


if __name__ == "__main__":
    unittest.main()
