#!/usr/bin/env python3
"""Memory notes for cloud sessions (owned core E; opt-in with `dryas cloud init --persist-memory`).

  memnotes.py export   SessionEnd stage `mem-notes`: this session's lessons and decisions, task outcomes and
                       /tune per-task rows as one short markdown note; its free text is redacted with redact.py

The note goes to $DRYAS_NOTES_DIR (set by cloud_hook.py), else <plugin root>/memory/notes, and only when that folder
exists; chain.json runs the stage only when $CD/memory/notes exists, so a plugin install never writes one. The notes
are committed with the work and reviewed in pull requests; the next session start indexes them as memory notes
(memhooks.py session-start reads DRYAS_NOTES_DIR). Observe-only: prints nothing, exits 0, stays inside the 2 s hook
budget; a failure is one memory.jsonl line."""
import datetime
import json
import os
import re
import sys
import threading
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jevlog
import memdb
import paths
import projns
import redact
import tune
import tune_tasks

BUDGET_S = 1.8
BUSY_MS = 500
MAX_BYTES = 16 * 1024
MAX_ITEMS = 20
KINDS = ("outcome", "fact", "retro")
ROW_FIELDS = ("start_tier", "final_tier", "tokens", "duration_ms", "escalated", "score")
STDIN_MAX = 1024 * 1024
TS = "%Y-%m-%dT%H:%M:%S%z"  # jevlog's record time


def notes_dir() -> str:
    return os.environ.get("DRYAS_NOTES_DIR") or os.path.join(paths.plugin_root(), "memory", "notes")


def safe_id(sid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", sid)[:12] or "session"


def _line(v: Any, cap: int = 240) -> str:
    """One redacted line of free text (titles, bodies, the summary); numbers are written as they are."""
    return " ".join(redact.redact(str(v or "")).split())[:cap]


def session_since(conn, sid: str) -> float:
    r = conn.execute("SELECT started FROM sessions WHERE id = ?", (sid,)).fetchone()
    return float(r["started"]) if r and r["started"] else 0.0


def recent_rows(rows: Dict[str, Dict[str, Any]], since: float) -> Dict[str, Dict[str, Any]]:
    """The /tune per-task rows of tasks first dispatched in this session."""
    out = {}
    for task, row in rows.items():
        try:
            t = datetime.datetime.strptime(str(row.get("first_ts")), TS).timestamp()
        except ValueError:
            continue
        if t >= since - 1:
            out[task] = row
    return out


def render(conn, ns: str, sid: str, since: float, rows: Dict[str, Dict[str, Any]], now: float) -> str:
    """The note; "" when the session left nothing worth keeping."""
    mems = conn.execute("SELECT kind, title, body FROM memory WHERE ns = ? AND source = 'dryas' AND kind IN (?, ?, ?)"
                        " AND created >= ? ORDER BY created LIMIT ?", (ns,) + KINDS + (since, MAX_ITEMS)).fetchall()
    tasks = conn.execute("SELECT task_id, title, tier_start, tier_end, outcome FROM tasks WHERE ns = ? AND ended >= ?"
                         " ORDER BY ended LIMIT ?", (ns, since, MAX_ITEMS)).fetchall()
    if not (mems or tasks or rows):
        return ""
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    out: List[str] = ["---", "name: Dryas session %s %s" % (day, safe_id(sid)), "---", "", "# Dryas session " + day, ""]
    summary = conn.execute("SELECT summary FROM sessions WHERE id = ?", (sid,)).fetchone()
    if summary and summary["summary"]:
        out += [_line(summary["summary"]), ""]
    if mems:
        out += ["## Lessons and decisions", ""]
        out += ["- %s: %s. %s" % (m["kind"], _line(m["title"], 120), _line(m["body"])) for m in mems] + [""]
    if tasks:
        out += ["## Tasks", ""]
        out += ["- %s %s: %s (%s -> %s)" % (_line(t["task_id"], 80), _line(t["title"], 120), _line(t["outcome"] or "open", 40),
                                            _line(t["tier_start"] or "?", 40), _line(t["tier_end"] or "?", 40))
                for t in tasks] + [""]
    if rows:
        out += ["## Task numbers (/tune)", ""]
        for task in sorted(rows)[:MAX_ITEMS]:
            vals = ["%s=%s" % (f, rows[task][f]) for f in ROW_FIELDS if rows[task].get(f) is not None]
            out.append("- %s: %s" % (_line(task, 80), ", ".join(vals)))
        out.append("")
    data = "\n".join(out).encode("utf-8")[:MAX_BYTES]
    return data.decode("utf-8", "ignore").rstrip("\n") + "\n"


def export(conn, event: Dict[str, Any], now: Optional[float] = None) -> Optional[str]:
    """Write this session's note. Its path, or None when there is no notes folder or nothing to keep."""
    d = notes_dir()
    if not os.path.isdir(d):
        return None
    now = time.time() if now is None else now
    cwd = str(event.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    sid = str(event.get("session_id") or "unknown")
    since = session_since(conn, sid)
    rows = recent_rows(tune_tasks.rows(tune.read("gate"), tune.read("dispatch"), tune.read("escalations"),
                                       tune.read("mcp")), since)
    text = render(conn, projns.project_ns(cwd), sid, since, rows, now)
    if not text:
        return None
    path = os.path.join(d, "%s-%s.md" % (time.strftime("%Y-%m-%d", time.localtime(now)), safe_id(sid)))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def _watchdog() -> threading.Timer:
    def fire() -> None:
        jevlog.append("memory", dict(stage="mem-notes", error="Timeout", detail=""))
        os._exit(0)
    t = threading.Timer(BUDGET_S, fire)
    t.daemon = True
    t.start()
    return t


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    dog = _watchdog()
    try:
        if argv[:1] != ["export"]:
            raise ValueError("usage: memnotes.py export")
        event = json.loads(sys.stdin.buffer.read(STDIN_MAX).decode("utf-8", "replace") or "{}")
        if not isinstance(event, dict):
            raise ValueError("hook event is not an object")
        if os.path.isdir(notes_dir()):
            conn = memdb.connect(busy_ms=BUSY_MS)
            try:
                export(conn, event)
            finally:
                conn.close()
    except Exception as e:
        jevlog.append("memory", dict(stage="mem-notes", error=type(e).__name__, detail=str(e)[:200]))
    dog.cancel()
    return 0


if __name__ == "__main__":
    sys.exit(main())
