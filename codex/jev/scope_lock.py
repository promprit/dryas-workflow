#!/usr/bin/env python3
"""Chain stage 0 on PreToolUse: deny Edit/Write outside the active tasks' Scope globs (this session's Claude scratchpad excepted).

Pure path check, no model call. Active only when a worktree has .orchestrate/active.json
with a non-empty "active" list. While active it fails closed (unreadable PLAN.md -> deny,
malformed hook input -> exit 2). Bash: during a run an executor's shell write is denied when a target it
names is outside the scope (scratch files in this session's Claude scratchpad excepted); other writes are allowed
and audited at task return (scope_audit.py). Nothing here asks the user.
"""
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jevlog
import planfile

TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"}
SCRATCH_BASE = ("/private/tmp/claude-%d" % os.getuid()) if hasattr(os, "getuid") else ""


def find_root(start: str) -> Optional[str]:
    d = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(d, ".orchestrate", "active.json")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def check(root: str, path: str, has_agent_id: bool = False) -> Optional[str]:
    try:
        with open(os.path.join(root, ".orchestrate", "active.json"), encoding="utf-8") as f:
            data = json.load(f)
        active_raw = data.get("active", [])
        # Validate shape: active must be a list of str/int task ids
        if not isinstance(active_raw, list):
            return "scope lock: unusable .orchestrate/active.json in %s (TypeError)" % root
        active: List[Any] = active_raw
        # Validate each element is str or int
        for item in active:
            if not isinstance(item, (str, int)):
                return "scope lock: unusable .orchestrate/active.json in %s (TypeError)" % root
        if not active:
            return None
        # Read PLAN.md from .orchestrate/PLAN.md, with fallback to root PLAN.md
        plan_path = os.path.join(root, ".orchestrate", "PLAN.md")
        plan_fallback = os.path.join(root, "PLAN.md")
        if os.path.isfile(plan_path):
            with open(plan_path, encoding="utf-8") as f:
                secs = planfile.sections(f.read())
        elif os.path.isfile(plan_fallback):
            with open(plan_fallback, encoding="utf-8") as f:
                secs = planfile.sections(f.read())
        else:
            return "scope lock: unusable .orchestrate/active.json or PLAN.md in %s (FileNotFoundError)" % root
    except Exception as e:
        return "scope lock: unusable .orchestrate/active.json or PLAN.md in %s (%s)" % (root, type(e).__name__)
    rel = os.path.relpath(path, root)
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return "scope lock: %s is outside worktree %s while tasks %s are active" % (path, root, ",".join(map(str, active)))
    # Bookkeeping: .orchestrate/ (PLAN.md, active.json with its task review set) belongs to the main session
    # (no agent_id). An executor never edits it, whatever its Scope globs say. The name is compared without case:
    # on a case-insensitive filesystem .ORCHESTRATE/active.json is the same file.
    if rel.split(os.sep, 1)[0].lower() == ".orchestrate":
        if not has_agent_id:
            return None
        return "scope lock: %s is orchestrator bookkeeping; executors never edit it" % rel.replace(os.sep, "/")
    globs = [g for t in active for g in planfile.scope(secs.get(str(t), ""))]
    if planfile.in_scope(rel, globs):
        return None
    return "scope lock: %s is outside the scope of active task(s) %s" % (rel.replace(os.sep, "/"), ",".join(map(str, active)))


def task_active(cwd: str) -> bool:
    """True when cwd (or a parent) has .orchestrate/active.json with a non-empty "active" list.
    An unreadable or malformed file counts as active (fail closed)."""
    root = find_root(cwd)
    if root is None:
        return False
    try:
        with open(os.path.join(root, ".orchestrate", "active.json"), encoding="utf-8") as f:
            return bool(json.load(f).get("active"))
    except Exception:
        return True


def _active_ids(root: str) -> List[str]:
    try:
        with open(os.path.join(root, ".orchestrate", "active.json"), encoding="utf-8") as f:
            a = json.load(f).get("active", [])
        return [str(x) for x in a] if isinstance(a, list) else []
    except Exception:
        return []


def _log_deny(root: str, path: str) -> None:
    """Record a deny for GOV-M4. Never raises, never changes the decision."""
    try:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        jevlog.append("scope", {"task": _active_ids(root), "path": rel, "decision": "deny",
                                "kind": "deny", "rule": "file", "run": True})
    except Exception:
        pass


def _in_scratchpad(real: str, event: Dict[str, Any]) -> bool:
    """True when `real` (a realpath) lies in this session's Claude Code scratchpad:
    <SCRATCH_BASE>/<one dir>/<session_id>/scratchpad/... Off Claude, without a session id or base: False."""
    sid = event.get("session_id")
    if os.environ.get("DRYAS_HARNESS", "claude") != "claude" or not SCRATCH_BASE or not isinstance(sid, str) \
            or not re.fullmatch(r"[0-9A-Za-z_-]{8,64}", sid):
        return False
    base = os.path.realpath(SCRATCH_BASE)
    if not real.startswith(base + os.sep):
        return False
    parts = os.path.relpath(real, base).split(os.sep)
    return len(parts) >= 4 and parts[1] == sid and parts[2] == "scratchpad"


def _log_bash(ids: List[str], decision: str, rule: str) -> None:
    try:
        jevlog.append("scope", {"task": ids, "tool": "Bash", "decision": decision, "kind": decision, "rule": rule,
                                "run": True})
    except Exception:
        pass


def _bash(event: Dict[str, Any], ti: Dict[str, Any], cwd: str) -> Optional[Dict[str, Any]]:
    """During a run, never ask: deny an executor's shell write when a target it names is outside the union Scope
    (and outside this session's scratchpad), or when the command names .orchestrate; allow the rest, which
    scope_audit.py checks at task return. The main session is not checked on Claude and OpenCode (it edits any
    file with Edit/Write anyway); Codex has no worker identity, so there every session is checked."""
    has_agent_id = "agent_id" in event
    if (not has_agent_id and os.environ.get("DRYAS_HARNESS") != "codex") or not task_active(cwd):
        return None
    cmd = str(ti.get("command", ""))
    root = find_root(cwd)
    real_root = os.path.realpath(root) if root else ""
    ids = _active_ids(real_root) if root else []
    import shellwrites  # only Bash needs the parser; most events are file edits
    a = shellwrites.analyse(cmd, cwd)
    if not a.writes:
        return None  # reads pass, .orchestrate/ included
    bare = re.sub(r"['\"\\]", "", cmd).lower()  # quotes and backslashes cannot hide the name
    if has_agent_id and any(k in bare for k in ("orchestr", "active.json", "approved.json")):
        _log_bash(ids, "deny", "orchestrate")
        return _deny("scope lock: executors never write .orchestrate/ (orchestrator bookkeeping)")
    for p in a.paths:
        real = os.path.realpath(p)
        if _in_scratchpad(real, event):
            continue
        reason = check(real_root, real, has_agent_id) if root else "scope lock: %s is outside any worktree" % p
        if reason:
            _log_bash(ids, "deny", a.rule)
            return _deny(reason + ". Use Edit/Write inside your Scope, put scratch files in your scratchpad, or "
                                  "report `SCOPE: need <path> because <reason>`")
    _log_bash(ids, "allow", a.rule)
    return None


def _deny(reason: str) -> Dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def run(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tool = event.get("tool_name")
    if tool not in TOOLS:
        return None
    ti = event.get("tool_input")
    if not isinstance(ti, dict):
        ti = {}
    cwd = event.get("cwd") or os.getcwd()
    if tool == "Bash":
        return _bash(event, ti, str(cwd))
    target = ti.get("file_path") or ti.get("notebook_path")
    if not target:
        if task_active(str(cwd)):  # fail closed: a file tool with no path cannot be checked against the scope
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": "scope lock: %s call has no file path" % tool}}
        return None
    path = os.path.realpath(os.path.join(cwd, str(target)))
    if _in_scratchpad(path, event):
        return None
    has_agent_id = "agent_id" in event
    roots = sorted({r for r in (find_root(cwd), find_root(os.path.dirname(path))) if r})
    for root in roots:
        try:
            reason = check(os.path.realpath(root), path, has_agent_id)
            if reason:
                _log_deny(os.path.realpath(root), path)
                return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                               "permissionDecisionReason": reason}}
        except Exception as e:
            _log_deny(os.path.realpath(root), path)
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": "scope lock: error checking %s (%s)" % (root, type(e).__name__)}}
    return None


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except Exception:
        event = None
    if not isinstance(event, dict):
        # Malformed or non-object input: fail closed while a task is active, silent otherwise.
        if task_active(os.getcwd()):
            sys.stderr.write("scope lock: malformed hook input while tasks are active\n")
            sys.exit(2)
        sys.exit(0)

    # Check if there's an active root before calling run()
    cwd = event.get("cwd") or os.getcwd()
    has_active_root = find_root(str(cwd)) is not None

    try:
        out = run(event)
        if out:
            sys.stdout.write(json.dumps(out))
    except Exception:
        # If an active root was found, emit a deny. Otherwise stay silent.
        if has_active_root:
            deny = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                          "permissionDecisionReason": "scope lock: internal error"}}
            sys.stdout.write(json.dumps(deny))
    sys.exit(0)
