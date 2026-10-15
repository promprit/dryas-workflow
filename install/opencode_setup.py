"""OpenCode edition setup: copy opencode/ into one OpenCode config dir, record what was written, and remove it again.

Record: <dir>/dryas/install.json = {version, py, tiers, files: {rel: sha256}}. Setup refuses to overwrite a file it
did not write (not in the record, no dryas-managed marker, other content) and keeps a file the user edited after setup
as <file>.dryas-old before writing the new one. OpenCode loads plugin/, skill/, command/ and agent/ from the config dir
itself; the plugin adds the jev MCP server when OpenCode loads it, so opencode.json is never edited.
"""
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import dryas_install as di
import plugin_setup as ps

MIN_OPENCODE = (1, 18, 0)
RECORD = "dryas/install.json"
MARK = "<!-- dryas-managed -->"
TIERS = ("fast", "standard", "strong", "frontier")
SKIP_PARTS = ("__pycache__", ".pytest_cache")
LEGACY_SKILLS = (Path(".claude") / "skills", Path(".agents") / "skills")


def opencode_dir(arg: Optional[str]) -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return ps.norm(arg or os.path.join(base, "opencode"))


def opencode_version(text: str) -> Optional[Tuple[int, ...]]:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def installed_version() -> Optional[Tuple[int, ...]]:
    """`opencode --version` as an int tuple; None when it does not run or prints no version."""
    rc, out = di.capture(["opencode", "--version"], timeout=60)
    return opencode_version(out) if rc == 0 else None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _version(repo: Path) -> str:
    return json.loads((Path(repo) / "claude/.claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]


def default_model(od: Path) -> str:
    """The top-level "model" of <dir>/opencode.json; "" when the file is missing, unreadable or JSONC."""
    try:
        v = json.loads((Path(od) / "opencode.json").read_text(encoding="utf-8")).get("model")
    except (OSError, ValueError, AttributeError):
        return ""
    return v if isinstance(v, str) else ""


def planned_files(repo: Path) -> Dict[str, Path]:
    """rel path under the config dir -> source file, for everything opencode/ ships."""
    base, out = Path(repo) / "opencode", {}
    for f in sorted(base.rglob("*")):
        rel = f.relative_to(base)
        if f.is_dir() or f.suffix == ".pyc" or any(p in SKIP_PARTS for p in rel.parts):
            continue
        out[rel.as_posix()] = f
    return out


def render(rel: str, data: bytes, models: Dict[str, str]) -> bytes:
    """Fill the model line of an executor agent; every other file is copied as it is."""
    m = re.fullmatch(r"agent/dryas-executor-(\w+)\.md", rel)
    if not m:
        return data
    model = models.get(m.group(1), "")
    text = data.decode("utf-8").replace("model: {{MODEL}}\n", ("model: %s\n" % model) if model else "")
    return text.encode("utf-8")


def _remove(od: Path, rel: str, sha: str) -> bool:
    """Delete a recorded file unless the user edited it; True when it is gone."""
    p = Path(od) / rel
    if not p.exists():
        return True
    if _sha(p.read_bytes()) != sha:
        return False
    p.unlink()
    d = p.parent
    while d != Path(od) and d.is_dir() and not os.listdir(str(d)):
        d.rmdir()
        d = d.parent
    return True


def _legacy_skill_warning(home: Path) -> None:
    names = ("brainstorm", "orchestrate", "worktree", "verify", "plan")
    for d in LEGACY_SKILLS:
        hits = [n for n in names if (home / d / n / "SKILL.md").is_file()]
        if hits:
            print("warning: OpenCode also loads %s, which holds %s; you may see two copies of these Dryas skills "
                  "(the OpenCode ones are named dryas-<name>)" % (home / d, ", ".join(hits)))


def setup(repo: Path, od: Path, comps: List[str], tiers: Dict[str, str], yes: bool, dry: bool = False) -> int:
    repo, od, root = Path(repo).resolve(), opencode_dir(str(od)), ps.data_root()
    ver = installed_version()
    if ver is None or ver < MIN_OPENCODE:
        print("error: Dryas needs OpenCode %s or newer (found: %s); nothing changed"
              % (".".join(map(str, MIN_OPENCODE)), ".".join(map(str, ver)) if ver else "no opencode --version"))
        return 1
    rec = ps._load_json(od / RECORD, {})
    rec = rec if isinstance(rec, dict) else {}
    old = rec.get("files") if isinstance(rec.get("files"), dict) else {}
    chosen = dict(rec.get("tiers") or {}) if isinstance(rec.get("tiers"), dict) else {}
    chosen.update({t: m for t, m in (tiers or {}).items() if m})
    fallback = default_model(od)
    models = {t: chosen.get(t) or fallback for t in TIERS}
    want: Dict[str, bytes] = {}
    refused = []
    for rel, src in planned_files(repo).items():
        data = render(rel, src.read_bytes(), models)
        dest = od / rel
        if dest.is_file() and rel not in old:
            cur = dest.read_bytes()
            if cur != data and MARK.encode("utf-8") not in cur:
                refused.append(dest)
        want[rel] = data
    if refused:
        print("error: these files exist and were not written by Dryas; move them away and re-run (nothing changed):")
        for p in refused:
            print("  %s" % p)
        return 1
    if dry:
        print("would write %d files into %s" % (len(want), od))
        return 0
    written = {}
    ps._save_json(od / RECORD, {"version": _version(repo), "py": str(di.PY).replace("\\", "/"), "tiers": chosen,
                                "files": {**{r: _sha(d) for r, d in want.items()}, **old}, "partial": True})
    for rel, data in want.items():
        dest = od / rel
        if dest.is_file() and rel in old and _sha(dest.read_bytes()) != old[rel] and dest.read_bytes() != data:
            keep = dest.with_name(dest.name + ".dryas-old")
            n = 0
            while keep.exists():
                n += 1
                keep = dest.with_name("%s.dryas-old.%d" % (dest.name, n))
            keep.write_bytes(dest.read_bytes())
            print("kept your edited %s as %s" % (dest, keep))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        written[rel] = _sha(data)
    for rel in sorted(set(old) - set(written)):
        if not _remove(od, rel, old[rel]):
            print("kept %s (edited after setup; no longer shipped)" % (od / rel))
    ps._save_json(od / RECORD, {"version": _version(repo), "py": str(di.PY).replace("\\", "/"), "tiers": chosen,
                                "files": written})
    ps.write_workflow_doc(repo, root)
    ps.write_chain_local(root, comps, None, repo, od)
    ps.add_account(root, od, "opencode_dirs")
    if len(set(models.values())) <= 1:
        print("warning: every executor tier runs on %s; set --tier-fast, --tier-standard, --tier-strong and "
              "--tier-frontier (provider/model) to give the ladder real steps" % (fallback or "OpenCode's default model"))
    _legacy_skill_warning(Path.home())
    print("Dryas set up in %s (state in %s). Restart OpenCode to load it." % (od, root))
    return 0


def uninstall(od: Path) -> int:
    od = opencode_dir(str(od))
    p = od / RECORD
    if not p.exists():
        print("nothing to uninstall in %s" % od)
        return 0
    rec = ps._load_json(p, {})
    rec = rec if isinstance(rec, dict) else {}
    files = rec.get("files") if isinstance(rec.get("files"), dict) else {}
    kept = [rel for rel, sha in sorted(files.items()) if not _remove(od, rel, sha)]
    if kept:
        rec.pop("partial", None)
        ps._save_json(p, {**rec, "files": {rel: files[rel] for rel in kept}})
    else:
        p.unlink()
        d = od / "dryas"
        if d.is_dir() and not os.listdir(str(d)):
            d.rmdir()
    ps.forget_account(ps.data_root(), od, "opencode_dirs")
    for rel in kept:
        print("kept %s (edited after setup)" % (od / rel))
    print("uninstalled Dryas from %s" % od)
    return 0


def rules_ok(od: Path, env: Optional[dict] = None) -> bool:
    """True when the installed rules hook prints the OpenCode rules."""
    rc, out = di.capture(di.PYX + [str(od / "dryas/jev/rules_inject.py"), "--harness", "opencode"], "{}", env=env,
                         timeout=60)
    try:
        return "Dryas paths:" in json.loads(out)["hookSpecificOutput"]["additionalContext"]
    except (ValueError, KeyError, TypeError):
        return False


def verify(od: Path, comps: List[str]) -> int:
    """PASS/FAIL lines for one OpenCode config dir; returns the number of FAILs."""
    od, fails = opencode_dir(str(od)), 0

    def say(status: str, name: str, detail: str = "") -> int:
        print("%s  %s%s" % (status, name, ("  (" + detail + ")") if detail else ""))
        return 1 if status == "FAIL" else 0

    rec = ps._load_json(od / RECORD, {})
    files = rec.get("files") if isinstance(rec, dict) and isinstance(rec.get("files"), dict) else {}
    fails += say("PASS" if files else "FAIL", "Dryas installed for OpenCode", str(od))
    if not files:
        return fails
    missing = [rel for rel in files if not (od / rel).is_file()]
    fails += say("FAIL" if missing else "PASS", "installed files present", ", ".join(missing[:3]))
    fails += say("PASS" if rules_ok(od) else "FAIL", "rules hook prints the OpenCode rules")
    fails += say("PASS" if di.scope_smoke(od / "dryas/jev/chain.py", {}, harness="opencode") else "FAIL",
                 "scope lock blocks an out-of-scope apply_patch")
    return fails
