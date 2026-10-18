import os
import socket
import stat
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import usage_watch

BASE = "http://127.0.0.1:4317/api/usage"
SID = "sess-1"


def acct(label, five, week=None):
    return {"label": label, "dir": "~/.claude-" + label, "fiveHour": five, "sevenDay": week, "at": 1}


def server(*accounts, switch=0.9, me="team"):
    """Fake fetch: the session URL returns `me`'s account, the bare URL the usage doc."""
    calls = []

    def fetch(url, timeout):
        calls.append((url, timeout))
        if url.startswith(BASE + "?session="):
            return {"label": me, "dir": "~/.claude-" + me}
        if url == BASE:
            return {"accounts": list(accounts), "switchAt": switch}
        return None
    fetch.calls = calls
    return fetch


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = {k: os.environ.get(k) for k in ("JEV_HANDOFF_DIR", "FO_PORT")}
        os.environ["JEV_HANDOFF_DIR"] = self.tmp
        os.environ.pop("FO_PORT", None)

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def ev(self, sid=SID):
        return {"session_id": sid, "hook_event_name": "UserPromptSubmit"}

    def test_warns_at_switch_with_calm_account(self):
        line = usage_watch.run(self.ev(), server(acct("team", 0.92), acct("team2", 0.03)))
        self.assertEqual(line, "Account team is at 5h 92%; team2 has room (5h 3%). Tell the user: run /handoff move, "
                               "then /exit, then start a new session in this folder with: cl --account team2 "
                               "(the handoff loads on startup within 30 min).")

    def test_once_per_tier_then_second_tier(self):
        f = server(acct("team", 0.91), acct("team2", 0.1))
        self.assertIsNotNone(usage_watch.run(self.ev(), f))
        self.assertIsNone(usage_watch.run(self.ev(), f))
        f2 = server(acct("team", 0.96), acct("team2", 0.1))
        self.assertIsNotNone(usage_watch.run(self.ev(), f2))
        self.assertIsNone(usage_watch.run(self.ev(), f2))

    def test_new_window_resets(self):
        self.assertIsNotNone(usage_watch.run(self.ev(), server(acct("team", 0.96), acct("team2", 0.1))))
        self.assertIsNone(usage_watch.run(self.ev(), server(acct("team", 0.05), acct("team2", 0.1))))
        self.assertIsNotNone(usage_watch.run(self.ev(), server(acct("team", 0.91), acct("team2", 0.1))))

    def test_below_switch_is_silent(self):
        self.assertIsNone(usage_watch.run(self.ev(), server(acct("team", 0.89), acct("team2", 0.0))))

    def test_weekly_names_week(self):
        line = usage_watch.run(self.ev(), server(acct("team", 0.2, 0.93), acct("team2", 0.1)))
        self.assertTrue(line.startswith("Account team is at week 93%; team2 has room (5h 10%)."))

    def test_calm_pick_is_lowest_five_hour_not_near(self):
        line = usage_watch.run(self.ev(), server(acct("team", 0.95), acct("a", 0.5), acct("b", 0.2, 0.95),
                                                 acct("c", 0.3), acct("d", None)))
        self.assertIn("c has room (5h 30%)", line)

    def test_no_calm_then_calm_warns(self):
        self.assertIsNone(usage_watch.run(self.ev(), server(acct("team", 0.92), acct("team2", 0.95))))
        self.assertIsNotNone(usage_watch.run(self.ev(), server(acct("team", 0.92), acct("team2", 0.4))))

    def test_unknown_session_is_silent(self):
        self.assertIsNone(usage_watch.run(self.ev(), lambda url, timeout: None))

    def test_session_account_missing_from_list_is_silent(self):
        self.assertIsNone(usage_watch.run(self.ev(), server(acct("team2", 0.1), acct("x", 0.1))))

    def test_malformed_docs_are_silent(self):
        for doc in ({"accounts": "x"}, {"accounts": [1, None]}, {"accounts": [acct("team", "hi")]}):
            f = lambda url, timeout, d=doc: {"label": "team", "dir": "~/.claude-team"} if "session=" in url else d
            self.assertIsNone(usage_watch.run(self.ev(), f))

    def test_bad_switch_at_uses_default(self):
        self.assertIsNotNone(usage_watch.run(self.ev(), server(acct("team", 0.91), acct("team2", 0.1), switch="x")))

    def test_budget_shared_and_exhausted_budget_stops(self):
        f = server(acct("team", 0.92), acct("team2", 0.1))
        ticks = iter([0.0, 0.31])
        self.assertIsNone(usage_watch.run(self.ev(), f, clock=lambda: next(ticks)))
        self.assertEqual(len(f.calls), 1)
        self.assertAlmostEqual(f.calls[0][1], 0.3)

    def test_session_id_is_quoted_and_bounded(self):
        f = server(acct("team", 0.92), acct("team2", 0.1))
        usage_watch.run(self.ev("a b/c"), f)
        self.assertEqual(f.calls[0][0], BASE + "?session=a%20b%2Fc")
        self.assertIsNone(usage_watch.run(self.ev("x" * 65), f))
        self.assertIsNone(usage_watch.run({}, f))

    def test_fo_port(self):
        os.environ["FO_PORT"] = "5000"
        f = server(acct("team", 0.92), acct("team2", 0.1))
        usage_watch.run(self.ev(), f)
        self.assertTrue(f.calls[0][0].startswith("http://127.0.0.1:5000/api/usage?session="))
        os.environ["FO_PORT"] = "50; rm"
        f = server(acct("team", 0.92), acct("team2", 0.1))
        usage_watch.run(self.ev("s2"), f)
        self.assertTrue(f.calls[0][0].startswith(BASE + "?session="))

    def test_state_is_private(self):
        usage_watch.run(self.ev(), server(acct("team", 0.92), acct("team2", 0.1)))
        d = os.path.join(self.tmp, ".usage-warned")
        self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o700)
        (f,) = os.listdir(d)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, f)).st_mode), 0o600)

    def test_unreachable_port_returns_fast(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        t = time.monotonic()
        self.assertIsNone(usage_watch.fetch_json("http://127.0.0.1:%d/api/usage" % port, 0.3))
        self.assertLess(time.monotonic() - t, 0.4)

    def test_slow_server_times_out_within_budget(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)  # accepts the connection, never answers
        try:
            t = time.monotonic()
            self.assertIsNone(usage_watch.fetch_json("http://127.0.0.1:%d/api/usage" % s.getsockname()[1], 0.3))
            self.assertLess(time.monotonic() - t, 0.4)
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
