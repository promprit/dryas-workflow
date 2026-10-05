"""Render shipped files (chain.json, markdown tokens) for the installer."""
import json
from pathlib import Path
from typing import Dict, List, Optional

import settings_merge as sm


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
        return sm.render_tokens(f.read_text(encoding="utf-8"), mapping).encode("utf-8")
    return f.read_bytes()
