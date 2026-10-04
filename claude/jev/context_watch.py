#!/usr/bin/env python3
"""Chain stage on UserPromptSubmit: warn when context use passes warn_pct so the user can /handoff then
/clear before auto-compaction. Reads only the last ~2 MB of the transcript, no network.
Tiers: once at warn_pct, once more at warn_pct+0.05; a tier never repeats within a session."""
import hashlib
import json
import os
import re
import sys
from typing import Any, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thresholds

TAIL_BYTES = 2 * 1024 * 1024
DEFAULT_WINDOW = 200000
STEP = 0.05
DEFAULT_AUTOCOMPACT = 95
_VERSION = re.compile(r"(?:opus|sonnet)-(\d{1,2})(?!\d)(?:-(\d{1,2})(?!\d))?")


def _state_dir() -> str:
    return os.path.join(os.environ.get("JEV_HANDOFF_DIR", os.path.expanduser("~/.claude/jev/handoff")), ".warned")


def _million_model(model: str) -> bool:
    """Models with a 1M window by default: Fable, Mythos, Opus/Sonnet 4.6 and later. Same rule as flowobserve's
    millionModel() (server/src/transcript.ts); keep the two in step."""
    if "fable" in model or "mythos" in model:
        return True
    # Versions are 1-2 digits so a date is never read as one: claude-sonnet-4-20250514 is 4.0, claude-3-opus-20240229 has no match.
    m = _VERSION.search(model)
    if not m:
        return False  # Haiku and unknown ids: 200k; the > 200k usage rule still corrects a miss
    major, minor = int(m.group(1)), int(m.group(2) or 0)
    return major > 4 or (major == 4 and minor >= 6)


def _window(model: str, max_tokens: int) -> int:
    """JEV_CONTEXT_WINDOW if valid; else 1M when the model id says [1m], names a 1M-default model, or usage ever
    exceeded 200k; else 200k."""
    try:
        w = int(os.environ.get("JEV_CONTEXT_WINDOW", ""))
        if w > 0:
            return w
    except ValueError:
        pass
    big = "[1m]" in model or _million_model(model) or max_tokens > DEFAULT_WINDOW
    return 1000000 if big else DEFAULT_WINDOW


def _autocompact_pct() -> int:
    try:
        v = int(os.environ.get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", ""))
        return v if 1 <= v <= 100 else DEFAULT_AUTOCOMPACT
    except ValueError:
        return DEFAULT_AUTOCOMPACT


def _warn_pct() -> float:
    v = thresholds.load()["context"]["warn_pct"]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0.1 <= v <= 0.95:
        return thresholds.DEFAULTS["context"]["warn_pct"]
    return float(v)


def read_usage(path: str) -> Optional[Tuple[int, int, str]]:
    """(tokens of the last assistant record with usage, max tokens seen in the tail, that record's model)."""
    with open(path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        start = max(0, size - TAIL_BYTES)
        f.seek(start)
        data = f.read()
    lines = data.split(b"\n")
    if start > 0:
        lines = lines[1:]  # first line is likely cut mid-record
    last: Optional[Tuple[int, str]] = None
    biggest = 0
    for raw in reversed(lines):
        if b'"usage"' not in raw:
            continue
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get("type") != "assistant":
            continue
        msg = rec.get("message")
        usage = msg.get("usage") if isinstance(msg, dict) else None
        if not isinstance(usage, dict):
            continue
        total = 0
        for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            v = usage.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                total += int(v)
        biggest = max(biggest, total)
        if last is None:
            model = msg.get("model")
            last = (total, model if isinstance(model, str) else "")
    return (last[0], biggest, last[1]) if last else None


def _read_state(sfile: str) -> Tuple[int, int]:
    try:
        with open(sfile, encoding="utf-8") as f:
            tier, last = f.read().split()
            return int(tier), int(last)
    except (OSError, ValueError):
        return -2, 0  # -2: no state yet


def run(event: Dict[str, Any]) -> Optional[str]:
    try:
        path, sid = event.get("transcript_path"), event.get("session_id")
        if not isinstance(path, str) or not os.path.isfile(path) or not isinstance(sid, str) or not sid:
            return None
        usage = read_usage(path)
        if usage is None:
            return None
        tokens, biggest, model = usage
        pct = tokens / float(_window(model, biggest))
        warn = _warn_pct()
        tier = 1 if pct >= warn + STEP - 1e-9 else 0 if pct >= warn - 1e-9 else -1
        sdir = _state_dir()
        sfile = os.path.join(sdir, hashlib.sha256(sid.encode("utf-8")).hexdigest()[:16])
        warned, last = _read_state(sfile)
        has_state = warned != -2
        if has_state and last > 0 and tokens < last * 0.7:
            warned = -1  # context shrank >30%: compaction or clear happened, warn again
        warned = max(warned, -1)
        emit = tier > warned
        if emit or (has_state and (tokens != last)):
            os.makedirs(sdir, mode=0o700, exist_ok=True)
            os.chmod(sdir, 0o700)
            fd = os.open(sfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, ("%d %d" % (max(tier, warned) if emit else warned, tokens)).encode())
            finally:
                os.close(fd)
            os.chmod(sfile, 0o600)
        if not emit:
            return None
        return ("Context %d%% — tell the user: run /handoff then /clear to continue with a Jev-scored context "
                "(auto-compaction is at %d%%)." % (int(pct * 100 + 1e-9), _autocompact_pct()))
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
