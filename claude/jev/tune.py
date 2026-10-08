#!/usr/bin/env python3
"""Calibration report over Jev logs; proposes threshold changes. Applies a change only via `apply`.

CLI: tune.py report | tune.py apply KEY JSON_VALUE | tune.py record-compare TASK SWARM_TOK PLAIN_TOK SWARM_S PLAIN_S
"""
import json
import math
import os
import re
import statistics
import sys
from collections import Counter
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jevlog
import thresholds

PRICE_PER_TOKEN = 0.042 / 1000000

# Dangerous heads never proposed in allowlist
DANGEROUS_HEADS = {
    "sh", "bash", "zsh", "fish", "dash",
    "python", "python3", "node", "npx", "npm", "pnpm", "yarn", "bun", "deno",
    "ruby", "perl", "php",
    "env", "sudo", "su", "rm", "mv", "cp", "dd", "chmod", "chown", "ln",
    "git", "curl", "wget", "ssh", "scp", "rsync", "find", "xargs", "make",
    "docker", "kubectl", "brew", "pip", "pip3", "uv", "open", "osascript",
    "eval", "exec", "source", "kill", "pkill", "launchctl", "defaults", "tee",
    "awk", "sed",
}


def read(name: str, log_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        with open(os.path.join(log_dir or jevlog.log_dir(), name + ".jsonl"), encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except OSError:
        pass
    return out


def _cost(recs: List[Dict[str, Any]]) -> float:
    total = 0.0
    for r in recs:
        if "latency_ms" not in r and "input_tokens" not in r:
            continue
        c = r.get("cost")
        try:
            total += float(c) if c is not None else float(r.get("input_tokens") or 0) * PRICE_PER_TOKEN
        except (ValueError, TypeError):
            continue
    return total


def _steps(esc: List[Dict[str, Any]], to_model: str, from_model: Optional[str] = None,
           skipped: bool = False) -> Dict[str, Any]:
    # skipped=True selects steps to to_model that did NOT come from from_model (ladder violations)
    hits = [r for r in esc if r.get("to_model") == to_model
            and (from_model is None or (r.get("from_model") != from_model) == skipped)]
    return {"count": len(hits), "reasons": dict(Counter(str(r.get("reason")) for r in hits))}


CANONICAL = ("executor", "specific", "failing_test_exists", "needs_opus", "needs_stronger_model",
             "done", "risk", "safe_to_commit", "needs_interrogate")
_ALIASES = {"failing_tests_exist": "failing_test_exists", "failing_test": "failing_test_exists"}


def canonical(name: str) -> str:
    """Fold '<question>.<task>' and legacy task-affixed names onto CANONICAL; unknown names pass through."""
    base = str(name).split(".", 1)[0]
    if base in CANONICAL:
        return base
    s = re.sub(r"^t\d+_", "", base)
    s = re.sub(r"(_t\d+|_\d+|\d+|_any|_all|_kind)$", "", s)
    s = _ALIASES.get(s, s)
    if s in CANONICAL:
        return s
    return base if "." in str(name) else str(name)


def _int(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if v == v and v >= 0 else None


def delivery(dispatch: List[Any], scope: List[Any], esc: List[Dict[str, Any]],
             review: List[Any], merge: List[Any]) -> Dict[str, Any]:
    dispatch = [r for r in dispatch if isinstance(r, dict)]
    review = [r for r in review if isinstance(r, dict)]
    merge = [r for r in merge if isinstance(r, dict) and r.get("task") is not None]
    tasks = {str(r["task"]) for r in dispatch if r.get("task") is not None and _int(r.get("attempt")) == 1}
    n = len(tasks)
    denials = sum(1 for r in scope if isinstance(r, dict))
    climbs = _steps(esc, "opus", "sonnet")["count"]
    rounds: Dict[str, int] = {}
    for r in review:
        k, v = r.get("task"), _int(r.get("round"))
        if k is not None and v is not None:
            rounds[str(k)] = max(rounds.get(str(k), 0), v)
    reviewed = {str(r.get("task")) for r in review if r.get("task") is not None}
    costed = [(c, _int(r.get("tasks_merged")) or 0) for r in merge for c in [_num(r.get("cost_usd"))] if c is not None and (_int(r.get("tasks_merged")) or 0) >= 1]
    merged_tasks = sum(t for _, t in costed)
    return {
        "tasks_dispatched": n,
        "scope_denials": denials,
        "scope_per_task": round(denials / n, 4) if n else None,
        "climb_rate": round(climbs / n, 4) if n else None,
        "review_rounds_median": float(statistics.median(rounds.values())) if rounds else None,
        "merges": len(merge),
        "merges_without_review": sum(1 for r in merge if str(r["task"]) not in reviewed),
        "cost_per_task": round(sum(c for c, _ in costed) / merged_tasks, 4) if merged_tasks else None,
        "merges_without_cost": sum(1 for r in merge if _num(r.get("cost_usd")) is None),
    }


def build(log_dir: Optional[str] = None) -> Dict[str, Any]:
    th = thresholds.load()
    calls, gate, route = read("calls", log_dir), read("gate", log_dir), read("route", log_dir)
    mcp, over, esc = read("mcp", log_dir), read("overrides", log_dir), read("escalations", log_dir)
    compare, compact = read("compare", log_dir), read("compact", log_dir)
    dispatch, scope = read("dispatch", log_dir), read("scope", log_dir)
    review, merge = read("review", log_dir), read("merge", log_dir)
    judged = [r for r in gate if "latency_ms" in r]
    q_calls: Counter = Counter()
    q_below: Counter = Counter()
    for r in mcp:
        answers = r.get("answers")
        # Tolerate malformed answers: not a dict, missing, or invalid content
        if not isinstance(answers, dict):
            continue
        for q, a in answers.items():
            q = canonical(q)
            q_calls[q] += 1
            # Tolerate missing or invalid confidence values
            if not isinstance(a, dict):
                continue
            try:
                conf = float(a.get("confidence", 0))
            except (ValueError, TypeError):
                # confidence is string or non-numeric, treat as below threshold
                conf = 0.0
            if conf < th["dispatch"]["min_confidence"]:
                q_below[q] += 1
    q_over = Counter(canonical(str(r.get("question"))) for r in over)
    questions = {q: {"calls": n, "below_threshold": q_below[q], "overrides": q_over[q],
                     "override_rate": round(q_over[q] / n, 4) if n else 0.0} for q, n in q_calls.items()}
    ratios: List[float] = []
    for r in compare:
        try:
            swarm = float(r.get("swarm_tokens") or 0)
            plain = float(r.get("plain_tokens") or 0)
            if plain > 0:
                ratios.append(swarm / plain)
        except (ValueError, TypeError):
            continue
    heads = Counter()
    for r in judged:
        head = r.get("head")
        if head is not None and r.get("decision") == "none":
            try:
                # Check if head is hashable (skip unhashable types)
                hash(head)
                if isinstance(head, str):
                    heads[head] += 1
            except TypeError:
                continue
    risky = {r.get("head") for r in judged if r.get("decision") in ("deny", "ask")}
    return {
        "tool_calls": len(calls),
        "gate_judged": len(judged),
        "judged_share": round(len(judged) / len(calls), 4) if calls else 0.0,
        "judge_latency_ms_median": statistics.median(lat) if (lat := [r["latency_ms"] for r in gate if isinstance(r.get("latency_ms"), (int, float)) and not isinstance(r.get("latency_ms"), bool) and math.isfinite(r["latency_ms"])]) else None,
        "gate_decisions": dict(Counter(r.get("decision") for r in gate)),
        "gate_skips_by_via": {v: sum(1 for r in gate if r.get("decision") == "skipped" and (r.get("via") or "legacy") == v)
                              for v in ("allowlist", "compound", "prescreen", "legacy")},
        "route_calls": len(route),
        "route_injected": sum(1 for r in route if r.get("injected")),
        "questions": questions,
        "opus_escalations": _steps(esc, "opus", "sonnet"),
        "fable": _steps(esc, "fable", "opus"),
        "fable_without_opus": _steps(esc, "fable", "opus", skipped=True),
        "delivery": delivery(dispatch, scope, esc, review, merge),
        "compare_count": len(ratios),
        "swarm_vs_plain": round(sum(ratios) / len(ratios), 3) if ratios else None,
        "jev_spend_usd": _cost(gate) + _cost(route) + _cost(mcp) + _cost(compact),
        "top_judged_heads": [h for h, _ in heads.most_common() if h not in risky][:3],
    }


def proposals(rep: Dict[str, Any], th: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    qs = [v for v in rep["questions"].values() if v["calls"] >= 20]
    if qs:
        calls = sum(v["calls"] for v in qs)
        o_rate = sum(v["overrides"] for v in qs) / calls
        below = sum(v["below_threshold"] for v in qs) / calls
        cur = th["dispatch"]["min_confidence"]
        if o_rate > 0.25 and cur < 0.95:
            out.append({"key": "dispatch.min_confidence", "old": cur, "new": round(min(0.95, cur + 0.05), 2),
                        "why": "Opus overrode %.0f%% of confident Jev answers" % (o_rate * 100)})
        elif o_rate < 0.05 and below > 0.5 and cur > 0.5:
            out.append({"key": "dispatch.min_confidence", "old": cur, "new": round(max(0.5, cur - 0.05), 2),
                        "why": "%.0f%% of answers fell below threshold but Opus rarely disagreed (%.0f%%)" % (below * 100, o_rate * 100)})
    if rep["tool_calls"] >= 100 and rep["judged_share"] > 0.30 and rep["top_judged_heads"]:
        cur_list = th["gate"]["allowlist"]
        candidates = []
        for h in rep["top_judged_heads"]:
            # Require >=10 judged-none records, safe head name, not dangerous
            if h in DANGEROUS_HEADS:
                continue
            # Check head matches pattern: ^[a-z][a-z0-9_-]{1,31}$
            if not re.match(r"^[a-z][a-z0-9_-]{1,31}$", h):
                continue
            candidates.append(h)
        if candidates:
            new = cur_list + [h for h in candidates if h not in cur_list]
            out.append({"key": "gate.allowlist", "old": cur_list, "new": new,
                        "why": "Jev judged %.0f%% of tool calls (target ~20%%); these heads were judged often and never denied or asked. Review each one: it is allowlisted for plain (metachar-free) use only."
                               % (rep["judged_share"] * 100)})
    if rep.get("swarm_vs_plain") and rep.get("compare_count", 0) >= 3 and rep["swarm_vs_plain"] > 3.0:
        cur = th["route"].get("swarm_min", 0.7)
        if cur < 0.95:
            out.append({"key": "route.swarm_min", "old": cur, "new": round(min(0.95, cur + 0.1), 2),
                        "why": "Swarm runs used %.1fx the tokens of plain Opus over %d comparisons; route to swarm only when Jev is more sure"
                               % (rep["swarm_vs_plain"], rep["compare_count"])})
    return [p for p in out if p["new"] != p["old"]]


def render(rep: Dict[str, Any], props: List[Dict[str, Any]]) -> str:
    d = rep["delivery"]

    def na(v: Any, fmt: str = "%.2f") -> str:
        return "n/a" if v is None else fmt % v

    delivery_lines = [
        "- Tasks dispatched: %d" % d["tasks_dispatched"],
        "- Scope-lock denials per task (healthy 0-1): %s (%d denials)" % (na(d["scope_per_task"]), d["scope_denials"]),
        "- Sonnet->Opus climb rate (healthy under 20%%): %s" % ("n/a" if d["climb_rate"] is None else "%.0f%%" % (d["climb_rate"] * 100)),
        "- Median review rounds per branch (healthy <= 2): %s" % na(d["review_rounds_median"], "%.1f"),
        "- Merges without a review (should be 0): %d of %d" % (d["merges_without_review"], d["merges"]),
        "- Cost per merged task: %s (%d of %d merges had no cost)" % (na(d["cost_per_task"], "$%.2f"), d["merges_without_cost"], d["merges"]),
    ]
    lines = ["# Jev calibration", "",
             "- Tool calls: %d; Jev judged %d (%.0f%%, target ~20%%)" % (rep["tool_calls"], rep["gate_judged"], rep["judged_share"] * 100),
             "- Judge latency median (healthy < 500 ms): %s" % ("n/a" if rep["judge_latency_ms_median"] is None else "%d ms" % rep["judge_latency_ms_median"]),
             "- Gate decisions: %s" % json.dumps(rep["gate_decisions"]),
             "- gate skips: allowlist %(allowlist)d, compound %(compound)d, prescreen %(prescreen)d, legacy %(legacy)d" % rep["gate_skips_by_via"],
             "- Route: %d calls, %d injected" % (rep["route_calls"], rep["route_injected"]),
             "- Escalations sonnet->opus: %d %s" % (rep["opus_escalations"]["count"], json.dumps(rep["opus_escalations"]["reasons"])),
             "- Fable dispatches (opus->fable only): %d %s" % (rep["fable"]["count"], json.dumps(rep["fable"]["reasons"])),
             "- Fable without a prior Opus step (should be 0): %d %s" % (rep["fable_without_opus"]["count"], json.dumps(rep["fable_without_opus"]["reasons"]))]
    lines += delivery_lines
    lines += ["- Swarm vs plain token ratio: %s" % rep["swarm_vs_plain"],
             "- Jev spend: $%.6f" % rep["jev_spend_usd"], "", "| question | calls | below thr | overrides | override rate |", "|---|---|---|---|---|"]
    for q, v in sorted(rep["questions"].items()):
        lines.append("| %s | %d | %d | %d | %.0f%% |" % (q, v["calls"], v["below_threshold"], v["overrides"], v["override_rate"] * 100))
    lines += ["", "## Proposals (apply only after approval)"]
    lines += ["- `%s`: %s -> %s. %s" % (p["key"], p["old"], p["new"], p["why"]) for p in props] or ["- none"]
    lines.append("")
    lines.append("PROPOSALS_JSON: " + json.dumps(props))
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "report"
    if cmd == "report":
        rep = build()
        props = proposals(rep, thresholds.load())
        print(render(rep, props))
        jevlog.append("tune", {"proposals": len(props)})
        return 0
    if cmd == "apply" and len(argv) == 4:
        try:
            value = json.loads(argv[3])
        except ValueError as e:
            sys.stderr.write("Bad JSON value: %s\n" % e)
            return 2
        err = thresholds.validate(argv[2], value)
        if err:
            sys.stderr.write("%s\n" % err)
            return 2
        thresholds.set_value(argv[2], value)
        print("set %s = %s" % (argv[2], argv[3]))
        return 0
    if cmd == "record-compare" and len(argv) == 7:
        jevlog.append("compare", {"task": argv[2], "swarm_tokens": int(argv[3]), "plain_tokens": int(argv[4]),
                                  "swarm_wall_s": float(argv[5]), "plain_wall_s": float(argv[6])})
        return 0
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
