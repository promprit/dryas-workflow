"""Per-task numbers for /tune (owned core A2): executor tokens and time, Jev calls, judge spend and gate wait per
task; medians and p90 by start tier; tokens of failed attempts; deny and ask rate per edit; escalation rate;
review findings; task score buckets against escalations; start tiers from the score against the tier questions;
task review false skips; and the evidence proposals for review.task_skip and dispatch.scored_tier. Pure functions
over parsed log records; never raises on bad records (they are skipped).

Dispatch records: one is logged at dispatch time (no `phase`); usage may arrive in a second record with
`phase: "return"` and the same task, role and attempt. Tasks and tiers come only from records without `phase`;
tokens and duration come from the return record when it has them, else from the dispatch record (old logs)."""
import math
import os
import statistics
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pathclass
from task_score import RANK, bucket


def _n(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) and v >= 0 else None


def _tier(v: Any) -> Optional[str]:
    """The tier a model name maps to: a name containing "haiku", "sonnet", "opus" or "fable" (Claude tiers and
    Codex model names alike) is that tier. Any other name is unknown and left out of the tier stats."""
    name = v.lower() if isinstance(v, str) else ""
    return next((t for t in RANK if t in name), None)


def as_int(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    return int(v.strip()) if isinstance(v, str) and v.strip().isdigit() else None


def _ids(r: Dict[str, Any]) -> List[str]:
    one = [r["task"]] if isinstance(r.get("task"), str) else []
    many = [t for t in (r.get("tasks") if isinstance(r.get("tasks"), list) else []) if isinstance(t, str)]
    return list(dict.fromkeys(one + many))


def _dispatched(dispatch: List[Any]) -> List[Dict[str, Any]]:
    """Dispatch-time records (no `phase`) with a task id."""
    return [r for r in dispatch if isinstance(r, dict) and isinstance(r.get("task"), str) and "phase" not in r]


def tiers(dispatch: List[Any]) -> Dict[str, Dict[str, Any]]:
    """task id -> start tier, final tier and highest attempt, used by tune.delivery and rows(). Start = the first
    coder dispatch (a fast tester before a skip-up coder does not make the task fast-started; attempts are
    numbered per task, so that coder may be attempt 2), else the first attempt-1 dispatch of any role.
    Final = the highest tier dispatched."""
    out: Dict[str, Dict[str, Any]] = {}
    coder: Dict[str, Optional[str]] = {}
    for r in _dispatched(dispatch):
        t = out.setdefault(r["task"], {"start": None, "final": None, "attempt": None})
        tier, attempt = _tier(r.get("tier")), as_int(r.get("attempt"))
        if r.get("role") == "coder":
            coder.setdefault(r["task"], tier)
        if attempt == 1 and "_first" not in t:
            t["_first"] = tier
        if tier and (t["final"] is None or RANK[tier] > RANK[t["final"]]):
            t["final"] = tier
        if attempt is not None and (t["attempt"] is None or attempt > t["attempt"]):
            t["attempt"] = attempt
    for task, t in out.items():
        first = t.pop("_first", None)
        t["start"] = coder[task] if task in coder else first
    return out


def _usage(dispatch: List[Any]) -> Dict[Tuple[str, Any, Optional[int]], Dict[str, float]]:
    """(task, role, attempt) -> tokens and duration_ms; a return record's value wins over the dispatch record's."""
    out: Dict[Tuple[str, Any, Optional[int]], Dict[str, float]] = {}
    recs = [r for r in dispatch if isinstance(r, dict) and isinstance(r.get("task"), str)]
    for r in sorted(recs, key=lambda r: r.get("phase") == "return"):
        role = r.get("role") if isinstance(r.get("role"), str) else None
        got = out.setdefault((r["task"], role, as_int(r.get("attempt"))), {})
        for f in ("tokens", "duration_ms"):
            if _n(r.get(f)) is not None:
                got[f] = _n(r.get(f))
    return out


def _row() -> Dict[str, Any]:
    return dict(start_tier=None, final_tier=None, tokens=None, duration_ms=None, wasted_tokens=0.0, jev_calls=0,
                judge_spend=0.0, gate_wait_ms=0.0, escalated=False, score=None, score_tier=None, first_ts=None,
                task_type=None, lines=None)


def rows(gate: List[Any], dispatch: List[Any], esc: List[Any], mcp: List[Any]) -> Dict[str, Dict[str, Any]]:
    """task id -> row. Only dispatched tasks get a row. Wasted tokens are the tokens of an attempt followed by a
    higher attempt of the same task and role (a re-dispatch after a failure), not any repeat of a role."""
    out: Dict[str, Dict[str, Any]] = {}
    for task, t in tiers(dispatch).items():
        out[task] = dict(_row(), start_tier=t["start"], final_tier=t["final"])
    for r in _dispatched(dispatch):
        row = out[r["task"]]
        if row["score"] is None and _n(r.get("score")) is not None and _tier(r.get("score_tier")):
            row["score"], row["score_tier"] = r["score"], r["score_tier"]
        if row["task_type"] is None and isinstance(r.get("task_type"), str):
            row["task_type"] = r["task_type"]
        if isinstance(r.get("ts"), str) and (row["first_ts"] is None or r["ts"] < row["first_ts"]):
            row["first_ts"] = r["ts"]
    for r in dispatch:
        if isinstance(r, dict) and r.get("phase") == "return" and isinstance(r.get("task"), str) and r["task"] in out \
                and as_int(r.get("lines")) is not None and 0 <= as_int(r["lines"]) <= 1000000:
            out[r["task"]]["lines"] = as_int(r["lines"])
    usage = _usage(dispatch)
    top: Dict[Tuple[str, Any], int] = {}
    for task, role, attempt in usage:
        if attempt is not None:
            top[(task, role)] = max(attempt, top.get((task, role), attempt))
    for (task, role, attempt), u in usage.items():
        row = out.get(task)
        if row is None:
            continue
        for f in ("tokens", "duration_ms"):
            if f in u:
                row[f] = (row[f] or 0.0) + u[f]
        if attempt is not None and attempt < top[(task, role)]:
            row["wasted_tokens"] += u.get("tokens", 0.0)
    for r in (x for x in mcp if isinstance(x, dict) and x.get("tool") == "task_review"):
        row = out.get(r.get("task")) if isinstance(r.get("task"), str) else None
        if row is None:
            continue
        if row["score"] is None and _n(r.get("score")) is not None and _tier(r.get("score_tier")):
            row["score"], row["score_tier"] = r["score"], r["score_tier"]
        if row["task_type"] is None and isinstance(r.get("task_type"), str):
            row["task_type"] = r["task_type"]
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
    return out


def _judged_skip(r: Dict[str, Any]) -> bool:
    """A would-skip edit that a provider able to answer deny or ask on a file edit (Jev) judged, as decider or in
    shadow. Skipped edits (enforced by task_review, or local_file) had no judge and are not evidence."""
    return (r.get("task_review") == "skip" and r.get("decision") != "skipped" and isinstance(r.get("false_skip"), bool)
            and (r.get("provider") == "jev" or (r.get("shadow_provider") == "jev" and "shadow_decision" in r)))


def skip_evidence(task_rows: Dict[str, Dict[str, Any]], gate: List[Any], min_tasks: int) -> Dict[str, Any]:
    """Evidence for review.task_skip from gate records of dispatched tasks.
    false_skip_rate = false skips / judged would-skip edits, None ("no evidence") below min_tasks tasks with a
    judged would-skip edit. Once enforced (the first via task_review skip), the evidence before it is frozen
    (frozen_rate, frozen_tasks) and false_skips_since counts false skips in judged edits from then on."""
    recs = [r for r in gate if isinstance(r, dict) and any(t in task_rows for t in _ids(r))]
    judged = [r for r in recs if _judged_skip(r)]
    enforced = [r for r in gate if isinstance(r, dict) and r.get("decision") == "skipped" and r.get("via") == "task_review"]
    since = min((r["ts"] for r in enforced if isinstance(r.get("ts"), str)), default=None)

    def rate(rs: List[Dict[str, Any]]) -> Tuple[Optional[float], int]:
        tasks = len({t for r in rs for t in _ids(r) if t in task_rows})
        return (round(sum(r["false_skip"] for r in rs) / len(rs), 4) if tasks >= min_tasks else None), tasks

    all_rate, tasks = rate(judged)
    before = [r for r in judged if since is None or (isinstance(r.get("ts"), str) and r["ts"] < since)]
    frozen_rate, frozen_tasks = rate(before)
    after = [r for r in judged if since is not None and isinstance(r.get("ts"), str) and r["ts"] >= since]
    return dict(skip_min_tasks=min_tasks, skip_tasks=tasks, skip_edits=len(judged),
                false_skips=sum(r["false_skip"] for r in judged), false_skip_rate=all_rate,
                would_skip_edits=sum(1 for r in recs if r.get("task_review") == "skip" and r.get("via") != "task_review"),
                enforced_skips=len(enforced), enforced_since=since, frozen_rate=frozen_rate, frozen_tasks=frozen_tasks,
                false_skips_since=sum(r["false_skip"] for r in after))


def _med(vals: List[float]) -> Optional[float]:
    return float(statistics.median(vals)) if vals else None


def _p90(vals: List[float]) -> Optional[float]:
    return sorted(vals)[math.ceil(0.9 * len(vals)) - 1] if vals else None


def _starts(rs: List[Dict[str, Any]]) -> Dict[str, Any]:
    tok = [r["tokens"] for r in rs if r["tokens"] is not None]
    return dict(tasks=len(rs), escalation_rate=round(sum(r["escalated"] for r in rs) / len(rs), 4) if rs else None,
                tokens_median=_med(tok))


def scored_evidence(rs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Evidence for dispatch.scored_tier. A task started from the score when its start tier equals its logged
    score_tier (scored_tier on, or the tier questions picked the same tier); every other task, scored or not,
    started from the tier questions. In shadow, a scored task whose score_tier differs from its start tier would
    help if the score starts lower on a task that did not escalate or higher on one that did, and would hurt
    otherwise (lower and escalated, higher and not escalated)."""
    from_score = [r for r in rs if r["score_tier"] and r["score_tier"] == r["start_tier"]]
    scored = [r for r in rs if r["score_tier"] and r["start_tier"]]
    lower = [r for r in scored if RANK[r["score_tier"]] < RANK[r["start_tier"]]]
    higher = [r for r in scored if RANK[r["score_tier"]] > RANK[r["start_tier"]]]
    return dict(score_starts=_starts(from_score), question_starts=_starts([r for r in rs if r not in from_score]),
                scored_tasks=len(scored), shadow_lower_ok=sum(not r["escalated"] for r in lower),
                shadow_higher_ok=sum(r["escalated"] for r in higher),
                shadow_helps=sum(not r["escalated"] for r in lower) + sum(r["escalated"] for r in higher),
                shadow_hurts=sum(r["escalated"] for r in lower) + sum(not r["escalated"] for r in higher))


def summary(task_rows: Dict[str, Dict[str, Any]], gate: List[Any], review: List[Any],
            th: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
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
    lines_by_tier = {t: _med([r["lines"] for r in rs if r["start_tier"] == t and r["lines"] is not None])
                     for t in sorted({r["start_tier"] for r in rs if r["start_tier"] and r["lines"] is not None}, key=RANK.get)}
    edits = [r for r in gate if isinstance(r, dict) and r.get("tool") in pathclass.FILE_TOOLS]
    findings: Dict[str, float] = {}
    for r in (x for x in review if isinstance(x, dict) and isinstance(x.get("task"), (str, int))):
        findings[str(r["task"])] = findings.get(str(r["task"]), 0.0) + sum(
            _n(r.get(k)) or 0.0 for k in ("critical", "important", "minor"))
    buckets: Dict[str, Dict[str, int]] = {}
    for r in (x for x in rs if x["score"] is not None and x["final_tier"]):
        b = buckets.setdefault(bucket(r["score"]), {"tasks": 0, "escalated": 0})
        b["tasks"] += 1
        b["escalated"] += r["escalated"]
    return dict(
        tasks=len(rs), per_task=per, by_tier=by_tier, lines_by_tier=lines_by_tier,
        lines_median=_med([r["lines"] for r in rs if r["lines"] is not None]),
        wasted_tokens=sum(r["wasted_tokens"] for r in rs),
        edits=len(edits),
        deny_per_edit=round(sum(1 for r in edits if r.get("decision") == "deny") / len(edits), 4) if edits else None,
        ask_per_edit=round(sum(1 for r in edits if r.get("decision") == "ask") / len(edits), 4) if edits else None,
        escalation_rate=round(sum(r["escalated"] for r in rs) / len(rs), 4) if rs else None,
        review_findings_median=_med(list(findings.values())),
        score_buckets=dict(sorted(buckets.items())), **scored_evidence(rs),
        **skip_evidence(task_rows, gate, th["review"]["min_tasks"]))


def _f(v: Any, fmt: str = "%.0f") -> str:
    return "n/a" if v is None else fmt % v


def _pct(v: Any) -> str:
    return "n/a" if v is None else "%.1f%%" % (v * 100)


def _skip_line(s: Dict[str, Any]) -> str:
    tail = "enforced skips %d, would-skip edits %d" % (s["enforced_skips"], s["would_skip_edits"])
    if s["enforced_since"]:
        return "- Task review: enforced since %s; evidence frozen at %s over %d tasks; false skips in judged edits since: %d; %s" % (
            s["enforced_since"], _pct(s["frozen_rate"]), s["frozen_tasks"], s["false_skips_since"], tail)
    if s["false_skip_rate"] is None:
        return "- Task review: no evidence (%d tasks with judged would-skip edits, need %d), %s" % (
            s["skip_tasks"], s["skip_min_tasks"], tail)
    return "- Task review: false-skip rate %s (%d of %d judged would-skip edits, %d tasks), %s" % (
        _pct(s["false_skip_rate"]), s["false_skips"], s["skip_edits"], s["skip_tasks"], tail)


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
    out.append("- Lines changed per task (median): %s" % _f(s["lines_median"]))
    out.append("- Lines per task by start tier: %s" % (
        ", ".join("%s %s" % (t, _f(v)) for t, v in s["lines_by_tier"].items()) or "n/a"))
    sc, qs = s["score_starts"], s["question_starts"]
    out += ["- Tokens of failed attempts (escalation waste): %.0f" % s["wasted_tokens"],
            "- Edits: deny rate %s, ask rate %s (%d edits)" % (_pct(s["deny_per_edit"]), _pct(s["ask_per_edit"]), s["edits"]),
            "- Escalation rate per task (skip-ups excluded): %s" % _pct(s["escalation_rate"]),
            "- Review findings per reviewed branch (median): %s" % _f(s["review_findings_median"], "%.1f"),
            "- Score buckets (tasks, escalated): %s" % (
                ", ".join("%s %d/%d" % (b, v["tasks"], v["escalated"]) for b, v in s["score_buckets"].items()) or "none"),
            "- Start tier from the score: %d tasks, escalation %s, tokens median %s; from the tier questions: %d tasks, "
            "escalation %s, tokens median %s" % (sc["tasks"], _pct(sc["escalation_rate"]), _f(sc["tokens_median"]),
                                                 qs["tasks"], _pct(qs["escalation_rate"]), _f(qs["tokens_median"])),
            "- Score in shadow (%d scored tasks): would help %d, would hurt %d (ON needs helps >= 2 x hurts and helps >= 1)" % (
                s["scored_tasks"], s["shadow_helps"], s["shadow_hurts"]),
            _skip_line(s)]
    return out


def proposals(s: Dict[str, Any], th: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """review.task_skip: OFF -> ON when the false-skip rate over judged would-skip edits is at most
    max_false_skip_rate over min_tasks tasks (enforced skips are never evidence). ON -> OFF once enforced when any
    judged edit since shows a false skip; before any enforced skip, when the rate is above the maximum.
    dispatch.scored_tier: OFF -> ON over min_tasks scored tasks when the score in shadow would help at least twice
    as many tasks as it would hurt and at least one (helps >= 2 * hurts, helps >= 1; scored_evidence). ON -> OFF when, with min_tasks tasks in each group, tasks started from
    the score escalate more often than tasks started from the tier questions."""
    out: List[Dict[str, Any]] = []
    rv, dp = th["review"], th["dispatch"]
    rate, mx = s["false_skip_rate"], rv["max_false_skip_rate"]
    if not rv["task_skip"] and rate is not None and rate <= mx:
        out.append({"key": "review.task_skip", "old": False, "new": True,
                    "why": "false-skip rate %s over %d judged would-skip edits in %d tasks (max %s)"
                           % (_pct(rate), s["skip_edits"], s["skip_tasks"], _pct(mx))})
    elif rv["task_skip"] and s["enforced_since"] and s["false_skips_since"]:
        out.append({"key": "review.task_skip", "old": True, "new": False,
                    "why": "%d false skips in judged edits since enforcement began %s"
                           % (s["false_skips_since"], s["enforced_since"])})
    elif rv["task_skip"] and not s["enforced_since"] and rate is not None and rate > mx:
        out.append({"key": "review.task_skip", "old": True, "new": False,
                    "why": "false-skip rate %s over %d tasks (max %s)" % (_pct(rate), s["skip_tasks"], _pct(mx))})
    sc, qs = s["score_starts"], s["question_starts"]
    if not dp["scored_tier"] and s["scored_tasks"] >= dp["min_tasks"] and s["shadow_helps"] >= 1 \
            and s["shadow_helps"] >= 2 * s["shadow_hurts"]:
        out.append({"key": "dispatch.scored_tier", "old": False, "new": True,
                    "why": "in shadow the score would have started lower on %d tasks that did not escalate and higher "
                           "on %d that did; helps %d, hurts %d (needs helps >= 2 x hurts; %d scored tasks)"
                           % (s["shadow_lower_ok"], s["shadow_higher_ok"], s["shadow_helps"], s["shadow_hurts"],
                              s["scored_tasks"])})
    elif (dp["scored_tier"] and sc["tasks"] >= dp["min_tasks"] and qs["tasks"] >= dp["min_tasks"]
          and sc["escalation_rate"] > qs["escalation_rate"]):
        out.append({"key": "dispatch.scored_tier", "old": True, "new": False,
                    "why": "tasks started from the score escalated %s of %d; from the tier questions %s of %d"
                           % (_pct(sc["escalation_rate"]), sc["tasks"], _pct(qs["escalation_rate"]), qs["tasks"])})
    return out
