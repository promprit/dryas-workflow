# Usage-limit handoff (Dryas side) — Implementation Plan

> **For agentic workers:** run with `/orchestrate` on this file (Dryas). Each `## Task N:` section is self-contained: its Goal/Scope/Done/Failing-test lines are the `.orchestrate/PLAN.md` contract; Interfaces and Steps follow. Steps use checkbox (`- [ ]`) syntax.

**Goal:** When a session's account nears its 5-hour or weekly limit and another account has room, Claude tells the user once per tier how to move, and `/handoff move` plus a fresh session restores the handoff at startup.
**Architecture:** A new UserPromptSubmit chain stage `jev/usage_watch.py` reads FlowObserve's `GET /api/usage` on 127.0.0.1 (300 ms budget, fail silent). `/handoff move` marks the saved handoff with `move=1`; `handoff_restore.py` also runs on `SessionStart(startup)` and restores only marked handoffs.
**Tech Stack:** Python 3.9 stdlib (`urllib.request`, `unittest`), Claude Code hooks, Dryas chain (`jev/chain.json`).
**Spec:** FlowObserve repo, `docs/superpowers/specs/2026-10-18-usage-limit-handoff-design.md` (approved 2026-10-18). The FlowObserve side (`cl` timeout) is a separate plan in that repo: `docs/superpowers/plans/2026-10-18-usage-limit-handoff-cl.md`.

## Global Constraints

- Python 3.9 stdlib only; tests run with `python3 -m pytest -q claude/jev/tests` from the repo root.
- No new approval prompts: the warning is `additionalContext` only.
- Fail silent and fast: the usage requests share a 300 ms budget; any error, timeout, 404, malformed JSON or missing account means no message. Never raise; the hook always exits 0.
- Network only to `http://127.0.0.1:<FO_PORT or 4317>/api/usage`, with proxies disabled (`ProxyHandler({})`).
- Claude harness only: the chain stage has `"harness": ["claude"]`.
- At most two warnings per limit window per session: tier 0 at `switchAt`, tier 1 at `switchAt + 0.05`; reset when use falls below `switchAt`.
- Warn only when another account has room (non-null `fiveHour`, both values below `switchAt`); otherwise silent.
- The new session is started with plain `cl --account <calm label>`, never `cl -c` (which follows the newest conversation, the account being left).
- Restore at startup only for a handoff whose header has `move=1`, under 30 min old, same project root; deleted after use.
- State files: dir mode 0700, file mode 0600, as in `context_watch.py`.

## Review Focus

- FlowObserve server down or slow (port closed, or answers after 1 s) → no message and the prompt is not delayed past ~0.35 s. Test: Task 1 `test_unreachable_port_returns_fast`.
- The session's account is not in the list (session never seen by FlowObserve, 404) → silent. Test: Task 1 `test_unknown_session_is_silent`.
- Every other account is also near → silent, and a later calm account still triggers the warning (tier not burned). Test: Task 1 `test_no_calm_then_calm_warns`.
- A plain `/handoff` (no move) followed by a new session started normally → not restored at startup; `/clear` behaves exactly as today. Test: Task 3 `test_startup_ignores_plain_handoff`, `test_clear_unchanged`.
- An old handoff file written before this change (header without `move=`) → parses with `move: False`. Test: Task 2 `test_old_header_has_no_move`.

---

## Task 1: usage_watch chain stage

Goal: Add `claude/jev/usage_watch.py` and register it as the `usage-watch` prompt stage after `context-watch`.
Scope:
- claude/jev/usage_watch.py
- claude/jev/tests/test_usage_watch.py
- claude/jev/chain.json
Done:
- `python3 -m pytest -q claude/jev/tests/test_usage_watch.py` passes
- `python3 -m pytest -q claude/jev/tests` passes (incl. `test_chain.py`, whose OpenCode stage list must stay unchanged)
Failing test first: claude/jev/tests/test_usage_watch.py :: WatchTest.test_warns_at_switch_with_calm_account

**Interfaces:**
- Consumes: `paths.handoff_dir()` (existing, `claude/jev/paths.py`).
- Produces: `usage_watch.run(event: dict, fetch=fetch_json, clock=time.monotonic) -> Optional[str]`; `usage_watch.fetch_json(url: str, timeout: float) -> Optional[dict]`; chain stage `usage-watch`.

- [ ] **Step 1: Write the failing tests.** Create `claude/jev/tests/test_usage_watch.py`:

```python
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
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q claude/jev/tests/test_usage_watch.py`. Expected: collection error `ModuleNotFoundError: No module named 'usage_watch'`.

- [ ] **Step 3: Implement.** Create `claude/jev/usage_watch.py`:

```python
#!/usr/bin/env python3
"""Chain stage on UserPromptSubmit (Claude only): when this session's account nears its 5-hour or weekly limit and
another account has room, tell the user how to move (/handoff move, /exit, cl --account <calm>).
Reads FlowObserve's GET /api/usage on 127.0.0.1, never through a proxy, within a 300 ms budget; any problem means
no message. Tiers: once at switchAt, once more at switchAt+0.05; reset when use falls below switchAt (a new window).
Same calm-account rule as FlowObserve's cl launcher (scripts/cl.py decide()); keep the two in step."""
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

BUDGET_S = 0.3
STEP = 0.05
DEFAULT_SWITCH = 0.9
MAX_SID = 64


def fetch_json(url: str, timeout: float) -> Optional[Dict[str, Any]]:
    """GET a local JSON object within `timeout` seconds, never through a proxy; None on any problem."""
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=max(timeout, 0.01)) as r:
            v = json.loads(r.read(65536).decode("utf-8"))
        return v if isinstance(v, dict) else None
    except Exception:
        return None


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _pct(x: float) -> str:
    return "%d%%" % int(x * 100 + 1e-9)


def _base() -> str:
    port = os.environ.get("FO_PORT", "")
    return "http://127.0.0.1:%s/api/usage" % (port if re.fullmatch(r"[0-9]{2,5}", port) else "4317")


def _assess(mine: Dict[str, Any], doc: Dict[str, Any]) -> Optional[Tuple[str, float, str, float, Optional[Dict[str, Any]]]]:
    """(my label, use, '5h'|'week', switchAt, calmest other account or None); None when my account is unknown."""
    at = _num(doc.get("switchAt"))
    if at is None or not 0 < at <= 1:
        at = DEFAULT_SWITCH
    rows = doc.get("accounts")
    rows = [a for a in rows if isinstance(a, dict)] if isinstance(rows, list) else []
    me = next((a for a in rows if isinstance(mine.get("dir"), str) and a.get("dir") == mine["dir"]), None) \
        or next((a for a in rows if isinstance(mine.get("label"), str) and a.get("label") == mine["label"]), None)
    if me is None or not isinstance(me.get("label"), str):
        return None
    vals = [(v, w) for v, w in ((_num(me.get("fiveHour")), "5h"), (_num(me.get("sevenDay")), "week")) if v is not None]
    if not vals:
        return None
    use, which = max(vals, key=lambda t: t[0])

    def near(a: Dict[str, Any]) -> bool:
        return any(v is not None and v >= at for v in (_num(a.get("fiveHour")), _num(a.get("sevenDay"))))

    calm: List[Dict[str, Any]] = sorted((a for a in rows if a is not me and isinstance(a.get("label"), str)
                                         and _num(a.get("fiveHour")) is not None and not near(a)),
                                        key=lambda a: _num(a.get("fiveHour")))
    return me["label"], use, which, at, (calm[0] if calm else None)


def _state_file(sid: str) -> str:
    return os.path.join(paths.handoff_dir(), ".usage-warned", hashlib.sha256(sid.encode("utf-8")).hexdigest()[:16])


def _read_tier(sfile: str) -> int:
    try:
        with open(sfile, encoding="utf-8") as f:
            return int(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return -1


def _write_tier(sfile: str, tier: int, use: float) -> None:
    d = os.path.dirname(sfile)
    os.makedirs(d, mode=0o700, exist_ok=True)
    os.chmod(d, 0o700)  # portable-ok: POSIX file privacy; no-op on Windows
    fd = os.open(sfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, ("%d %.4f" % (tier, use)).encode())
    finally:
        os.close(fd)
    os.chmod(sfile, 0o600)  # portable-ok: POSIX file privacy; no-op on Windows


def run(event: Dict[str, Any], fetch: Callable[[str, float], Optional[Dict[str, Any]]] = fetch_json,
        clock: Callable[[], float] = time.monotonic) -> Optional[str]:
    try:
        sid = event.get("session_id")
        if not isinstance(sid, str) or not sid or len(sid) > MAX_SID:
            return None
        base = _base()
        t0 = clock()
        mine = fetch(base + "?session=" + urllib.parse.quote(sid, safe=""), BUDGET_S)
        if not mine:
            return None
        left = BUDGET_S - (clock() - t0)
        if left <= 0:
            return None
        doc = fetch(base, left)
        a = _assess(mine, doc) if doc else None
        if a is None:
            return None
        label, use, which, at, calm = a
        tier = 1 if use >= at + STEP - 1e-9 else 0 if use >= at - 1e-9 else -1
        sfile = _state_file(sid)
        warned = _read_tier(sfile)
        if tier < 0:
            if warned >= 0:
                _write_tier(sfile, -1, use)  # a new window: warn again next time
            return None
        if tier <= warned or calm is None:
            return None  # a tier is spent only when it was shown
        _write_tier(sfile, tier, use)
        return ("Account %s is at %s %s; %s has room (5h %s). Tell the user: run /handoff move, then /exit, then "
                "start a new session in this folder with: cl --account %s (the handoff loads on startup within 30 min)."
                % (label, which, _pct(use), calm["label"], _pct(_num(calm.get("fiveHour")) or 0.0), calm["label"]))
    except Exception:
        return None


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        ev = json.loads(raw) if raw.strip() else {}
        line = run(ev if isinstance(ev, dict) else {})
        if line:
            sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": line}}))
    except Exception:
        pass
    sys.exit(0)
```

Then in `claude/jev/chain.json`, in the `"prompt"` list, insert this line directly after the `context-watch` entry:

```json
    {"name": "usage-watch", "harness": ["claude"], "component": "core", "cmd": ["$PY", "-X", "utf8", "$CD/jev/usage_watch.py"], "timeout": 2},
```

- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q claude/jev/tests/test_usage_watch.py && python3 -m pytest -q claude/jev/tests`. Expected: PASS (the OpenCode list in `test_chain.py::test_shipped_chain_runs_all_but_ruflo_and_flowobserve_on_opencode` is unchanged because the stage is Claude-only).
- [ ] **Step 5: Commit** `claude/jev/usage_watch.py claude/jev/tests/test_usage_watch.py claude/jev/chain.json` — `feat(jev): usage-watch warns before an account's limit when another has room`.

## Task 2: /handoff move

Goal: `/handoff move` saves a handoff whose header carries `move=1`, and `parse_header` reports it.
Scope:
- claude/jev/handoff.py
- claude/jev/handoff_paths.py
- claude/commands/handoff.md
- claude/jev/tests/test_handoff.py
Done:
- `python3 -m pytest -q claude/jev/tests/test_handoff.py` passes
Failing test first: claude/jev/tests/test_handoff.py :: MoveTest.test_move_header_round_trips

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `handoff.run(cwd, transcript=None, judge_fn=judge, deadline_s=60, move=False) -> str`; `handoff.render(..., note="", move=False)`; `handoff.build_handoff(..., move=False)` (passes `move` to `render`); `handoff_paths.parse_header(line) -> {"cwd", "session", "time", "move": bool} | None`; CLI `handoff.py save --cwd DIR [--transcript P] [--move]`.

- [ ] **Step 1: Write the failing tests.** Append to `claude/jev/tests/test_handoff.py` (it already imports `handoff`, `write_jsonl`, `user`, `judge_keeping` and defines `HandoffBase` with `self.cwd` and `self.tp`):

```python
class MoveTest(HandoffBase):
    def test_move_header_round_trips(self):
        write_jsonl(self.tp, [user("u")])
        out = handoff.run(self.cwd, self.tp, judge_keeping(lambda t: True), move=True)
        with open(handoff.handoff_path(self.cwd), encoding="utf-8") as f:
            first = f.readline()
        self.assertRegex(first, r" move=1 -->$")
        from handoff_paths import parse_header
        self.assertIs(parse_header(first)["move"], True)
        self.assertIn("for another account", out)
        self.assertIn("/exit", out)
        self.assertNotIn("/clear", out)

    def test_plain_save_has_no_move(self):
        write_jsonl(self.tp, [user("u")])
        out = handoff.run(self.cwd, self.tp, judge_keeping(lambda t: True))
        with open(handoff.handoff_path(self.cwd), encoding="utf-8") as f:
            first = f.readline()
        self.assertNotIn("move=", first)
        self.assertIn("Now run /clear.", out)

    def test_old_header_has_no_move(self):
        from handoff_paths import parse_header
        meta = parse_header("<!-- handoff cwd=/x session=s time=2026-10-01T00:00:00+0700 kept=1 total=2 -->")
        self.assertEqual(meta, {"cwd": "/x", "session": "s", "time": "2026-10-01T00:00:00+0700", "move": False})

    def test_cli_move_flag(self):
        from unittest import mock
        with mock.patch.object(handoff, "run", return_value="ok") as r:
            self.assertEqual(handoff.main(["handoff.py", "save", "--cwd", self.cwd, "--move"]), 0)
        r.assert_called_once_with(self.cwd, None, move=True)
        with mock.patch.object(handoff, "run", return_value="ok") as r:
            handoff.main(["handoff.py", "save", "--cwd", self.cwd])
        r.assert_called_once_with(self.cwd, None, move=False)
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q claude/jev/tests/test_handoff.py -k Move`. Expected: FAIL with `TypeError: run() got an unexpected keyword argument 'move'`.

- [ ] **Step 3: Implement.**
  - `claude/jev/handoff.py`:
    - `render(cwd, session, always, jev, total, note="", move=False)`: the header becomes
      `"<!-- handoff cwd=%s session=%s time=%s kept=%d total=%d%s -->" % (root, session, time.strftime("%Y-%m-%dT%H:%M:%S%z"), len(always) + len(jev), total, " move=1" if move else "")`.
    - `build_handoff(..., move=False)` passes `move=move` to `render`.
    - `run(cwd, transcript=None, judge_fn=judge, deadline_s=60, move=False)` passes `move` to `build_handoff`, and returns, when `move`:
      `"Handoff saved for another account: %d/%d items (%s%s). Now /exit, then start the new session in this folder within 30 min; it loads this handoff on startup." % (...)`; otherwise today's string unchanged.
    - `main`: `s.add_argument("--move", action="store_true")`; call `run(args.cwd, args.transcript, move=args.move)`; both usage strings become `"Handoff: usage: handoff.py save --cwd <dir> [--transcript <path>] [--move]"`.
  - `claude/jev/handoff_paths.py`: `parse_header` returns `{"cwd": m.group(1), "session": m.group(2), "time": m.group(3), "move": bool(re.search(r"\smove=1(\s|$)", first_line))}`.
  - `claude/commands/handoff.md`: replace the body with:

    ````markdown
    Run exactly one of these commands with the Bash tool, then show its one-line output to the user.
    If the arguments are `move`, run:

    ```
    "${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/handoff.py" save --cwd "$PWD" --move
    ```

    Otherwise run:

    ```
    "${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/handoff.py" save --cwd "$PWD"
    ```

    Arguments: $ARGUMENTS

    After a plain save, tell the user to type `/clear` (Claude cannot run `/clear` itself). After a move, tell the user to type `/exit` and start the new session as the output says. Do nothing else.
    ````
    Keep the frontmatter; set `description: Score this session with Jev and save a handoff; then /clear starts fresh with only what matters (/handoff move: for a session on another account)`. The existing `allowed-tools` pattern (`save:*`) already covers `--move`.

- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q claude/jev/tests/test_handoff.py claude/jev/tests`. Expected: PASS (existing `RestoreTest` still passes because `parse_header` only gained a key).
- [ ] **Step 5: Commit** `claude/jev/handoff.py claude/jev/handoff_paths.py claude/commands/handoff.md claude/jev/tests/test_handoff.py` — `feat(handoff): /handoff move marks a handoff for a session on another account`.

## Task 3: restore a move handoff at startup

Goal: `handoff_restore.py` also runs on `SessionStart(startup)` and injects only a handoff marked `move=1`; docs name the new flow.
Scope:
- claude/jev/handoff_restore.py
- claude/hooks/hooks.json
- claude/jev/tests/test_handoff.py
- docs/workflow.md
- claude/CLAUDE.md.template
Done:
- `python3 -m pytest -q claude/jev/tests` passes
- `python3 tools/release_check.py` passes (or reports only pre-existing findings, listed in the report)
Failing test first: claude/jev/tests/test_handoff.py :: StartupRestoreTest.test_startup_restores_move_handoff

**Interfaces:**
- Consumes: `handoff.run(..., move=True)` and `parse_header(...)["move"]` from Task 2.
- Produces: `handoff_restore.run(event)` accepting `source` in `(None, "clear", "startup")`.

- [ ] **Step 1: Write the failing tests.** Append to `claude/jev/tests/test_handoff.py`:

```python
class StartupRestoreTest(HandoffBase):
    def save(self, move):
        write_jsonl(self.tp, [user("u")])
        handoff.run(self.cwd, self.tp, judge_keeping(lambda t: True), move=move)
        return handoff.handoff_path(self.cwd)

    def test_startup_restores_move_handoff(self):
        p = self.save(move=True)
        out = handoff_restore.run({"cwd": self.cwd, "source": "startup"})
        self.assertIn("## Always kept", out["hookSpecificOutput"]["additionalContext"])
        self.assertFalse(os.path.exists(p))

    def test_startup_ignores_plain_handoff(self):
        p = self.save(move=False)
        self.assertIsNone(handoff_restore.run({"cwd": self.cwd, "source": "startup"}))
        self.assertTrue(os.path.exists(p))

    def test_clear_unchanged(self):
        for move in (False, True):
            p = self.save(move=move)
            self.assertIsNotNone(handoff_restore.run({"cwd": self.cwd, "source": "clear"}))
            self.assertFalse(os.path.exists(p))

    def test_resume_and_compact_ignored(self):
        p = self.save(move=True)
        for src in ("resume", "compact"):
            self.assertIsNone(handoff_restore.run({"cwd": self.cwd, "source": src}))
        self.assertTrue(os.path.exists(p))

    def test_startup_stale_move_ignored(self):
        p = self.save(move=True)
        t = time.time() - 1900
        os.utime(p, (t, t))
        self.assertIsNone(handoff_restore.run({"cwd": self.cwd, "source": "startup"}))
```

(`time` and `os` are already imported in this test file; add `import time` at the top if not.)

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q claude/jev/tests/test_handoff.py -k StartupRestore`. Expected: FAIL in `test_startup_restores_move_handoff` (`run` returns None for source `startup`).

- [ ] **Step 3: Implement.**
  - `claude/jev/handoff_restore.py`: docstring first line becomes `"""SessionStart(clear|startup) hook: seed the fresh context with the Jev-scored handoff, then delete it.` and add `On startup only a handoff saved with /handoff move (header move=1) is used.`. In `run`: replace the source check with
    ```python
    source = event.get("source")
    if source not in (None, "clear", "startup"):
        return None
    ```
    and change the meta check to
    ```python
    if not meta or meta["cwd"] != project_root(cwd) or not ctx or (source == "startup" and not meta.get("move")):
        return None
    ```
  - `claude/hooks/hooks.json`: the `handoff_restore.py` entry's `"matcher": "clear"` becomes `"matcher": "clear|startup"`.
  - `docs/workflow.md` line 155: `` `SessionStart(clear)` runs `handoff_restore.py` (for `/handoff`) `` becomes `` `SessionStart(clear|startup)` runs `handoff_restore.py` (for `/handoff`; on startup only a `/handoff move` handoff) ``. After the line-201 bullet ("Manual (preferred …)"), add:
    `  - **Moving to another account: \`/handoff move\`, \`/exit\`, then \`cl --account <label>\`.** \`usage_watch.py\` (prompt chain stage, Claude only) reads FlowObserve's \`GET /api/usage\` on 127.0.0.1 (300 ms, fail silent) and, when this session's account is at \`switchAt\` (and again at +5 points) on its 5-hour or weekly use while another account is below it, tells you to move. \`/handoff move\` saves the handoff with \`move=1\`; the new session's \`SessionStart(startup)\` restores it (same 30 min / same project rules) and deletes it.`
    Add `usage_watch.py` to the file list on line 171 after `context_watch.py`, and in the commands table (line 263) change the `/handoff` row to: `` | `/handoff` | Jev-scored context reset: saves kept items, then you type `/clear`; `/handoff move` for a new session on another account (§6) | ``.
  - `claude/CLAUDE.md.template` line 14: `` `/handoff` (Jev-scored context reset: run it, then `/clear`) `` becomes `` `/handoff` (Jev-scored context reset: run it, then `/clear`; `/handoff move` then `/exit` and `cl` to continue on another account) ``.

- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q claude/jev/tests && python3 tools/release_check.py`. Expected: PASS.
- [ ] **Step 5: Commit** `claude/jev/handoff_restore.py claude/hooks/hooks.json claude/jev/tests/test_handoff.py docs/workflow.md claude/CLAUDE.md.template` — `feat(handoff): restore a /handoff move handoff at the next session's startup`.
