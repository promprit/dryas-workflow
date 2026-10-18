"""Plan 2: the chain runs the memory, context-watch and outcome stages for --harness opencode (spec section 4);
Codex coverage is unchanged."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "claude/jev"))
import chain  # noqa: E402

OPENCODE = {"prompt": ["jev-route", "context-watch"], "post": ["mem-edit", "gate-outcome"],
            "subagent-stop": ["mem-task"], "session-start": ["mem-session-start"],
            "session-end": ["mem-session-end", "mem-notes"], "precompact": ["mem-session-end", "mem-notes"],
            "stop": ["mem-notes"]}


def names(kind, harness):
    with mock.patch.dict(os.environ, {"JEV_CHAIN_LOCAL": os.path.join(tempfile.gettempdir(), "no-such-chain.local.json")}):
        return [s["name"] for s in chain.load_stages(kind, harness)]


class StageListTest(unittest.TestCase):
    def test_opencode_runs_every_stage_but_ruflo_and_flowobserve(self):
        for kind, want in OPENCODE.items():
            self.assertEqual(names(kind, "opencode"), want, kind)
        self.assertEqual(names("pretool", "opencode"), ["scope-lock", "jev-gate"])

    def test_codex_unchanged(self):
        self.assertEqual(names("prompt", "codex"), ["jev-route"])
        for kind in ("post", "subagent-stop", "session-start", "session-end", "precompact", "stop"):
            self.assertEqual(names(kind, "codex"), [], kind)

    def test_claude_unchanged(self):
        self.assertEqual(names("post", "claude"), ["mem-edit", "gate-outcome", "bridge-deliver"])
        self.assertEqual(names("session-end", "claude"), ["mem-session-end", "mem-notes"])


class ObserveEventTest(unittest.TestCase):
    """Claude-shaped events as the shim sends them reach the real memory stages."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dryas-oc-chain-")
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj)
        subprocess.run(["git", "init", "-q", self.proj], check=True)
        # Slow CI runners (Windows, Python 3.9) can miss the memory stages' 2 s limit; the test is about which
        # stages the events reach, so give them room through chain.local.json's per-stage timeout override.
        local = os.path.join(self.tmp, "chain.local.json")
        with open(local, "w", encoding="utf-8") as f:
            json.dump({"stages": {kind: {name: {"timeout": 30}} for kind, name in (
                ("session-start", "mem-session-start"), ("post", "mem-edit"), ("session-end", "mem-session-end"))}}, f)
        self.env = dict(os.environ, DRYAS_DATA_ROOT=os.path.join(self.tmp, "data"), JEV_CHAIN_LOCAL=local)

    def run_chain(self, kind, event):
        subprocess.run([sys.executable, "-X", "utf8", str(REPO / "claude/jev/chain.py"), kind, "--harness", "opencode"],
                       input=json.dumps(event), text=True, env=self.env, check=True, timeout=60)

    def rows(self, sql, *args):
        con = sqlite3.connect(os.path.join(self.tmp, "data", "dryas.db"))
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    def test_session_start_and_post_write_rows(self):
        base = {"session_id": "ses_oc1", "cwd": self.proj}
        self.run_chain("session-start", dict(base, hook_event_name="SessionStart", source="startup"))
        self.run_chain("post", dict(base, hook_event_name="PostToolUse", tool_name="Write", tool_use_id="call_1",
                                    tool_input={"file_path": "a.txt", "content": "x"}, tool_response={"output": ""}))
        self.run_chain("post", dict(base, hook_event_name="PostToolUseFailure", tool_name="Edit", tool_use_id="call_2",
                                    tool_input={"file_path": "b.txt", "old_string": "a", "new_string": "b"}, error="no match"))
        self.assertEqual(self.rows("SELECT id FROM sessions WHERE id = ?", "ses_oc1"), [("ses_oc1",)])
        self.assertEqual(sorted(self.rows("SELECT file, ok FROM edits WHERE session = ?", "ses_oc1")),
                         [("a.txt", 1), ("b.txt", 0)])

    def test_session_end_closes_the_session(self):
        base = {"session_id": "ses_oc2", "cwd": self.proj}
        self.run_chain("session-start", dict(base, hook_event_name="SessionStart", source="startup"))
        self.run_chain("session-end", dict(base, hook_event_name="SessionEnd", reason="deleted"))
        (ended,), = self.rows("SELECT ended FROM sessions WHERE id = ?", "ses_oc2")
        self.assertIsNotNone(ended)


if __name__ == "__main__":
    unittest.main()
