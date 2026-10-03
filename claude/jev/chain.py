#!/usr/bin/env python3
"""Run hook stages in order for one Claude Code event (pretool | prompt). Stages: chain.json.

PreToolUse: deny beats ask; a stage's allow is ignored (the chain never auto-allows);
after a deny only observe stages run. UserPromptSubmit: additionalContext is concatenated.
Any failure of a stage is skipped; the chain itself always exits 0.
"""
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jevlog

RANK = {"ask": 1, "deny": 2}


def config_path() -> str:
    return os.environ.get("JEV_CHAIN_CONFIG", os.path.join(HERE, "chain.json"))


def load_stages(kind: str) -> List[Dict[str, Any]]:
    try:
        with open(config_path(), encoding="utf-8") as f:
            return list(json.load(f).get(kind, []))
    except (OSError, ValueError):
        return []


def _expand(s: str) -> Optional[str]:
    out = os.path.expanduser(os.path.expandvars(s))
    return None if "$" in out else out


def _applies(stage: Dict[str, Any], event: Dict[str, Any]) -> bool:
    if stage.get("enabled") is False:
        return False
    req = stage.get("requires_path")
    if req:
        r = _expand(req)
        if r is None or not os.path.exists(r):
            return False
    m = stage.get("match")
    if m and not re.fullmatch(m, str(event.get("tool_name", ""))):
        return False
    return True


def _run(stage: Dict[str, Any], raw: str) -> Tuple[Optional[int], str, str]:
    cmd = [_expand(str(c)) for c in stage["cmd"]]
    if any(c is None for c in cmd):
        return None, "", ""
    try:
        p = subprocess.run(cmd, input=raw.encode("utf-8", "replace"), capture_output=True, timeout=stage.get("timeout", 5))
        stdout = p.stdout.decode("utf-8", "replace")
        stderr = p.stderr.decode("utf-8", "replace")
        return p.returncode, stdout, stderr
    except Exception:
        return None, "", ""


def _json(out: str) -> Optional[Dict[str, Any]]:
    try:
        v = json.loads(out)
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def pretool(event: Dict[str, Any], raw: str, stages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    decision: Optional[str] = None
    reason = ""
    for st in stages:
        try:
            if not _applies(st, event):
                continue
            if st.get("observe"):
                _run(st, raw)
                continue
            if decision == "deny":
                continue
            code, out, err = _run(st, raw)
            if code is None:
                continue
            if code == 2:
                d, r = "deny", (err.strip() or "blocked")
            else:
                j = _json(out)
                hso = (j or {}).get("hookSpecificOutput") if isinstance(j, dict) else None
                if not isinstance(hso, dict):
                    hso = {}
                d, r = hso.get("permissionDecision"), str(hso.get("permissionDecisionReason", ""))
            if d in RANK and RANK[d] > RANK.get(decision or "", 0):
                decision, reason = d, "[%s] %s" % (st.get("name", "?"), r)
        except Exception:
            continue
    if decision is None:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": reason}}


def prompt(event: Dict[str, Any], raw: str, stages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    parts: List[str] = []
    for st in stages:
        try:
            if not _applies(st, event):
                continue
            code, out, err = _run(st, raw)
            if st.get("observe") or code is None:
                continue
            if code == 2:
                return {"decision": "block", "reason": err.strip() or st.get("name", "blocked")}
            j = _json(out)
            if j is not None and isinstance(j, dict):
                if j.get("decision") == "block":
                    return {"decision": "block", "reason": str(j.get("reason", st.get("name", "blocked")))}
                ctx = (j.get("hookSpecificOutput") or {}).get("additionalContext")
                if ctx:
                    parts.append(str(ctx))
            elif out.strip():
                parts.append(out.strip())
        except Exception:
            continue
    if not parts:
        return None
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "\n".join(parts)}}


def main(argv: List[str]) -> int:
    kind = argv[1] if len(argv) > 1 else ""
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except ValueError:
        event = {}
    if not isinstance(event, dict):
        event = {}
    for key, env in (("session_id", "JEV_SESSION_ID"), ("cwd", "JEV_CWD")):
        v = event.get(key)
        if isinstance(v, str) and v:
            os.environ[env] = v  # inherited by every stage subprocess; read by jevlog.append
    if kind == "pretool":
        jevlog.append("calls", {"tool": str(event.get("tool_name", ""))})
        out = pretool(event, raw, load_stages("pretool"))
    elif kind == "prompt":
        out = prompt(event, raw, load_stages("prompt"))
    else:
        return 0
    if out:
        sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception:
        sys.exit(0)
