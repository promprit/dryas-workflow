#!/usr/bin/env python3
"""Scope audit at task return (unattended orchestration): did a task change only files its Scope allows?

  scope_audit.py PLAN.md N [--base SHA] [SHA...]
  prints {"ok": bool, "outside": [paths], "commits": [shas], "error": str (only on error)}; exit 0

Run by the orchestrator in the worktree for every executor report, before jev_judge. It checks
- each reported commit on its own (git diff-tree), against task N's Scope, so other executors' commits in the
  shared worktree never count; a sha that is unknown or not an ancestor of HEAD fails the audit;
- with no shas and --base: the commits since BASE whose message contains "(task N)";
- uncommitted and untracked changes against the union Scope of the tasks in .orchestrate/active.json (another
  running executor's in-scope work is not this task's fault);
- .orchestrate/ is never a valid change.
No model call. A failure is logged to scope.jsonl as a violation. A git error is a failed audit, never a crash.
"""
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jevlog
import planfile


def _git(args: List[str], cwd: str) -> str:
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, check=True, timeout=20).stdout


def _active(root: str) -> List[str]:
    try:
        with open(os.path.join(root, ".orchestrate", "active.json"), encoding="utf-8") as f:
            ids = json.load(f).get("active", [])
    except (OSError, ValueError, AttributeError):
        return []
    return [str(t) for t in ids if isinstance(t, (str, int))] if isinstance(ids, list) else []


def _bad(rel: str, globs: List[str]) -> bool:
    return rel.split("/", 1)[0].lower() == ".orchestrate" or not planfile.in_scope(rel, globs)


def _status_paths(root: str) -> List[str]:
    out, entries, i = [], _git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], root).split("\0"), 0
    while i < len(entries):
        e = entries[i]
        i += 1
        if len(e) < 4:
            continue
        out.append(e[3:])
        if e[0] in "RC":
            i += 1  # the original path of a rename or copy follows
    return out


def audit(plan: str, task: str, shas: List[str], base: Optional[str], cwd: str) -> Dict[str, Any]:
    root = _git(["rev-parse", "--show-toplevel"], cwd).strip()
    with open(plan if os.path.isabs(plan) else os.path.join(cwd, plan), encoding="utf-8") as f:
        secs = planfile.sections(f.read())
    if task not in secs:
        return {"ok": False, "outside": [], "commits": [], "error": "no Task %s in %s" % (task, plan)}
    own = planfile.scope(secs[task])
    if not shas and base:
        shas = _git(["log", "--format=%H", "--fixed-strings", "--grep=(task %s)" % task, "%s..HEAD" % base],
                    root).split()
    outside: List[str] = []
    for sha in shas:
        if subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"], cwd=root,
                          capture_output=True).returncode != 0:
            return {"ok": False, "outside": [], "commits": shas, "error": "commit %s is not on this branch" % sha}
        files = _git(["diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "--root", sha], root).split("\0")
        outside += [p for p in files if p and _bad(p, own)]
    union = own + [g for t in _active(root) for g in planfile.scope(secs.get(t, ""))]
    outside += [p for p in _status_paths(root) if _bad(p, union)]
    outside = sorted(set(outside))
    if outside:
        try:
            jevlog.append("scope", {"task": [task], "tool": "audit", "decision": "violation", "kind": "violation",
                                    "rule": "audit", "paths": outside, "run": True, "cwd": root})
        except Exception:
            pass
    return {"ok": not outside, "outside": outside, "commits": shas}


def main(argv: List[str]) -> int:
    args = argv[1:]
    base = None
    if "--base" in args:
        k = args.index("--base")
        base = args[k + 1] if k + 1 < len(args) else None
        args = args[:k] + args[k + 2:]
    if len(args) < 2 or (("--base" in argv) and not base):
        sys.stderr.write("usage: scope_audit.py PLAN.md N [--base SHA] [SHA...]\n")
        return 2
    try:
        out = audit(args[0], args[1], args[2:], base, os.getcwd())
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        out = {"ok": False, "outside": [], "commits": [], "error": "%s: %s" % (type(e).__name__, e)}
    sys.stdout.write(json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
