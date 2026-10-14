"""The spec's "Done when" check for task-level judgement (owned core A2), computed by /tune: a baseline window of
tasks against the current window, per task (medians), with PASS or FAIL per line.
  Jev calls per task      current <= half of baseline
  Gate wait per task      current < baseline (both 0 passes)
  Executor tokens / task  current <= baseline
  Escalation rate         current <= baseline
Windows: tasks first dispatched before thresholds baseline.until (YYYY-MM-DD) against the rest, or, when it is "",
the earlier half of the logged tasks against the later half (ordered by first dispatch time). A window with fewer
than WINDOW_MIN tasks gives n/a."""
import datetime
import statistics
from typing import Any, Dict, List, Optional, Tuple

WINDOW_MIN = 10
Rows = Dict[str, Dict[str, Any]]


def _until(until: Any) -> str:
    """The baseline.until date, or "" (earlier half) when it is not a real YYYY-MM-DD string."""
    try:
        return until if isinstance(until, str) and datetime.datetime.strptime(until, "%Y-%m-%d") and len(until) == 10 else ""
    except ValueError:
        return ""


def windows(task_rows: Rows, until: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    until = _until(until)
    timed = sorted((r for r in task_rows.values() if isinstance(r.get("first_ts"), str)), key=lambda r: r["first_ts"])
    if until:
        return [r for r in timed if r["first_ts"] < until], [r for r in timed if r["first_ts"] >= until]
    half = len(timed) // 2
    return timed[:half], timed[half:]


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


def check(task_rows: Rows, until: str) -> Dict[str, Any]:
    until = _until(until)
    base, cur = windows(task_rows, until)
    out = {"basis": ("before %s" % until) if until else "earlier half", "base_tasks": len(base),
           "current_tasks": len(cur), "lines": []}
    enough = len(base) >= WINDOW_MIN and len(cur) >= WINDOW_MIN
    for name, key, target, ok in CHECKS:
        b = _median(base, key) if key else _rate(base)
        c = _median(cur, key) if key else _rate(cur)
        verdict = "n/a" if not enough or b is None or c is None else ("PASS" if ok(b, c) else "FAIL")
        out["lines"].append({"name": name, "base": b, "current": c, "target": target, "verdict": verdict})
    return out


def _v(x: Optional[float]) -> str:
    return "n/a" if x is None else ("%.2f" % x).rstrip("0").rstrip(".")


def lines(res: Dict[str, Any]) -> List[str]:
    out = ["- Done-when check (baseline %s: %d tasks; current: %d tasks; n/a below %d each)" % (
        res["basis"], res["base_tasks"], res["current_tasks"], WINDOW_MIN)]
    out += ["- Done-when %s: baseline %s, current %s (target: %s): %s" % (
        l["name"], _v(l["base"]), _v(l["current"]), l["target"], l["verdict"]) for l in res["lines"]]
    return out
