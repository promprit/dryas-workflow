#!/usr/bin/env python3
"""Scope audit at task return (unattended orchestration): did a task change only files its Scope allows?

  scope_audit.py PLAN.md N [--base SHA] [--approved-sha HEX] [SHA...]
  prints {"ok": bool, "outside": [paths], "commits": [shas], "approved_sha": hex, "error": str (only on error)};
  exit 0

Run by the orchestrator in the worktree for every executor report, before jev_judge. It checks
- each reported commit on its own (git diff-tree), against task N's Scope, so other executors' commits in the
  shared worktree never count; a sha that is unknown or not an ancestor of HEAD fails the audit;
- with no shas and --base: the commits since BASE whose message contains "(task N)";
- with --base: every commit in BASE..HEAD, labelled or not, against the union Scope (this task's plus the tasks
  in .orchestrate/active.json);
- uncommitted and untracked changes against that union Scope (another running executor's in-scope work is not
  this task's fault);
- git-ignored .env* files anywhere and .orchestrate/ content other than PLAN.md, active.json and approved.json,
  against that union Scope (other ignored paths, such as caches and build output, are not counted);
- with --approved-sha: the sha256 of .orchestrate/approved.json (of "" when missing) must equal HEX, else it
  changed outside the orchestrator. "approved_sha" is always the current value, for the orchestrator to record;
- .orchestrate/ is never a valid change.
No model call. A failure is logged to scope.jsonl as a violation. A git error is a failed audit, never a crash.
Known limit (GOV-2, same as Dryas 1.0): a script or interpreter file (`python x.py`, `make`, `node x.js`) can
write anywhere; such writes inside the worktree show up here, writes outside it are not seen.
"""
import hashlib
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jevlog
import planfile

APPROVED = ".orchestrate/approved.json"
_OWN = {".orchestrate/PLAN.md", ".orchestrate/active.json", APPROVED}  # the orchestrator's own files

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


def _status_paths(root: str, *extra: str) -> List[str]:
    out, i = [], 0
    entries = _git(["status", "--porcelain=v1", "-z", "--untracked-files=all", *extra], root).split("\0")
    while i < len(entries):
        e = entries[i]
        i += 1
        if len(e) < 4:
            continue
        out.append(e[3:])
        if e[0] in "RC":
            i += 1  # the original path of a rename or copy follows
    return out


def _sensitive(rel: str) -> bool:
    """An ignored path the audit still counts: .orchestrate/ content other than the orchestrator's own files, or
    a .env* file anywhere. Other ignored paths (caches, build output) are not counted."""
    parts = rel.split("/")
    if parts[0].lower() == ".orchestrate":
        return rel not in _OWN
    return parts[-1].startswith(".env")


def _ignored_paths(root: str) -> List[str]:
    out = []
    for p in _status_paths(root, "--ignored=matching"):
        if not p.endswith("/"):
            out.append(p)
            continue
        for d, _, files in os.walk(os.path.join(root, p)):  # a whole ignored directory is listed once
            out += [os.path.relpath(os.path.join(d, f), root).replace(os.sep, "/") for f in files]
    return [p for p in out if _sensitive(p)]


def _sha256(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        return hashlib.sha256(b"").hexdigest()


def _files(sha: str, root: str) -> List[str]:
    return [p for p in _git(["diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "--root", sha],
                            root).split("\0") if p]


def audit(plan: str, task: str, shas: List[str], base: Optional[str], cwd: str,
          approved: Optional[str] = None) -> Dict[str, Any]:
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
        outside += [p for p in _files(sha, root) if _bad(p, own)]
    union = own + [g for t in _active(root) for g in planfile.scope(secs.get(t, ""))]
    if base:  # every commit since the base, labelled or not, against the union Scope
        for sha in _git(["log", "--format=%H", "%s..HEAD" % base], root).split():
            outside += [p for p in _files(sha, root) if _bad(p, union)]
    outside += [p for p in _status_paths(root) if _bad(p, union)]
    outside += [p for p in _ignored_paths(root) if not planfile.in_scope(p, union)]
    out: Dict[str, Any] = {}
    if approved is not None and _sha256(os.path.join(root, APPROVED)) != approved:
        outside.append(APPROVED)
        out["error"] = "%s changed outside the orchestrator" % APPROVED
    outside = sorted(set(outside))
    if outside:
        try:
            jevlog.append("scope", {"task": [task], "tool": "audit", "decision": "violation", "kind": "violation",
                                    "rule": "audit", "paths": outside, "run": True, "cwd": root})
        except Exception:
            pass
    return dict({"ok": not outside, "outside": outside, "commits": shas}, **out)


def main(argv: List[str]) -> int:
    args, opts = argv[1:], {}
    for name in ("--base", "--approved-sha"):
        if name in args:
            k = args.index(name)
            opts[name] = args[k + 1] if k + 1 < len(args) else None
            args = args[:k] + args[k + 2:]
    if len(args) < 2 or None in opts.values():
        sys.stderr.write("usage: scope_audit.py PLAN.md N [--base SHA] [--approved-sha HEX] [SHA...]\n")
        return 2
    try:
        out = audit(args[0], args[1], args[2:], opts.get("--base"), os.getcwd(), opts.get("--approved-sha"))
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        out = {"ok": False, "outside": [], "commits": [], "error": "%s: %s" % (type(e).__name__, e)}
    try:
        root = _git(["rev-parse", "--show-toplevel"], os.getcwd()).strip()
    except (OSError, subprocess.SubprocessError):
        root = os.getcwd()
    out["approved_sha"] = _sha256(os.path.join(root, APPROVED))
    sys.stdout.write(json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
