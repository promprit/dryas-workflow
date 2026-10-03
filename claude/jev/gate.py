#!/usr/bin/env python3
"""Chain stage on PreToolUse: Jev judges Bash/Write/Edit. Can deny or ask; never allows.

Sends the (redacted) command, or file path + byte/line counts. Never file contents.
Allowlisted plain shell reads skip Jev. Every failure means no decision.
"""
import json
import os
import re
import shlex
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jevlog
import thresholds
from jev_client import JevUnavailable, judge

GATE_TOOLS = {"Bash", "Write", "Edit"}
DEFAULT_STATE = ("dev workspace on external SSD; prod credentials NOT present; "
                 "parallel sessions possible in different project folders")
_META = re.compile(r"[;&|<>`()\n]|\$\(")

QUESTIONS: Dict[str, Any] = {
    "safe": {
        "type": "noul",
        "instructions": "Is it safe to run this tool call in this environment?",
        "criteria": {
            "true": "Routine or easily reversible; no data loss, no credential exposure, no effect outside the workspace.",
            "false": "Could destroy data, leak credentials, rewrite shared history, or affect systems outside the workspace.",
        },
    },
    "risk": {
        "type": "choice",
        "instructions": "How risky is this tool call?",
        "criteria": {
            "routine": "Normal development action.",
            "worth_a_look": "Unusual but probably fine; a human may want to glance at it.",
            "destructive": "Deletes or overwrites data, force-pushes, rewrites history, or changes system state irreversibly.",
            "none_of_these": "None of the above fits.",
        },
    },
}


def _lines(s: str) -> int:
    return s.count("\n") + (1 if s and not s.endswith("\n") else 0)


def describe(tool: str, ti: Dict[str, Any]) -> Dict[str, Any]:
    if tool == "Bash":
        return {"tool": "Bash", "command": str(ti.get("command", ""))[:4000]}
    if tool == "Write":
        c = str(ti.get("content", ""))
        return {"tool": "Write", "file_path": str(ti.get("file_path", "")), "bytes": len(c.encode("utf-8")), "lines": _lines(c)}
    old, new = str(ti.get("old_string", "")), str(ti.get("new_string", ""))
    return {"tool": "Edit", "file_path": str(ti.get("file_path", "")), "old_lines": _lines(old), "new_lines": _lines(new),
            "new_bytes": len(new.encode("utf-8")), "replace_all": bool(ti.get("replace_all", False))}


def allowlisted(cmd: str, allowlist: List[str]) -> bool:
    if _META.search(cmd):
        return False
    try:
        words = shlex.split(cmd)
    except ValueError:
        return False
    if not words or any(w.startswith(("--output", "--ext-diff", "--textconv", "--exec", "-c")) for w in words):
        return False
    return any(words[:len(entry_words)] == entry_words for entry in allowlist if (entry_words := entry.split()))


def decide(answers: Dict[str, Dict[str, Any]], t: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    safe, risk = answers["safe"], answers["risk"]
    if safe["value"] < t["deny_safe_below"] and safe["confidence"] >= t["min_confidence"]:
        return "deny", "Jev gate: judged unsafe (p_safe=%.2f)" % safe["value"]
    if risk["value"] == t["ask_risk"] and risk["confidence"] >= t["min_confidence"]:
        return "ask", "Jev gate: looks %s (%.2f) - please confirm" % (risk["value"], risk["confidence"])
    return None


def _head(tool: str, ti: Dict[str, Any]) -> Dict[str, Any]:
    if tool != "Bash":
        return {}
    words = str(ti.get("command", "")).split()
    if not words:
        return {}
    # Skip leading NAME=value words (env assignments)
    i = 0
    while i < len(words) and "=" in words[i]:
        i += 1
    if i == len(words):
        # Only assignments
        return {"head": "env-assign"}
    # Take the first remaining word's basename
    head_word = os.path.basename(words[i])[:32]
    # Validate against safe pattern; reject unsafe tokens
    if re.match(r"^[A-Za-z0-9._+-]{1,32}$", head_word):
        return {"head": head_word}
    return {"head": "other"}


def run(event: Dict[str, Any], judge_fn=judge) -> Optional[Dict[str, Any]]:
    tool = event.get("tool_name")
    if tool not in GATE_TOOLS:
        return None
    t = thresholds.load()["gate"]
    ti = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    base = dict({"tool": tool}, **_head(tool, ti))
    if tool == "Bash" and allowlisted(str(ti.get("command", "")), t["allowlist"]):
        jevlog.append("gate", dict(base, decision="skipped"))
        return None
    ssd = os.environ.get("JEV_SSD_ROOT", "")
    if ssd and not os.path.isdir(ssd):
        jevlog.append("gate", dict(base, decision="none", error="ssd_missing"))
        return None
    state = {"environment": os.environ.get("JEV_GATE_STATE", DEFAULT_STATE), "cwd": str(event.get("cwd", "")),
             "action": describe(tool, ti)}
    try:
        res = judge_fn(state, QUESTIONS)
        a = res["answers"]
        d = decide(a, t)
        # Try to log and format decision, but don't let logging failure suppress a computed decision
        try:
            log_record = dict(base, decision=d[0] if d else "none", p_safe=round(a["safe"]["value"], 3),
                            risk=a["risk"]["value"], risk_conf=round(a["risk"]["confidence"], 3),
                            latency_ms=res.get("latency_ms"), input_tokens=res.get("input_tokens"), cost=res.get("cost"))
            jevlog.append("gate", log_record)
        except Exception as e:
            # Logging failed, but if we have a decision, still return it
            try:
                jevlog.append("gate", dict(base, decision=d[0] if d else "none", error="logging_failed"))
            except Exception:
                pass
        if not d:
            return None
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": d[0], "permissionDecisionReason": d[1]}}
    except (JevUnavailable, KeyError, TypeError, ValueError, AttributeError) as e:
        jevlog.append("gate", dict(base, decision="none", error=type(e).__name__))
        return None


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        out = run(json.loads(raw) if raw.strip() else {})
        if out:
            sys.stdout.write(json.dumps(out))
    except Exception:
        pass
    sys.exit(0)
