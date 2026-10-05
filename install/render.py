"""Render shipped files (chain.json, markdown tokens) for the installer."""
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import settings_merge as sm

GATED: Tuple[str, ...] = ("pstack-picks",)
_MARK = re.compile(r"^<!-- (/?)(%s) -->\n?" % "|".join(re.escape(g) for g in GATED), re.M)


def gate_blocks(text: str, comps: Iterable[str]) -> str:
    """Keep the body of each <!-- NAME --> ... <!-- /NAME --> block when NAME is selected, else drop it."""
    on, out, pos, open_name = set(comps), [], 0, None
    for m in _MARK.finditer(text):
        closing, name = m.group(1) == "/", m.group(2)
        if closing != (open_name is not None) or (closing and name != open_name):
            raise ValueError("unbalanced <!-- %s%s --> marker" % (m.group(1), name))
        if not closing:
            out.append(text[pos:m.start()])
            open_name = name
        else:
            if open_name in on:
                out.append(text[pos:m.start()])
            open_name = None
        pos = m.end()
    if open_name is not None:
        raise ValueError("unclosed <!-- %s --> marker" % open_name)
    out.append(text[pos:])
    return "".join(out)


def _installed_stages(cd: Optional[Path]) -> dict:
    p = Path(cd) / "jev" / "chain.json" if cd else None
    try:
        c = json.loads(p.read_text(encoding="utf-8")) if p and p.is_file() else {}
    except (OSError, ValueError):
        return {}
    return c if isinstance(c, dict) else {}


def chain_bytes(f: Path, comps: List[str], mapping: Dict[str, str], cd: Optional[Path] = None) -> bytes:
    c = json.loads(f.read_text(encoding="utf-8"))
    old = _installed_stages(cd)
    for event, stages in c.items():
        for i, st in enumerate(stages):
            comp = st.get("component")
            if comp and comp != "core" and comp not in comps:
                kept = [x for x in old.get(event, []) if isinstance(x, dict) and x.get("name") == st.get("name")]
                if kept:
                    stages[i] = kept[0]  # the user's own stage settings survive a re-install
                    continue
                st["enabled"] = False
            where = "chain.json stage " + str(st.get("name", "?"))
            st["cmd"] = [sm.render_str(str(x), mapping, where) for x in st.get("cmd", [])]
            if "requires_path" in st:
                st["requires_path"] = sm.render_str(str(st["requires_path"]), mapping, where)
    return (json.dumps(c, indent=2) + "\n").encode("utf-8")


def rendered(rel: str, f: Path, comps: List[str], mapping: Dict[str, str], cd: Optional[Path] = None) -> bytes:
    if rel == "jev/chain.json":
        return chain_bytes(f, comps, mapping, cd)
    if rel.endswith(".md"):
        return sm.render_tokens(gate_blocks(f.read_text(encoding="utf-8"), comps), mapping).encode("utf-8")
    return f.read_bytes()
