#!/usr/bin/env python3
"""PostToolUse observe stage `gate-outcome`: log the tool_use_id of an asked Bash call that ran.

gate.py notes the tool_use_id of every Bash `ask` in asks_pending.json (Jev log dir, last MAX_PENDING ids). When
that call ran, the user approved the ask: record() logs it to outcomes.jsonl (for /tune allowlist proposals) and
drops it from the pending set. Any other call writes nothing. chain.py calls record() in-process (stage "inproc");
running this file reads the event from stdin. Observe-only: prints nothing, never raises."""
import json
import os
import sys
import tempfile
from typing import Any, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jevlog

MAX_STDIN = 1024 * 1024
MAX_PENDING = 200
PENDING = "asks_pending.json"


def _path() -> str:
    return os.path.join(jevlog.log_dir(), PENDING)


def _read() -> List[str]:
    try:
        with open(_path(), encoding="utf-8") as f:
            v = json.load(f)
    except (OSError, ValueError):
        return []
    return [i for i in v if isinstance(i, str)][-MAX_PENDING:] if isinstance(v, list) else []


def _write(ids: List[str]) -> None:
    d = jevlog.log_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".asks_pending-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(ids[-MAX_PENDING:], f)
        os.replace(tmp, _path())
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def note_ask(tool_use_id: str) -> None:
    """Remember an asked Bash call (gate.py). Never raises.
    The read-modify-write is unlocked by design: the worst case is a lost id, i.e. a missed /tune approval,
    never a looser gate."""
    try:
        tid = tool_use_id[:64]
        _write([i for i in _read() if i != tid] + [tid])
    except Exception:
        pass


def record(event: Any) -> None:
    """Log an asked call that ran; a failed one (PostToolUseFailure, possibly a refused ask) is dropped unlogged.
    Unlocked read-modify-write, as in note_ask (a lost id only misses a /tune approval)."""
    try:
        if not isinstance(event, dict) or not isinstance(event.get("tool_use_id"), str):
            return
        tid = event["tool_use_id"][:64]
        ids = _read()
        if tid not in ids:
            return
        _write([i for i in ids if i != tid])
        if event.get("hook_event_name") != "PostToolUseFailure":
            jevlog.append("outcomes", dict(tool_use_id=tid, tool="Bash"))
    except Exception:
        pass


if __name__ == "__main__":
    try:
        record(json.loads(sys.stdin.read(MAX_STDIN)))
    except Exception:
        pass
    sys.exit(0)
