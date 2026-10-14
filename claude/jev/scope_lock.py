#!/usr/bin/env python3
"""Chain stage 0 on PreToolUse: deny Edit/Write outside the active tasks' Scope globs.

Pure path check, no model call. Active only when a worktree has .orchestrate/active.json
with a non-empty "active" list. While active it fails closed (unreadable PLAN.md -> deny,
malformed hook input -> exit 2). Bash is never denied: a write-like command gets "ask",
because shell writes are not covered by the file scope.
"""
import json
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jevlog
import planfile

TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"}


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
        jevlog.append("scope", {"task": _active_ids(root), "path": rel, "decision": "deny"})
    except Exception:
        pass


def _shell_writes(cmd: str) -> bool:
    """prescreen is imported here, not at module load: only Bash needs its regexes, and most events are file edits.
    A broken or missing prescreen counts every command as a write while a task is active."""
    try:
        import prescreen
        return prescreen.writes(cmd)
    except Exception:
        return True


def _bash(ti: Dict[str, Any], cwd: str, has_agent_id: bool = False) -> Optional[Dict[str, Any]]:
    """Ask for a write-like shell command while a task is active; deny it when an executor's command names
    .orchestrate (the orchestrator's bookkeeping, see check)."""
    if not task_active(cwd):
        return None
    cmd = str(ti.get("command", ""))
    if not _shell_writes(cmd):
        return None
    root = find_root(cwd)
    ids = _active_ids(os.path.realpath(root)) if root else []
    # Literal matching is the deny line: a command that spells .orchestrate (in any letter case) is denied. Forms
    # that hide the name (quotes, variables) are not parsed; they fall through to the ask below, never to an allow.
    if has_agent_id and ".orchestrate" in cmd.lower():
        try:
            jevlog.append("scope", {"task": ids, "tool": "Bash", "decision": "deny"})
        except Exception:
            pass
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": "scope lock: executors never write .orchestrate/ "
                                                                   "(orchestrator bookkeeping)"}}
    try:
        jevlog.append("scope", {"task": ids, "tool": "Bash", "decision": "ask"})
    except Exception:
        pass
    reason = ("scope lock: shell command looks like it writes files; shell writes are not covered by the file scope "
              "of active task(s) %s - confirm it stays in scope" % ",".join(ids))
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
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
        return _bash(ti, str(cwd), "agent_id" in event)
    target = ti.get("file_path") or ti.get("notebook_path")
    if not target:
        if task_active(str(cwd)):  # fail closed: a file tool with no path cannot be checked against the scope
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": "scope lock: %s call has no file path" % tool}}
        return None
    path = os.path.realpath(os.path.join(cwd, str(target)))
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
