#!/usr/bin/env python3
"""Chain stage on PreToolUse: Jev judges Bash/Write/Edit. Can deny or ask; never allows.

Sends the (redacted) command, or file path + byte/line counts. Never file contents.
Allowlisted plain shell reads skip Jev. Every failure means no decision.
"""
import json
import os
import re
import shlex
import string
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


MAX_PARTS = 8
_SAFE_REDIRECTS = ("2>/dev/null", "2>&1", ">/dev/null")
_BAD_IN_QUOTES = set(";&|<>()`")
_BAD_OUTSIDE = set("&<>()`")
_SAFE_CHARS = frozenset(string.ascii_letters + string.digits + " \t._/=:@%+,-'\"")


def _plain(s: str) -> bool:
    """Only plain characters: no expansion, glob, comment, history or non-ASCII."""
    return all(c in _SAFE_CHARS for c in s)


def split_compound(cmd: str) -> Optional[List[str]]:
    """Split on &&, ||, ; and | outside quotes; drop safe standalone redirects.

    Returns None (send to the judge) for anything else unusual. Never returns a part that
    contains a shell operator, a backslash or a newline.
    """
    if not cmd or "\\" in cmd or "\n" in cmd or "\r" in cmd:
        return None
    parts: List[str] = []
    cur: List[str] = []
    quote: Optional[str] = None
    i, n = 0, len(cmd)
    while i < n:
        c = cmd[i]
        if quote:
            if c == quote:
                quote = None
            elif c in _BAD_IN_QUOTES:
                return None
            cur.append(c)
            i += 1
            continue
        if c in "'\"":
            quote = c
            cur.append(c)
            i += 1
            continue
        if not cur or cur[-1] in " \t":
            r = next((r for r in _SAFE_REDIRECTS if cmd.startswith(r, i)), None)
            if r and (i + len(r) == n or cmd[i + len(r)] in " \t;|&"):
                i += len(r)
                continue
        if cmd.startswith("|&", i):
            return None
        op = "&&" if cmd.startswith("&&", i) else "||" if cmd.startswith("||", i) else c if c in ";|" else ""
        if op:
            part = "".join(cur).strip(" \t")
            if not part or not _plain(part):
                return None
            parts.append(part)
            cur = []
            i += len(op)
            continue
        if c in _BAD_OUTSIDE:
            return None
        cur.append(c)
        i += 1
    if quote:
        return None
    part = "".join(cur).strip(" \t")
    if not part or not _plain(part):
        return None
    parts.append(part)
    return parts if len(parts) <= MAX_PARTS else None


def allowlisted_compound(cmd: str, allowlist: List[str], cwd: str) -> Tuple[bool, int]:
    """Skip only if every part is allowlisted and every cd stays inside cwd."""
    parts = split_compound(cmd)
    if not parts or not all(allowlisted(p, allowlist) for p in parts):
        return False, 0
    root = os.path.realpath(cwd) if cwd else ""
    current = root
    for p in parts:
        try:
            words = shlex.split(p)
        except ValueError:
            return False, 0
        if words[0] != "cd":
            continue
        if not root or len(words) != 2 or words[1].startswith("-") or os.environ.get("CDPATH"):
            return False, 0
        if ".." in words[1].split("/"):  # shells resolve .. logically, before symlinks
            return False, 0
        current = os.path.realpath(os.path.join(current, words[1]))
        if current != root and not current.startswith(root.rstrip(os.sep) + os.sep):
            return False, 0
    return True, len(parts)


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
    if tool == "Bash":
        cmd = str(ti.get("command", ""))
        ok = allowlisted(cmd, t["allowlist"])
        ok, n = ok and _plain(cmd), 1
        if not ok and t.get("compound", True):
            ok, n = allowlisted_compound(cmd, t["allowlist"], str(event.get("cwd") or ""))
        if ok:
            jevlog.append("gate", dict(base, decision="skipped", **({"parts": n} if n > 1 else {})))
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
