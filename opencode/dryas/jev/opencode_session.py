#!/usr/bin/env python3
"""OpenCode edition: OpenCode keeps no Claude JSONL transcript, so the shim (opencode/plugin/dryas.ts) passes the
session messages it reads through the SDK, and this turns them into a Claude-shaped transcript and runs the same
engines as Claude Code.
  opencode_session.py compact   compact_keep + compact_restore -> {"context": ...} (experimental.session.compacting)
  opencode_session.py handoff   handoff.run -> {"line": ...} (/handoff)
stdin: {"session_id", "cwd", "messages": [{"info", "parts"}]}. Prints one JSON object, always exits 0. The transcript
is private (0600) and removed after use."""
import json
import os
import sys
from typing import Any, Callable, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compact_keep
import compact_restore
import handoff
import paths
from jev_client import judge

MAX_RESULT = 4000
# OpenCode tool -> (Claude tool name, {OpenCode arg: Claude arg}) so transcript_items picks the key argument.
TOOLS = {"bash": ("Bash", {"command": "command"}), "write": ("Write", {"filePath": "file_path"}),
         "edit": ("Edit", {"filePath": "file_path"}), "read": ("Read", {"filePath": "file_path"}),
         "grep": ("Grep", {"pattern": "pattern"}), "glob": ("Glob", {"pattern": "pattern"}),
         "task": ("Task", {"description": "description"})}


def transcript_dir() -> str:
    return os.path.join(paths.jev_dir(), "opencode")


def _tool(name: str, inp: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    if name in TOOLS:
        claude, keys = TOOLS[name]
        return claude, {dst: inp[src] for src, dst in keys.items() if isinstance(inp.get(src), str)}
    return name, {k: v for k, v in inp.items() if isinstance(v, str)}


def records(messages: Any) -> List[Dict[str, Any]]:
    """Claude transcript records (user / assistant with tool_use / user with tool_result). Synthetic text parts
    (context Dryas itself added) are dropped. Never raises on odd input."""
    out: List[Dict[str, Any]] = []
    for m in messages if isinstance(messages, list) else []:
        info = m.get("info") if isinstance(m, dict) else None
        parts = m.get("parts") if isinstance(m, dict) else None
        if not isinstance(info, dict) or not isinstance(parts, list):
            continue
        parts = [p for p in parts if isinstance(p, dict)]
        mid = str(info.get("id") or "")
        texts = [p["text"] for p in parts if p.get("type") == "text" and isinstance(p.get("text"), str)
                 and not p.get("synthetic")]
        if info.get("role") == "user":
            if texts:
                out.append({"type": "user", "uuid": mid, "message": {"role": "user", "content": "\n".join(texts)}})
            continue
        if info.get("role") != "assistant":
            continue
        content: List[Dict[str, Any]] = [{"type": "text", "text": t} for t in texts]
        results: List[Dict[str, Any]] = []
        for p in parts:
            if p.get("type") != "tool":
                continue
            st = p.get("state") if isinstance(p.get("state"), dict) else {}
            cid = str(p.get("callID") or "")
            name, inp = _tool(str(p.get("tool") or ""), st.get("input") if isinstance(st.get("input"), dict) else {})
            content.append({"type": "tool_use", "id": cid, "name": name, "input": inp})
            if st.get("status") in ("completed", "error"):
                res = st.get("output") if st.get("status") == "completed" else st.get("error")
                results.append({"type": "tool_result", "tool_use_id": cid, "content": str(res or "")[:MAX_RESULT],
                                "is_error": st.get("status") == "error"})
        if content:
            out.append({"type": "assistant", "uuid": mid, "message": {"role": "assistant", "content": content}})
        if results:
            out.append({"type": "user", "uuid": mid + "-results", "message": {"role": "user", "content": results}})
    return out


def _write(sid: str, messages: Any) -> str:
    path = os.path.join(transcript_dir(), compact_keep.safe_name(sid) + ".jsonl")
    handoff.write_private(path, "".join(json.dumps(r) + "\n" for r in records(messages)))
    return path


def _with_transcript(event: Dict[str, Any], fn: Callable[[str, str, str], Dict[str, Any]]) -> Dict[str, Any]:
    sid, cwd = event.get("session_id"), event.get("cwd")
    if not isinstance(sid, str) or not sid.strip() or not isinstance(cwd, str) or not cwd:
        raise ValueError("session_id and cwd are required")
    path = _write(sid, event.get("messages"))
    try:
        return fn(sid, cwd, path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def compact(event: Dict[str, Any], judge_fn=judge) -> Dict[str, Any]:
    def go(sid: str, cwd: str, path: str) -> Dict[str, Any]:
        compact_keep.run({"session_id": sid, "cwd": cwd, "transcript_path": path}, judge_fn)
        out = compact_restore.run({"session_id": sid})
        return {"context": out["hookSpecificOutput"]["additionalContext"] if out else ""}
    return _with_transcript(event, go)


def save_handoff(event: Dict[str, Any], judge_fn=judge) -> Dict[str, Any]:
    def go(sid: str, cwd: str, path: str) -> Dict[str, Any]:
        return {"line": handoff.run(cwd, path, judge_fn).replace("Now run /clear.", "Now type /new.")}
    return _with_transcript(event, go)


def main(argv: List[str]) -> Dict[str, Any]:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd not in ("compact", "handoff"):
        return {"error": "usage: opencode_session.py compact|handoff"}
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
        if not isinstance(event, dict):
            raise ValueError("not an object")
        return compact(event) if cmd == "compact" else save_handoff(event)
    except Exception as e:
        return {"context": ""} if cmd == "compact" else {"line": "Handoff failed (%s); nothing saved." % type(e).__name__}


if __name__ == "__main__":
    try:
        sys.stdout.write(json.dumps(main(sys.argv)))
    except Exception:
        sys.stdout.write("{}")
    sys.exit(0)
