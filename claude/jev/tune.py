#!/usr/bin/env python3
"""Calibration report over Jev logs; proposes threshold changes. Applies a change only via `apply`.

CLI: tune.py report | tune.py apply KEY JSON_VALUE | tune.py record-compare TASK SWARM_TOK PLAIN_TOK SWARM_S PLAIN_S
"""
import json
import os
import re
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


def _steps(esc: List[Dict[str, Any]], to_model: str) -> Dict[str, Any]:
    hits = [r for r in esc if r.get("to_model") == to_model]
    return {"count": len(hits), "reasons": dict(Counter(str(r.get("reason")) for r in hits))}


def build(log_dir: Optional[str] = None) -> Dict[str, Any]:
    th = thresholds.load()
    calls, gate, route = read("calls", log_dir), read("gate", log_dir), read("route", log_dir)
    mcp, over, esc = read("mcp", log_dir), read("overrides", log_dir), read("escalations", log_dir)
    compare, compact = read("compare", log_dir), read("compact", log_dir)
    judged = [r for r in gate if "latency_ms" in r]
    q_calls: Counter = Counter()
    q_below: Counter = Counter()
    for r in mcp:
        answers = r.get("answers")
        # Tolerate malformed answers: not a dict, missing, or invalid content
        if not isinstance(answers, dict):
            continue
        for q, a in answers.items():
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
    q_over = Counter(str(r.get("question")) for r in over)
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
        "gate_decisions": dict(Counter(r.get("decision") for r in gate)),
        "route_calls": len(route),
        "route_injected": sum(1 for r in route if r.get("injected")),
        "questions": questions,
        "opus_escalations": _steps(esc, "opus"),
        "fable": _steps(esc, "fable"),
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
    return out


def render(rep: Dict[str, Any], props: List[Dict[str, Any]]) -> str:
    lines = ["# Jev calibration", "",
             "- Tool calls: %d; Jev judged %d (%.0f%%, target ~20%%)" % (rep["tool_calls"], rep["gate_judged"], rep["judged_share"] * 100),
             "- Gate decisions: %s" % json.dumps(rep["gate_decisions"]),
             "- Route: %d calls, %d injected" % (rep["route_calls"], rep["route_injected"]),
             "- Escalations sonnet->opus: %d %s" % (rep["opus_escalations"]["count"], json.dumps(rep["opus_escalations"]["reasons"])),
             "- Fable dispatches (opus->fable only): %d %s" % (rep["fable"]["count"], json.dumps(rep["fable"]["reasons"])),
             "- Swarm vs plain token ratio: %s" % rep["swarm_vs_plain"],
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
