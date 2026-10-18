#!/usr/bin/env python3
"""Run hook stages in order for one hook event. Kinds: pretool | prompt | the observe kinds. Stages: chain.json.

PreToolUse: deny beats ask; a stage's allow is ignored (the chain never auto-allows);
after a deny only observe stages run. UserPromptSubmit: additionalContext is concatenated.
Any failure of a stage is skipped, except a "fail_closed" stage while a task is active
(.orchestrate/active.json): its timeout, crash or unparseable output becomes a deny.
The chain itself always exits 0.
A stage with `inproc` runs in this process (only the known modules: `scope_lock`, `gate_outcome`, `bridge_deliver`);
its `cmd` stays for tools that run stages one by one. Only `bridge_deliver` returns text: in `prompt` it joins the
additionalContext, and in `post` a stage marked `"context": true` prints it as PostToolUse additionalContext.
"""
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import codex_event
import jevlog
import paths

RANK = {"ask": 1, "deny": 2}


def config_path() -> str:
    return os.environ.get("JEV_CHAIN_CONFIG", os.path.join(HERE, "chain.json"))


_PH = re.compile(r"\$(?:\{(CD|PY|DRYAS_DATA_ROOT)\}|(CD|PY|DRYAS_DATA_ROOT)(?![A-Za-z0-9_]))")


def placeholders() -> Dict[str, str]:
    fwd = lambda p: p.replace("\\", "/")
    return {"CD": fwd(paths.plugin_root()), "PY": fwd(paths.python()), "DRYAS_DATA_ROOT": fwd(paths.data_root())}


def load_local() -> Dict[str, Any]:
    p = paths.chain_local()
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            v = json.load(f)
        if not isinstance(v, dict):
            raise ValueError("not an object")
        return v
    except (OSError, ValueError) as e:
        sys.stderr.write("dryas: ignoring %s (%s); using chain defaults\n" % (p, str(e).splitlines()[0][:80]))
        return {}


def apply_local(stages: List[Dict[str, Any]], event: str, local: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Copies of stages with the user's enabled/timeout applied by stage name. Nothing else can be overridden."""
    sect = local.get("stages") if isinstance(local, dict) else None
    over = sect.get(event) if isinstance(sect, dict) else None
    out = []
    for st in stages:
        st = dict(st)
        o = over.get(st.get("name")) if isinstance(over, dict) else None
        if isinstance(o, dict):
            if isinstance(o.get("enabled"), bool):
                st["enabled"] = o["enabled"]
            t = o.get("timeout")
            if isinstance(t, (int, float)) and not isinstance(t, bool) and 0 < t <= 120:
                st["timeout"] = t
        out.append(st)
    return out


def load_stages(kind: str, harness: str = "claude") -> List[Dict[str, Any]]:
    try:
        with open(config_path(), encoding="utf-8") as f:
            stages = list(json.load(f).get(kind, []))
    except (OSError, ValueError):
        return []
    stages = [s for s in stages if isinstance(s, dict)]
    try:
        stages = apply_local(stages, kind, load_local())
    except Exception:
        pass  # a bad local file never changes the defaults (scope lock must keep denying)
    return [s for s in stages if harness in s.get("harness", ["claude"])]


def _expand(s: str) -> Optional[str]:
    """Placeholders are substituted last, so a `$` inside their values (Windows profile names) is not an unresolved var."""
    ph = placeholders()
    parts = _PH.split(s)  # [text, group1, group2, text, ...]
    out = []
    for i in range(0, len(parts), 3):
        t = os.path.expandvars(parts[i])
        if "$" in t:
            return None
        out.append(t)
        if i + 1 < len(parts):
            out.append(ph[parts[i + 1] or parts[i + 2]])
    return os.path.expanduser("".join(out))


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
    raw_cmd = stage.get("cmd")
    if not isinstance(raw_cmd, list) or not raw_cmd or not all(isinstance(c, str) for c in raw_cmd):
        return None, "", ""
    cmd = [_expand(c) for c in raw_cmd]
    if any(c is None for c in cmd):
        jevlog.append("chain", {"stage": str(stage.get("name", "?")), "skipped": "unresolved placeholder"})
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


def _task_active(event: Dict[str, Any]) -> bool:
    """Mirror of scope_lock.task_active: cwd (or a parent) has .orchestrate/active.json with a non-empty
    "active" list; an unreadable file counts as active. Replicated so chain never depends on importing the stage."""
    try:
        d = os.path.realpath(str(event.get("cwd") or os.getcwd()))
        while True:
            p = os.path.join(d, ".orchestrate", "active.json")
            if os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        return bool(json.load(f).get("active"))
                except Exception:
                    return True
            parent = os.path.dirname(d)
            if parent == d:
                return False
            d = parent
    except Exception:
        return False


def _fail_closed(st: Dict[str, Any], event: Dict[str, Any], what: str) -> Optional[Tuple[str, str]]:
    """Deny for a failed fail_closed stage while a task is active; None otherwise (stage skipped)."""
    if st.get("fail_closed") is True and _task_active(event):
        return "deny", "stage %s while tasks are active (fail closed)" % what
    return None


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
            if st.get("inproc") == "scope_lock":  # pure path check: no process start per tool call
                try:
                    import scope_lock
                    hso = ((scope_lock.run(event) or {}).get("hookSpecificOutput") or {})
                    d, r = hso.get("permissionDecision"), str(hso.get("permissionDecisionReason", ""))
                except Exception as e:
                    fc = _fail_closed(st, event, "failed in process (%s)" % type(e).__name__)
                    if fc is None:
                        continue
                    d, r = fc
                if d in RANK and RANK[d] > RANK.get(decision or "", 0):
                    decision, reason = d, "[%s] %s" % (st.get("name", "?"), r)
                continue
            code, out, err = _run(st, raw)
            if code is None or code not in (0, 2):
                fc = _fail_closed(st, event, "timed out or failed to run" if code is None else "exited %d" % code)
                if fc is None:
                    continue
                d, r = fc
            elif code == 2:
                d, r = "deny", (err.strip() or "blocked")
            else:
                j = _json(out)
                if j is None and out.strip() and (fc := _fail_closed(st, event, "wrote unparseable output")):
                    j = {"hookSpecificOutput": {"permissionDecision": fc[0], "permissionDecisionReason": fc[1]}}
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


def _deny(reason: str) -> Dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def _stricter(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if b is None:
        return a
    if a is None:
        return b
    rb = RANK.get(b["hookSpecificOutput"]["permissionDecision"], 0)
    return b if rb > RANK.get(a["hookSpecificOutput"]["permissionDecision"], 0) else a


def pretool_codex(event: Dict[str, Any], stages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Codex apply_patch: per_file stages run once per touched file (stop at the first deny), the rest run once
    on one combined Write event (first path, whole patch). Other events: one pass with all stages."""
    try:
        events = codex_event.expand(event)
        patch = codex_event.patch_text(event.get("tool_input")) if event.get("tool_name") == "apply_patch" else None
    except codex_event.PatchError as e:
        return _deny("[codex-patch] unparseable apply_patch (%s)" % e)
    if patch is None:
        best: Optional[Dict[str, Any]] = None
        for ev in events:
            best = _stricter(best, pretool(ev, json.dumps(ev), stages))
        return best
    is_pf = lambda st: bool(st.get("per_file")) or st.get("name") == "scope-lock"  # name: fail closed without the flag
    per_file = [s for s in stages if is_pf(s)]
    rest = [s for s in stages if not is_pf(s)]
    combined = {k: v for k, v in event.items() if k not in ("tool_name", "tool_input")}
    combined["tool_name"] = "Write"
    combined["tool_input"] = {"file_path": events[0]["tool_input"]["file_path"], "content": patch,
                              "paths": [e["tool_input"]["file_path"] for e in events]}  # gate checks them all
    best = None
    for ev in events:
        best = _stricter(best, pretool(ev, json.dumps(ev), per_file))
        if best is not None and best["hookSpecificOutput"]["permissionDecision"] == "deny":
            pretool(combined, json.dumps(combined), [s for s in rest if s.get("observe")])  # observers only; output ignored
            return best
    return _stricter(best, pretool(combined, json.dumps(combined), rest))


def _harness(argv: List[str]) -> str:
    if "--harness" in argv:
        i = argv.index("--harness")
        if i + 1 < len(argv):
            return argv[i + 1]
    return "claude"


def prompt(event: Dict[str, Any], raw: str, stages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    parts: List[str] = []
    for st in stages:
        try:
            if not _applies(st, event):
                continue
            if "inproc" in st:
                ctx = _inproc(st, event)
                if ctx:
                    parts.append(ctx)  # text only: an inproc stage can never block
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


OBSERVE_KINDS = ("post", "subagent-stop", "session-start", "session-end", "precompact", "stop")


def observe(event: Dict[str, Any], raw: str, stages: List[Dict[str, Any]], kind: str = "") -> List[str]:
    """Observe-only events (memory, outcomes): every applicable stage runs in order; exit codes and output are
    ignored, so a slow, crashing or noisy stage never changes the session. The one exception: on "post", the text
    of an inproc stage marked "context": true (bridge delivery) is returned for the caller to print."""
    ctx: List[str] = []
    for st in stages:
        try:
            if not _applies(st, event):
                continue
            if "inproc" in st:
                out = _inproc(st, event)
                if out and st.get("context") is True and kind == "post":
                    ctx.append(out)
            else:
                _run(st, raw)
        except Exception:
            continue
    return ctx


def _inproc(stage: Dict[str, Any], event: Dict[str, Any]) -> Optional[str]:
    """A stage with an "inproc" module runs in this process (no subprocess). Only known modules; anything else is
    skipped. Only bridge_deliver returns text."""
    if stage["inproc"] == "gate_outcome":
        import gate_outcome
        gate_outcome.record(event)
    elif stage["inproc"] == "bridge_deliver":
        import bridge_deliver
        return bridge_deliver.deliver(event) or None
    return None


def main(argv: List[str]) -> int:
    kind = argv[1] if len(argv) > 1 else ""
    harness = _harness(argv)
    os.environ["DRYAS_HARNESS"] = harness  # inherited by every stage subprocess
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
        rec = {"tool": str(event.get("tool_name", ""))}
        mode = event.get("permission_mode")  # Claude Code: default, acceptEdits, plan, auto, bypassPermissions
        if isinstance(mode, str) and mode:
            rec["permission_mode"] = mode[:32]
        jevlog.append("calls", rec)
        stages = load_stages("pretool", harness)
        out = pretool_codex(event, stages) if harness in ("codex", "opencode") else pretool(event, raw, stages)
    elif kind == "prompt":
        out = prompt(event, raw, load_stages("prompt", harness))
    elif kind in OBSERVE_KINDS:
        ctx = observe(event, raw, load_stages(kind, harness), kind)
        if ctx:
            name = event.get("hook_event_name")
            sys.stdout.write(json.dumps({"hookSpecificOutput": {
                "hookEventName": name if name in ("PostToolUse", "PostToolUseFailure") else "PostToolUse",
                "additionalContext": "\n".join(ctx)}}))
        return 0
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
