#!/usr/bin/env python3
"""Task review set (owned core A2): which files of a plan task need per-edit judgement, and the verdict the gate
logs next to its own (shadow) or, with review.task_skip on, acts on.

The orchestrator writes the set into .orchestrate/active.json (the scope lock denies executors .orchestrate/):
  {"active": ["3"], "review_version": 1,
   "review": {"3": {"skip": ["src/a.py"], "review": ["src/**"], "tier": "sonnet", "score": 42}}}
An edit would be skipped only when it touches no always-judged path, its new text has no content signal, every
active task has a well-formed entry, some entry's skip list names the file and no entry's review list matches it.
Missing, unreadable, malformed or other-version data means the edit is judged (fail safe). Never raises.
Path classes come from pathclass.py (shared with the gate). CONTENT_SIGNALS is a best-effort list of lowercase
substrings of the new text (process spawn, dynamic import and native calls, eval, deletes, env reads, network,
install hooks); WORD_SIGNALS match only at a word start (socket: not websocket) or as a whole word (pty: not
empty). A missed signal never skips an always-judged file.

CLI: task_review.py answer PLAN.md N   (prints the entry to write; see task_score.answer)"""
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pathclass
import planfile
import taskctx

REVIEW_VERSION = 1
FILE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
CONTENT_SIGNALS = ("subprocess", "os.system", "os.popen", "os.exec", "os.spawn", "child_process", "execsync",
                   "__import__", "importlib", "ctypes", "eval(", "exec(", "deno.run", "bun.spawn", "shutil.rmtree",
                   "os.remove", "unlink(", "rmsync", "fs.rm(", "rm -", "os.environ", "getenv", "process.env",
                   "requests.", "urllib", "http.client", "fetch(", "curl ", "wget ", "sudo ", "chmod ",
                   "postinstall", "preinstall")
WORD_SIGNALS = (("socket", re.compile(r"(?<![a-z0-9_])socket")), ("pty", re.compile(r"\bpty\b")))
MAX_TEXT = 1 << 20
_WILD = frozenset("*?[")
always_judged = pathclass.always_judged  # dot paths, CI files, keys, secrets, SENSITIVE_* build files, outside


def path_class(rel: str) -> str:
    """"always" (always judged) or "plain"."""
    return "always" if always_judged(rel) else "plain"


def content_signal(text: str) -> Optional[str]:
    low = str(text)[:MAX_TEXT].lower()
    hit = next((s for s in CONTENT_SIGNALS if s in low), None)
    return hit or next((name for name, rx in WORD_SIGNALS if rx.search(low)), None)


def edit_text(tool: str, ti: Dict[str, Any]) -> str:
    if tool == "Write":
        return str(ti.get("content", ""))
    if tool == "NotebookEdit":
        return str(ti.get("new_source", ""))
    if tool == "MultiEdit":
        edits = ti.get("edits") if isinstance(ti.get("edits"), list) else []
        return "\n".join(str(e.get("new_string", "")) for e in edits if isinstance(e, dict))
    return str(ti.get("new_string", ""))


def targets(tool: str, ti: Dict[str, Any]) -> List[str]:
    """Every path an edit touches (a combined Codex apply_patch event lists them in "paths"); [] if one is unusable."""
    first = ti.get("notebook_path" if tool == "NotebookEdit" else "file_path")
    extra = ti.get("paths") if isinstance(ti.get("paths"), list) else []
    out = [first] + extra
    return out if all(isinstance(t, str) and t for t in out) else []


def review_set(globs: List[str]) -> Dict[str, List[str]]:
    """Local answer: a scope entry that names one file (no wildcard) and is not always judged may skip per-edit
    judgement; every other entry (wildcards, always-judged paths) stays reviewed."""
    out: Dict[str, List[str]] = {"skip": [], "review": []}
    for g in globs:
        g = g[2:] if g.startswith("./") else g
        literal = not (set(g) & _WILD)
        out["skip" if literal and path_class(g) != "always" else "review"].append(g)
    return out


def review_sets(data: Any) -> Optional[Dict[str, Dict[str, List[str]]]]:
    """The review set of every active task in parsed active.json, or None when any part is missing or malformed."""
    if not isinstance(data, dict) or data.get("review_version") != REVIEW_VERSION:
        return None
    active, review = data.get("active"), data.get("review")
    if not isinstance(active, list) or not active or not isinstance(review, dict):
        return None
    out: Dict[str, Dict[str, List[str]]] = {}
    for a in active:
        e = review.get(str(a))
        if not isinstance(e, dict) or not isinstance(e.get("skip"), list) or not isinstance(e.get("review"), list):
            return None
        if not all(isinstance(x, str) for x in e["skip"] + e["review"]):
            return None
        out[str(a)] = {"skip": e["skip"], "review": e["review"]}
    return out


def edit_verdict(cwd: str, tool: str, ti: Dict[str, Any],
                 loaded: Optional[Tuple[Optional[str], Any]] = None) -> Optional[Tuple[str, str]]:
    """(verdict, why) for a file edit inside an orchestrated task, None outside one. verdict: "skip" (the task
    verdict would skip per-edit judgement), "review" or "unknown" (no usable review set: judged).
    Paths are taken relative to the worktree root. loaded: taskctx.load(cwd) when the caller already read it."""
    try:
        if tool not in FILE_TOOLS:
            return None
        loaded = loaded if loaded is not None else taskctx.load(cwd)
        root = loaded[0]
        if root is None or not taskctx.context(cwd, loaded):
            return None
        paths = targets(tool, ti)
        if not paths:
            return ("review", "no_path")
        base = os.path.realpath(cwd or ".")
        rels = [os.path.relpath(os.path.realpath(os.path.join(base, t)), root).replace(os.sep, "/") for t in paths]
        if any(always_judged(r) for r in rels):
            return ("review", "always")
        sig = content_signal(edit_text(tool, ti))
        if sig:
            return ("review", "content:" + sig)
        sets = review_sets(loaded[1])
        if sets is None:
            return ("unknown", "no_review_set")
        for r in rels:
            if any(planfile.in_scope(r, e["review"]) for e in sets.values()):
                return ("review", "review_glob")
            if not any(planfile.in_scope(r, e["skip"]) for e in sets.values()):
                return ("review", "not_in_skip")
        return ("skip", "task_review")
    except Exception as e:
        return ("unknown", "error:" + type(e).__name__)


def _plan_root(plan: str) -> str:
    d = os.path.dirname(os.path.abspath(plan))
    return os.path.dirname(d) if os.path.basename(d) == ".orchestrate" else d


def main(argv: List[str]) -> int:
    """answer PLAN.md N: print the task_review answer for task N and log it (mcp.jsonl, tool task_review).
    The orchestrator copies "entry" into active.json and "log_dispatch" into its log_dispatch call."""
    if len(argv) != 4 or argv[1] != "answer":
        sys.stderr.write("usage: task_review.py answer PLAN.md N\n")
        return 2
    import time
    import jevlog
    import task_score
    import thresholds
    try:
        with open(argv[2], encoding="utf-8") as f:
            sec = planfile.sections(f.read()).get(argv[3])
    except OSError as e:
        sys.stderr.write("cannot read %s (%s)\n" % (argv[2], type(e).__name__))
        return 1
    if sec is None:
        sys.stderr.write("no Task %s in %s\n" % (argv[3], argv[2]))
        return 1
    root = _plan_root(argv[2])
    task_id = "%s:%s" % (taskctx.branch(root) or "?", argv[3])
    t0 = time.monotonic()
    ans = task_score.answer(root, sec, task_id, thresholds.load())
    wall_ms = round((time.monotonic() - t0) * 1000, 2)
    jevlog.append("mcp", dict(tool="task_review", question="task_review", provider="local", task=task_id,
                              answer=dict(skip=len(ans["skip"]), review=len(ans["review"]), tier=ans["tier"]),
                              confidence=1.0, shadow_provider="none", score=ans["score"], score_tier=ans["tier"],
                              task_type=ans["task_type"], wall_ms=wall_ms,
                              reasons=["%s:%d" % (k, v) for k, v in sorted(ans["parts"].items())]))
    entry = {"skip": ans["skip"], "review": ans["review"], "tier": ans["tier"], "score": ans["score"]}
    print(json.dumps({"task": task_id, "review_version": REVIEW_VERSION, "entry": entry,
                      "log_dispatch": {"score": ans["score"], "score_tier": ans["tier"], "task_type": ans["task_type"]}}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
