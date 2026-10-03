#!/usr/bin/env python3
"""Chain stage on UserPromptSubmit: Jev suggests a route and whether work needs more than Sonnet (-> Opus).
Advisory only. Never suggests Fable: Fable is reached only after an Opus executor fails.

Injects one line, e.g. 'Jev route: swarm (0.82); opus: no (0.91)'. Parts below the route
confidence threshold are dropped; if nothing is confident, nothing is injected.
"""
import json
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jevlog
import thresholds
from jev_client import JevUnavailable, judge

QUESTIONS: Dict[str, Any] = {
    "route": {
        "type": "choice",
        "instructions": "How should a coding orchestrator handle this request?",
        "criteria": {
            "single_agent": "One focused change the main session can make directly.",
            "swarm": "Multi-step work across several files or tasks that should be split among executor agents.",
            "question_only": "A question or explanation; no code changes.",
            "none_of_these": "None of the above fits.",
        },
    },
    "opus": {
        "type": "noul",
        "instructions": "Does this request need a model stronger than Sonnet?",
        "criteria": {
            "true": "Cross-cutting refactor, concurrency- or security-sensitive code, or deep architectural judgment.",
            "false": "Standard implementation work a capable mid-tier model handles.",
        },
    },
}


def run(event: Dict[str, Any], judge_fn=judge) -> Optional[str]:
    prompt = str(event.get("prompt", ""))
    if not prompt.strip():
        return None
    t = thresholds.load()["route"]
    try:
        res = judge_fn({"prompt": prompt[:4000], "cwd": str(event.get("cwd", ""))}, QUESTIONS)
        r, f = res["answers"]["route"], res["answers"]["opus"]
        parts: List[str] = []
        route_criteria = QUESTIONS["route"]["criteria"]
        # Only inject route if value is one of the valid criteria keys (not none_of_these)
        need = max(t.get("swarm_min", t["min_confidence"]), t["min_confidence"]) if r["value"] == "swarm" else t["min_confidence"]
        if r["confidence"] >= need and r["value"] in route_criteria and r["value"] != "none_of_these":
            parts.append("route: %s (%.2f)" % (str(r["value"]).replace("_", "-"), r["confidence"]))
        if f["confidence"] >= t["min_confidence"]:
            parts.append("opus: %s (%.2f)" % ("yes" if float(f["value"]) >= 0.5 else "no", f["confidence"]))
        line = ("Jev " + "; ".join(parts)) if parts else None
        jevlog.append("route", {"route": str(r["value"]), "route_conf": round(r["confidence"], 3), "opus_p": round(f["value"], 3),
                                "opus_conf": round(f["confidence"], 3), "injected": bool(line),
                                "latency_ms": res.get("latency_ms"), "input_tokens": res.get("input_tokens"), "cost": res.get("cost")})
        return line
    except (JevUnavailable, KeyError, TypeError, ValueError, AttributeError) as e:
        jevlog.append("route", {"error": type(e).__name__})
        return None


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        line = run(json.loads(raw) if raw.strip() else {})
        if line:
            sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": line}}))
    except Exception:
        pass
    sys.exit(0)
