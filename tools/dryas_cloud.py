#!/usr/bin/env python3
"""dryas cloud: make a GitHub repo work in claude.ai/code cloud sessions with the Dryas workflow (owned core E).

  dryas_cloud.py init   [--repo PATH] [--yes] [--force] [--prefix P] [--with-design] [--with-own NAME]...
                        [--confirm-own NAME]... [--persist-memory] [--claude-dir DIR]
  dryas_cloud.py update [the same options; options left out keep what the manifest records]
  dryas_cloud.py check  [--repo PATH] [--claude-dir DIR]
  dryas_cloud.py remove [--repo PATH] [--yes] [--force]

Also reached as `install.sh --repo PATH` / `install.ps1 -Repo PATH` (init), `dryas cloud ...` and /dryas-cloud.
init, update and remove always print the dry run (every file added, changed or removed, with sizes) and write only
with --yes. Nothing is committed: a run ends with the `git add` line and a suggested message. Preflight: the root of
a git work tree, Python 3.9+, and no uncommitted changes in the paths the run writes (--force skips that check)."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
for _d in (ROOT / "tools", ROOT / "install", ROOT / "claude" / "jev"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
import cloud_check as cc  # noqa: E402
import cloud_config as cfg  # noqa: E402
import cloud_plan as cp  # noqa: E402
import cloud_text as ct  # noqa: E402

CONFIG = (".claude/settings.json", ".mcp.json", "CLAUDE.md", ".gitignore")
KEYS = ("source", "group", "version", "licence", "licence_file", "notice")
_PREFIX = re.compile(r"[a-z0-9-]{0,20}\Z")
Changes = Dict[str, Optional[bytes]]


def parse(argv: List[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="dryas cloud", description="Dryas in claude.ai/code cloud sessions.")
    ap.add_argument("cmd", choices=("init", "check", "update", "remove"))
    ap.add_argument("--repo", default=".")
    ap.add_argument("--yes", action="store_true", help="write; without it the run is a dry run")
    ap.add_argument("--force", action="store_true", help="write over uncommitted changes and hand edits")
    ap.add_argument("--prefix", default=None, help="rename the Dryas copies, for example dryas-")
    ap.add_argument("--with-design", action="store_true", default=None)
    ap.add_argument("--with-own", action="append", default=None, metavar="NAME")
    ap.add_argument("--confirm-own", action="append", default=None, metavar="NAME")
    ap.add_argument("--persist-memory", action="store_true", default=None)
    ap.add_argument("--claude-dir", default=None)
    a = ap.parse_args(argv)
    if a.prefix is not None and not _PREFIX.match(a.prefix):
        ap.error("--prefix takes up to 20 characters of a-z, 0-9 and -")
    return a


def claude_dir(a: argparse.Namespace) -> Path:
    return Path(a.claude_dir or os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude"))


def options(a: argparse.Namespace, old: Any = None) -> Dict[str, Any]:
    old = old if isinstance(old, dict) else {}
    own = [str(n) for n in old.get("own") or []]
    for n in a.with_own or []:
        if n not in own:
            own.append(n)
    return dict(prefix=a.prefix if a.prefix is not None else str(old.get("prefix") or ""),
                design=bool(a.with_design or old.get("design")), own=own, confirm_own=list(a.confirm_own or []),
                persist_memory=bool(a.persist_memory or old.get("persist_memory")))


def _git(repo: Path, *args: str) -> Tuple[int, str]:
    try:
        p = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def roots(rels: Iterable[str]) -> List[str]:
    """Top paths for git: .dryas, each copied skill folder, every other file itself."""
    out: List[str] = []
    for r in sorted(rels):
        parts = r.split("/")
        if parts[0] == ".dryas":
            top = ".dryas"
        elif parts[:2] == [".claude", "skills"] and len(parts) > 3:
            top = "/".join(parts[:3])
        else:
            top = r
        if top not in out:
            out.append(top)
    return out


def preflight(repo: Path, rels: Iterable[str], force: bool) -> List[str]:
    if sys.version_info < (3, 9):
        return ["dryas cloud needs Python 3.9 or newer"]
    rc, out = _git(repo, "rev-parse", "--show-toplevel")
    if rc != 0 or not out.strip():
        return ["%s is not a git work tree" % repo]
    top = Path(out.strip()).resolve()
    if top != repo.resolve():
        return ["%s is not the repo root; run it on %s (cloud sessions read .claude/ and CLAUDE.md there)"
                % (repo, top)]
    rels = list(rels)
    if force or not rels:
        return []
    rc, out = _git(repo, "status", "--porcelain", "--", *roots(rels))
    # __pycache__ is generated (a skill's scripts make one under .claude/skills/, outside the ignored .dryas/)
    dirty = [line[3:] for line in out.splitlines() if line.strip() and "__pycache__" not in line[3:].split("/")]
    if dirty:
        return ["uncommitted changes in %s; commit or stash them, or re-run with --force" % ", ".join(dirty)]
    return []


def _read(repo: Path, rel: str) -> Optional[str]:
    p = repo / rel
    if not p.is_file():
        return None
    try:
        with open(p, encoding="utf-8", newline="") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise cfg.CloudError("%s is not readable (%s); nothing changed" % (rel, e))


def _bytes(texts: Dict[str, Optional[str]]) -> Changes:
    return {r: (t.encode("utf-8") if t is not None else None) for r, t in texts.items()}


def config_new(repo: Path, plan: Dict[str, Any], old: Dict[str, Any]
               ) -> Tuple[Dict[str, Optional[str]], Dict[str, Any], List[str]]:
    """New text of the four config files, the records the manifest keeps, and notes. old: an earlier run's records."""
    cur = {r: _read(repo, r) for r in CONFIG}
    o_s, o_m, o_g = old.get("settings") or {}, old.get("mcp") or {}, old.get("gitignore") or {}
    s_orig = o_s["original"] if "original" in o_s else cur[".claude/settings.json"]
    m_orig = o_m["original"] if "original" in o_m else cur[".mcp.json"]
    s_text = cur[".claude/settings.json"]
    if o_s.get("added"):
        s_text = cfg.remove_settings(s_text, o_s["added"], s_orig)
    hooks_json = json.loads((ROOT / "claude/hooks/hooks.json").read_text(encoding="utf-8"))
    s_new, added, conflicts = cfg.add_settings(s_text, cfg.fragment(hooks_json))
    m_new, entry = cfg.add_mcp(cur[".mcp.json"], o_m.get("entry"))
    rec = dict(old.get("claude_md") or {})
    tpl = (ROOT / "claude/CLAUDE.md.template").read_text(encoding="utf-8")
    c_new = cfg.claude_md(cur["CLAUDE.md"], ct.claude_md_body(tpl, plan["names"], cp.COMPS, plan["version"]), rec)
    g_new, g_rec = cfg.add_gitignore(cur[".gitignore"])
    if o_g:
        g_rec = dict(added=list(o_g.get("added") or []) + g_rec["added"], sep=o_g.get("sep", ""),
                     created=bool(o_g.get("created")))
    texts = {".claude/settings.json": s_new, ".mcp.json": m_new, "CLAUDE.md": c_new, ".gitignore": g_new}
    records = dict(settings=dict(added=added, original=s_orig), mcp=dict(entry=entry, original=m_orig),
                   claude_md=rec, gitignore=g_rec)
    return texts, records, ["kept the repo's own .claude/settings.json value for %s" % k for k in conflicts]


def config_undo(repo: Path, old: Dict[str, Any]) -> Dict[str, Optional[str]]:
    cur = {r: _read(repo, r) for r in CONFIG}
    s, m = old.get("settings") or {}, old.get("mcp") or {}
    return {".claude/settings.json": cfg.remove_settings(cur[".claude/settings.json"], s.get("added") or {},
                                                         s.get("original")),
            ".mcp.json": cfg.remove_mcp(cur[".mcp.json"], m.get("entry"), m.get("original")),
            "CLAUDE.md": cfg.undo_claude_md(cur["CLAUDE.md"], dict(old.get("claude_md") or {})),
            ".gitignore": cfg.remove_gitignore(cur[".gitignore"], old.get("gitignore") or {})}


def manifest_bytes(plan: Dict[str, Any], records: Dict[str, Any], opts: Dict[str, Any],
                   kept: Dict[str, Any]) -> bytes:
    files = {rel: dict({k: e[k] for k in KEYS}, sha256=cc.sha256(e["data"])) for rel, e in plan["files"].items()}
    files.update(kept)  # a kept hand edit keeps its old record, so check goes on reporting the drift
    shas = {r: str((f or {}).get("sha256")) for r, f in files.items()}
    m = dict(format=1, dryas=dict(version=plan["version"], commit=plan["commit"], files_hash=cc.files_hash(shas)),
             options={k: opts[k] for k in ("prefix", "design", "own", "persist_memory")}, files=files, config=records)
    return (json.dumps(m, indent=1, sort_keys=True) + "\n").encode("utf-8")


def clash_message(rels: Iterable[str]) -> str:
    tops = sorted({"/".join(r.split("/")[:3]) if r.startswith(".claude/") else r for r in rels})
    return ("already in the repo and not written by Dryas: %s. Nothing changed. Re-run with --prefix <p> "
            "(for example --prefix dryas-) to rename the Dryas copies" % ", ".join(tops))


def _differs(repo: Path, rel: str, new: Optional[bytes]) -> bool:
    p = repo / rel
    return (p.read_bytes() if p.is_file() else None) != new


def show(repo: Path, changes: Changes, trash: List[Path]) -> None:
    for rel in sorted(changes):
        new, p = changes[rel], repo / rel
        old = p.stat().st_size if p.is_file() else None
        if new is None:
            print("  remove  %s (%d bytes)" % (rel, old or 0))
        elif old is None:
            print("  add     %s (%d bytes)" % (rel, len(new)))
        else:
            print("  change  %s (%d -> %d bytes)" % (rel, old, len(new)))
    for d in trash:
        print("  remove  %s/ (generated, git-ignored)" % d.relative_to(repo).as_posix())


def write(repo: Path, changes: Changes, execs: List[str]) -> None:
    for rel in sorted(changes):
        p, data = repo / rel, changes[rel]
        if data is None:
            if p.is_file():
                p.unlink()
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
    if os.name != "nt":
        for rel in execs:
            os.chmod(str(repo / rel), 0o755)


def prune(repo: Path, rels: Iterable[str]) -> None:
    """Remove the folders a removal left empty, up to the repo root."""
    for rel in rels:
        d = (repo / rel).parent
        while d != repo and repo in d.parents and d.is_dir() and not any(d.iterdir()):
            d.rmdir()
            d = d.parent


def run(a: argparse.Namespace, repo: Path, changes: Changes, plan: Optional[Dict[str, Any]], notes: List[str],
        message: str, trash: Optional[List[Path]] = None) -> int:
    trash = list(trash or [])
    changes = {r: v for r, v in changes.items() if _differs(repo, r, v)}
    probs = preflight(repo, list(changes), a.force)
    if probs:
        for p in probs:
            print("dryas cloud: " + p, file=sys.stderr)
        return 1
    print("dryas cloud %s: %s" % (a.cmd, repo))
    show(repo, changes, trash)
    for line in notes:
        print("  " + line)
    if not changes and not trash:
        print("Nothing to change.")
        return 0
    if not a.yes:
        print("Dry run: nothing written. Re-run with --yes to write these %d changes." % (len(changes) + len(trash)))
        return 0
    files = (plan or {}).get("files", {})
    execs = sorted(r for r, e in files.items() if e.get("exec") and changes.get(r) is not None)
    write(repo, changes, execs)
    for d in trash:
        shutil.rmtree(str(d), ignore_errors=True)
    prune(repo, [r for r, v in changes.items() if v is None] + [d.relative_to(repo).as_posix() for d in trash])
    print("Nothing committed. To commit:")
    print("  git add -A -- %s" % " ".join(roots(changes)))
    for r in execs:
        print("  git add --chmod=+x -- %s" % r)
    print('  git commit -m "%s"' % message)
    return 0


def _manifest(repo: Path) -> Dict[str, Any]:
    try:
        return cc.load_manifest(str(repo))
    except OSError:
        raise cfg.CloudError("no Dryas copy here (%s is missing); run dryas cloud init" % cc.MANIFEST)
    except ValueError as e:
        raise cfg.CloudError("%s is unreadable (%s); nothing changed" % (cc.MANIFEST, e))


def _plan(a: argparse.Namespace, opts: Dict[str, Any]) -> Dict[str, Any]:
    plan = cp.build(ROOT, opts, claude_dir(a))
    cp.finish(plan)
    return plan


def init(a: argparse.Namespace, repo: Path) -> int:
    if (repo / cc.MANIFEST).exists():
        raise cfg.CloudError("this repo already has a Dryas copy (%s); use update or remove" % cc.MANIFEST)
    opts = options(a)
    plan = _plan(a, opts)
    skill_dirs = sorted({"/".join(r.split("/")[:3]) for r in plan["files"] if r.startswith(".claude/skills/")})
    clashes = [r for r in plan["files"] if (repo / r).exists()] + [d for d in skill_dirs if (repo / d).exists()]
    if clashes:
        raise cfg.CloudError(clash_message(clashes))
    texts, records, notes = config_new(repo, plan, {})
    changes: Changes = {r: e["data"] for r, e in plan["files"].items()}
    changes.update(_bytes(texts))
    changes[cc.MANIFEST] = manifest_bytes(plan, records, opts, {})
    notes = (["skipped %s: %s" % s for s in plan["skipped"]] + ["not copied: %s (%s)" % n for n in cp.NOT_COPIED]
             + notes)
    return run(a, repo, changes, plan, notes, "chore: add Dryas %s for cloud sessions" % plan["version"])


def update(a: argparse.Namespace, repo: Path) -> int:
    man = _manifest(repo)
    opts = options(a, man.get("options"))
    plan = _plan(a, opts)
    old = man["files"]
    changes: Changes = {}
    kept: Dict[str, Any] = {}
    clashes: List[str] = []
    for rel, e in sorted(plan["files"].items()):
        cur = cc.file_sha(str(repo / rel))
        if rel in old:
            if cur is not None and cur != (old[rel] or {}).get("sha256") and not a.force:
                kept[rel] = old[rel]
            else:
                changes[rel] = e["data"]
        elif cur is not None and cur != cc.sha256(e["data"]):
            clashes.append(rel)
        else:
            changes[rel] = e["data"]
    if clashes:
        raise cfg.CloudError(clash_message(clashes))
    for rel, e in sorted(old.items()):
        cur = cc.file_sha(str(repo / rel))
        if rel in plan["files"] or cur is None:
            continue
        if cur == (e or {}).get("sha256") or a.force:
            changes[rel] = None
        else:
            kept[rel] = e
    texts, records, cnotes = config_new(repo, plan, man.get("config") or {})
    changes.update(_bytes(texts))
    changes[cc.MANIFEST] = manifest_bytes(plan, records, opts, kept)
    notes = ["kept hand-edited %s (drift; --force replaces it)" % r for r in sorted(kept)]
    notes += ["skipped %s: %s" % s for s in plan["skipped"]] + cnotes
    return run(a, repo, changes, plan, notes, "chore: update the Dryas cloud copy to %s" % plan["version"])


def remove(a: argparse.Namespace, repo: Path) -> int:
    man = _manifest(repo)
    changes: Changes = {}
    kept: List[str] = []
    for rel, e in sorted(man["files"].items()):
        cur = cc.file_sha(str(repo / rel))
        if cur is None:
            continue
        if cur == (e or {}).get("sha256") or a.force:
            changes[rel] = None
        else:
            kept.append(rel)
    changes.update(_bytes(config_undo(repo, man.get("config") or {})))
    changes[cc.MANIFEST] = None
    state = repo / ".dryas" / "state"
    trash = [state] if state.is_dir() else []
    bases = {".dryas"} | {"/".join(r.split("/")[:3]) for r in man["files"] if r.startswith(".claude/skills/")}
    for b in sorted(bases):
        if (repo / b).is_dir():
            trash += [p for p in sorted((repo / b).rglob("__pycache__")) if p.is_dir() and state not in p.parents]
    notes = ["kept hand-edited %s (--force removes it)" % r for r in kept]
    if any((repo / ".dryas" / "memory" / "notes").glob("*.md")):
        notes.append("kept .dryas/memory/notes/*.md (memory notes are the repo's own work)")
    return run(a, repo, changes, None, notes, "chore: remove the Dryas cloud copy", trash)


def check(a: argparse.Namespace, repo: Path) -> int:
    probs = cc.check(str(repo), cp.version(ROOT))
    try:
        man: Optional[Dict[str, Any]] = cc.load_manifest(str(repo))
    except (OSError, ValueError):
        man = None
    if man is not None:
        plan = cp.build(ROOT, options(a, man.get("options")), claude_dir(a))
        old = man["files"]
        stale = sorted(r for r, e in plan["files"].items()
                       if e["group"] == "dryas" and (old.get(r) or {}).get("sha256") != cc.sha256(e["data"]))
        if stale:
            probs.append("out of date: %d files differ from this Dryas checkout (first: %s); run dryas cloud update"
                         % (len(stale), stale[0]))
        d = man.get("dryas") or {}
        print("copy: Dryas %s (%s); this checkout: Dryas %s (%s)"
              % (d.get("version"), str(d.get("commit"))[:12], plan["version"], plan["commit"][:12]))
    for p in probs:
        print(p)
    print("dryas cloud check: %d problem%s" % (len(probs), "" if len(probs) == 1 else "s"))
    return 1 if probs else 0


def main(argv: Optional[List[str]] = None) -> int:
    a = parse(sys.argv[1:] if argv is None else list(argv))
    repo = Path(a.repo).resolve()
    try:
        if a.cmd == "check":
            return check(a, repo)
        probs = preflight(repo, [], True)
        if probs:
            for p in probs:
                print("dryas cloud: " + p, file=sys.stderr)
            return 1
        return {"init": init, "update": update, "remove": remove}[a.cmd](a, repo)
    except cfg.CloudError as e:
        print("dryas cloud: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
