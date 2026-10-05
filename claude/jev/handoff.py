#!/usr/bin/env python3
"""/handoff: Jev scores the whole session item by item and saves the kept lines; /clear then starts
a fresh context seeded only with them (handoff_restore.py). Replaces lossy compaction.

Usage: handoff.py save --cwd <dir> [--transcript <path>]
Never raises on expected failures: prints one line and exits 0.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jevlog
import thresholds
import transcript_items
from handoff_paths import handoff_dir, handoff_path, key_for, project_root  # noqa: F401 (re-exported)
from jev_client import JevUnavailable, judge
from redact import redact

CHUNK = 40
FALLBACK_NEWEST = 30
CAP = 12000
SCORE_WINDOW = 200
PRUNE_SECONDS = 86400
NOTE_UNAVAILABLE = "Jev unavailable — kept newest 30"
NOTE_PARTIAL = "Jev deadline reached — newest 30 of the unscored rest kept"


def projects_dir() -> str:
    return os.environ.get("JEV_PROJECTS_DIR", os.path.expanduser("~/.claude/projects"))


def encode_cwd(cwd: str) -> str:
    """Claude Code's project folder name: every char outside [A-Za-z0-9] becomes '-'.
    Verified against ~/.claude/projects: /Users/x/.claude -> -Users-x--claude."""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def find_transcript(cwd: str) -> Optional[str]:
    """Newest *.jsonl among: encoded cwd, encoded project root, and every project dir of that root
    (worktrees and subdirs encode to root + '-...')."""
    pdir = projects_dir()
    root_enc = encode_cwd(project_root(cwd))
    dirs = [encode_cwd(cwd), encode_cwd(os.path.realpath(cwd)), root_enc]
    try:
        dirs += [n for n in os.listdir(pdir) if n.startswith(root_enc + "-")]
    except OSError:
        pass
    best, best_t = None, -1.0
    for name in dict.fromkeys(dirs):
        d = os.path.join(pdir, name)
        try:
            for n in os.listdir(d):
                f = os.path.join(d, n)
                if n.endswith(".jsonl") and os.path.isfile(f) and os.stat(f).st_mtime > best_t:
                    best, best_t = f, os.stat(f).st_mtime
        except OSError:
            continue
    return best


def questions_for(n: int) -> Dict[str, Any]:
    return {"keep_%d" % i: {
        "type": "noul",
        "instructions": ("Must the session item at `items.i%d` be kept so the next, fresh context can continue this work? "
                         "Keep decisions, constraints, user instructions, file paths, open errors and facts later steps depend on." % i),
        "criteria": {"true": "Later work in this session depends on it.",
                     "false": "Chatter, superseded output, or detail captured elsewhere."},
    } for i in range(n)}


def _keep_min() -> float:
    v = thresholds.load()["handoff"]["keep_min"]
    return v if isinstance(v, (int, float)) and 0.0 <= v <= 1.0 else thresholds.DEFAULTS["handoff"]["keep_min"]


def _kept(answer: Any, keep_min: float) -> bool:
    if not isinstance(answer, dict):
        return False
    v = answer.get("value")
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and v >= keep_min


def _line(it: Dict[str, Any]) -> str:
    text = redact(it["text"]).replace("\n", " ")
    if it["kind"] == "tool":
        return "- %s%s" % (text, " [error]" if it.get("is_error") else "")
    return "- **%s:** %s" % (it["kind"], text)


def score(scored: List[Dict[str, Any]], judge_fn, keep_min: Optional[float] = None, deadline_s: Optional[float] = None,
          clock=time.monotonic, t0: Optional[float] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return (kept items in order, stats). Raises JevUnavailable if any chunk fails. If the deadline passes
    before a chunk, scoring stops and the newest 30 of the unscored rest are kept (stats partial=True)."""
    t0 = clock() if t0 is None else t0
    partial = False
    keep_min = _keep_min() if keep_min is None else keep_min
    kept: List[Dict[str, Any]] = []
    cost, tokens, chunks = 0.0, 0, 0
    for start in range(0, len(scored), CHUNK):
        if deadline_s is not None and clock() - t0 > deadline_s:
            partial = True
            kept += scored[start:][-FALLBACK_NEWEST:]
            break
        chunk = scored[start:start + CHUNK]
        state = {"items": {"i%d" % i: {"kind": it["kind"], "text": redact(it["text"])} for i, it in enumerate(chunk)}}
        try:
            res = judge_fn(state, questions_for(len(chunk)))
        except JevUnavailable:
            raise
        except Exception as e:
            raise JevUnavailable(type(e).__name__)
        answers = res.get("answers") if isinstance(res, dict) else None
        if not isinstance(answers, dict) or any("keep_%d" % i not in answers for i in range(len(chunk))):
            raise JevUnavailable("incomplete answers")  # degraded Jev must not silently drop the session
        kept += [it for i, it in enumerate(chunk) if _kept(answers.get("keep_%d" % i), keep_min)]
        chunks += 1
        if isinstance(res.get("cost"), (int, float)):
            cost += res["cost"]
        if isinstance(res.get("input_tokens"), int):
            tokens += res["input_tokens"]
    return kept, {"chunks": chunks, "cost": cost, "input_tokens": tokens, "partial": partial}


def render(cwd: str, session: str, always: List[str], jev: List[str], total: int, note: str = "") -> str:
    always, jev = list(always), list(jev)
    root = project_root(cwd)  # once: it spawns git
    while True:
        head = "<!-- handoff cwd=%s session=%s time=%s kept=%d total=%d -->" % (
            root, session, time.strftime("%Y-%m-%dT%H:%M:%S%z"), len(always) + len(jev), total)
        parts = [head]
        if note:
            parts.append("> " + note)
        parts += ["## Always kept"] + (always or ["(none)"]) + ["## Jev kept (in order)"] + (jev or ["(none)"])
        text = "\n".join(parts) + "\n"
        if len(text) <= CAP or not (jev or always):
            return text[:CAP] if len(text) > CAP else text
        (jev or always).pop(0)  # drop oldest line first, newest survive


def write_private(path: str, text: str) -> None:
    d = os.path.dirname(path)
    os.makedirs(d, mode=0o700, exist_ok=True)
    os.chmod(d, 0o700)  # portable-ok: POSIX file privacy; no-op on Windows
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".handoff-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, 0o600)  # portable-ok: POSIX file privacy; no-op on Windows
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def build_handoff(path: str, cwd: str, judge_fn=judge, keep_min: Optional[float] = None, deadline_s: float = 20,
                  clock=time.monotonic) -> Tuple[str, Dict[str, Any]]:
    """Shared engine (handoff + auto-compaction). Returns (file text, stats); text is "" when there are no items."""
    t0 = clock()
    items = transcript_items.extract_items(path)
    if not items:
        return "", {"total": 0}
    always_lines, represented = transcript_items.always_keep_split(items)
    always_lines = [redact(l) for l in always_lines]
    scored = [it for i, it in enumerate(items) if i not in represented][-SCORE_WINDOW:]
    note, jev_ok, stats = "", True, {}
    try:
        kept, stats = score(scored, judge_fn, keep_min, deadline_s, clock, t0)
        if stats.get("partial"):
            jev_ok, note = "partial", NOTE_PARTIAL
    except JevUnavailable:
        jev_ok, note = False, NOTE_UNAVAILABLE
        kept = scored[-FALLBACK_NEWEST:]
    jev_lines = [_line(it) for it in kept]
    session = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.splitext(os.path.basename(path))[0])
    text = render(cwd, session, always_lines, jev_lines, len(items), note)
    m = re.search(r"kept=(\d+)", text.split("\n", 1)[0])
    stats = dict(stats, total=len(items), scored=len(scored), always=len(always_lines), jev_ok=jev_ok, note=note,
                 kept=int(m.group(1)) if m else len(always_lines) + len(jev_lines))
    return text, stats


def prune(d: str, max_age: float = PRUNE_SECONDS) -> None:
    try:
        now = time.time()
        for n in os.listdir(d):
            f = os.path.join(d, n)
            if n.endswith(".md") and os.path.isfile(f) and now - os.stat(f).st_mtime > max_age:
                os.unlink(f)
    except OSError:
        pass


def run(cwd: str, transcript: Optional[str] = None, judge_fn=judge, deadline_s: float = 60) -> str:
    path = transcript or find_transcript(cwd)
    if not path or not os.path.isfile(path):
        return "Handoff: No transcript found for %s." % cwd
    text, st = build_handoff(path, cwd, judge_fn, deadline_s=deadline_s)
    if not text:
        return "Handoff: nothing to save (no items in the transcript)."
    target = handoff_path(cwd)
    write_private(target, text)
    prune(os.path.dirname(target))
    jevlog.append("handoff", {"kept": st["kept"], "total": st["total"], "scored": st["scored"], "always": st["always"],
                              "jev_ok": st["jev_ok"], "chunks": st.get("chunks"), "cost": st.get("cost"),
                              "input_tokens": st.get("input_tokens")})
    note = st["note"]
    return "Handoff saved: %d/%d items (%s%s). Now run /clear." % (st["kept"], st["total"], target, "; " + note if note else "")


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="handoff.py")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("save")
    s.add_argument("--cwd", required=True)
    s.add_argument("--transcript")
    try:
        args = ap.parse_args(argv[1:])
    except SystemExit:
        print("Handoff: usage: handoff.py save --cwd <dir> [--transcript <path>]")
        return 0
    if args.cmd != "save":
        print("Handoff: usage: handoff.py save --cwd <dir> [--transcript <path>]")
        return 0
    try:
        print(run(args.cwd, args.transcript))
    except Exception as e:
        print("Handoff failed (%s); nothing saved." % type(e).__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
