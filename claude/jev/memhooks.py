#!/usr/bin/env python3
"""Memory hook stages for the dryas memory provider (owned core, sub-project B). Observe-only: read the hook
event on stdin, write the memory store, print nothing, always exit 0, stay inside a 2 s budget (busy timeout
0.5 s). A failure is one line in memory.jsonl.

  memhooks.py edit                       PostToolUse / PostToolUseFailure on Write|Edit|MultiEdit|NotebookEdit
  memhooks.py task                       SubagentStop: upsert the active task rows (tiers from dispatch.jsonl), close finished ones
  memhooks.py session-start              SessionStart: session row; Claude memory files indexed as notes
  memhooks.py session-end [manual|auto]  SessionEnd (summary, consolidate) / PreCompact (summary only)
A consolidation skipped inside the budget is marked pending and finished by a detached `memcli.py consolidate`.
Sub-project D wires these into chain.json (mem-edit, mem-task, mem-session-start, mem-session-end)."""
import datetime
import json
import os
import re
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import consolidate_bg
import jevlog
import memdb
import memlearn
import paths
import planfile
import projns
import redact
import taskctx

HOOK_BUSY_MS = 500
CONSOLIDATE_DEADLINE_S = 1.2  # consolidation must finish this long after the stage began (watchdog: 1.8)
CONSOLIDATE_BEFORE_S = 1.0  # consolidate only if the stage has used less than this of its 2 s budget
NOTE_MAX_BYTES = 64 * 1024
BUDGET_S = 1.8  # the watchdog fires here, inside the 2 s hook budget
STDIN_MAX = 1024 * 1024
TAIL_BYTES = 2 * 1024 * 1024
EDIT_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
STAGES = ("edit", "task", "session-start", "session-end")
_NAME = re.compile(r"^name:\s*(.+)$", re.M)


def _cwd(event: Dict[str, Any]) -> str:
    return event.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def _find_up(start: str, rel: str) -> Optional[str]:
    d = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(d, rel)):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def repo_rel(path: str) -> str:
    """Path relative to the enclosing checkout (a .git dir, or a worktree's .git file), so worktrees of one repo
    agree on file names; the absolute path when there is none."""
    p = os.path.abspath(path)
    root = _find_up(os.path.dirname(p), ".git")
    return os.path.relpath(p, root).replace(os.sep, "/") if root else p.replace(os.sep, "/")


def _task_ids(cwd: str) -> List[str]:
    """Every active task id (taskctx returns {"task": id} or {"tasks": [ids]})."""
    ctx = taskctx.context(cwd)
    if ctx.get("task"):
        return [str(ctx["task"])]
    extra = ctx.get("tasks")
    return [str(t) for t in extra] if isinstance(extra, list) else []


def on_edit(conn, event: Dict[str, Any]) -> bool:
    if event.get("tool_name") not in EDIT_TOOLS:
        return False
    ti = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    f = ti.get("file_path") or ti.get("notebook_path")
    if not isinstance(f, str) or not f:
        return False
    cwd = _cwd(event)
    resp = event.get("tool_response")
    failed = event.get("hook_event_name") == "PostToolUseFailure" or (
        isinstance(resp, dict) and (resp.get("success") is False or bool(resp.get("error"))))
    ids = _task_ids(cwd)
    with memdb.tx(conn):
        conn.execute("INSERT INTO edits (ns, session, task_id, file, ok, ts) VALUES (?, ?, ?, ?, ?, ?)",
                     (projns.project_ns(cwd), event.get("session_id"), ids[0] if len(ids) == 1 else None,
                      repo_rel(os.path.join(cwd, f)), 0 if failed else 1, time.time()))
    return True


def _dispatches(task_id: str) -> List[Dict[str, Any]]:
    try:
        with open(os.path.join(jevlog.log_dir(), "dispatch.jsonl"), "rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - TAIL_BYTES))
            data = fh.read()
    except OSError:
        return []
    out = []
    for line in data.decode("utf-8", "replace").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and str(r.get("task")) == task_id:
            out.append(r)
    return out


def _plan_section(cwd: str, task_id: str) -> Tuple[str, List[str]]:
    root = _find_up(cwd, os.path.join(".orchestrate", "PLAN.md"))
    if not root:
        return "", []
    try:
        with open(os.path.join(root, ".orchestrate", "PLAN.md"), encoding="utf-8") as fh:
            sec = planfile.sections(fh.read()).get(task_id.rsplit(":", 1)[-1])
    except (OSError, UnicodeDecodeError):
        return "", []
    if not sec:
        return "", []
    return sec.splitlines()[0].split(":", 1)[-1].strip()[:200], planfile.scope(sec)


def _orch_root(cwd: str) -> Optional[str]:
    """Realpath of the dir holding .orchestrate, found upwards from cwd; stops at the checkout root."""
    d = os.path.realpath(cwd)
    while True:
        if os.path.isdir(os.path.join(d, ".orchestrate")):
            return d
        parent = os.path.dirname(d)
        if os.path.exists(os.path.join(d, ".git")) or parent == d:
            return None
        d = parent


def _ts(rec: Dict[str, Any], default: float) -> float:
    try:
        return datetime.datetime.strptime(str(rec.get("ts")), "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except ValueError:
        return default


def sweep(conn, ns: str, root: Optional[str], active: List[str]) -> int:
    """Close this root's open task rows whose id is no longer active."""
    if not root:
        return 0
    stale = []
    for r in conn.execute("SELECT task_id, meta FROM tasks WHERE ns = ? AND ended IS NULL", (ns,)):
        try:
            if json.loads(r["meta"] or "{}").get("root") == root and r["task_id"] not in active:
                stale.append(r["task_id"])
        except (ValueError, AttributeError):
            continue
    if stale:
        with memdb.tx(conn):
            conn.executemany("UPDATE tasks SET ended = ?, outcome = 'done' WHERE ns = ? AND task_id = ?",
                             [(time.time(), ns, t) for t in stale])
    return len(stale)


def on_task(conn, event: Dict[str, Any]) -> int:
    cwd = _cwd(event)
    ns, now, root, ids = projns.project_ns(cwd), time.time(), _orch_root(cwd), _task_ids(cwd)
    for tid in ids:
        d = _dispatches(tid)
        tiers = [str(r["tier"]) for r in d if r.get("tier")]
        title, scope = _plan_section(cwd, tid)
        title, scope = redact.redact(title), [redact.redact(s) for s in scope]
        with memdb.tx(conn):
            conn.execute(
                "INSERT INTO tasks (task_id, ns, title, scope, tier_start, tier_end, outcome, started, ended, meta) "
                "VALUES (?, ?, ?, ?, ?, ?, NULL, ?, NULL, ?) ON CONFLICT(ns, task_id) DO UPDATE SET "
                "title = CASE WHEN excluded.title != '' THEN excluded.title ELSE tasks.title END, "
                "scope = CASE WHEN excluded.scope != '[]' THEN excluded.scope ELSE tasks.scope END, "
                "tier_start = COALESCE(tasks.tier_start, excluded.tier_start), "
                "tier_end = COALESCE(excluded.tier_end, tasks.tier_end), "
                "started = COALESCE(tasks.started, excluded.started), "
                "outcome = NULL, ended = NULL, meta = excluded.meta",
                (tid, ns, title, json.dumps(scope), tiers[0] if tiers else None, tiers[-1] if tiers else None,
                 _ts(d[0], now) if d else now, json.dumps({"dispatches": len(d), "root": root})))
    sweep(conn, ns, root, ids)
    return len(ids)


def notes_dir(cwd: str) -> Optional[str]:
    env = os.environ.get("DRYAS_NOTES_DIR")
    if env:
        return env if os.path.isdir(env) else None
    for root in (projns.main_root(cwd), cwd):
        if root:
            d = os.path.join(paths.projects_dir(), re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(root)), "memory")
            if os.path.isdir(d):
                return d
    return None


def _title(text: str, fallback: str) -> str:
    front = text.split("---", 2)[1] if text.startswith("---") and text.count("---") >= 2 else ""
    m = _NAME.search(front)
    return (m.group(1).strip() if m else fallback)[:200]


def index_notes(conn, ns: str, d: str) -> Dict[str, int]:
    counts = {"indexed": 0, "unchanged": 0, "skipped": 0, "removed": 0}
    with memdb.tx(conn):  # one transaction for the whole run
        existing: Dict[str, Tuple[int, Any]] = {}
        for r in conn.execute("SELECT id, key, meta FROM memory WHERE ns = ? AND source = 'claude-memory'", (ns,)):
            try:
                meta = json.loads(r["meta"] or "{}")
            except ValueError:
                meta = {}
            if isinstance(meta, dict) and isinstance(meta.get("path"), str) and os.path.dirname(meta["path"]) == d:
                existing[r["key"]] = (r["id"], meta.get("mtime"))
        seen = set()
        for name in sorted(os.listdir(d)):
            if not name.endswith(".md"):
                continue
            p = os.path.join(d, name)
            seen.add(p)
            try:
                st = os.stat(p)
                if st.st_size > NOTE_MAX_BYTES:
                    counts["skipped"] += 1
                    continue
                if p in existing and existing[p][1] == st.st_mtime:
                    counts["unchanged"] += 1
                    continue
                with open(p, encoding="utf-8") as fh:
                    text = fh.read()
            except (OSError, UnicodeDecodeError):
                counts["skipped"] += 1
                continue
            title, body = redact.redact(_title(text, name[:-3])), redact.redact(text)
            meta, h = json.dumps({"mtime": st.st_mtime, "path": p}), memdb.content_hash(title, body)
            if p in existing:
                conn.execute("UPDATE memory SET title = ?, body = ?, hash = ?, meta = ? WHERE id = ?",
                             (title, body, h, meta, existing[p][0]))
            else:
                conn.execute("INSERT INTO memory (ns, kind, title, body, tags, source, key, hash, meta, created) "
                             "VALUES (?, 'note', ?, ?, '[\"claude-memory\"]', 'claude-memory', ?, ?, ?, ?)",
                             (ns, title, body, p, h, meta, st.st_mtime))
            counts["indexed"] += 1
        gone = [v[0] for k, v in existing.items() if k not in seen]
        if gone:
            conn.execute("DELETE FROM memory WHERE id IN (%s)" % ",".join("?" * len(gone)), gone)
            counts["removed"] = len(gone)
    return counts


def on_session_start(conn, event: Dict[str, Any]) -> Dict[str, int]:
    cwd = _cwd(event)
    ns = projns.project_ns(cwd)
    with memdb.tx(conn):
        conn.execute("INSERT OR IGNORE INTO sessions (id, ns, started) VALUES (?, ?, ?)",
                     (str(event.get("session_id") or "unknown"), ns, time.time()))
    d = notes_dir(cwd)
    counts = index_notes(conn, ns, d) if d else {"indexed": 0, "unchanged": 0, "skipped": 0, "removed": 0}
    if consolidate_bg.pending(conn):
        consolidate_bg.spawn(None)  # memcli takes the lock; a run already going makes this one exit at once
    return counts


def summary(conn, ns: str, sid: str) -> str:
    e = conn.execute("SELECT COUNT(*), SUM(ok = 0), COUNT(DISTINCT file) FROM edits WHERE ns = ? AND session = ?",
                     (ns, sid)).fetchone()
    since = conn.execute("SELECT started FROM sessions WHERE id = ?", (sid,)).fetchone()[0] or 0
    t = conn.execute("SELECT COUNT(*) FROM tasks WHERE ns = ? AND ended >= ?", (ns, since)).fetchone()[0]
    m = conn.execute("SELECT COUNT(*) FROM memory WHERE ns = ? AND source = 'dryas' AND created >= ?",
                     (ns, since)).fetchone()[0]
    return "%d edits (%d failed) in %d files; %d tasks closed; %d memories stored" % (e[0], e[1] or 0, e[2], t, m)


def on_session_end(conn, event: Dict[str, Any], mode: Optional[str], t0: float) -> Dict[str, Any]:
    cwd = _cwd(event)
    ns, sid, now = projns.project_ns(cwd), str(event.get("session_id") or "unknown"), time.time()
    with memdb.tx(conn):
        conn.execute("INSERT OR IGNORE INTO sessions (id, ns, started) VALUES (?, ?, ?)", (sid, ns, now))
    text = summary(conn, ns, sid)
    with memdb.tx(conn):
        if mode is None:
            conn.execute("UPDATE sessions SET summary = ?, ended = ? WHERE id = ?", (text, now, sid))
        else:
            conn.execute("UPDATE sessions SET summary = ? WHERE id = ?", (text, sid))
    root = _orch_root(cwd)
    if root:
        sweep(conn, ns, root, _task_ids(cwd))
    out: Dict[str, Any] = {"summary": text}
    if mode is None:
        reason = "budget"
        if time.monotonic() - t0 < CONSOLIDATE_BEFORE_S:
            res = memlearn.consolidate(conn, ns, deadline=t0 + CONSOLIDATE_DEADLINE_S)
            reason = res.get("skipped")
            if not reason:
                out["consolidated"] = res
        if reason:
            jevlog.append("memory", dict(stage="session-end", error="ConsolidateSkipped", detail=reason))
            consolidate_bg.mark_pending(conn, ns)
            consolidate_bg.spawn(ns)
            out["consolidate_skipped"] = reason
    return out


def run(stage: str, event: Dict[str, Any], rest: List[str], t0: float) -> Any:
    if stage not in STAGES:
        raise ValueError("unknown stage %r" % stage[:32])
    conn = memdb.connect(busy_ms=HOOK_BUSY_MS)
    try:
        if stage == "edit":
            return on_edit(conn, event)
        if stage == "task":
            return on_task(conn, event)
        if stage == "session-start":
            return on_session_start(conn, event)
        return on_session_end(conn, event, rest[0] if rest and rest[0] in ("manual", "auto") else None, t0)
    finally:
        conn.close()


def _watchdog(stage: str, seconds: float) -> threading.Timer:
    """Armed timer: on expiry log a Timeout line and exit 0, so a stuck stage never outlives its budget."""
    def fire() -> None:
        jevlog.append("memory", dict(stage=stage[:32], error="Timeout", detail=""))
        os._exit(0)
    t = threading.Timer(seconds, fire)
    t.daemon = True
    t.start()
    return t


def main(argv: Optional[List[str]] = None) -> int:
    t0 = time.monotonic()
    argv = sys.argv[1:] if argv is None else argv
    stage = argv[0] if argv else ""
    dog = _watchdog(stage, BUDGET_S)
    try:
        event = json.loads(sys.stdin.buffer.read(STDIN_MAX).decode("utf-8", "replace") or "{}")
        if not isinstance(event, dict):
            raise ValueError("hook event is not an object")
        run(stage, event, argv[1:], t0)
    except Exception as e:
        jevlog.append("memory", dict(stage=stage[:32], error=type(e).__name__, detail=str(e)[:200]))
    dog.cancel()
    return 0


if __name__ == "__main__":
    sys.exit(main())
