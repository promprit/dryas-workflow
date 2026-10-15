"""The spec's "Done when" check for task-level judgement (owned core A2), computed by /tune: a baseline window of
tasks against the current window, per task (medians), with PASS or FAIL per line.
  Jev calls per task      current <= half of baseline
  Gate wait per task      current < baseline (both 0 passes)
  Executor tokens / task  current <= baseline
  Escalation rate         current <= baseline
  Review findings per reviewed branch  current <= baseline (severity basis: critical + important; every review
                          round of a branch is summed, then the median over branches; records split by their ts at
                          the same boundary as the tasks; n/a with fewer than REVIEW_MIN reviewed branches in a window)
  No enforced false skip on an always-judged file  (always printed) PASS unless a gate record shows a
                          task_review skip of a path pathclass.always_judged says is always judged; n/a without
                          gate records, or when skips were enforced but no record names the path
Windows: tasks first dispatched before thresholds baseline.until (YYYY-MM-DD) against the rest, or, when it is "",
the earlier half of the logged tasks against the later half (ordered by first dispatch time). A window with fewer
than WINDOW_MIN tasks gives n/a. Each window states its task-type mix (a shift in mix moves the medians).
baseline.until is validated by thresholds (a real YYYY-MM-DD date); this module trusts it."""
import math
import statistics
from collections import Counter
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pathclass

WINDOW_MIN = 10
REVIEW_MIN = 3
Rows = Dict[str, Dict[str, Any]]


def _until(until: Any) -> str:
    """The baseline.until date thresholds validated, or "" (earlier half) when it is not a string."""
    return until if isinstance(until, str) else ""


def windows(task_rows: Rows, until: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
    """(baseline rows, current rows, the until date used or "")."""
    until = _until(until)
    timed = sorted((r for r in task_rows.values() if isinstance(r.get("first_ts"), str)), key=lambda r: r["first_ts"])
    if until:
        return [r for r in timed if r["first_ts"] < until], [r for r in timed if r["first_ts"] >= until], until
    half = len(timed) // 2
    return timed[:half], timed[half:], until


def _types(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    mix = Counter(r["task_type"] if isinstance(r.get("task_type"), str) else "unknown" for r in rows)
    return dict(sorted(mix.items()))


def _median(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return float(statistics.median(vals)) if vals else None


def _rate(rows: List[Dict[str, Any]]) -> Optional[float]:
    return sum(1 for r in rows if r.get("escalated")) / len(rows) if rows else None


CHECKS = (
    ("Jev calls per task", "jev_calls", "at most half", lambda b, c: c <= b / 2),
    ("Gate wait per task (ms)", "gate_wait_ms", "lower", lambda b, c: c < b or b == c == 0),
    ("Executor tokens per task", "tokens", "no higher", lambda b, c: c <= b),
    ("Escalation rate", None, "no higher", lambda b, c: c <= b),
)


def _count(v: Any) -> float:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) \
        and math.isfinite(v) and v >= 0 else 0.0


def _findings(review: List[Any], keep) -> Optional[float]:
    """Median over branches of critical + important (all rounds summed), from the review records whose ts passes
    keep; None below REVIEW_MIN branches."""
    per: Dict[str, float] = {}
    for r in review:
        if isinstance(r, dict) and isinstance(r.get("task"), (str, int)) and not isinstance(r.get("task"), bool) \
                and isinstance(r.get("ts"), str) and keep(r["ts"]):
            per[str(r["task"])] = per.get(str(r["task"]), 0.0) + _count(r.get("critical")) + _count(r.get("important"))
    return float(statistics.median(per.values())) if len(per) >= REVIEW_MIN else None


def _false_skip(gate: List[Any]) -> str:
    recs = [r for r in gate if isinstance(r, dict)]
    if not recs:
        return "n/a"
    enforced = [r for r in recs if r.get("decision") == "skipped" and r.get("via") == "task_review"]
    paths = [p for r in enforced for k in ("path", "file_path", "rel")
             for p in (r.get(k) if isinstance(r.get(k), list) else [r.get(k)])
             if isinstance(p, str)]
    if enforced and not paths:
        return "n/a"
    # outside the worktree is always judged
    return "FAIL" if any(p == "<outside>" or p.startswith("../") or pathclass.always_judged(p) for p in paths) else "PASS"


def check(task_rows: Rows, until: Any, review: Optional[List[Any]] = None,
          gate: Optional[List[Any]] = None) -> Dict[str, Any]:
    base, cur, until = windows(task_rows, until)
    out = {"basis": ("before %s" % until) if until else "earlier half", "base_tasks": len(base),
           "current_tasks": len(cur), "base_types": _types(base), "current_types": _types(cur), "lines": []}
    enough = len(base) >= WINDOW_MIN and len(cur) >= WINDOW_MIN
    for name, key, target, ok in CHECKS:
        b = _median(base, key) if key else _rate(base)
        c = _median(cur, key) if key else _rate(cur)
        verdict = "n/a" if not enough or b is None or c is None else ("PASS" if ok(b, c) else "FAIL")
        out["lines"].append({"name": name, "base": b, "current": c, "target": target, "verdict": verdict})
    cut = until or (cur[0]["first_ts"] if cur else None)
    b = _findings(review or [], lambda ts: cut is not None and ts < cut)
    c = _findings(review or [], lambda ts: cut is not None and ts >= cut)
    verdict = "n/a" if not enough or b is None or c is None else ("PASS" if c <= b else "FAIL")
    out["lines"].append({"name": "Review findings per reviewed branch", "base": b, "current": c, "target": "no higher",
                         "verdict": verdict})
    out["false_skip"] = _false_skip(gate or [])
    return out


def _v(x: Optional[float]) -> str:
    return "n/a" if x is None else ("%.2f" % x).rstrip("0").rstrip(".")


def lines(res: Dict[str, Any]) -> List[str]:
    mix = lambda m: ", ".join("%s %d" % kv for kv in m.items()) or "none"
    out = ["- Done-when check (baseline %s: %d tasks [%s]; current: %d tasks [%s]; n/a below %d each)" % (
        res["basis"], res["base_tasks"], mix(res["base_types"]), res["current_tasks"], mix(res["current_types"]),
        WINDOW_MIN)]
    out += ["- Done-when %s: baseline %s, current %s (target: %s): %s" % (
        l["name"], _v(l["base"]), _v(l["current"]), l["target"], l["verdict"]) for l in res["lines"]]
    out.append("- Done-when No enforced false skip on an always-judged file: %s" % res.get("false_skip", "n/a"))
    return out
