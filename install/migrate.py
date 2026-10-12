"""Copy install (files in <config dir>) -> plugin. Data moves before anything is removed; a second run is a no-op."""
import json
import os
import shutil
from pathlib import Path
from typing import Dict, List

import dryas_install as di

STATE_DIRS = ("logs", "handoff", "compact")
SHIPPED = Path(__file__).resolve().parents[1] / "claude" / "jev" / "thresholds.json"
LOCAL_DOC = "docs/dryas-local.md"


def is_copy_install(cd: Path) -> bool:
    if not (Path(cd) / di.RECORD).exists():
        return False
    try:
        rec = di.load_record(Path(cd))
    except (OSError, ValueError):
        return False
    hooks = rec.get("settings", {}).get("hooks", [])
    return bool(rec.get("claude_md")) or "jev" in rec.get("mcp", []) or \
        any("/jev/chain.py" in str(h[-1]).replace("\\", "/") for h in hooks if h)


def _merge_tree(src: Path, dst: Path, msgs: List[str]) -> None:
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        out = dst / f.relative_to(src)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists() and f.suffix == ".jsonl":
            with open(str(out), "ab") as o:
                o.write(f.read_bytes())
            msgs.append("appended %s" % out)
        elif out.exists():
            msgs.append("kept %s (already present); ignored %s" % (out, f))
        else:
            shutil.copy2(str(f), str(out))


def _overrides(old: dict, shipped: dict) -> dict:
    out = {}
    for sec, vals in old.items():
        if isinstance(vals, dict):
            ship = shipped.get(sec) if isinstance(shipped.get(sec), dict) else {}
            diff = {k: v for k, v in vals.items() if ship.get(k) != v}
            if diff:
                out[sec] = diff
        elif shipped.get(sec) != vals:
            out[sec] = vals
    return out


def move_state(cd: Path, root: Path) -> List[str]:
    src, dst, msgs = Path(cd) / "jev", Path(root) / "jev", []
    for d in STATE_DIRS:
        if (src / d).is_dir():
            _merge_tree(src / d, dst / d, msgs)
    old = src / "thresholds.json"
    if old.is_file():
        try:
            data = _overrides(json.loads(old.read_text(encoding="utf-8")), json.loads(SHIPPED.read_text(encoding="utf-8")))
        except (OSError, ValueError, AttributeError):
            data = None
        new = dst / "thresholds.json"
        if data is None:
            msgs.append("ignored unreadable %s" % old)
        elif new.exists() and new.stat().st_mtime >= old.stat().st_mtime:
            msgs.append("kept %s (newer); ignored %s" % (new, old))
        elif data:
            new.parent.mkdir(parents=True, exist_ok=True)
            new.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            os.utime(str(new), (old.stat().st_mtime,) * 2)
            msgs.append("moved your /tune values to %s" % new)
    doc_src, doc_dst = Path(cd) / LOCAL_DOC, Path(root) / LOCAL_DOC
    if doc_src.is_file():
        if doc_dst.exists():
            msgs.append("kept %s (already present); ignored %s" % (doc_dst, doc_src))
        else:
            doc_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(doc_src), str(doc_dst))
            msgs.append("copied your local notes to %s (original kept)" % doc_dst)
    return msgs


def stage_settings(cd: Path) -> Dict[str, Dict[str, dict]]:
    try:
        old = json.loads((Path(cd) / "jev" / "chain.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}  # type: Dict[str, Dict[str, dict]]
    for event, stages in (old.items() if isinstance(old, dict) else []):
        for st in stages if isinstance(stages, list) else []:
            if isinstance(st, dict) and st.get("name") and st.get("component") not in (None, "core") \
                    and isinstance(st.get("enabled", True), bool):
                out.setdefault(event, {})[st["name"]] = {"enabled": st.get("enabled", True)}
    return out


def migrate(cd: Path, root: Path) -> int:
    """Steps 1-3: move state, carry stage settings into chain.local.json, uninstall the copy. Setup (step 4) is the caller's."""
    cd, root = Path(cd), Path(root)
    if not is_copy_install(cd):
        return 0
    print("Migrating the copy install in %s to the plugin" % cd)
    for m in move_state(cd, root):
        print("  " + m)
    stages = stage_settings(cd)
    if stages:
        p = root / "chain.local.json"
        try:
            loc = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except ValueError:
            loc = {}
        loc = loc if isinstance(loc, dict) else {}
        if not isinstance(loc.get("stages"), dict):
            loc["stages"] = {}
        for event, by_name in stages.items():
            ev = loc["stages"].get(event)
            ev = loc["stages"][event] = ev if isinstance(ev, dict) else {}
            for name, v in by_name.items():
                if not isinstance(ev.get(name), dict):
                    ev[name] = {}
                ev[name].update(v)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(loc, indent=2) + "\n", encoding="utf-8")
    return di.uninstall(cd)
