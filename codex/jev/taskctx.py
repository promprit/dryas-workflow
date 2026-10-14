"""Task context for log records: the orchestrated task(s) active in a worktree, as "<branch>:<id>"
(the task id format /orchestrate uses for log_dispatch). Read-only; never raises; {} when nothing is active."""
import json
import os
from typing import Any, Dict, Optional, Tuple


def root(start: str) -> Optional[str]:
    """The worktree root holding .orchestrate/active.json above start, None outside one."""
    d = os.path.realpath(start or ".")
    while True:
        if os.path.isfile(os.path.join(d, ".orchestrate", "active.json")):
            return d
        if os.path.exists(os.path.join(d, ".git")):
            return None
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load(start: str) -> Tuple[Optional[str], Any]:
    """(root, parsed active.json): the one read per hook call. (None, None) outside a task, data None if unreadable."""
    try:
        r = root(start)
        if r is None:
            return None, None
        with open(os.path.join(r, ".orchestrate", "active.json"), encoding="utf-8") as f:
            return r, json.load(f)
    except Exception:
        return None, None


def branch(root: str) -> str:
    """The branch checked out in root, read from .git (a dir, or a worktree's "gitdir:" file). "" when unknown."""
    try:
        dot = os.path.join(root, ".git")
        if os.path.isfile(dot):
            with open(dot, encoding="utf-8") as f:
                first = f.readline().strip()
            if not first.startswith("gitdir:"):
                return ""
            gitdir = first[len("gitdir:"):].strip()
            dot = gitdir if os.path.isabs(gitdir) else os.path.join(root, gitdir)
        with open(os.path.join(dot, "HEAD"), encoding="utf-8") as f:
            head = f.readline().strip()
        prefix = "ref: refs/heads/"
        return head[len(prefix):] if head.startswith(prefix) else ""
    except Exception:
        return ""


def context(cwd: str, loaded: Optional[Tuple[Optional[str], Any]] = None) -> Dict[str, Any]:
    """loaded: taskctx.load(cwd) when the caller already has it."""
    try:
        r, data = loaded if loaded is not None else load(cwd)
        if r is None:
            return {}
        active = data.get("active", []) if isinstance(data, dict) else []
        ids = [str(a) for a in active if isinstance(a, (str, int))] if isinstance(active, list) else []
        if not ids:
            return {}
        b = branch(r) or "?"
        tasks = ["%s:%s" % (b, i) for i in ids]
        return {"task": tasks[0]} if len(tasks) == 1 else {"tasks": tasks[:16]}
    except Exception:
        return {}
