import json
import os
import sys
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bridge_fixture as bf  # noqa: E402
import bridge  # noqa: E402
import bridge_peers as bp  # noqa: E402


@unittest.skipIf(os.name == "nt", "start-time matching uses ps (POSIX)")
class SendTest(unittest.TestCase):
    def setUp(self):
        self.sb = bf.Sandbox(self)
        self.sb.me()
        self.pid_b = self.sb.child()
        bf.write_session(self.sb.acc2, self.pid_b, bf.SID_B, "peer-b", status="idle")

    def box(self, sid=bf.SID_B):
        return os.path.join(self.sb.root, "inbox", sid)

    def msgs(self, sid=bf.SID_B):
        out = []
        for n in sorted(os.listdir(self.box(sid))):
            if n.endswith(".json"):
                with open(os.path.join(self.box(sid), n), encoding="utf-8") as f:
                    out.append(json.load(f))
        return out

    def send(self, **args):
        return bridge.call("send_message", args)

    def test_send_by_name_writes_one_message(self):
        out, err = self.send(to="peer-b", text="hello there")
        self.assertFalse(err, out)
        [m] = self.msgs()
        self.assertEqual(m["v"], 1)
        self.assertRegex(m["id"], r"^m-[0-9a-f]{12}$")
        self.assertEqual(m["from"], {"sessionId": bf.SID_ME, "name": "me", "account": ".claude", "cwd": "/work/me"})
        self.assertEqual((m["to"], m["reply_to"], m["text"]), (bf.SID_B, None, "hello there"))
        self.assertEqual(out["id"], m["id"])
        self.assertEqual(out["to"], {"name": "peer-b", "sessionId": bf.SID_B, "account": ".claude-two"})
        self.assertIn("is idle", out["note"])
        self.assertFalse([n for n in os.listdir(self.box()) if n.startswith(".tmp-")])
        self.assertEqual(os.stat(self.box()).st_mode & 0o777, 0o700)
        f = [n for n in os.listdir(self.box()) if n.endswith(".json")][0]
        self.assertEqual(os.stat(os.path.join(self.box(), f)).st_mode & 0o777, 0o600)

    def test_send_by_prefix(self):
        self.assertFalse(self.send(to=bf.SID_B[:8], text="x")[1])
        self.assertEqual(len(self.msgs()), 1)

    def test_send_to_self_refused(self):
        for to in ("me", bf.SID_ME[:8]):
            out, err = self.send(to=to, text="x")
            self.assertTrue(err)
            self.assertEqual(out["error"], "that is this session")

    def test_same_name_peer_on_other_account_reachable(self):
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_C, "me")
        out, err = self.send(to="me", text="x")
        self.assertFalse(err, out)
        self.assertEqual(len(self.msgs(bf.SID_C)), 1)

    def test_rate_counted_before_message(self):
        real = bridge._write

        def fail_inbox(folder, name, obj):
            if folder == self.box():
                raise OSError("disk")
            return real(folder, name, obj)

        with mock.patch.object(bridge, "_write", fail_inbox):
            self.assertTrue(self.send(to="peer-b", text="x")[1])
        self.assertEqual(len(bridge._recent_sends(bf.SID_ME, time.time())), 1)

    def test_ambiguous_name_refused_with_candidates(self):
        bf.write_session(self.sb.acc1, self.sb.child(), bf.SID_C, "peer-b")
        out, err = self.send(to="peer-b", text="x")
        self.assertTrue(err)
        self.assertIn("matches 2 sessions", out["error"])

    def test_not_running_refused(self):
        bf.write_session(self.sb.acc2, self.sb.dead_pid(), bf.SID_C, "gone", proc_start="Mon Jan  1 00:00:00 2001")
        self.assertEqual(self.send(to="gone", text="x"), ({"error": "gone is not running"}, True))

    def test_redacted_before_size_check(self):
        text = "x" * 8100 + " Bearer " + "a" * 200  # 8308 bytes raw, 8118 after redaction
        out, err = self.send(to="peer-b", text=text)
        self.assertFalse(err, out)
        self.assertNotIn("a" * 200, self.msgs()[0]["text"])
        self.assertIn("Bearer [REDACTED]", self.msgs()[0]["text"])

    def test_too_long_refused(self):
        self.assertEqual(self.send(to="peer-b", text="x" * 8193)[0]["error"],
                         "too long, 8193 bytes; send a file path instead")
        self.assertFalse(self.send(to="peer-b", text="x" * 8192)[1])

    def test_limit_counts_utf8_bytes(self):
        thai = "สวัสดี"  # 6 characters, 18 bytes
        self.assertTrue(self.send(to="peer-b", text=thai * 456)[1])  # 8208 bytes
        self.assertFalse(self.send(to="peer-b", text=thai * 455)[1])  # 8190 bytes
        self.assertEqual(self.msgs()[0]["text"], thai * 455)

    def test_empty_text_refused(self):
        self.assertEqual(self.send(to="peer-b", text="  ")[0]["error"], "text is empty")

    def test_reply_to(self):
        self.assertEqual(self.send(to="peer-b", text="x", reply_to="m-zz")[0]["error"], "bad reply_to")
        self.assertFalse(self.send(to="peer-b", text="x", reply_to="m-0123456789ab")[1])
        self.assertEqual(self.msgs()[0]["reply_to"], "m-0123456789ab")

    def test_inbox_full(self):
        os.makedirs(self.box())
        for i in range(50):
            with open(os.path.join(self.box(), "%013d-0000000%d.json" % (i, i % 10)), "w", encoding="utf-8") as f:
                f.write("{}")
        self.assertEqual(self.send(to="peer-b", text="x")[0]["error"], "inbox full: peer-b has not taken a turn")

    def test_rate_limit(self):
        for _ in range(20):
            self.assertFalse(self.send(to="peer-b", text="x")[1])
        self.assertEqual(self.send(to="peer-b", text="x")[0]["error"], "rate limit, 20 sent in 10 min")

    def test_unknown_caller(self):
        os.remove(os.path.join(self.sb.acc1, "sessions", "%d.json" % os.getppid()))
        bp._ME.clear()
        self.assertEqual(self.send(to="peer-b", text="x")[0]["error"], "cannot tell which session this is")

    def test_cloud_copy_refused(self):
        with mock.patch("paths.copy_root", return_value="/copy/.dryas"):
            self.assertEqual(self.send(to="peer-b", text="x"), ({"error": "not supported in a cloud copy"}, True))

    def test_log_never_holds_text(self):
        self.send(to="peer-b", text="private words")
        self.send(to="nobody", text="other private words")
        with open(os.path.join(self.sb.d, "logs", "bridge.jsonl"), encoding="utf-8") as f:
            log = f.read()
        self.assertIn('"event":"sent"', log)
        self.assertIn('"event":"refused"', log)
        self.assertNotIn("private words", log)

    def test_peer_without_dryas_refused(self):
        os.remove(os.path.join(self.sb.acc2, ".dryas-plugin.json"))
        out, err = self.send(to="peer-b", text="x")
        self.assertTrue(err)
        self.assertIn(".claude-two", out["error"])
        self.assertIn("no Dryas", out["error"])
        self.assertNotIn(self.sb.d, out["error"])
        self.assertFalse(os.path.exists(self.box()))
        self.assertEqual(bridge._recent_sends(bf.SID_ME, time.time()), [])

    def test_message_has_no_recipient_process_fields(self):
        self.assertFalse(self.send(to="peer-b", text="x")[1])
        [m] = self.msgs()
        self.assertNotIn("to_pid", m)
        self.assertNotIn("to_proc_start", m)

    def test_no_pointer_without_procstart(self):
        pid = self.sb.child()
        bf.write_session(self.sb.acc2, pid, bf.SID_C, "peer-c", proc_start="")
        with mock.patch.object(bp, "start_times", return_value=None):  # pid-only liveness
            out, err = self.send(to="peer-c", text="x")
        self.assertFalse(err, out)
        self.assertFalse(os.path.exists(os.path.join(self.sb.root, "inbox", ".bypid", "%d.json" % pid)))

    def test_bypid_pointer_written_and_merged(self):
        pdir = os.path.join(self.sb.root, "inbox", ".bypid")
        self.send(to="peer-b", text="x")
        self.send(to="peer-b", text="y")
        with open(os.path.join(pdir, "%d.json" % self.pid_b), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"procStart": bf.ps_start(self.pid_b), "sids": [bf.SID_B]})
        self.assertEqual(os.stat(pdir).st_mode & 0o777, 0o700)
        pid_c = self.sb.child()
        bf.write_session(self.sb.acc2, pid_c, bf.SID_C, "peer-c")
        self.assertFalse(self.send(to="peer-c", text="z")[1])
        self.assertEqual(sorted(os.listdir(pdir)), sorted(["%d.json" % self.pid_b, "%d.json" % pid_c]))

    def test_list_peers_tool(self):
        out, err = bridge.call("list_peers", {})
        self.assertFalse(err)
        self.assertEqual([p["name"] for p in out["peers"]], ["peer-b"])


if __name__ == "__main__":
    unittest.main()
