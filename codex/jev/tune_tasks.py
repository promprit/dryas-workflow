"""Per-task numbers for /tune (owned core A2): executor tokens and time, Jev calls, judge spend and gate wait per
task; medians and p90 by start tier; tokens of failed attempts; deny and ask rate per edit; escalation rate;
review findings; task score buckets against escalations; task review false skips; and the evidence proposals
for review.task_skip and dispatch.scored_tier. Pure functions over parsed log records; never raises on bad
records (they are skipped)."""
import math
import statistics
from typing import Any, Dict, List, Optional

FILE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
RANK = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 3}
BUCKETS = ((30, "0-29"), (60, "30-59"))


def _n(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) and v >= 0 else None


def _tier(v: Any) -> Optional[str]:
    return v if isinstance(v, str) and v in RANK else None


def _ids(r: Dict[str, Any]) -> List[str]:
    one = [r["task"]] if isinstance(r.get("task"), str) else []
    many = [t for t in (r.get("tasks") if isinstance(r.get("tasks"), list) else []) if isinstance(t, str)]
    return list(dict.fromkeys(one + many))


def bucket(score: float) -> str:
    return next((name for limit, name in BUCKETS if score < limit), "60-100")


def _row() -> Dict[str, Any]:
    return dict(start_tier=None, final_tier=None, tokens=None, duration_ms=None, wasted_tokens=0.0, jev_calls=0,
                judge_spend=0.0, gate_wait_ms=0.0, escalated=False, score=None, score_tier=None, first_ts=None,
                review_edits=0, would_skip=0, false_skips=0)


def rows(gate: List[Any], dispatch: List[Any], esc: List[Any], mcp: List[Any]) -> Dict[str, Dict[str, Any]]:
    """task id -> row. Only dispatched tasks get a row."""
    out: Dict[str, Dict[str, Any]] = {}
    last_role: Dict[str, Dict[Any, float]] = {}
    for r in (x for x in dispatch if isinstance(x, dict) and isinstance(x.get("task"), str)):
        row = out.setdefault(r["task"], _row())
        tier = _tier(r.get("tier"))
        if row["start_tier"] is None or (r.get("role") == "coder" and not row.get("_coder")):
            row["start_tier"] = tier or row["start_tier"]
            row["_coder"] = r.get("role") == "coder"
        if tier and (row["final_tier"] is None or RANK[tier] > RANK[row["final_tier"]]):
            row["final_tier"] = tier
        tok, dur = _n(r.get("tokens")), _n(r.get("duration_ms"))
        if tok is not None:
            row["tokens"] = (row["tokens"] or 0.0) + tok
        if dur is not None:
            row["duration_ms"] = (row["duration_ms"] or 0.0) + dur
        role = r.get("role") if isinstance(r.get("role"), str) else None
        prev = last_role.get(r["task"], {}).get(role)
        if prev is not None:  # a re-dispatch of the same role: the earlier attempt failed
            row["wasted_tokens"] += prev
        last_role.setdefault(r["task"], {})[role] = tok or 0.0
        if _n(r.get("score")) is not None and _tier(r.get("score_tier")):
            row["score"], row["score_tier"] = r["score"], r["score_tier"]
        if isinstance(r.get("ts"), str) and (row["first_ts"] is None or r["ts"] < row["first_ts"]):
            row["first_ts"] = r["ts"]
    for r in (x for x in mcp if isinstance(x, dict) and x.get("tool") == "task_review"):
        row = out.get(r.get("task")) if isinstance(r.get("task"), str) else None
        if row is not None and row["score"] is None and _n(r.get("score")) is not None and _tier(r.get("score_tier")):
            row["score"], row["score_tier"] = r["score"], r["score_tier"]
    for r in (x for x in esc if isinstance(x, dict)):
        row = out.get(r.get("task")) if isinstance(r.get("task"), str) else None
        if row is not None and not str(r.get("reason", "")).startswith("skip-up"):
            row["escalated"] = True
    for r in (x for x in gate if isinstance(x, dict)):
        for t in _ids(r):
            row = out.get(t)
            if row is None:
                continue
            row["jev_calls"] += ("latency_ms" in r) + (r.get("shadow_provider") == "jev" and "shadow_error" not in r)
            row["judge_spend"] += (_n(r.get("cost")) or 0.0) + (_n(r.get("shadow_cost")) or 0.0)
            row["gate_wait_ms"] += (_n(r.get("latency_ms")) or 0.0) + (_n(r.get("local_ms")) or 0.0)
            if r.get("task_review") in ("skip", "review", "unknown"):
                row["review_edits"] += 1
            if r.get("task_review") == "skip":
                row["would_skip"] += 1
                row["false_skips"] += r.get("false_skip") is True
    for row in out.values():
        row.pop("_coder", None)
    return out


def _med(vals: List[float]) -> Optional[float]:
    return float(statistics.median(vals)) if vals else None


def _p90(vals: List[float]) -> Optional[float]:
    return sorted(vals)[math.ceil(0.9 * len(vals)) - 1] if vals else None


def summary(task_rows: Dict[str, Dict[str, Any]], gate: List[Any], review: List[Any]) -> Dict[str, Any]:
    rs = list(task_rows.values())
    per = {k: _med([r[k] for r in rs if r[k] is not None])
           for k in ("tokens", "duration_ms", "jev_calls", "judge_spend", "gate_wait_ms")}
    by_tier = {}
    for tier in sorted({r["start_tier"] for r in rs if r["start_tier"]}, key=RANK.get):
        mine = [r for r in rs if r["start_tier"] == tier]
        tok = [r["tokens"] for r in mine if r["tokens"] is not None]
        dur = [r["duration_ms"] for r in mine if r["duration_ms"] is not None]
        by_tier[tier] = dict(tasks=len(mine), tokens_median=_med(tok), tokens_p90=_p90(tok),
                             duration_ms_median=_med(dur), duration_ms_p90=_p90(dur))
    edits = [r for r in gate if isinstance(r, dict) and r.get("tool") in FILE_TOOLS]
    findings: Dict[str, float] = {}
    for r in (x for x in review if isinstance(x, dict) and isinstance(x.get("task"), (str, int))):
        findings[str(r["task"])] = findings.get(str(r["task"]), 0.0) + sum(
            _n(r.get(k)) or 0.0 for k in ("critical", "important", "minor"))
    scored = [r for r in rs if r["score"] is not None and r["final_tier"]]
    buckets: Dict[str, Dict[str, int]] = {}
    for r in scored:
        b = buckets.setdefault(bucket(r["score"]), {"tasks": 0, "escalated": 0})
        b["tasks"] += 1
        b["escalated"] += r["escalated"]
    with_set = [r for r in rs if r["review_edits"]]
    return dict(
        tasks=len(rs), per_task=per, by_tier=by_tier,
        wasted_tokens=sum(r["wasted_tokens"] for r in rs),
        edits=len(edits),
        deny_per_edit=round(sum(1 for r in edits if r.get("decision") == "deny") / len(edits), 4) if edits else None,
        ask_per_edit=round(sum(1 for r in edits if r.get("decision") == "ask") / len(edits), 4) if edits else None,
        escalation_rate=round(sum(r["escalated"] for r in rs) / len(rs), 4) if rs else None,
        review_findings_median=_med(list(findings.values())),
        score_buckets=dict(sorted(buckets.items())), scored_tasks=len(scored),
        score_accuracy=round(sum(r["score_tier"] == r["final_tier"] for r in scored) / len(scored), 4) if scored else None,
        tier_accuracy=round(sum(r["start_tier"] == r["final_tier"] for r in scored) / len(scored), 4) if scored else None,
        review_tasks=len(with_set), would_skip_edits=sum(r["would_skip"] for r in rs),
        false_skip_tasks=sum(1 for r in with_set if r["false_skips"]),
        false_skip_rate=round(sum(1 for r in with_set if r["false_skips"]) / len(with_set), 4) if with_set else None,
        enforced_skips=sum(1 for r in gate if isinstance(r, dict) and r.get("via") == "task_review"))


def _f(v: Any, fmt: str = "%.0f") -> str:
    return "n/a" if v is None else fmt % v


def _pct(v: Any) -> str:
    return "n/a" if v is None else "%.1f%%" % (v * 100)


def lines(s: Dict[str, Any]) -> List[str]:
    p = s["per_task"]
    out = ["- Per task (median over %d tasks): executor tokens %s, executor time %s s, Jev calls %s, judge spend %s, gate wait %s ms"
           % (s["tasks"], _f(p["tokens"]), _f(None if p["duration_ms"] is None else p["duration_ms"] / 1000, "%.1f"),
              _f(p["jev_calls"], "%.1f"), _f(p["judge_spend"], "$%.4f"), _f(p["gate_wait_ms"]))]
    for tier, t in s["by_tier"].items():
        out.append("- Start tier %s (%d tasks): tokens median %s p90 %s; time median %s s p90 %s s" % (
            tier, t["tasks"], _f(t["tokens_median"]), _f(t["tokens_p90"]),
            _f(None if t["duration_ms_median"] is None else t["duration_ms_median"] / 1000, "%.1f"),
            _f(None if t["duration_ms_p90"] is None else t["duration_ms_p90"] / 1000, "%.1f")))
    out += ["- Tokens of failed attempts (escalation waste): %.0f" % s["wasted_tokens"],
            "- Edits: deny rate %s, ask rate %s (%d edits)" % (_pct(s["deny_per_edit"]), _pct(s["ask_per_edit"]), s["edits"]),
            "- Escalation rate per task (skip-ups excluded): %s" % _pct(s["escalation_rate"]),
            "- Review findings per reviewed branch (median): %s" % _f(s["review_findings_median"], "%.1f"),
            "- Score buckets (tasks, escalated): %s; start tier right: score %s, tier question %s (%d scored tasks)" % (
                ", ".join("%s %d/%d" % (b, v["tasks"], v["escalated"]) for b, v in s["score_buckets"].items()) or "none",
                _pct(s["score_accuracy"]), _pct(s["tier_accuracy"]), s["scored_tasks"]),
            "- Task review: %d tasks, %d would-skip edits, false-skip tasks %d (%s), enforced skips %d" % (
                s["review_tasks"], s["would_skip_edits"], s["false_skip_tasks"], _pct(s["false_skip_rate"]),
                s["enforced_skips"])]
    return out


def proposals(s: Dict[str, Any], th: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    rv, dp = th["review"], th["dispatch"]
    rate = s["false_skip_rate"]
    if s["review_tasks"] >= rv["min_tasks"] and rate is not None:
        ok = rate <= rv["max_false_skip_rate"]
        if ok != rv["task_skip"]:
            out.append({"key": "review.task_skip", "old": rv["task_skip"], "new": ok,
                        "why": "false-skip rate %s over %d tasks with a review set (max %s)"
                               % (_pct(rate), s["review_tasks"], _pct(rv["max_false_skip_rate"]))})
    sa, ta = s["score_accuracy"], s["tier_accuracy"]
    if s["scored_tasks"] >= dp["min_tasks"] and sa is not None and ta is not None:
        if not dp["scored_tier"] and sa > ta:
            out.append({"key": "dispatch.scored_tier", "old": False, "new": True,
                        "why": "the score picked the tier that finished %s of %d tasks; the tier questions %s"
                               % (_pct(sa), s["scored_tasks"], _pct(ta))})
        elif dp["scored_tier"] and sa < ta:
            out.append({"key": "dispatch.scored_tier", "old": True, "new": False,
                        "why": "scored start tiers were right for %s of %d tasks, below %s" % (_pct(sa), s["scored_tasks"], _pct(ta))})
    return out
