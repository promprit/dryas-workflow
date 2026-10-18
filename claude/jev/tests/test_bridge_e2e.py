import json
import os
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
JEV = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bridge_fixture as bf  # noqa: E402
import bridge  # noqa: E402
import bridge_peers as bp  # noqa: E402
import jev_mcp  # noqa: E402


def real_bridge_config(tmp):
    """chain.json reduced to the shipped bridge-deliver stages, so the test checks what ships."""
    with open(os.path.join(JEV, "chain.json"), encoding="utf-8") as f:
        chain = json.load(f)
    cfg = {k: [s for s in chain[k] if s.get("name") == "bridge-deliver"] for k in ("prompt", "post")}
    assert cfg["prompt"] and cfg["post"], "bridge-deliver missing from chain.json"
    p = os.path.join(tmp, "chain.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return p


@unittest.skipIf(os.name == "nt", "start-time matching uses ps (POSIX)")
class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.sb = bf.Sandbox(self)
        self.sb.me()
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_B, "peer-b")
        self.cfg = real_bridge_config(self.sb.d)

    def hook(self, kind, sid, name):
        env = dict(os.environ, JEV_CHAIN_CONFIG=self.cfg, JEV_CHAIN_LOCAL=os.path.join(self.sb.d, "none.json"))
        ev = {"session_id": sid, "hook_event_name": name, "prompt": "hi", "tool_name": "Bash", "tool_input": {}}
        r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(JEV, "chain.py"), kind], input=json.dumps(ev),
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 0)
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""

    def test_message_and_reply(self):
        with mock.patch.dict(os.environ, {"DRYAS_HARNESS": "claude"}):
            r = jev_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                "params": {"name": "send_message", "arguments": {"to": "peer-b", "text": "can you review?"}}})
        sent = json.loads(r["result"]["content"][0]["text"])
        out = self.hook("prompt", bf.SID_B, "UserPromptSubmit")
        self.assertIn("can you review?", out)
        self.assertIn("id %s," % sent["id"], out)
        self.assertEqual(self.hook("prompt", bf.SID_B, "UserPromptSubmit"), "")
        b = [s for s in bp.read_sessions(bp.account_dirs()[0]) if s["sessionId"] == bf.SID_B][0]
        with mock.patch.object(bp, "me", return_value=b):
            reply, err = bridge.call("send_message", {"to": "me", "text": "done", "reply_to": sent["id"]})
        self.assertFalse(err, reply)
        back = self.hook("post", bf.SID_ME, "PostToolUse")
        self.assertIn("[reply to %s]" % sent["id"], back)
        self.assertIn("done", back)


if __name__ == "__main__":
    unittest.main()
