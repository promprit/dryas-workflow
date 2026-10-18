# Usage-limit handoff follow-ups — Implementation Plan

> **For agentic workers:** run with `/orchestrate` on this file (Dryas). Each `## Task N:` section is self-contained: its Goal/Scope/Done/Failing-test lines are the `.orchestrate/PLAN.md` contract; Interfaces and Steps follow. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Close the four review findings left open by the usage-limit handoff (merged c8441d5): a real 300 ms ceiling per usage request, account labels checked before they reach Claude's context, `/handoff move` decided by code instead of by the model, and restore skipping an unreadable handoff file.
**Architecture:** `usage_watch.fetch_json` runs the request in a daemon thread and waits at most the budget; `_assess` accepts only labels matching `[A-Za-z0-9._-]{1,32}`. `/handoff` always passes its arguments to `handoff.py save --mode '<args>'`, and `handoff.py` decides move, plain or refuse. `handoff_restore.run` treats a read or decode error like any other unusable candidate.
**Tech Stack:** Python 3.9 stdlib (`threading`, `urllib.request`, `re`, `unittest`), Claude Code command markdown.
**Spec:** the usage-limit handoff plan `docs/plans/2026-10-18-usage-limit-handoff.md` (its Global Constraints still hold) plus the review findings recorded in the 2026-10-18 orchestrate run report: interrogate reviewer B findings 4, 6, 7 and branch review round 2 minor finding 2.

## Global Constraints

- Python 3.9 stdlib only; no new dependencies.
- Fail silent and fast in `usage_watch.py`: the usage requests share a 300 ms budget in total (connect, headers and body); any problem means no message; never raise; the hook always exits 0.
- Network only to `http://127.0.0.1:<FO_PORT or 4317>/api/usage`, proxies disabled (`ProxyHandler({})`).
- Account labels accepted only when they fully match `[A-Za-z0-9._-]{1,32}`; otherwise that account is ignored (and when it is this session's own account, no message).
- `/handoff` with no arguments saves a plain handoff exactly as today; `/handoff move` saves a move handoff exactly as today; any other argument saves nothing and says so.
- Restore never raises; `/clear` with a usable plain handoff behaves as today; startup still restores only a fresh `move=1` handoff from this folder's `move_path`.
- After changing any `claude/jev/*.py` or `claude/commands/*.md`, regenerate the copies with `python3 tools/sync_codex_plugin.py` and `python3 tools/sync_opencode.py` (they write only under `codex/` and `opencode/`).
- Full CI check: `python3 -m pytest -q -rs claude/jev/tests install/tests claude/ruflo/tests` must show 0 failed (about 6 min).

## Review Focus

- FlowObserve answers slowly byte by byte (each byte within 300 ms, the whole body over 1 s) → no message, and `fetch_json` returns within ~0.4 s. Test: Task 1 `test_drip_feeding_server_is_cut_at_budget`.
- An account label with a space, `;`, a newline or more than 32 characters → never appears in the message; a valid calm account is picked instead, or silence. Test: Task 1 `test_invalid_calm_label_is_skipped`, `test_invalid_own_label_is_silent`.
- `/handoff Move` (capital M, spaces) → a move handoff, not a plain one. Test: Task 2 `test_mode_decides_move`.
- `/handoff now` or any other word → nothing saved, the output says why. Test: Task 2 `test_unknown_mode_saves_nothing`.
- A plain handoff file that is not valid UTF-8, or a directory where the file should be → `/clear` still restores a fresh move handoff. Test: Task 3 `test_clear_skips_undecodable_plain_for_fresh_move`, `test_clear_skips_unopenable_plain_for_fresh_move`.

---

## Task 1: usage-watch total deadline and label check

Goal: `usage_watch.fetch_json` returns within its timeout even when the server drip-feeds bytes, and `_assess` ignores accounts whose label does not match `[A-Za-z0-9._-]{1,32}`.
Scope:
- claude/jev/usage_watch.py
- claude/jev/tests/test_usage_watch.py
- codex/jev/usage_watch.py
- opencode/dryas/jev/usage_watch.py
Done:
- `python3 -m pytest -q claude/jev/tests/test_usage_watch.py` passes
- `python3 -m pytest -q claude/jev/tests install/tests/test_codex_plugin_sync.py install/tests/test_opencode_sync.py` passes
Failing test first: claude/jev/tests/test_usage_watch.py :: WatchTest.test_drip_feeding_server_is_cut_at_budget

**Interfaces:**
- Consumes: nothing new.
- Produces: `usage_watch.fetch_json(url: str, timeout: float) -> Optional[dict]` (same signature, total deadline); `usage_watch.LABEL_RE`.

- [ ] **Step 1: Write the failing tests.** In `claude/jev/tests/test_usage_watch.py` add `import threading` to the imports, then add these methods to `class WatchTest` (after `test_slow_server_times_out_within_budget`):

```python
    def serve_once(self, body, delay):
        """A one-shot local HTTP server that sends `body` one byte every `delay` seconds."""
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        stop = threading.Event()

        def serve():
            try:
                c, _ = s.accept()
                c.recv(1024)
                c.sendall(b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n")
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

    def test_invalid_calm_label_is_skipped(self):
        line = usage_watch.run(self.ev(), server(acct("team", 0.95), acct("x y", 0.01), acct("a" * 33, 0.02),
                                                 acct("ok\n", 0.03), acct("good-1", 0.2)))
        self.assertIn("good-1 has room (5h 20%)", line)
        for bad in ("x y", "a" * 33, "ok\n"):
            self.assertNotIn(bad, line)

    def test_invalid_own_label_is_silent(self):
        self.assertIsNone(usage_watch.run(self.ev(), server(acct("te am", 0.95), acct("team2", 0.1), me="te am")))
```

- [ ] **Step 2: Run them to see them fail.** Run: `python3 -m pytest -q claude/jev/tests/test_usage_watch.py`. Expected: `test_drip_feeding_server_is_cut_at_budget` FAILS (`AssertionError: ... not less than 0.4`, about 1.7 s), `test_invalid_calm_label_is_skipped` FAILS (picks `x y`), `test_invalid_own_label_is_silent` FAILS (a message is returned); `test_fast_server_returns_the_object` passes.

- [ ] **Step 3: Implement.** In `claude/jev/usage_watch.py`:
  - Add `import threading` to the imports (keep them sorted) and, after `MAX_SID = 64`, add `LABEL_RE = re.compile(r"[A-Za-z0-9._-]{1,32}")`.
  - Replace `fetch_json` with:

```python
def fetch_json(url: str, timeout: float) -> Optional[Dict[str, Any]]:
    """GET a local JSON object within `timeout` seconds in total, never through a proxy; None on any problem.
    The request runs in a daemon thread, so a server that drip-feeds bytes cannot hold the prompt past the budget."""
    box: List[Optional[Dict[str, Any]]] = [None]

    def get() -> None:
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=max(timeout, 0.01)) as r:
                v = json.loads(r.read(65536).decode("utf-8"))
            box[0] = v if isinstance(v, dict) else None
        except Exception:
            pass
    try:
        t = threading.Thread(target=get, daemon=True)
        t.start()
        t.join(max(timeout, 0.01))
        return None if t.is_alive() else box[0]
    except Exception:
        return None
```

  - Add after `_num`:

```python
def _label_ok(v: Any) -> bool:
    return isinstance(v, str) and LABEL_RE.fullmatch(v) is not None
```

  - In `_assess`: change `if me is None or not isinstance(me.get("label"), str):` to `if me is None or not _label_ok(me.get("label")):`, and in the `calm` generator change `isinstance(a.get("label"), str)` to `_label_ok(a.get("label"))`.
  - Then run `python3 tools/sync_codex_plugin.py` and `python3 tools/sync_opencode.py`; `git status` must show only `codex/jev/usage_watch.py` and `opencode/dryas/jev/usage_watch.py` besides your two files.

- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q claude/jev/tests/test_usage_watch.py && python3 -m pytest -q claude/jev/tests install/tests/test_codex_plugin_sync.py install/tests/test_opencode_sync.py`. Expected: PASS.
- [ ] **Step 5: Commit** `claude/jev/usage_watch.py claude/jev/tests/test_usage_watch.py codex/jev/usage_watch.py opencode/dryas/jev/usage_watch.py` — `fix(jev): usage-watch has a total 300 ms deadline and accepts only plain account labels`.

## Task 2: /handoff decides move in code

Goal: `/handoff` always runs `handoff.py save --cwd "$PWD" --mode '$ARGUMENTS'`, and `handoff.py` saves a move handoff for `move`/`--move` (any case, trimmed), a plain one for no argument, and nothing (with a message) for anything else.
Scope:
- claude/jev/handoff.py
- claude/commands/handoff.md
- claude/jev/tests/test_handoff.py
- codex/**
- opencode/**
Done:
- `python3 -m pytest -q claude/jev/tests/test_handoff.py` passes
- `python3 -m pytest -q claude/jev/tests install/tests` passes
Failing test first: claude/jev/tests/test_handoff.py :: ModeTest.test_mode_decides_move

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: CLI `handoff.py save --cwd DIR [--transcript P] [--move] [--mode TEXT]`; `handoff.run(...)` unchanged.

- [ ] **Step 1: Write the failing tests.** Append to `claude/jev/tests/test_handoff.py` (add `import io` at the top if it is not there; if the file has no repo-root constant, add `REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))` near the other module constants):

```python
class ModeTest(HandoffBase):
    def test_mode_decides_move(self):
        from unittest import mock
        for mode, move in (("move", True), (" Move ", True), ("--move", True), ("", False)):
            with self.subTest(mode=mode), mock.patch.object(handoff, "run", return_value="ok") as r:
                self.assertEqual(handoff.main(["handoff.py", "save", "--cwd", self.cwd, "--mode", mode]), 0)
                r.assert_called_once_with(self.cwd, None, move=move)

    def test_unknown_mode_saves_nothing(self):
        from unittest import mock
        out = io.StringIO()
        with mock.patch.object(handoff, "run") as r, mock.patch("sys.stdout", out):
            handoff.main(["handoff.py", "save", "--cwd", self.cwd, "--mode", "now please"])
        r.assert_not_called()
        self.assertIn("unknown argument", out.getvalue())
        self.assertIn("Nothing saved", out.getvalue())

    def test_command_passes_arguments_through(self):
        with open(os.path.join(REPO, "claude", "commands", "handoff.md"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("save --cwd \"$PWD\" --mode '$ARGUMENTS'", md)
        self.assertNotIn("If the arguments are", md)
```

- [ ] **Step 2: Run them to see them fail.** Run: `python3 -m pytest -q claude/jev/tests/test_handoff.py -k ModeTest`. Expected: all three FAIL (argparse rejects `--mode`; the command file still branches in prose).

- [ ] **Step 3: Implement.**
  - `claude/jev/handoff.py` `main`: add `s.add_argument("--mode", default="")`; both usage strings become `"Handoff: usage: handoff.py save --cwd <dir> [--transcript <path>] [--move] [--mode move]"`; replace the `print(run(args.cwd, args.transcript, move=args.move))` call with:

```python
    mode = args.mode.strip().lower()
    if mode not in ("", "move", "--move"):
        print("Handoff: unknown argument %r; use /handoff or /handoff move. Nothing saved." % args.mode[:40])
        return 0
    try:
        print(run(args.cwd, args.transcript, move=args.move or bool(mode)))
```
    (keep the existing `except Exception as e:` branch; `test_cli_move_flag` must still pass).
  - `claude/commands/handoff.md`: keep the frontmatter unchanged; replace the body with:

    ````markdown
    Run this command with the Bash tool exactly as written, then show its one-line output to the user:

    ```
    "${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/handoff.py" save --cwd "$PWD" --mode '$ARGUMENTS'
    ```

    If the output says the handoff was saved for another account, tell the user to type `/exit` and start the new session as the output says. If it says a handoff was saved, tell the user to type `/clear` (Claude cannot run `/clear` itself). Otherwise only show the output. Do nothing else.
    ````
  - Run `python3 tools/sync_codex_plugin.py` and `python3 tools/sync_opencode.py`; `git status` must show changes only under `claude/`, `codex/` and `opencode/` within this Scope.

- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q claude/jev/tests/test_handoff.py && python3 -m pytest -q claude/jev/tests install/tests`. Expected: PASS.
- [ ] **Step 5: Commit** the changed files (list them from `git status`) — `fix(handoff): /handoff passes its arguments to handoff.py, which decides move or refuses`.

## Task 3: restore skips an unreadable handoff file

Goal: In `handoff_restore.run`, a candidate that cannot be opened or decoded is skipped like any unusable candidate, so a fresh move handoff is still restored; the full CI check passes.
Scope:
- claude/jev/handoff_restore.py
- claude/jev/tests/test_handoff.py
- codex/jev/handoff_restore.py
- opencode/dryas/jev/handoff_restore.py
Done:
- `python3 -m pytest -q claude/jev/tests/test_handoff.py` passes
- `python3 -m pytest -q -rs claude/jev/tests install/tests claude/ruflo/tests` shows 0 failed
- `python3 tools/inventory.py --check` reports 0 problems
- `python3 tools/release_check.py` exits 0 with no FAIL lines
Failing test first: claude/jev/tests/test_handoff.py :: UnreadableTest.test_clear_skips_undecodable_plain_for_fresh_move

**Interfaces:**
- Consumes: `handoff.run(..., move=True)`, `handoff.handoff_path`, `handoff_paths.move_path` (existing).
- Produces: nothing new.

- [ ] **Step 1: Write the failing tests.** Append to `claude/jev/tests/test_handoff.py` (it already imports `handoff`, `handoff_restore`, `write_jsonl`, `user` and defines `judge_keeping`; add `import handoff_paths` next to `import handoff_restore` if it is not imported at module level):

```python
class UnreadableTest(HandoffBase):
    def save_move(self):
        write_jsonl(self.tp, [user("MOVETEXT")])
        handoff.run(self.cwd, self.tp, judge_keeping(lambda t: True), move=True)
        return handoff_paths.move_path(self.cwd)

    def test_clear_skips_undecodable_plain_for_fresh_move(self):
        mp = self.save_move()
        plain = handoff.handoff_path(self.cwd)
        with open(plain, "wb") as f:
            f.write(b"<!-- handoff \xff\xfe not utf-8 -->\n")
        out = handoff_restore.run({"cwd": self.cwd, "source": "clear"})
        self.assertIn("MOVETEXT", out["hookSpecificOutput"]["additionalContext"])
        self.assertFalse(os.path.exists(mp))

    def test_clear_skips_unopenable_plain_for_fresh_move(self):
        mp = self.save_move()
        os.makedirs(handoff.handoff_path(self.cwd))  # stat works, open fails
        out = handoff_restore.run({"cwd": self.cwd, "source": "clear"})
        self.assertIn("MOVETEXT", out["hookSpecificOutput"]["additionalContext"])
        self.assertFalse(os.path.exists(mp))
```

- [ ] **Step 2: Run them to see them fail.** Run: `python3 -m pytest -q claude/jev/tests/test_handoff.py -k UnreadableTest`. Expected: both FAIL with `TypeError: 'NoneType' object is not subscriptable` (the read error ends the run before the move candidate).

- [ ] **Step 3: Implement.** In `claude/jev/handoff_restore.py`, inside the candidate loop, replace

```python
            with open(path, encoding="utf-8") as f:
                text = f.read()
```
with
```python
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue
```
  Then run `python3 tools/sync_codex_plugin.py` and `python3 tools/sync_opencode.py`.

- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q claude/jev/tests/test_handoff.py`, then the three Done commands for the whole repo (`python3 -m pytest -q -rs claude/jev/tests install/tests claude/ruflo/tests`, `python3 tools/inventory.py --check`, `python3 tools/release_check.py`) and read each result. Expected: 0 failed, 0 problems, no FAIL lines.
- [ ] **Step 5: Commit** `claude/jev/handoff_restore.py claude/jev/tests/test_handoff.py codex/jev/handoff_restore.py opencode/dryas/jev/handoff_restore.py` — `fix(handoff): restore skips a handoff file it cannot read`.
