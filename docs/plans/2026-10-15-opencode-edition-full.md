# OpenCode edition, plan 2 (full) — Implementation Plan

> **For agentic workers:** run with `/orchestrate` on this file (Dryas). Each `## Task N:` section is self-contained: its Goal/Scope/Done/Failing-test lines are the `.orchestrate/PLAN.md` contract; Interfaces and Steps follow. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Bring the OpenCode edition from core to Dryas Full: memory hook stages, context-window warnings, compaction keep/restore and `/handoff` run on OpenCode, and the OC column of the conformance table says so.

**Architecture:** The TS shim (`opencode/plugin/dryas.ts`) gains the spec's step-2 rows: it builds Claude-shaped events from OpenCode hooks and bus events and pipes them to `chain.py --harness opencode` (observe-only, not awaited), as plan 1 did for `pretool` and `prompt`. OpenCode keeps no Claude JSONL transcript, so a new Python entry point, `opencode_session.py`, turns the session messages the shim reads through the SDK into a Claude-shaped transcript and runs the existing engines (`compact_keep`, `compact_restore`, `handoff`) on it; `context_watch.py` reads token usage from the event instead. No engine is ported to TS.

**Tech Stack:** Python 3.8+ stdlib (Jev), TypeScript plugin run by OpenCode's Bun, pytest, a real `opencode serve` (1.18.x) against `install/tests/fixtures/mock_llm.py`.

**Spec:** `docs/specs/2026-10-15-opencode-edition-design.md` (section 9, plan 2; rows marked step 2 in sections 4, 5 and 7).

## Global Constraints

- OpenCode version floor `>=1.18`; CI pins 1.18.x. The end-to-end tests skip when no `opencode` 1.18+ binary is on PATH.
- The plugin never reads or changes OpenCode's `permission` settings and setup never edits the user's `opencode.json`.
- No Python port to TS, no Node install for the user. The shim stays thin: every decision and engine lives in `claude/jev/*.py`.
- `claude/jev` and `claude/pstack` are the sources of truth. After any change under them run `python3 tools/sync_codex_plugin.py` (it writes `codex/jev`, `opencode/dryas/jev` and the rest of `opencode/`); never edit the synced copies by hand. `python3 tools/sync_codex_plugin.py --check` must exit 0.
- Codex coverage is unchanged: Codex memory stages stay off (the 2.0 choice pinned by a test). Only `opencode` is added to stage `harness` lists.
- Stages with no `harness` key default to `["claude"]`; a stage that gains OpenCode gets the explicit list `["claude", "opencode"]` (stages already listing `codex` keep it).
- Observe-only chain calls (`post`, `stop`, `subagent-stop`, `session-start`, `session-end`, `precompact`) are started and not awaited by the shim, and never block or change a tool call.
- `ruflo-pre-bash` and `flowobserve` never run on OpenCode.
- Python files: no new third-party imports; file-privacy calls carry the `# portable-ok:` comment used elsewhere; `python3 tools/inventory.py --check` must report 0 problems.
- Files stay under 500 lines.
- Executors do not push. Commit with explicit paths and conventional messages.
- Tests: `python3 -m pytest -q -p no:cacheprovider claude/jev/tests install/tests` passes (the full run takes about 8 minutes).

## Review Focus

1. **A call the shim itself blocked** (scope lock or judge ask) shows up in OpenCode as a tool part with `state: "error"`; it must not reach `post` as a `PostToolUseFailure`, or `mem-edit` records a failed edit that never ran. Pinned in Task 4 (`test_blocked_write_is_not_a_failed_edit`).
2. **A fresh handoff is restored once, into the next root session only**: subagent sessions and later sessions of the same process do not get it, and the restored text stays in that session's system prompt on every later request (the file is deleted after the first read). Pinned in Task 5 (`test_handoff_restores_into_next_session_only`).
3. **Python missing or failing during compaction or `/handoff`**: compaction still runs (no context added) and `/handoff` tells the user nothing was saved instead of hanging or showing the raw template. Pinned in Task 5 (`test_handoff_without_python_says_nothing_saved`).
4. **An OpenCode model with a known context limit** (`chat.params` `model.limit.context`) must use that limit, not Claude's 200k/1M guess; `JEV_CONTEXT_WINDOW` still wins. Pinned in Task 2 (`test_event_context_limit_sets_window`, `test_env_window_beats_event_limit`).
5. **Large or odd session messages** (tool parts with no state, unknown tools, synthetic Dryas text parts, megabyte outputs) must convert without raising and without copying Dryas's own injected context back into the handoff. Pinned in Task 3 (`test_synthetic_and_odd_parts`).

---

Tasks run in order (1 → 6): Tasks 1–3 each re-run the sync tool, which rewrites `opencode/dryas/jev` and `codex/jev`, so their scopes overlap and they must not run in parallel.

## Task 1: Memory, context-watch and outcome stages run on OpenCode

Goal: Every `chain.json` stage except `ruflo-pre-bash` and `flowobserve` runs for `--harness opencode`, Codex unchanged, proven by mock-event tests.
Scope:
- claude/jev/chain.json
- install/tests/test_opencode_chain_stages.py
- opencode/dryas/jev/**
- codex/jev/**
Done:
- `python3 -m pytest -q -p no:cacheprovider install/tests/test_opencode_chain_stages.py claude/jev/tests/test_chain.py` passes
- `python3 tools/sync_codex_plugin.py --check` exits 0
Failing test first: install/tests/test_opencode_chain_stages.py :: StageListTest.test_opencode_runs_every_stage_but_ruflo_and_flowobserve

**Interfaces:**
- Consumes: `chain.load_stages(kind, harness)` (claude/jev/chain.py:71); `chain.main(argv)`; env `JEV_CHAIN_CONFIG`, `JEV_CHAIN_LOCAL`, `DRYAS_DATA_ROOT`, `DRYAS_DB`.
- Produces: `chain.json` stage lists that Tasks 4 and 5 rely on: on `opencode`, `prompt` = `jev-route, context-watch`; `post` = `mem-edit, gate-outcome`; `subagent-stop` = `mem-task`; `session-start` = `mem-session-start`; `session-end` and `precompact` = `mem-session-end, mem-notes`; `stop` = `mem-notes`.

- [ ] **Step 1: Write the failing test.** Create `install/tests/test_opencode_chain_stages.py`:

```python
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
        self.assertEqual(names("post", "claude"), ["mem-edit", "gate-outcome"])
        self.assertEqual(names("session-end", "claude"), ["mem-session-end", "mem-notes"])


class ObserveEventTest(unittest.TestCase):
    """Claude-shaped events as the shim sends them reach the real memory stages."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dryas-oc-chain-")
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj)
        subprocess.run(["git", "init", "-q", self.proj], check=True)
        self.env = dict(os.environ, DRYAS_DATA_ROOT=os.path.join(self.tmp, "data"),
                        JEV_CHAIN_LOCAL=os.path.join(self.tmp, "none.json"))

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
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q -p no:cacheprovider install/tests/test_opencode_chain_stages.py`. Expected: `test_opencode_runs_every_stage_but_ruflo_and_flowobserve` fails (`['jev-route'] != ['jev-route', 'context-watch']`), the two `ObserveEventTest` tests fail (no `sessions` table or no rows: the stages do not run on opencode). If `repo_rel` stores a path other than `a.txt` for a file in a git repo root, fix the expectation to what `memhooks.repo_rel` returns for the repo root and note it in the report.

- [ ] **Step 3: Implement.** In `claude/jev/chain.json` add `"harness": ["claude", "opencode"],` right after the `"name"` key of each of these entries (and nothing else): `prompt/context-watch`, `post/mem-edit`, `post/gate-outcome`, `subagent-stop/mem-task`, `session-start/mem-session-start`, `session-end/mem-session-end`, `session-end/mem-notes`, `precompact/mem-session-end`, `precompact/mem-notes`, `stop/mem-notes`. Example:

```json
{"name": "mem-edit", "harness": ["claude", "opencode"], "component": "memory", "cmd": ["$PY", "-X", "utf8", "$CD/jev/memhooks.py", "edit"], "match": "Write|Edit|MultiEdit|NotebookEdit", "timeout": 2, "observe": true},
```

Then run `python3 tools/sync_codex_plugin.py`.

- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q -p no:cacheprovider install/tests/test_opencode_chain_stages.py claude/jev/tests/test_chain.py install/tests/test_opencode_sync.py install/tests/test_codex_plugin_sync.py && python3 tools/sync_codex_plugin.py --check`. Expected: PASS, exit 0. Also run `grep -rn "Claude Code only" install/tests/test_*.py claude/jev/tests/test_*.py | grep -i "mem\|harness"` and run any test it names: a test pinning "memory stages are Claude Code only" for Codex must still pass; one pinning them for OpenCode is updated to the new lists.

- [ ] **Step 5: Commit** (explicit paths, conventional message, e.g. `feat(jev): memory, context-watch and outcome stages run on OpenCode`) when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 2: Context watch reads usage from the event

Goal: `context_watch.py` warns from the event's `usage`, `context_limit` and `model` when there is no transcript (OpenCode), with OpenCode wording.
Scope:
- claude/jev/context_watch.py
- claude/jev/tests/test_context_watch_event.py
- opencode/dryas/jev/**
- codex/jev/**
Done:
- `python3 -m pytest -q -p no:cacheprovider claude/jev/tests/test_context_watch_event.py claude/jev/tests/ -k context_watch` passes
- `python3 tools/sync_codex_plugin.py --check` exits 0
Failing test first: claude/jev/tests/test_context_watch_event.py :: EventUsageTest.test_warns_from_event_usage

**Interfaces:**
- Consumes: `context_watch.run(event) -> Optional[str]`, `_window(model, max_tokens)`, state dir `paths.handoff_dir()/.warned`; env `DRYAS_HARNESS` (set by `chain.py` for every stage subprocess).
- Produces: event fields Task 4's shim sends on `UserPromptSubmit`: `usage: {"input_tokens": int, "cache_read_input_tokens": int, "cache_creation_input_tokens": int}`, `context_limit: int` (0 = unknown), `model: str`. Warning text on OpenCode contains `run /handoff then /new`.

- [ ] **Step 1: Write the failing test.** Create `claude/jev/tests/test_context_watch_event.py`:

```python
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import context_watch  # noqa: E402


def ev(sid, input_tokens, limit=0, model="mock/m1", **extra):
    e = {"session_id": sid, "cwd": "/tmp", "model": model, "context_limit": limit,
         "usage": {"input_tokens": input_tokens, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}
    e.update(extra)
    return e


class EventUsageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"JEV_HANDOFF_DIR": self.tmp, "DRYAS_HARNESS": "opencode"})
        self.env.start()
        os.environ.pop("JEV_CONTEXT_WINDOW", None)

    def tearDown(self):
        self.env.stop()

    def test_warns_from_event_usage(self):
        line = context_watch.run(ev("s1", 190000, limit=200000))
        self.assertIsNotNone(line)
        self.assertIn("run /handoff then /new", line)
        self.assertNotIn("/clear", line)

    def test_below_threshold_is_quiet(self):
        self.assertIsNone(context_watch.run(ev("s2", 1234, limit=200000)))

    def test_event_context_limit_sets_window(self):
        # 190k of a 1M window is 19%: quiet; the model-name guess (200k) would have warned.
        self.assertIsNone(context_watch.run(ev("s3", 190000, limit=1000000)))

    def test_env_window_beats_event_limit(self):
        with mock.patch.dict(os.environ, {"JEV_CONTEXT_WINDOW": "200000"}):
            self.assertIsNotNone(context_watch.run(ev("s4", 190000, limit=1000000)))

    def test_no_limit_falls_back_to_model_guess(self):
        self.assertIsNotNone(context_watch.run(ev("s5", 190000, limit=0, model="")))

    def test_tier_does_not_repeat(self):
        self.assertIsNotNone(context_watch.run(ev("s6", 170000, limit=200000)))
        self.assertIsNone(context_watch.run(ev("s6", 171000, limit=200000)))

    def test_bad_usage_is_ignored(self):
        for bad in ({"usage": "x"}, {"usage": {"input_tokens": True}}, {"usage": {}}, {"context_limit": "big"}):
            e = ev("s7", 190000, limit=200000)
            e.update(bad)
            context_watch.run(e)  # never raises
        self.assertIsNone(context_watch.run({"session_id": "s8", "usage": {"input_tokens": -5}}))

    def test_claude_wording_unchanged(self):
        with mock.patch.dict(os.environ, {"DRYAS_HARNESS": "claude"}):
            line = context_watch.run(ev("s9", 190000, limit=200000))
        self.assertIn("/handoff then /clear", line)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q -p no:cacheprovider claude/jev/tests/test_context_watch_event.py`. Expected: the warning tests fail with `None` (no `transcript_path`, so `run` returns early).

- [ ] **Step 3: Implement.** In `claude/jev/context_watch.py`:

1. Give `_window` a `limit` parameter used after the env override and before the model guess:

```python
def _window(model: str, max_tokens: int, limit: int = 0) -> int:
    """JEV_CONTEXT_WINDOW if valid; else the harness's own limit for the model (OpenCode `context_limit`) when known;
    else 1M when the model id says [1m], names a 1M-default model, or usage ever exceeded 200k; else 200k."""
    try:
        w = int(os.environ.get("JEV_CONTEXT_WINDOW", ""))
        if w > 0:
            return w
    except ValueError:
        pass
    if limit > 0:
        return limit
    big = "[1m]" in model or _million_model(model) or max_tokens > DEFAULT_WINDOW
    return 1000000 if big else DEFAULT_WINDOW
```

2. Add, after `read_usage`:

```python
USAGE_KEYS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def _count(v: Any) -> int:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else 0


def event_usage(event: Dict[str, Any]) -> Optional[Tuple[int, int, str]]:
    """Same shape as read_usage, from the event's `usage` (harnesses with no Claude transcript: OpenCode)."""
    u = event.get("usage")
    if not isinstance(u, dict):
        return None
    total = sum(_count(u.get(k)) for k in USAGE_KEYS)
    if total <= 0:
        return None
    model = event.get("model")
    return total, total, model if isinstance(model, str) else ""
```

3. In `run`, replace the first five lines of the `try` body with:

```python
        path, sid = event.get("transcript_path"), event.get("session_id")
        if not isinstance(sid, str) or not sid:
            return None
        usage = read_usage(path) if isinstance(path, str) and os.path.isfile(path) else event_usage(event)
        if usage is None:
            return None
        tokens, biggest, model = usage
        pct = tokens / float(_window(model, biggest, _count(event.get("context_limit"))))
```

4. Replace the final `return (...)` with:

```python
        if os.environ.get("DRYAS_HARNESS") == "opencode":
            return ("Context %d%% — tell the user: run /handoff then /new to continue with a Jev-scored context "
                    "(OpenCode compacts on its own near the limit)." % int(pct * 100 + 1e-9))
        return ("Context %d%% — tell the user: run /handoff then /clear to continue with a Jev-scored context "
                "(auto-compaction is at %d%%)." % (int(pct * 100 + 1e-9), _autocompact_pct()))
```

Update the module docstring's first line to say it reads the transcript tail, or the event's `usage` when there is no transcript. Run `python3 tools/sync_codex_plugin.py`.

- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q -p no:cacheprovider claude/jev/tests -k "context_watch" && python3 tools/sync_codex_plugin.py --check`. Expected: PASS (new and existing context-watch tests), exit 0.

- [ ] **Step 5: Commit** (e.g. `feat(jev): context watch reads usage from the event on OpenCode`) when the dispatch prompt allows it; otherwise report.

## Task 3: `opencode_session.py`: transcript, compaction keep and `/handoff` for OpenCode

Goal: A Python entry point turns OpenCode session messages into a Claude-shaped transcript and runs the existing compaction-keep and handoff engines on it.
Scope:
- claude/jev/opencode_session.py
- claude/jev/tests/test_opencode_session.py
- opencode/dryas/jev/**
- codex/jev/**
Done:
- `python3 -m pytest -q -p no:cacheprovider claude/jev/tests/test_opencode_session.py` passes
- `python3 tools/sync_codex_plugin.py --check` exits 0 and `python3 tools/inventory.py --check` reports 0 problems
Failing test first: claude/jev/tests/test_opencode_session.py :: RecordsTest.test_user_assistant_and_tool_items

**Interfaces:**
- Consumes: `transcript_items.extract_items(path)`; `compact_keep.run(event, judge_fn)`, `compact_keep.safe_name(sid)`; `compact_restore.run(event)`; `handoff.run(cwd, transcript, judge_fn, deadline_s)`, `handoff.write_private(path, text)`; `paths.jev_dir()`. OpenCode message shape from `client.session.messages`: `[{"info": {"id", "role": "user"|"assistant", ...}, "parts": [{"type": "text", "text", "synthetic"?} | {"type": "tool", "tool", "callID", "state": {"status", "input", "output"?, "error"?}}]}]`.
- Produces: CLI `opencode_session.py compact|handoff`, stdin `{"session_id": str, "cwd": str, "messages": [...]}`; stdout one JSON object: `compact` → `{"context": str}` (`""` when nothing kept), `handoff` → `{"line": str}`; always exit 0. Functions `records(messages) -> list`, `compact(event, judge_fn=judge) -> dict`, `save_handoff(event, judge_fn=judge) -> dict`. Task 5's shim calls the CLI.

- [ ] **Step 1: Write the failing test.** Create `claude/jev/tests/test_opencode_session.py`:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q -p no:cacheprovider claude/jev/tests/test_opencode_session.py`. Expected: `ModuleNotFoundError: No module named 'opencode_session'`.

- [ ] **Step 3: Implement.** Create `claude/jev/opencode_session.py`:

```python
#!/usr/bin/env python3
"""OpenCode edition: OpenCode keeps no Claude JSONL transcript, so the shim (opencode/plugin/dryas.ts) passes the
session messages it reads through the SDK, and this turns them into a Claude-shaped transcript and runs the same
engines as Claude Code.
  opencode_session.py compact   compact_keep + compact_restore -> {"context": ...} (experimental.session.compacting)
  opencode_session.py handoff   handoff.run -> {"line": ...} (/handoff)
stdin: {"session_id", "cwd", "messages": [{"info", "parts"}]}. Prints one JSON object, always exits 0. The transcript
is private (0600) and removed after use."""
import json
import os
import sys
from typing import Any, Callable, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compact_keep
import compact_restore
import handoff
import paths
from jev_client import judge

MAX_RESULT = 4000
# OpenCode tool -> (Claude tool name, {OpenCode arg: Claude arg}) so transcript_items picks the key argument.
TOOLS = {"bash": ("Bash", {"command": "command"}), "write": ("Write", {"filePath": "file_path"}),
         "edit": ("Edit", {"filePath": "file_path"}), "read": ("Read", {"filePath": "file_path"}),
         "grep": ("Grep", {"pattern": "pattern"}), "glob": ("Glob", {"pattern": "pattern"}),
         "task": ("Task", {"description": "description"})}


def transcript_dir() -> str:
    return os.path.join(paths.jev_dir(), "opencode")


def _tool(name: str, inp: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    if name in TOOLS:
        claude, keys = TOOLS[name]
        return claude, {dst: inp[src] for src, dst in keys.items() if isinstance(inp.get(src), str)}
    return name, {k: v for k, v in inp.items() if isinstance(v, str)}


def records(messages: Any) -> List[Dict[str, Any]]:
    """Claude transcript records (user / assistant with tool_use / user with tool_result). Synthetic text parts
    (context Dryas itself added) are dropped. Never raises on odd input."""
    out: List[Dict[str, Any]] = []
    for m in messages if isinstance(messages, list) else []:
        info = m.get("info") if isinstance(m, dict) else None
        parts = m.get("parts") if isinstance(m, dict) else None
        if not isinstance(info, dict) or not isinstance(parts, list):
            continue
        parts = [p for p in parts if isinstance(p, dict)]
        mid = str(info.get("id") or "")
        texts = [p["text"] for p in parts if p.get("type") == "text" and isinstance(p.get("text"), str)
                 and not p.get("synthetic")]
        if info.get("role") == "user":
            if texts:
                out.append({"type": "user", "uuid": mid, "message": {"role": "user", "content": "\n".join(texts)}})
            continue
        if info.get("role") != "assistant":
            continue
        content: List[Dict[str, Any]] = [{"type": "text", "text": t} for t in texts]
        results: List[Dict[str, Any]] = []
        for p in parts:
            if p.get("type") != "tool":
                continue
            st = p.get("state") if isinstance(p.get("state"), dict) else {}
            cid = str(p.get("callID") or "")
            name, inp = _tool(str(p.get("tool") or ""), st.get("input") if isinstance(st.get("input"), dict) else {})
            content.append({"type": "tool_use", "id": cid, "name": name, "input": inp})
            if st.get("status") in ("completed", "error"):
                res = st.get("output") if st.get("status") == "completed" else st.get("error")
                results.append({"type": "tool_result", "tool_use_id": cid, "content": str(res or "")[:MAX_RESULT],
                                "is_error": st.get("status") == "error"})
        if content:
            out.append({"type": "assistant", "uuid": mid, "message": {"role": "assistant", "content": content}})
        if results:
            out.append({"type": "user", "uuid": mid + "-results", "message": {"role": "user", "content": results}})
    return out


def _write(sid: str, messages: Any) -> str:
    path = os.path.join(transcript_dir(), compact_keep.safe_name(sid) + ".jsonl")
    handoff.write_private(path, "".join(json.dumps(r) + "\n" for r in records(messages)))
    return path


def _with_transcript(event: Dict[str, Any], fn: Callable[[str, str, str], Dict[str, Any]]) -> Dict[str, Any]:
    sid, cwd = event.get("session_id"), event.get("cwd")
    if not isinstance(sid, str) or not sid.strip() or not isinstance(cwd, str) or not cwd:
        raise ValueError("session_id and cwd are required")
    path = _write(sid, event.get("messages"))
    try:
        return fn(sid, cwd, path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def compact(event: Dict[str, Any], judge_fn=judge) -> Dict[str, Any]:
    def go(sid: str, cwd: str, path: str) -> Dict[str, Any]:
        compact_keep.run({"session_id": sid, "cwd": cwd, "transcript_path": path}, judge_fn)
        out = compact_restore.run({"session_id": sid})
        return {"context": out["hookSpecificOutput"]["additionalContext"] if out else ""}
    return _with_transcript(event, go)


def save_handoff(event: Dict[str, Any], judge_fn=judge) -> Dict[str, Any]:
    def go(sid: str, cwd: str, path: str) -> Dict[str, Any]:
        return {"line": handoff.run(cwd, path, judge_fn).replace("Now run /clear.", "Now type /new.")}
    return _with_transcript(event, go)


def main(argv: List[str]) -> Dict[str, Any]:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd not in ("compact", "handoff"):
        return {"error": "usage: opencode_session.py compact|handoff"}
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
        if not isinstance(event, dict):
            raise ValueError("not an object")
        return compact(event) if cmd == "compact" else save_handoff(event)
    except Exception as e:
        return {"context": ""} if cmd == "compact" else {"line": "Handoff failed (%s); nothing saved." % type(e).__name__}


if __name__ == "__main__":
    try:
        sys.stdout.write(json.dumps(main(sys.argv)))
    except Exception:
        sys.stdout.write("{}")
    sys.exit(0)
```

If `records` output trips `transcript_items` (for example a string `content` on a user record is not read as a user item), adapt `records` to the shape `transcript_items.extract_items` reads (do not change `transcript_items.py`). Run `python3 tools/sync_codex_plugin.py`; if `python3 tools/inventory.py --check` reports the new file, follow its message (add the `# portable-ok:` comment it asks for, or the baseline entry it names).

- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q -p no:cacheprovider claude/jev/tests/test_opencode_session.py claude/jev/tests -k "handoff or compact or opencode_session" && python3 tools/sync_codex_plugin.py --check && python3 tools/inventory.py --check | tail -1`. Expected: PASS, exit 0, `0 problems`.

- [ ] **Step 5: Commit** (e.g. `feat(jev): opencode_session runs compaction keep and handoff on OpenCode messages`) when the dispatch prompt allows it; otherwise report.

## Task 4: Shim: observe rows (post, failures, stop, subagent stop, session start/end) and usage

Goal: `dryas.ts` sends `post`, `stop`, `subagent-stop`, `session-start` and `session-end` to the chain and adds token usage to prompt events, proven against a real `opencode serve`.
Scope:
- opencode/plugin/dryas.ts
- install/tests/opencode_e2e.py
- install/tests/fixtures/mock_llm.py
- install/tests/test_opencode_observe_e2e.py
Done:
- `python3 -m pytest -q -rs -p no:cacheprovider install/tests/test_opencode_observe_e2e.py install/tests/test_opencode_shim_e2e.py` passes with `opencode` 1.18.x on PATH (no skips)
- `wc -l opencode/plugin/dryas.ts` under 500
Failing test first: install/tests/test_opencode_observe_e2e.py :: ProbeTest.test_post_reaches_chain

**Interfaces:**
- Consumes: Task 1's stage lists; Task 2's prompt event fields `usage`, `context_limit`, `model`; existing shim helpers `runScript`, `parse`, `toolEvent`, `base`, `session`, `resolveSession`; OpenCode bus events `session.created`, `session.idle` (`properties.sessionID`), `session.deleted`, `message.updated` (`properties.info`: assistant `tokens.{input,cache.read,cache.write}`, `modelID`, `sessionID`), `message.part.updated` (`properties.part`: tool part with `callID`, `sessionID`, `state.status`, `state.input`, `state.error`); hook `chat.params` `input.model.limit.context`.
- Produces: shim helpers `observe(kind, ev, timeoutMs?)`, `toolCwd(tool, args)`, `sessionMessages(id)` (Task 5 uses the last two); `Session` fields `contextLimit`, `usage`, `model`, `ended`; `Server.cfg` (the OpenCode config dir) in `opencode_e2e.py`; mock keyword `BIGUSAGE` and a `user` field (last user message text) in each mock log line.

- [ ] **Step 1: Write the failing test.** First extend the harness (test support, no behavior yet):
  - `install/tests/opencode_e2e.py`: in `Server.__init__`, after `cfg = self.tmp / "xdg/config/opencode"`, add `self.cfg = cfg`.
  - `install/tests/fixtures/mock_llm.py`: add `("BIGUSAGE", None, None)` handling: in `plan`, before the `for key, tool, args in SCRIPT` loop, add `if "BIGUSAGE" in text: return ("text", "big")`; in `do_POST`, set the usage per request: `usage = dict(USAGE, prompt_tokens=190000, total_tokens=190005) if p == ("text", "big") else USAGE` and use it in `chunk` (`c["usage"] = usage`); add `"user": text[:20000]` to the logged JSON, where `text` is the JSON dump of the last user message content (compute it in `do_POST` as `plan` does).

  Then create `install/tests/test_opencode_observe_e2e.py`:

```python
"""Plan 2, step-2 rows of the shim: observe-only chain calls and usage, against a real opencode serve."""
import json
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

from opencode_e2e import Server, opencode_ok

SKIP = opencode_ok()
PLAN = "## Task 1: t\nGoal: g\nScope:\n- src/**\nDone:\n- d\nFailing test first: none (review)\n"


def wait_for(fn, timeout=30.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.3)
    return fn()


def probe_chain(path: Path, log: Path) -> None:
    """A chain.json whose observe kinds append each event to LOG (one JSON line); pretool and prompt stay empty."""
    cmd = ["$PY", "-c", "import sys; open(sys.argv[1], 'a').write(sys.stdin.read().replace('\\n', ' ') + '\\n')",
           str(log).replace("\\", "/")]
    kinds = ("post", "stop", "subagent-stop", "session-start", "session-end", "precompact")
    path.write_text(json.dumps({k: [{"name": "probe", "harness": ["opencode"], "cmd": cmd, "timeout": 5,
                                     "observe": True}] for k in kinds}), encoding="utf-8")


@unittest.skipIf(SKIP, SKIP)
class ProbeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="dryas-oc-probe-"))
        cls.log = cls.dir / "events.jsonl"
        cls.log.touch()
        probe_chain(cls.dir / "chain.json", cls.log)
        cls.s = Server(cls.dir / "srv", env_extra={"JEV_CHAIN_CONFIG": str(cls.dir / "chain.json")})

    @classmethod
    def tearDownClass(cls):
        cls.s.close()
        shutil.rmtree(str(cls.dir), ignore_errors=True)

    def events(self, name, sid=None):
        evs = [json.loads(l) for l in self.log.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [e for e in evs if e.get("hook_event_name") == name and (sid is None or e.get("session_id") == sid)]

    def test_post_reaches_chain(self):
        sid = self.s.prompt("WRITE_ALLOWED")
        post = wait_for(lambda: self.events("PostToolUse", sid))
        self.assertEqual(post[0]["tool_name"], "Write")
        self.assertTrue(post[0]["tool_input"]["file_path"].endswith("allowed.txt"))
        self.assertTrue(post[0]["tool_use_id"])

    def test_session_start_and_stop_reach_chain(self):
        sid = self.s.prompt("hello")
        self.assertTrue(wait_for(lambda: self.events("SessionStart", sid)))
        self.assertTrue(wait_for(lambda: self.events("Stop", sid)))

    def test_subagent_stop_carries_agent_identity(self):
        sid = self.s.prompt("DELEGATE")
        kid = self.s.children(sid)[0]
        stop = wait_for(lambda: self.events("SubagentStop", kid))
        self.assertEqual(stop[0]["agent_id"], kid)
        self.assertEqual(stop[0]["agent_type"], "dryas-executor-fast")
        self.assertFalse(self.events("SessionStart", kid), "a subagent session is not a session start")

    def test_session_end_on_delete(self):
        sid = self.s.prompt("hello")
        self.s._http("DELETE", "/session/%s" % sid)
        self.assertTrue(wait_for(lambda: self.events("SessionEnd", sid)))


@unittest.skipIf(SKIP, SKIP)
class RealStageTest(unittest.TestCase):
    """The default chain: memory rows, context warning, and no failed edit for a call the shim blocked."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="dryas-oc-real-")
        cls.s = Server(Path(cls.dir))

    @classmethod
    def tearDownClass(cls):
        cls.s.close()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def rows(self, sql, *args):
        db = self.s.data / "dryas.db"
        if not db.exists():
            return []
        con = sqlite3.connect(str(db))
        try:
            return con.execute(sql, args).fetchall()
        except sqlite3.OperationalError:
            return []
        finally:
            con.close()

    def test_edit_is_recorded(self):
        sid = self.s.prompt("WRITE_ALLOWED")
        self.assertEqual(wait_for(lambda: self.rows("SELECT ok FROM edits WHERE session = ?", sid)), [(1,)])

    def test_blocked_write_is_not_a_failed_edit(self):
        orch = self.s.proj / ".orchestrate"
        orch.mkdir()
        try:
            (orch / "PLAN.md").write_text(PLAN, encoding="utf-8")
            (orch / "active.json").write_text(json.dumps({"active": ["1"]}), encoding="utf-8")
            sid = self.s.prompt("DELEGATE")
            kid = self.s.children(sid)[0]
            self.assertEqual([t[1] for t in self.s.tools(kid) if t[0] == "write"], ["error"])
            self.assertTrue(wait_for(lambda: self.rows("SELECT task_id FROM tasks WHERE task_id = '1'")))  # subagent-stop
            time.sleep(2)
            self.assertEqual(self.rows("SELECT ok FROM edits WHERE session = ?", kid), [])
        finally:
            shutil.rmtree(str(orch))

    def test_context_warning_reaches_model(self):
        sid = self.s.prompt("BIGUSAGE")
        self.s._http("POST", "/session/%s/message" % sid, {"parts": [{"type": "text", "text": "next"}]})
        last = [r for r in self.s.requests() if "next" in r.get("user", "")]
        self.assertTrue(last and "run /handoff then /new" in last[-1]["user"], last[-1:] or self.s.requests()[-1:])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q -rs -p no:cacheprovider install/tests/test_opencode_observe_e2e.py`. Expected: every test fails (no observe calls, no usage on the prompt event); none skips. If it skips, install OpenCode 1.18.x first (`opencode --version`).

- [ ] **Step 3: Implement.** In `opencode/plugin/dryas.ts`:

1. Constants and types (top of file):

```ts
const OBSERVE_MS = 10000
const END_MS = 3000
type Usage = { input_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number }
type Session = { agent?: string; parentID?: string; known?: boolean; contextLimit?: number; usage?: Usage; model?: string; ended?: boolean }
```

2. A module-level helper beside `toolEvent`:

```ts
function toolCwd(dir: string, tool: string, args: any): string {
  const wd = args?.workdir
  return tool === "bash" && typeof wd === "string" && wd ? resolve(dir, wd) : dir
}
```

and use it in `tool.execute.before` (`const cwd = toolCwd(ctx.directory, input.tool, output.args)`), replacing the two inline lines.

3. Inside `DryasPlugin`, after `approved`: `const blocked = new Set<string>()` and `const seen = new Set<string>()` (call IDs the shim blocked; failure events already sent; clear either when it passes 5000 entries), and:

```ts
  // Observe-only chain call: started, never awaited by a hook, never blocks or changes the session.
  const observe = (kind: string, ev: Record<string, unknown>, ms: number = OBSERVE_MS) =>
    runScript("chain.py", [kind, "--harness", "opencode"], ev, ms)
  const sessionMessages = async (id: string): Promise<any[]> => {
    try {
      return (await ctx.client.session.messages({ path: { id } }))?.data ?? []
    } catch {
      return []
    }
  }
  const end = (id: string, reason: string, ms?: number) => {
    const s = sessions.get(id)
    if (!s?.known || s.parentID || s.ended) return Promise.resolve(null)
    s.ended = true
    return observe("session-end", { ...base(id), hook_event_name: "SessionEnd", reason }, ms)
  }
```

4. In `tool.execute.before`: add `tool_use_id: input.callID` to `ev`; before every `throw` in that hook (the unknown-session, could-not-run, deny and ask throws) add `blocked.add(input.callID)` (the approved-ask `return` does not add it).

5. Replace the `event` hook body with:

```ts
      const p = event?.properties ?? {}
      const type = event?.type
      if (type === "session.created" && p.info?.id) {
        const s = session(p.info.id)
        s.parentID = p.info.parentID
        s.known = true
        if (!s.parentID) void observe("session-start", { ...base(p.info.id), hook_event_name: "SessionStart", source: "startup" })
      } else if (type === "session.deleted" && p.info?.id) {
        await end(p.info.id, "deleted")
        sessions.delete(p.info.id)
      } else if (type === "session.idle" && p.sessionID) {
        const s = await resolveSession(p.sessionID)
        const sub = !!s.parentID
        void observe(sub ? "subagent-stop" : "stop", { ...base(p.sessionID), hook_event_name: sub ? "SubagentStop" : "Stop" })
      } else if (type === "message.updated" && p.info?.role === "assistant" && p.info.tokens) {
        const t = p.info.tokens
        const u = { input_tokens: t.input ?? 0, cache_read_input_tokens: t.cache?.read ?? 0, cache_creation_input_tokens: t.cache?.write ?? 0 }
        if (u.input_tokens + u.cache_read_input_tokens + u.cache_creation_input_tokens > 0) {
          const s = session(p.info.sessionID)
          s.usage = u
          s.model = String(p.info.modelID ?? "")
        }
      } else if (type === "message.part.updated" && p.part?.type === "tool" && p.part.state?.status === "error") {
        const part = p.part
        if (seen.has(part.callID)) return
        if (seen.size > 5000) seen.clear()
        seen.add(part.callID)
        if (blocked.delete(part.callID)) return // the shim blocked it: Claude Code sends no failure event for a hook deny
        const te = toolEvent(part.tool, part.state.input)
        if (te)
          void observe("post", {
            ...base(part.sessionID, toolCwd(ctx.directory, part.tool, part.state.input)),
            hook_event_name: "PostToolUseFailure", ...te, tool_use_id: part.callID, error: String(part.state.error ?? ""),
          })
      }
```

   (`end` awaits only on delete, where the session record is about to go; its run is bounded by `OBSERVE_MS`.) If `blocked` grows past 5000, clear it.

6. `chat.params`: also record the window: `const lim = input?.model?.limit?.context; if (input?.sessionID && typeof lim === "number" && lim > 0) session(input.sessionID).contextLimit = lim`.

7. `chat.message`: build the prompt event with usage when known:

```ts
      const s = session(input.sessionID)
      const ev = {
        ...base(input.sessionID), hook_event_name: "UserPromptSubmit", prompt,
        ...(s.usage ? { usage: s.usage, context_limit: s.contextLimit ?? 0, model: s.model ?? "" } : {}),
      }
```

8. New hook `tool.execute.after`:

```ts
    "tool.execute.after": async (input: any, output: any) => {
      const te = toolEvent(input.tool, input.args)
      if (!te) return
      void observe("post", {
        ...base(input.sessionID, toolCwd(ctx.directory, input.tool, input.args)), hook_event_name: "PostToolUse", ...te,
        tool_use_id: input.callID, tool_response: { output: String(output?.output ?? "").slice(0, 2000) },
      })
    },
```

9. New hook `dispose` (best effort; OpenCode sends no event on a TUI exit, spec section 8):

```ts
    dispose: async () => {
      await Promise.all([...sessions.keys()].map((id) => end(id, "exit", END_MS)))
    },
```

- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q -rs -p no:cacheprovider install/tests/test_opencode_observe_e2e.py install/tests/test_opencode_shim_e2e.py install/tests/test_opencode_e2e.py`. Expected: PASS, no skips. If `session.idle` arrives before the subagent's `chat.params` sets its agent, read the agent name from the child session (`ctx.client.session.get`) in `resolveSession` rather than weakening the assertion.

- [ ] **Step 5: Commit** (e.g. `feat(opencode): shim sends post, stop, subagent-stop and session events to the chain`) when the dispatch prompt allows it; otherwise report.

## Task 5: Shim: compaction keep, `/handoff` and handoff restore

Goal: On OpenCode, compaction carries the Jev-kept lines, `/handoff` saves a Jev-scored handoff, and the next root session starts with it.
Scope:
- opencode/plugin/dryas.ts
- tools/sync_opencode.py
- opencode/command/handoff.md
- opencode/dryas/AGENTS.md.template
- install/tests/test_opencode_compact_e2e.py
- install/tests/test_opencode_sync.py
Done:
- `python3 -m pytest -q -rs -p no:cacheprovider install/tests/test_opencode_compact_e2e.py install/tests/test_opencode_sync.py install/tests/test_opencode_setup.py` passes with `opencode` 1.18.x on PATH (no skips)
- `python3 tools/sync_codex_plugin.py --check` exits 0
Failing test first: install/tests/test_opencode_compact_e2e.py :: CompactTest.test_compaction_context_reaches_model

**Interfaces:**
- Consumes: Task 3's CLI `opencode_session.py compact|handoff` (stdin `{session_id, cwd, messages}`, stdout `{"context"}` / `{"line"}`); `handoff_restore.py` (stdin `{cwd, source: "clear"}`, stdout `hookSpecificOutput.additionalContext`); Task 4's `observe`, `sessionMessages`, `Server.cfg`, mock `user` log field; hooks `experimental.session.compacting` (`output.context: string[]`), `command.execute.before` (`input.command`, `output.parts`), `experimental.chat.system.transform` (`input.sessionID`, `output.system`).
- Produces: `opencode/command/handoff.md` (dryas-managed, installed by `opencode_setup.py` with the other commands); `Session.restore?: string | null`.

- [ ] **Step 1: Write the failing test.** Create `install/tests/test_opencode_compact_e2e.py`:

```python
"""Plan 2: compaction keep and /handoff on a real opencode serve (no API key: Jev is unavailable, so the engines keep
the always-kept lines and the newest items, which include the user's prompt)."""
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from opencode_e2e import Server, opencode_ok

SKIP = opencode_ok()
HEADER = "Handoff from previous session"


@unittest.skipIf(SKIP, SKIP)
class CompactTest(unittest.TestCase):
    def test_compaction_context_reaches_model(self):
        with tempfile.TemporaryDirectory() as d:
            s = Server(Path(d))
            try:
                sid = s.prompt("WRITE_ALLOWED")
                s._http("POST", "/session/%s/summarize" % sid, {"providerID": "mock", "modelID": "m1"})
                hits = [r for r in s.requests() if HEADER in r.get("user", "")]
                self.assertTrue(hits, [r.get("user", "")[-300:] for r in s.requests()[-3:]])
                self.assertIn("WRITE_ALLOWED", hits[-1]["user"])
            finally:
                s.close()


@unittest.skipIf(SKIP, SKIP)
class HandoffTest(unittest.TestCase):
    def test_handoff_restores_into_next_session_only(self):
        with tempfile.TemporaryDirectory() as d:
            s = Server(Path(d))
            try:
                sid = s.prompt("WRITE_ALLOWED")
                s._http("POST", "/session/%s/command" % sid, {"command": "handoff", "arguments": ""})
                saved = [r for r in s.requests() if "Handoff saved:" in r.get("user", "")]
                self.assertTrue(saved, s.requests()[-1:])
                self.assertIn("/new", saved[-1]["user"])
                n = len(s.requests())
                s.prompt("hello")  # the next root session gets the handoff in its system prompt
                first = s.requests()[n:]
                self.assertTrue(any(HEADER in str(x) and "WRITE_ALLOWED" in str(x) for r in first for x in r["system"]), first)
                n = len(s.requests())
                s.prompt("hello again")  # the file was used once: a later session starts clean
                self.assertFalse(any(HEADER in str(x) for r in s.requests()[n:] for x in r["system"]))
            finally:
                s.close()

    def test_handoff_without_python_says_nothing_saved(self):
        with tempfile.TemporaryDirectory() as d:
            s = Server(Path(d), env_extra={"DRYAS_PY": str(Path(d) / "no-such-python")})
            try:
                sid = s.prompt("hello")
                s._http("POST", "/session/%s/command" % sid, {"command": "handoff", "arguments": ""})
                self.assertIn("nothing saved", s.requests()[-1].get("user", ""))
                s._http("POST", "/session/%s/summarize" % sid, {"providerID": "mock", "modelID": "m1"})  # still compacts
            finally:
                s.close()


if __name__ == "__main__":
    unittest.main()
```

  In `install/tests/test_opencode_sync.py` add a test that `opencode/command/handoff.md` is in `sync_opencode.plan(REPO)`, carries the `<!-- dryas-managed -->` marker, and that the rendered rules (`opencode/dryas/AGENTS.md.template`) no longer contain `Not yet on OpenCode`:

```python
    def test_handoff_command_and_rules_tail(self):
        out = sync_opencode.plan(REPO)
        self.assertIn(sync_opencode.MARK, out["opencode/command/handoff.md"])
        self.assertNotIn("Not yet on OpenCode", out["opencode/dryas/AGENTS.md.template"])
        self.assertIn("/handoff", out["opencode/dryas/AGENTS.md.template"])
```

  (Match the existing import name and class in that file.)

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q -rs -p no:cacheprovider install/tests/test_opencode_compact_e2e.py install/tests/test_opencode_sync.py`. Expected: the e2e tests fail (no kept lines in the compaction request; `/handoff` is an unknown command), the sync test fails with `KeyError: 'opencode/command/handoff.md'`.

- [ ] **Step 3: Implement.**

  `tools/sync_opencode.py`:
  - Add the command text and render it in `plan()` after the `THIN + FROM_CODEX` loop: `out["opencode/command/handoff.md"] = HANDOFF_COMMAND`.

```python
HANDOFF_COMMAND = (
    "---\ndescription: \"Score this session with Jev and save a handoff; then /new starts fresh with only what matters\"\n"
    "---\n" + MARK + "\n"
    "The Dryas plugin replaces this text with the result of the handoff. If you can read this, the plugin did not "
    "load: tell the user /handoff needs the Dryas plugin (re-run install.sh --harness opencode), that nothing was "
    "saved, and stop.\n")
```

  - Replace `RULES_TAIL`'s second bullet with: `"- Context warnings, compaction keep and the memory hooks run on their own. `/handoff` saves a Jev-scored handoff; the next new session (`/new`) starts with it.\n"`.
  - Run `python3 tools/sync_codex_plugin.py`.

  `opencode/plugin/dryas.ts`:

```ts
const COMPACT_MS = 30000
const HANDOFF_MS = 90000
const RESTORE_MS = 5000
```

  Add `restore?: string | null` to `Session`. New hooks:

```ts
    "experimental.session.compacting": async (input: any, output: any) => {
      const ev = { ...base(input.sessionID), hook_event_name: "PreCompact", trigger: "auto" }
      const messages = await sessionMessages(input.sessionID)
      const out = parse(await runScript("opencode_session.py", ["compact"], { ...ev, messages }, COMPACT_MS))
      if (out?.context) output.context.push(String(out.context))
      void observe("precompact", ev)
    },

    "command.execute.before": async (input: any, output: any) => {
      if (input?.command !== "handoff") return
      const messages = await sessionMessages(input.sessionID)
      const out = parse(await runScript("opencode_session.py", ["handoff"], { ...base(input.sessionID), messages }, HANDOFF_MS))
      const line = String(out?.line || `Handoff failed: Dryas could not run Python (${PY}); nothing saved.`)
      const text = `Show the user this line exactly, and if it says the handoff was saved, tell them to type /new to start a fresh session seeded with it. Do nothing else.\n\n${line}`
      for (const p of output?.parts ?? []) if (p?.type === "text") p.text = text
    },
```

  In `experimental.chat.system.transform`, after the rules push (rename `_input` to `input`):

```ts
      const sid = input?.sessionID
      if (sid) {
        const s = await resolveSession(sid)
        if (s.known && !s.parentID && s.restore === undefined) {
          s.restore = null // first request of this root session: a fresh /handoff for this project, used once
          const out = parse(await runScript("handoff_restore.py", [], { cwd: ctx.directory, source: "clear", session_id: sid }, RESTORE_MS))
          const add = out?.hookSpecificOutput?.additionalContext
          if (add) s.restore = String(add)
        }
        if (s.restore) output.system.push(s.restore)
      }
```

  Check `install/opencode_setup.py` installs every file under `opencode/command/` (it copies the folder; if it lists commands by name, add `handoff`), and that `install/tests/test_opencode_setup.py` still passes.

- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q -rs -p no:cacheprovider install/tests/test_opencode_compact_e2e.py install/tests/test_opencode_observe_e2e.py install/tests/test_opencode_shim_e2e.py install/tests/test_opencode_sync.py install/tests/test_opencode_setup.py && python3 tools/sync_codex_plugin.py --check`. Expected: PASS, no skips, exit 0. If OpenCode puts the compaction `context` somewhere other than the last user message, change the mock's `user` log field to all message text of the request (not the assertion).

- [ ] **Step 5: Commit** (e.g. `feat(opencode): compaction keep, /handoff and handoff restore`) when the dispatch prompt allows it; otherwise report.

## Task 6: Docs and conformance: the OpenCode edition is Full

Goal: The OC column, harness docs, roadmap, changelog and spec binding describe the OpenCode edition at Dryas Full, with `partial` only where OpenCode lacks the capability.
Scope:
- reference/README.md
- reference/dryas.yaml
- docs/harnesses.md
- docs/roadmap.md
- README.md
- CHANGELOG.md
- install/tests/test_opencode_docs.py
Done:
- `python3 -m pytest -q -p no:cacheprovider install/tests/test_opencode_docs.py install/tests/test_framework_docs.py install/tests/test_owned_core_docs.py` passes
- `grep -rnE "plan 2|step 2" reference/README.md reference/dryas.yaml docs/harnesses.md README.md` prints nothing
- the full suite `python3 -m pytest -q -p no:cacheprovider claude/jev/tests install/tests` passes
Failing test first: install/tests/test_opencode_docs.py :: OpenCodeDocsTest.test_no_plan_2_rows_left

**Interfaces:**
- Consumes: Tasks 1–5 behavior (the stage lists, `/handoff` then `/new`, compaction keep through `experimental.session.compacting`, best-effort session end).
- Produces: none (docs).

- [ ] **Step 1: Write the failing test.** Add to `OpenCodeDocsTest` in `install/tests/test_opencode_docs.py`:

```python
    def test_no_plan_2_rows_left(self):
        text = (REPO / "reference/README.md").read_text(encoding="utf-8")
        rows = [l for l in text.splitlines() if re.match(r"^\| [A-Z]+-\d", l)]
        for row in rows:
            oc = [c.strip() for c in row.strip("|").split("|")][3]
            self.assertNotRegex(oc, r"plan 2|step 2", row)
        harn = (REPO / "docs/harnesses.md").read_text(encoding="utf-8")
        self.assertIn("/handoff", harn)
        self.assertIn("/new", harn)
        self.assertNotIn("plan 2", (REPO / "reference/dryas.yaml").read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q -p no:cacheprovider install/tests/test_opencode_docs.py`. Expected: FAIL on the `MEM-6` row (`partial: plan 2`).

- [ ] **Step 3: Implement.**
  - `reference/README.md`: `MEM-6` OC → `met`; `How` text: OpenCode runs the memory hook stages through the chain, keeps Jev-scored lines through `experimental.session.compacting`, and `/handoff` then `/new` restores into the next session. `GOV-11` OC → `met`; the memory stages run on OpenCode (Codex still Claude Code only for memory). Any other OC cell or `How` text naming plan 2 or step 2: update it to the shipped behavior. Rows touched by spec section 8 keep `partial` with their reason: session end (no event on a TUI exit; `session.deleted` and plugin `dispose` cover the rest, `mem-session-end` also runs at `precompact` and `mem-notes` at `stop`) and the headless ask.
  - `reference/dryas.yaml` line 5 comment: `# opencode: Dryas Full (memory hooks, compaction, /handoff since plan 2)` or drop the plan wording; keep the `harness:` list.
  - `docs/harnesses.md` OpenCode section: replace "Supported (core). Conformance is partial: …" with the Full status; describe context warnings (`run /handoff then /new`), compaction keep, `/handoff` then `/new` (the next new root session in the same project within 30 minutes gets the handoff once), the memory stages, and the known gaps of spec section 8 (session end best effort, headless ask, experimental hooks).
  - `docs/roadmap.md`, `README.md`: tick or reword any "plan 2" / "memory hooks not yet" item for OpenCode (`grep -n "plan 2\|not yet" docs/roadmap.md README.md`).
  - `CHANGELOG.md`: under an `## Unreleased` heading at the top (create it if missing; the release check skips an unreleased heading), an entry: "OpenCode edition at Dryas Full: memory hook stages, context-window warnings, compaction keep and `/handoff` run on OpenCode (`opencode_session.py` turns OpenCode session messages into a transcript for the existing engines)."

- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q -p no:cacheprovider install/tests/test_opencode_docs.py install/tests/test_framework_docs.py install/tests/test_owned_core_docs.py install/tests/test_release_version.py`, then the full suite `python3 -m pytest -q -p no:cacheprovider claude/jev/tests install/tests` and `python3 tools/inventory.py --check | tail -1`. Expected: PASS; `0 problems`.

- [ ] **Step 5: Commit** (e.g. `docs(opencode): the OpenCode edition is Dryas Full`) when the dispatch prompt allows it; otherwise report.
