"""Upgrade an existing install: find recorded settings entries and files the new version no longer ships."""
import os
from pathlib import Path
from typing import Iterable, List

import platform_util as pu


def stale_settings(recorded: dict, fragment: dict) -> dict:
    """Entries of the installer's settings record that the rendered fragment no longer produces."""
    out = {"env": {}, "allow": [], "deny": [], "hooks": [], "top": {}}
    fenv = fragment.get("env", {})
    for k, v in recorded.get("env", {}).items():
        if fenv.get(k) != v:
            out["env"][k] = v
    perms = fragment.get("permissions", {})
    for kind in ("allow", "deny"):
        out[kind] = [r for r in recorded.get(kind, []) if r not in perms.get(kind, [])]
    have = {(ev, g.get("matcher"), h.get("command"))
            for ev, groups in fragment.get("hooks", {}).items() for g in groups for h in g.get("hooks", [])}
    out["hooks"] = [list(t) for t in recorded.get("hooks", []) if tuple(t) not in have]
    for k, v in recorded.get("top", {}).items():
        if fragment.get(k) != v:
            out["top"][k] = v
    return out


def subtract(recorded: dict, stale: dict) -> dict:
    out = {"env": {k: v for k, v in recorded.get("env", {}).items() if k not in stale["env"]},
           "top": {k: v for k, v in recorded.get("top", {}).items() if k not in stale["top"]}}
    for kind in ("allow", "deny", "hooks"):
        out[kind] = [x for x in recorded.get(kind, []) if x not in stale[kind]]
    return out


def has_any(stale: dict) -> bool:
    return any(stale.get(k) for k in ("env", "allow", "deny", "hooks", "top"))


def stale_files(recorded_files: Iterable[str], shipped: Iterable[str]) -> List[str]:
    keep = set(shipped)
    return sorted(r for r in recorded_files if r not in keep)


def remove_stale_files(cd: Path, rec: dict, shipped: set, dry: bool) -> None:
    for rel in stale_files(rec["files"], shipped):
        if dry:
            print("would remove (no longer shipped): %s" % rel)
            continue
        dest = cd / rel
        try:
            pu.remove_path(str(dest))
        except OSError:
            print("kept (could not remove): %s" % rel)
            continue
        b = rec["files"][rel].get("backup")
        if b and os.path.lexists(b):
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(b, str(dest))
        del rec["files"][rel]
        print("removed (no longer shipped): %s" % rel)
