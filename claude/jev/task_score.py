"""Task score (owned core A2): a deterministic estimate of how hard a plan task is and the start tier it would pick.
Shadow by default: the orchestrator writes it into the dispatch record and dispatches as before, unless
dispatch.scored_tier is on. Points (0-100):
  size     3 per file in scope (max 10 files) + 1 per 100 lines in those files (max 20)
  risk     20 if a scope entry is always judged (dot paths, CI, keys, secrets, build files, scripts)
  tests    15 when no Done line runs a test
  history  30 x the escalation rate of this task type, only once history.min_tasks scored tasks of the type exist
Tier: under 30 haiku, under 60 sonnet, else opus. Stdlib only; reads files in scope, never raises from answer()."""
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jevlog
import planfile
import task_review

MAX_FILES = 5000
MAX_BYTES = 2 << 20
SKIP_DIRS = frozenset((".git", ".orchestrate", "node_modules", "__pycache__", ".venv", "venv", ".tox",
                       ".mypy_cache", ".pytest_cache"))
TEST_WORDS = ("pytest", "unittest", "jest", "vitest", "mocha", "go test", "cargo test", "swift test", "npm test",
              "pnpm test", "yarn test", "rspec", "phpunit", "ctest", "make test", "tox", "nox")
TIERS = ((30, "haiku"), (60, "sonnet"))
BUCKETS = ((30, "0-29"), (60, "30-59"))
RANK = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 3}


def done_lines(section: str) -> List[str]:
    out: List[str] = []
    inside = False
    for line in section.splitlines():
        if line.startswith("Done:"):
            inside = True
            continue
        if inside:
            s = line.strip()
            if s.startswith("- "):
                out.append(s[2:])
            elif s:
                break
    return out


def runs_test(section: str) -> bool:
    return any(w in line.lower() for line in done_lines(section) for w in TEST_WORDS)


def task_type(globs: List[str]) -> str:
    kinds = set()
    for g in globs:
        low = g.lower()
        if low.endswith((".md", ".rst", ".txt")) or low.startswith("docs/"):
            kinds.add("docs")
        elif "test" in low:
            kinds.add("tests")
        else:
            kinds.add("code")
    return "+".join(sorted(kinds)) or "none"


def _lines(path: str) -> int:
    try:
        with open(path, "rb") as f:
            return f.read(MAX_BYTES).count(b"\n")
    except OSError:
        return 0


def scope_size(root: str, globs: List[str]) -> Tuple[int, int]:
    """(files, lines) in scope. A wildcard-free entry that does not exist yet counts as one empty file."""
    files = lines = seen = 0
    found = set()
    for d, dirs, names in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        for name in sorted(names):
            seen += 1
            if seen > MAX_FILES:
                break
            rel = os.path.relpath(os.path.join(d, name), root).replace(os.sep, "/")
            if planfile.in_scope(rel, globs):
                files += 1
                lines += _lines(os.path.join(d, name))
                found.add(rel)
        if seen > MAX_FILES:
            break
    new = {g[2:] if g.startswith("./") else g for g in globs if not set(g) & set("*?[")}
    return files + len(new - found), lines


def history(ttype: str, min_tasks: int, log_dir: Optional[str] = None) -> Optional[float]:
    """Escalation rate of scored tasks of this type (skip-ups are start tiers, not escalations), or None below
    min_tasks tasks."""
    types: Dict[str, str] = {}
    escalated = set()
    d = log_dir or jevlog.log_dir()
    for name in ("mcp", "escalations"):
        try:
            with open(os.path.join(d, name + ".jsonl"), encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(r, dict) or not isinstance(r.get("task"), str):
                        continue
                    if name == "mcp" and r.get("tool") == "task_review" and isinstance(r.get("task_type"), str):
                        types[r["task"]] = r["task_type"]
                    elif name == "escalations" and not str(r.get("reason", "")).startswith("skip-up"):
                        escalated.add(r["task"])
        except OSError:
            continue
    mine = [t for t, k in types.items() if k == ttype]
    if len(mine) < min_tasks:
        return None
    return sum(1 for t in mine if t in escalated) / len(mine)


def tier(score: int) -> str:
    return next((name for limit, name in TIERS if score < limit), "opus")


def bucket(score: int) -> str:
    return next((name for limit, name in BUCKETS if score < limit), "60-100")


def score(files: int, lines: int, classes: List[str], has_test: bool, hist: Optional[float]) -> Dict[str, int]:
    parts = {"size": min(files, 10) * 3 + min(lines // 100, 20),
             "risk": 20 if "always" in classes else 0,
             "tests": 0 if has_test else 15,
             "history": round(hist * 30) if hist is not None else 0}
    parts["total"] = min(100, sum(parts.values()))
    return parts


def answer(root: str, section: str, task_id: str, th: Dict[str, Any], log_dir: Optional[str] = None) -> Dict[str, Any]:
    """The task_review answer for one plan section: review set, score, tier and task type."""
    globs = planfile.scope(section)
    ttype = task_type(globs)
    files, lines = scope_size(root, globs)
    hist = history(ttype, th["history"]["min_tasks"], log_dir)
    parts = score(files, lines, [task_review.path_class(g) for g in globs], runs_test(section), hist)
    rs = task_review.review_set(globs)
    return {"task": task_id, "skip": rs["skip"], "review": rs["review"], "score": parts["total"],
            "tier": tier(parts["total"]), "task_type": ttype, "parts": parts, "files": files, "lines": lines,
            "history": hist}
