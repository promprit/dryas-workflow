import builtins
import json
import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bridge_fixture as bf  # noqa: E402  (puts claude/jev on sys.path)
import bridge_peers as bp  # noqa: E402
import paths  # noqa: E402


@unittest.skipIf(os.name == "nt", "start-time matching uses ps (POSIX)")
class PeersTest(unittest.TestCase):
    def setUp(self):
        self.sb = bf.Sandbox(self)
        self.sb.me()

    def names(self, out=None):
        return sorted(p["name"] for p in (out or bp.list_peers())["peers"])

    def test_finds_peer_on_other_account(self):
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_B, "peer-b")
        out = bp.list_peers()
        self.assertEqual(self.names(out), ["peer-b"])
        p = out["peers"][0]
        self.assertEqual(p["account"], ".claude-two")
        self.assertFalse(p["same_account"])
        self.assertNotIn("note", out)

    def test_copied_live_session_listed_once(self):
        pid = self.sb.child()
        bf.write_session(self.sb.acc2, pid, bf.SID_B, "peer-b")
        bak = os.path.join(self.sb.d, ".claude.bak")
        os.makedirs(os.path.join(bak, "sessions"))
        shutil.copy(os.path.join(self.sb.acc2, "sessions", "%d.json" % pid), os.path.join(bak, "sessions"))
        out = bp.list_peers()
        self.assertEqual(self.names(out), ["peer-b"])
        self.assertEqual(out["peers"][0]["account"], ".claude-two")

    def test_stale_record_does_not_hide_live_session(self):
        pid = self.sb.child()
        bf.write_session(self.sb.acc1, pid, "33333333-3333-4333-8333-333333333333", "stale", proc_start="Mon Jan  1 00:00:00 2001")
        bf.write_session(self.sb.acc2, pid, bf.SID_B, "peer-b")
        self.assertEqual(self.names(), ["peer-b"])

    def test_same_account_peer_marked(self):
        bf.write_session(self.sb.acc1, self.sb.child(), bf.SID_B, "peer-b")
        self.assertTrue(bp.list_peers()["peers"][0]["same_account"])

    def test_dead_pid_skipped(self):
        bf.write_session(self.sb.acc2, self.sb.dead_pid(), bf.SID_B, "gone", proc_start="Mon Jan  1 00:00:00 2001")
        self.assertEqual(self.names(), [])

    def test_start_time_mismatch_counts_as_dead(self):
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_B, "reused", proc_start="Mon Jan  1 00:00:00 2001")
        self.assertEqual(self.names(), [])

    def test_procstart_compared_in_utc(self):
        pid = self.sb.child()
        local = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                               env=dict(os.environ, TZ="Asia/Bangkok", LC_ALL="C")).stdout
        bf.write_session(self.sb.acc2, pid, bf.SID_B, "local-time", proc_start=" ".join(local.split()))
        with mock.patch.dict(os.environ, {"TZ": "Asia/Bangkok"}):
            self.assertEqual(self.names(), [])  # a local-time procStart never matches: ps is read in UTC
        bf.write_session(self.sb.acc2, pid, bf.SID_B, "utc")
        with mock.patch.dict(os.environ, {"TZ": "Asia/Bangkok"}):
            self.assertEqual(self.names(), ["utc"])

    def test_exact_fields_and_no_config_path(self):
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_B, "peer-b")
        out = bp.list_peers()
        self.assertEqual(set(out["peers"][0]), set(bp.PEER_KEYS))
        self.assertIn("dryas", bp.PEER_KEYS)
        self.assertNotIn(self.sb.acc2, json.dumps(out))
        self.assertNotIn("messagingSocketPath", json.dumps(out))

    def test_key_files_never_opened(self):
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_B, "peer-b")
        opened = []
        real = builtins.open

        def spy(path, *a, **kw):
            opened.append(str(path))
            return real(path, *a, **kw)

        with mock.patch("builtins.open", spy):
            bp.list_peers()
        self.assertTrue(opened)
        self.assertFalse([p for p in opened if p.endswith(".key")])

    def test_fallback_without_accounts_json(self):
        os.remove(paths.accounts_file())
        bf.write_session(self.sb.acc1, self.sb.child(), bf.SID_B, "here")
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_C, "elsewhere")
        out = bp.list_peers()
        self.assertEqual(self.names(out), ["elsewhere", "here"])  # discovery finds .claude-two too
        self.assertIn("accounts.json unreadable", out["note"])

    def test_duplicate_account_dirs_listed_once(self):
        with open(paths.accounts_file(), "w", encoding="utf-8") as f:
            json.dump({"claude_dirs": [self.sb.acc1, self.sb.acc2, self.sb.acc2 + os.sep]}, f)
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_B, "peer-b")
        self.assertEqual(self.names(), ["peer-b"])

    def test_caller_and_background_left_out(self):
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_B, "worker", kind="background")
        self.assertEqual(self.names(), [])

    def test_odd_session_fields(self):
        pid = self.sb.child()
        bf.write_session(self.sb.acc2, pid, bf.SID_B, "odd", updated="yesterday", extra={"newField": [1, 2]})
        bf.write_session(self.sb.acc1, self.sb.child(), bf.SID_C, "no-start", proc_start="")
        with open(os.path.join(self.sb.acc2, "sessions", "999999.json"), "w", encoding="utf-8") as f:
            f.write("{not json")
        out = bp.list_peers()
        self.assertEqual(self.names(out), ["no-start", "odd"])
        self.assertIn("start time missing for 1 session(s)", out["note"])
        self.assertIsNone([p for p in out["peers"] if p["name"] == "odd"][0]["idle_for"])

    def test_mismatch_is_noted(self):
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_B, "reused", proc_start="Mon Jan  1 00:00:00 2001")
        out = bp.list_peers()
        self.assertEqual(self.names(out), [])
        self.assertIn("1 session(s) skipped", out["note"])

    def test_finds_unlisted_account(self):
        bot = os.path.join(self.sb.d, ".claude-bot")
        bf.write_session(bot, self.sb.child(), bf.SID_B, "bot-peer")
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_C, "listed")
        out = bp.list_peers()
        self.assertEqual(self.names(out), ["bot-peer", "listed"])
        self.assertEqual([p["account"] for p in out["peers"] if p["name"] == "bot-peer"], [".claude-bot"])

    def test_listed_and_discovered_not_duplicated(self):
        dirs = bp.account_dirs()[0]
        self.assertEqual(dirs[:2], [self.sb.acc1, self.sb.acc2])
        self.assertEqual(len(dirs), 2)
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_B, "peer-b")
        self.assertEqual(self.names(), ["peer-b"])

    def test_stale_backup_dir_not_listed(self):
        bf.write_session(os.path.join(self.sb.d, ".claude.bak-1"), self.sb.dead_pid(), bf.SID_B, "old")
        out = bp.list_peers()
        self.assertEqual(self.names(out), [])
        self.assertNotIn("note", out)

    def test_unrelated_dirs_ignored(self):
        bf.write_session(os.path.join(self.sb.d, ".claudex"), self.sb.child(), bf.SID_B, "x")
        bf.write_session(os.path.join(self.sb.d, "claude"), self.sb.child(), bf.SID_C, "y")
        self.assertEqual(self.names(), [])

    def test_dryas_flag(self):
        os.remove(os.path.join(self.sb.acc2, ".dryas-plugin.json"))
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_B, "no-dryas")
        bf.write_session(self.sb.acc1, self.sb.child(), bf.SID_C, "has-dryas")
        got = {p["name"]: p["dryas"] for p in bp.list_peers()["peers"]}
        self.assertEqual(got, {"no-dryas": False, "has-dryas": True})

    def test_discovery_without_accounts_json(self):
        os.remove(paths.accounts_file())
        bf.write_session(os.path.join(self.sb.d, ".claude-bot"), self.sb.child(), bf.SID_B, "bot-peer")
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_C, "elsewhere")
        out = bp.list_peers()
        self.assertEqual(self.names(out), ["bot-peer", "elsewhere"])
        self.assertIn("scanning ~/.claude*", out["note"])

    def test_symlinked_dir_not_followed(self):
        real = os.path.join(self.sb.d, "elsewhere")
        bf.write_session(real, self.sb.child(), bf.SID_B, "linked")
        os.symlink(real, os.path.join(self.sb.d, ".claude-link"))
        self.assertEqual(self.names(), [])

    def test_me_follows_session_id_change(self):
        dirs = bp.account_dirs()[0]
        self.assertEqual(bp.me(dirs)["sessionId"], bf.SID_ME)
        bf.write_session(self.sb.acc1, os.getppid(), bf.SID_C, "me")
        self.assertEqual(bp.me(dirs)["sessionId"], bf.SID_C)

    def test_me_found_from_parent(self):
        s = bp.me(bp.account_dirs()[0])
        self.assertEqual(s["sessionId"], bf.SID_ME)

    def test_me_none_without_session_file(self):
        os.remove(os.path.join(self.sb.acc1, "sessions", "%d.json" % os.getppid()))
        bp._ME.clear()
        self.assertIsNone(bp.me(bp.account_dirs()[0]))


@unittest.skipIf(os.name == "nt", "start-time matching uses ps (POSIX)")
class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.sb = bf.Sandbox(self)
        self.sb.me()

    def run_resolve(self, to):
        dirs = bp.account_dirs()[0]
        sessions = bp.read_sessions(dirs)
        alive = bp.live(sessions)[0]
        return bp.resolve(to, sessions, bp.pool(alive, bp.me(dirs)), {s["sessionId"] for s in alive})

    def test_by_name_and_by_prefix(self):
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_B, "peer-b")
        self.assertEqual(self.run_resolve("peer-b")[0]["sessionId"], bf.SID_B)
        self.assertEqual(self.run_resolve(bf.SID_B[:8])[0]["sessionId"], bf.SID_B)
        self.assertIsNone(self.run_resolve(bf.SID_B[:7])[0])

    def test_ambiguous_name_lists_candidates(self):
        bf.write_session(self.sb.acc2, self.sb.child(), bf.SID_B, "twin")
        bf.write_session(self.sb.acc1, self.sb.child(), bf.SID_C, "twin")
        s, err = self.run_resolve("twin")
        self.assertIsNone(s)
        self.assertIn("matches 2 sessions", err)
        self.assertIn(bf.SID_B[:8], err)
        self.assertIn(bf.SID_C[:8], err)

    def test_not_running(self):
        bf.write_session(self.sb.acc2, self.sb.dead_pid(), bf.SID_B, "gone", proc_start="Mon Jan  1 00:00:00 2001")
        self.assertEqual(self.run_resolve("gone"), (None, "gone is not running"))

    def test_unknown(self):
        self.assertIn("no live session named or starting with", self.run_resolve("nobody")[1])


class PidTest(unittest.TestCase):
    def test_pid_running(self):
        self.assertTrue(bp.pid_running(os.getpid()))
        self.assertFalse(bp.pid_running(0))
        self.assertFalse(bp.pid_running(-5))


if __name__ == "__main__":
    unittest.main()
