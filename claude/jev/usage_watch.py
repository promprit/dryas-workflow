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
            sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                                "additionalContext": line}}))
    except Exception:
        pass
    sys.exit(0)
