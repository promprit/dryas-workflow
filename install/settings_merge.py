#!/usr/bin/env python3
"""Merge a Dryas settings fragment into ~/.claude/settings.json and undo exactly what was added.
Never overwrites a value the user already has; such keys are reported as conflicts and not recorded."""
import copy
import difflib
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

_PH = re.compile(r"\$\{?([A-Z_][A-Z0-9_]*)\}?")


def render(fragment: dict, mapping: Dict[str, str]) -> dict:
    out = copy.deepcopy(fragment)
    for k, v in out.get("env", {}).items():
        def sub(m, k=k):
            name = m.group(1)
            if name not in mapping:
                raise ValueError("unmapped placeholder $%s in env %s" % (name, k))
            return mapping[name]
        out["env"][k] = _PH.sub(sub, v)
    return out


def _hook_entries(hooks: dict):
    for ev, groups in hooks.items():
        for g in groups:
            for h in g.get("hooks", []):
                yield ev, g.get("matcher"), h


def merge(settings: dict, fragment: dict) -> Tuple[dict, dict, List[str]]:
    s = copy.deepcopy(settings)
    added = {"env": {}, "allow": [], "deny": [], "hooks": [], "top": {}}
    conflicts = []
    for k, v in fragment.items():
        if k in ("env", "permissions", "hooks"):
            continue
        if k not in s:
            s[k] = v
            added["top"][k] = v
        elif s[k] != v:
            conflicts.append(k)
    env = s.setdefault("env", {}) if fragment.get("env") else s.get("env", {})
    for k, v in fragment.get("env", {}).items():
        if k not in env:
            env[k] = v
            added["env"][k] = v
        elif env[k] != v:
            conflicts.append("env." + k)
    for kind in ("allow", "deny"):
        rules = fragment.get("permissions", {}).get(kind, [])
        if not rules:
            continue
        cur = s.setdefault("permissions", {}).setdefault(kind, [])
        for r in rules:
            if r not in cur:
                cur.append(r)
                added[kind].append(r)
    have = {(ev, m, h.get("command")) for ev, m, h in _hook_entries(s.get("hooks", {}))}
    for ev, m, h in _hook_entries(fragment.get("hooks", {})):
        if (ev, m, h["command"]) in have:
            continue
        s.setdefault("hooks", {}).setdefault(ev, []).append({**({"matcher": m} if m is not None else {}), "hooks": [h]})
        added["hooks"].append([ev, m, h["command"]])
    return s, added, conflicts


def unmerge(settings: dict, added: dict) -> dict:
    s = copy.deepcopy(settings)
    for k, v in added.get("top", {}).items():
        if s.get(k) == v:
            s.pop(k)
    env = s.get("env", {})
    for k, v in added.get("env", {}).items():
        if env.get(k) == v:
            env.pop(k)
    if "env" in s and not s["env"]:
        s.pop("env")
    perms = s.get("permissions", {})
    for kind in ("allow", "deny"):
        if kind in perms:
            perms[kind] = [r for r in perms[kind] if r not in added.get(kind, [])]
            if not perms[kind]:
                perms.pop(kind)
    if "permissions" in s and not s["permissions"]:
        s.pop("permissions")
    drop = {(ev, m, c) for ev, m, c in added.get("hooks", [])}
    hooks = s.get("hooks", {})
    for ev in list(hooks):
        groups = []
        for g in hooks[ev]:
            g = dict(g, hooks=[h for h in g.get("hooks", []) if (ev, g.get("matcher"), h.get("command")) not in drop])
            if g["hooks"]:
                groups.append(g)
        if groups:
            hooks[ev] = groups
        else:
            hooks.pop(ev)
    if "hooks" in s and not s["hooks"]:
        s.pop("hooks")
    return s


def load_settings(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SystemExit("settings.json is not valid JSON (line %s col %s); nothing changed"
                         % (getattr(e, "lineno", "?"), getattr(e, "colno", "?")))


def diff_text(before: dict, after: dict) -> str:
    a = json.dumps(before, indent=2, sort_keys=True).splitlines(keepends=True)
    b = json.dumps(after, indent=2, sort_keys=True).splitlines(keepends=True)
    return "".join(difflib.unified_diff(a, b, "settings.json (current)", "settings.json (after)"))
