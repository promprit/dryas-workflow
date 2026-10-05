#!/usr/bin/env python3
"""Normalise Codex hook events for the chain (chain.py --harness codex).

Codex sends file edits as tool_name "apply_patch" with the patch text in tool_input.command. Each touched
file becomes one synthetic Write event so the existing stages (scope lock, Jev gate) see a file_path.
A patch that cannot be read raises PatchError; the chain denies it (fail closed).
"""
import re
from typing import Any, Dict, List, Tuple

_HDR = re.compile(r"^\*\*\* (Add File|Update File|Delete File|Move to): (.*\S)\s*$")
_FRAME = ("*** Begin Patch", "*** End Patch", "*** End of File")


class PatchError(ValueError):
    pass


def patch_text(tool_input: Any) -> str:
    if not isinstance(tool_input, dict):
        raise PatchError("tool_input is not an object")
    v = tool_input.get("command", tool_input.get("input", tool_input.get("patch")))
    if isinstance(v, list):
        v = "\n".join(str(x) for x in v)
    if not isinstance(v, str):
        raise PatchError("no patch text")
    return v


def patch_files(patch: str) -> List[Tuple[str, str]]:
    """[(path, hunk text)] in patch order. A move yields both the source and the destination."""
    out: List[Tuple[str, List[str]]] = []
    for line in patch.replace("\r\n", "\n").split("\n"):
        bare = line.lstrip()  # an indented header still counts (stricter: may over-match context lines)
        m = _HDR.match(bare)
        if m:
            out.append((m.group(2).strip(), [line]))
        elif out and not bare.startswith(_FRAME):
            out[-1][1].append(line)
    if not out:
        raise PatchError("no file headers")
    return [(p, "\n".join(h).rstrip("\n")) for p, h in out]


def expand(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Events to run the pretool chain on. Raises PatchError for an unusable apply_patch."""
    tool = event.get("tool_name")
    ti = event.get("tool_input")
    if tool == "Bash" and isinstance(ti, dict) and isinstance(ti.get("command"), list):
        e = dict(event)
        e["tool_input"] = dict(ti, command=" ".join(str(x) for x in ti["command"]))
        return [e]
    if tool != "apply_patch":
        return [event]
    out = []
    for path, hunk in patch_files(patch_text(ti)):
        e = {k: v for k, v in event.items() if k not in ("tool_name", "tool_input")}
        e["tool_name"] = "Write"
        e["tool_input"] = {"file_path": path, "content": hunk}
        out.append(e)
    return out
