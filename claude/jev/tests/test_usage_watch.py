import os
import socket
import stat
import sys
import tempfile
import threading
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
        self.every = usage_watch.CHECK_EVERY_S
        usage_watch.CHECK_EVERY_S = 0  # these tests check every prompt; ThrottleTest covers the interval

    def tearDown(self):
        usage_watch.CHECK_EVERY_S = self.every
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

    @unittest.skipIf(os.name == "nt", "POSIX file modes; chmod is a no-op on Windows")
    def test_state_is_private(self):
        usage_watch.run(self.ev(), server(acct("team", 0.92), acct("team2", 0.1)))
        d = os.path.join(self.tmp, ".usage-warned")
        self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o700)
        names = os.listdir(d)
        self.assertEqual(len(names), 2)  # the tier and the last-check marker
        for f in names:
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

    def serve_once(self, body, delay, head=b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n"):
        """A one-shot local HTTP server that sends `head`, then `body` one byte every `delay` seconds."""
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        stop = threading.Event()

        def serve():
            try:
                c, _ = s.accept()
                c.recv(1024)
                c.sendall(head)
                for ch in body:
                    if stop.is_set():
                        break
                    c.sendall(bytes([ch]))
                    if delay:
                        time.sleep(delay)
                c.close()
            except OSError:
                pass
        threading.Thread(target=serve, daemon=True).start()
        self.addCleanup(s.close)
        self.addCleanup(stop.set)
        return "http://127.0.0.1:%d/api/usage" % s.getsockname()[1]

    def test_drip_feeding_server_is_cut_at_budget(self):
        url = self.serve_once(b'{"accounts": [], "switchAt": 0.9}', 0.05)  # ~1.7 s in total, each byte < 0.3 s
        t = time.monotonic()
        self.assertIsNone(usage_watch.fetch_json(url, 0.3))
        self.assertLess(time.monotonic() - t, 0.4)

    def test_fast_server_returns_the_object(self):
        url = self.serve_once(b'{"accounts": [], "switchAt": 0.9}', 0)
        self.assertEqual(usage_watch.fetch_json(url, 0.3), {"accounts": [], "switchAt": 0.9})

    def test_run_with_drip_feeding_server_stays_in_budget(self):
        url = self.serve_once(b'{"label": "team", "dir": "~/.claude-team"}', 0.05)
        os.environ["FO_PORT"] = url.split(":")[2].split("/")[0]
        t = time.monotonic()
        self.assertIsNone(usage_watch.run(self.ev()))
        self.assertLess(time.monotonic() - t, 0.4)

    def test_run_slow_fetches_share_one_budget(self):
        def slow(url, timeout):
            time.sleep(min(timeout, 0.25))
            return {"label": "team", "dir": "~/.claude-team"} if "session=" in url else None
        t = time.monotonic()
        self.assertIsNone(usage_watch.run(self.ev(), slow))
        self.assertLess(time.monotonic() - t, 0.4)

    def test_error_status_returns_none(self):
        url = self.serve_once(b'{"error":"unknown session"}', 0, head=b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n")
        self.assertIsNone(usage_watch.fetch_json(url, 0.3))

    def test_chunked_body_returns_none(self):
        url = self.serve_once(b"5\r\n{\"a\":\r\n0\r\n\r\n", 0,
                              head=b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n")
        self.assertIsNone(usage_watch.fetch_json(url, 0.3))

    def test_http11_close_delimited_body(self):
        url = self.serve_once(b'{"switchAt": 0.8}', 0, head=b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\n"
                                                         b"Connection: close\r\n\r\n")
        self.assertEqual(usage_watch.fetch_json(url, 0.3), {"switchAt": 0.8})

    def test_fetch_never_loads_urllib_request(self):
        import subprocess
        url = self.serve_once(b'{"switchAt": 0.8}', 0)
        code = ("import sys; sys.path.insert(0, %r); import usage_watch; v = usage_watch.fetch_json(%r, 0.3); "
                "print(v, 'urllib.request' in sys.modules)" % (HERE, url))
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, "{'switchAt': 0.8} False")

    def test_invalid_calm_label_is_skipped(self):
        line = usage_watch.run(self.ev(), server(acct("team", 0.95), acct("x y", 0.01), acct("a" * 33, 0.02),
                                                 acct("ok\n", 0.03), acct("good-1", 0.2)))
        self.assertIn("good-1 has room (5h 20%)", line)
        for bad in ("x y", "a" * 33, "ok\n"):
            self.assertNotIn(bad, line)

    def test_invalid_own_label_is_silent(self):
        self.assertIsNone(usage_watch.run(self.ev(), server(acct("te am", 0.95), acct("team2", 0.1), me="te am")))


class ThrottleTest(unittest.TestCase):
    """FlowObserve is asked at most once per CHECK_EVERY_S per session; other prompts only read a file's age."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.environ.get("JEV_HANDOFF_DIR")
        os.environ["JEV_HANDOFF_DIR"] = self.tmp
        self.t = 1_800_000_000.0

    def tearDown(self):
        if self.old is None:
            os.environ.pop("JEV_HANDOFF_DIR", None)
        else:
            os.environ["JEV_HANDOFF_DIR"] = self.old

    def run_at(self, dt, f, sid=SID):
        return usage_watch.run({"session_id": sid}, f, now=lambda: self.t + dt)

    def test_interval_is_a_minute(self):
        self.assertEqual(usage_watch.CHECK_EVERY_S, 60)

    def test_second_prompt_within_a_minute_does_not_fetch(self):
        f = server(acct("team", 0.5), acct("team2", 0.1))
        self.run_at(0, f)
        n = len(f.calls)
        self.assertIsNone(self.run_at(59, f))
        self.assertEqual(len(f.calls), n)

    def test_after_a_minute_fetches_and_warns(self):
        self.run_at(0, server(acct("team", 0.5), acct("team2", 0.1)))
        f = server(acct("team", 0.92), acct("team2", 0.1))
        self.assertIsNotNone(self.run_at(60, f))
        self.assertTrue(f.calls)

    def test_failed_fetch_also_waits(self):
        calls = []
        self.run_at(0, lambda u, t: calls.append(u))
        self.run_at(30, lambda u, t: calls.append(u))
        self.assertEqual(len(calls), 1)

    def test_sessions_are_throttled_apart(self):
        self.run_at(0, server(acct("team", 0.5), acct("team2", 0.1)))
        f = server(acct("team", 0.92), acct("team2", 0.1), me="team")
        self.assertIsNotNone(self.run_at(1, f, sid="sess-2"))

    def test_clock_set_back_checks_again(self):
        self.run_at(0, server(acct("team", 0.5), acct("team2", 0.1)))
        f = server(acct("team", 0.92), acct("team2", 0.1))
        self.assertIsNotNone(self.run_at(-3600, f))

    def test_unsafe_session_id_is_throttled_by_hash(self):
        calls = []
        self.run_at(0, lambda u, t: calls.append(u), sid="a b/c")
        self.run_at(1, lambda u, t: calls.append(u), sid="a b/c")
        self.assertEqual(len(calls), 1)
        self.assertFalse(any("/" in n or " " in n for n in os.listdir(os.path.join(self.tmp, ".usage-warned"))))

    @unittest.skipIf(os.name == "nt", "POSIX file modes; chmod is a no-op on Windows")
    def test_marker_is_private(self):
        self.run_at(0, lambda u, t: None)
        d = os.path.join(self.tmp, ".usage-warned")
        self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o700)
        for n in os.listdir(d):
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, n)).st_mode), 0o600)

    def test_throttled_prompt_loads_no_socket_hashlib_or_urllib(self):
        import subprocess
        code = ("import os, sys, time; sys.path.insert(0, %r); os.environ['JEV_HANDOFF_DIR'] = %r; import usage_watch; "
                "usage_watch.run({'session_id': 'sess-9'}, lambda u, t: None); "
                "[sys.modules.pop(m, None) for m in ('socket', 'hashlib', 'urllib.parse')]; "
                "usage_watch.run({'session_id': 'sess-9'}); "
                "print('socket' in sys.modules, 'hashlib' in sys.modules, 'urllib.parse' in sys.modules)"
                % (HERE, self.tmp))
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "False False False", out.stderr)


if __name__ == "__main__":
    unittest.main()
