#!/usr/bin/env python3
"""Dryas Workflow installer core: copy files, render chain, merge settings, CLAUDE.md block, MCP, record, uninstall."""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import claude_mcp  # noqa: E402
import platform_util as pu  # noqa: E402
import ruflo_helpers  # noqa: E402
import settings_merge as sm  # noqa: E402
import upgrade  # noqa: E402
from render import chain_bytes, gate_blocks, rendered as _rendered  # noqa: E402
from hookcheck import hook_problems  # noqa: E402
from claude_md_block import START, END, claude_md, remove_claude_md  # noqa: E402,F401

RECORD = ".dryas-installed.json"
SKIP = {"settings.fragment.json", "CLAUDE.md.template"}
COMPONENT_DIRS = {"ruflo": ("ruflo/",), "pstack-picks": ("pstack/", "skills/interrogate/", "skills/benchmark-checklist/")}
PY = pu.python_exe()
PYX = [PY, "-X", "utf8"]
USER_DATA = {"jev/thresholds.json"}
SHIM_LINK = "ruflo/mcp-shim/dist"
KEY_LINE = ("Jev needs OPENROUTER_API_KEY in your shell profile: export OPENROUTER_API_KEY=...  "
            "(not stored by this installer)")


def run(argv: List[str], cwd=None) -> int:
    try:
        return subprocess.call(pu.resolve_argv(argv), cwd=cwd)
    except OSError:
        return 127


def capture(argv: List[str], input_text: Optional[str] = None, env: Optional[dict] = None) -> Tuple[int, str]:
    try:
        p = subprocess.run(pu.resolve_argv(argv), input=input_text, capture_output=True, text=True, env=env,
                           encoding="utf-8", errors="replace")
    except OSError:
        return 127, ""
    return p.returncode, p.stdout


def confirm(prompt: str) -> bool:
    try:
        return input(prompt + " [y/N] ").strip().lower() == "y"
    except EOFError:
        return False


def detect() -> Dict[str, str]:
    npm, nm = pu.which("npm"), ""
    if npm:
        rc, out = capture([npm, "root", "-g"])
        nm = out.strip() if rc == 0 else ""

    def under(*parts):
        return os.path.join(nm, *parts) if nm else ""
    return {"RUFLO_BIN": pu.which("ruflo"), "RUFLO_JS": under("ruflo", "bin", "ruflo.js"),
            "RUFLO_NODE_FALLBACK": pu.which("node"), "RUFLO_NODE_MODULES": under("ruflo", "node_modules"),
            "RUFLO_CLI_DIST": under("ruflo", "node_modules", "@claude-flow", "cli", "dist")}


def load_record(cd: Path) -> dict:
    p = cd / RECORD
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"components": [], "files": {}, "settings": {"env": {}, "allow": [], "deny": [], "hooks": [], "top": {}},
            "settings_backup": None, "claude_md": False, "mcp": []}


def save_record(cd: Path, rec: dict) -> None:
    (cd / RECORD).write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")


def _plan_files(repo: Path, comps: List[str]):
    src = repo / "claude"
    for f in sorted(p for p in src.rglob("*") if p.is_file() or p.is_symlink()):
        rel = f.relative_to(src).as_posix()
        if "__pycache__" in rel.split("/") or rel.endswith(".pyc"):
            continue
        if rel in SKIP or any(rel.startswith(d) and c not in comps for c, ds in COMPONENT_DIRS.items() for d in ds):
            continue
        yield rel, f
    wf = repo / "docs" / "workflow.md"
    if wf.exists():
        yield "docs/dryas-workflow.md", wf


def _mkdirs(cd: Path, d: Path, rec: dict) -> None:
    """Create d (under cd) and record every directory this installer created."""
    missing = []
    while not d.exists() and d != cd:
        missing.append(d)
        d = d.parent
    for m in reversed(missing):
        m.mkdir()
        rel = m.relative_to(cd).as_posix()
        if rel not in rec.setdefault("dirs", []):
            rec["dirs"].append(rel)


def _put(cd: Path, rel: str, rec: dict, force: bool, ts: str, rep: dict, dry: bool,
         data: Optional[bytes] = None, link: Optional[str] = None, mode_src: Optional[Path] = None,
         mode: Optional[int] = None, dir_link: bool = False) -> None:
    dest = cd / rel
    backup = None
    if rel in USER_DATA and os.path.lexists(str(dest)):
        return  # user data after the first install (e.g. /tune edits); never overwritten, even with --force
    if os.path.lexists(str(dest)):
        cur_link = pu.read_dir_link(str(dest))
        if link is not None:
            same = cur_link is not None and pu.same_path(cur_link, link)
        else:
            same = cur_link is None and dest.is_file() and dest.read_bytes() == data
        if same:
            if rel not in rec["files"] and not dry:
                entry = {"backup": None, "adopted": True}
                if link is not None:
                    entry["link"] = "symlink"
                rec["files"][rel] = entry
            return
        ours = rel in rec["files"]
        if dest.is_dir() and cur_link is None:
            rep["skipped"].append(rel)
            return
        if not ours and not force:
            rep["skipped"].append(rel)
            return
        if dry:
            rep["replace"].append(rel)
            return
        if ours:
            backup = rec["files"][rel]["backup"]
            pu.remove_path(str(dest))
        else:
            b = cd / (".dryas-backup-" + ts) / rel
            b.parent.mkdir(parents=True, exist_ok=True)
            os.replace(str(dest), str(b))
            backup = str(b)
    elif dry:
        rep["new"].append(rel)
        return
    _mkdirs(cd, dest.parent, rec)
    entry = {"backup": backup}
    if link is not None:
        if dir_link:
            entry["link"] = pu.make_dir_link(link, str(dest))
        else:
            os.symlink(link, str(dest))  # portable-ok: POSIX checkouts only; no shipped file is a symlink
            entry["link"] = "symlink"
    else:
        dest.write_bytes(data)
        if mode_src is not None:
            shutil.copymode(str(mode_src), str(dest))
        if mode is not None:
            os.chmod(str(dest), mode)  # portable-ok: keeps helper exec bit; no-op on Windows
    rec["files"][rel] = entry
    rep["written"].append(rel)


def copy_files(repo: Path, cd: Path, comps: List[str], rec: dict, force: bool, ts: str, dry: bool = False,
               mapping: Optional[Dict[str, str]] = None) -> dict:
    mapping = mapping if mapping is not None else _mapping(comps, Path.home(), cd)
    rep = {"new": [], "replace": [], "written": [], "skipped": []}
    text_comps = sorted(set(rec.get("components", [])) | set(comps))
    for rel, f in _plan_files(repo, comps):
        if f.is_symlink():
            _put(cd, rel, rec, force, ts, rep, dry, link=os.readlink(str(f)))
        else:
            _put(cd, rel, rec, force, ts, rep, dry, data=_rendered(rel, f, text_comps if rel.endswith(".md") else comps, mapping, cd), mode_src=f)
    if "ruflo" in comps:
        target = (mapping or {}).get("RUFLO_CLI_DIST")
        if target:
            _put(cd, SHIM_LINK, rec, force, ts, rep, dry, link=target, dir_link=True)
        else:
            print("warning: could not find the Ruflo CLI dist folder; %s not linked" % SHIM_LINK)
    return rep


def _remove_stale_files(repo: Path, cd: Path, comps_all: List[str], rec: dict, dry: bool) -> None:
    shipped = {rel for rel, _ in _plan_files(repo, comps_all)}
    if "ruflo" in comps_all:
        shipped |= {r for r in rec["files"] if r.startswith("ruflo/helpers/")} | {SHIM_LINK}
    upgrade.remove_stale_files(cd, rec, shipped, dry)


def _mapping(comps: List[str], home: Path, cd: Path) -> Dict[str, str]:
    m = {"HOME": pu.fwd(home), "DRYAS_DATA_ROOT": pu.fwd(os.environ.get("DRYAS_DATA_ROOT", str(Path(home) / ".dryas"))),
         "PY": PY, "CD": pu.fwd(cd),
         "PY_SAFE": pu.fwd(pu.space_free(sys.executable) or ""), "CD_SAFE": pu.fwd(pu.space_free(cd) or "")}
    if "ruflo" in comps:
        m.update(detect())
    return m


def _fragment(repo: Path, comps: List[str], mapping: Dict[str, str]) -> dict:
    p = repo / "claude" / "settings.fragment.json"
    if not p.exists():
        return {}
    by_comp = json.loads(p.read_text(encoding="utf-8"))
    frag = {}
    for c in comps:
        if by_comp.get(c):
            frag = sm.merge(frag, by_comp[c])[0]
    return sm.render(frag, mapping)


def _prevalidate(repo: Path, comps: List[str], mapping: Dict[str, str], cd: Optional[Path] = None) -> None:
    """Render everything once so unmapped placeholders or tokens abort before any write."""
    _fragment(repo, comps, mapping)
    for rel, f in _plan_files(repo, comps):
        if not f.is_symlink() and (rel == "jev/chain.json" or rel.endswith(".md")):
            _rendered(rel, f, comps, mapping, cd)
    tpl = repo / "claude" / "CLAUDE.md.template"
    if tpl.exists():
        gate_blocks(tpl.read_text(encoding="utf-8"), comps)


def _unique(p: Path) -> Path:
    n, cand = 0, p
    while cand.exists():
        n, cand = n + 1, p.with_name("%s-%d" % (p.name, n + 1))
    return cand


def apply_settings(repo: Path, cd: Path, comps: List[str], rec: dict, home: Path, ts: str = "",
                   mapping: Optional[Dict[str, str]] = None, dry: bool = False, yes: bool = False,
                   comps_all: Optional[List[str]] = None) -> bool:
    mapping = mapping if mapping is not None else _mapping(comps, home, cd)
    frag = _fragment(repo, comps, mapping)
    stale = upgrade.stale_settings(rec.get("settings", {}), _fragment(repo, comps_all or comps, mapping))
    path = cd / "settings.json"
    orig = sm.load_settings(path)
    base = sm.unmerge(orig, stale) if upgrade.has_any(stale) else orig
    merged, added, conflicts = sm.merge(base, frag)
    for c in conflicts:
        print("kept your value for %s" % c)
    diff = sm.diff_text(orig, merged)
    if not diff:
        if not dry and upgrade.has_any(stale):
            rec["settings"] = upgrade.subtract(rec.get("settings", {}), stale)
        print("settings.json: nothing to change")
        return True
    print(diff)
    if dry:
        print("dry run: settings.json not changed")
        return False
    if not (yes or confirm("Apply these settings changes?")):
        print("settings.json not changed")
        return False
    if path.exists():
        b = _unique(cd / ("settings.json.dryas-bak-" + (ts or _ts())))
        shutil.copy2(str(path), str(b))
        if not rec.get("settings_backup"):
            rec["settings_backup"] = str(b)
        rec.setdefault("settings_created", False)
    else:
        rec["settings_created"] = True
    path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    rec["settings"] = upgrade.subtract(rec.get("settings", {}), stale)
    acc = rec["settings"]
    for k, v in added.items():
        if isinstance(v, list):
            acc.setdefault(k, []).extend(x for x in v if x not in acc.get(k, []))
        else:
            acc.setdefault(k, {}).update(v)
    return True


def _ts() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def install(repo: Path, cd: Path, comps: List[str], home: Path, force: bool = False, dry: bool = False,
            yes: bool = False, claude: bool = True) -> int:
    repo, cd, home, ts = Path(repo), Path(cd), Path(home), _ts()
    if sys.prefix != sys.base_prefix:
        print("warning: installing with a virtual-environment Python (%s); hooks will break if that environment is "
              "removed. Re-run with a system Python to avoid this." % PY)
    sm.load_settings(cd / "settings.json")  # malformed settings.json aborts here, before any write
    rec = load_record(cd)
    comps_all = sorted(set(rec.get("components", [])) | set(comps))
    mapping = _mapping(comps_all, home, cd)
    _prevalidate(repo, comps, mapping, cd)  # unmapped placeholders or tokens abort here, before any write
    helpers = {}
    if "ruflo" in comps:
        if dry:
            print("would generate Ruflo helpers with: %s" % " ".join(ruflo_helpers.init_argv(mapping.get("RUFLO_BIN", ""))))
        else:
            try:
                helpers = ruflo_helpers.patched_helpers(mapping.get("RUFLO_BIN", ""))
            except ruflo_helpers.HelperError as e:
                print("error: Ruflo helpers: %s" % e)
                return 1
    if dry:
        print("dry run: nothing will be written")
    elif not cd.exists():
        cd.mkdir(parents=True)
        rec["claude_dir_created"] = True
    try:
        rep = copy_files(repo, cd, comps, rec, force, ts, dry, mapping)
        for n, (data, mode) in helpers.items():
            _put(cd, "ruflo/helpers/" + n, rec, force, ts, rep, dry, data=data, mode=mode)
        tpl = repo / "claude" / "CLAUDE.md.template"
        if dry:
            for rel in rep["new"]:
                print("would add: %s" % rel)
            for rel in rep["replace"]:
                print("would replace: %s" % rel)
            if claude and tpl.exists():
                print("would add or update the Dryas block in CLAUDE.md")
        elif claude and tpl.exists():
            claude_md(cd, gate_blocks(tpl.read_text(encoding="utf-8"), comps_all), rec)
        if not claude or apply_settings(repo, cd, comps, rec, home, ts, mapping, dry, yes=yes, comps_all=comps_all):
            _remove_stale_files(repo, cd, comps_all, rec, dry)
        if "ruflo" in comps:
            root = Path(mapping["DRYAS_DATA_ROOT"])
            if dry:
                print("would create data root: %s" % root)
            elif not root.exists():
                root.mkdir(parents=True)
                rec["data_root_created"] = True
                rec["data_root"] = str(root)
        if claude and "jev" in comps:
            claude_mcp.ensure_jev(cd, PYX, rec, run, capture, dry)
        for rel in rep["skipped"]:
            print("kept your file: %s (use --force to replace, original is backed up)" % rel)
    finally:
        if not dry:
            rec["components"] = sorted(set(rec["components"]) | set(comps))
            save_record(cd, rec)
    if dry:
        return 0
    print("installed %d file(s) into %s" % (len(rep["written"]), cd))
    if "jev" in comps:
        print(KEY_LINE)
    return 0


def mapping_for(comps: List[str], home: Path, cd: Path) -> Dict[str, str]:
    return _mapping(comps, home, cd)


def ruflo_env(repo: Path, mapping: Dict[str, str]) -> Dict[str, str]:
    return _fragment(repo, ["ruflo"], mapping).get("env", {})


def _prune(d: Path) -> None:
    for root, dirs, files in os.walk(str(d), topdown=False):
        if not os.listdir(root):
            os.rmdir(root)


def uninstall(cd: Path) -> int:
    cd = Path(cd)
    if not (cd / RECORD).exists():
        print("nothing to uninstall")
        return 0
    rec = load_record(cd)
    spath = cd / "settings.json"
    cur = sm.load_settings(spath)  # malformed settings.json aborts before anything is removed
    for rel, info in rec["files"].items():
        dest = cd / rel
        if info.get("link") or (os.path.lexists(str(dest)) and (dest.is_symlink() or not dest.is_dir())):
            pu.remove_path(str(dest))
        b = info.get("backup")
        if b and os.path.lexists(b):
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(b, str(dest))
    for bd in cd.glob(".dryas-backup-*"):
        if bd.is_dir() and not bd.is_symlink():
            _prune(bd)
    for rel in sorted(rec.get("dirs", []), key=lambda r: r.count("/"), reverse=True):
        d = cd / rel
        if d.is_dir() and not d.is_symlink() and not os.listdir(str(d)):
            d.rmdir()
    remove_claude_md(cd, rec)
    if spath.exists():
        new = sm.unmerge(cur, rec.get("settings", {}))
        if rec.get("settings_created") and new == {}:
            spath.unlink()
        elif new != cur:
            spath.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
    if rec.get("data_root_created") and rec.get("data_root"):
        root = Path(rec["data_root"])
        if root.is_dir() and not os.listdir(str(root)):
            root.rmdir()
        elif root.exists():
            print("kept data root (not empty): %s" % root)
    if "jev" in rec.get("mcp", []):
        run(["claude", "mcp", "remove", "--scope", "user", "jev"])
    (cd / RECORD).unlink()
    if rec.get("claude_dir_created") and cd.is_dir() and not cd.is_symlink() and not os.listdir(str(cd)):
        cd.rmdir()
    print("uninstalled")
    if rec.get("settings_backup"):
        print("settings backup from before the merge (manual fallback): %s" % rec["settings_backup"])
    return 0


SMOKE_PLAN = "## Task 1: a\nGoal: g\nScope:\n- src/feature/**\nDone:\n- d\n"


def verify(cd: Path, comps: List[str]) -> int:
    cd, fails = Path(cd), 0

    def say(status, name, detail=""):
        print("%s  %s%s" % (status, name, ("  (" + detail + ")") if detail else ""))
        return 1 if status == "FAIL" else 0

    tdir = cd / "jev" / "tests"
    if not tdir.is_dir():
        fails += say("SKIP", "Jev tests", "no jev/tests folder")
    elif run(PYX + ["-c", "import pytest"]) != 0:
        fails += say("SKIP", "Jev tests", "install pytest to run the Jev tests")
    else:
        fails += say("PASS" if run(PYX + ["-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(tdir), str(tdir)], cwd=str(tdir)) == 0 else "FAIL", "Jev tests")
    if "jev" in comps:
        rc, out = capture(["claude", "mcp", "list"])
        fails += say("PASS" if "jev:" in out else "FAIL", "jev MCP server registered")
    if "ruflo" in comps:
        probs = ruflo_helpers.check(cd / "ruflo" / "helpers")
        fails += say("FAIL" if probs else "PASS", "Ruflo helpers patched", "; ".join(probs))
    probs = hook_problems(load_record(cd).get("settings", {}).get("hooks", []))
    fails += say("FAIL" if probs else "PASS", "hook commands point at existing files", "; ".join(probs))
    wt = Path(tempfile.mkdtemp())
    try:
        (wt / ".orchestrate").mkdir()
        (wt / ".orchestrate" / "PLAN.md").write_text(SMOKE_PLAN, encoding="utf-8")
        (wt / ".orchestrate" / "active.json").write_text(json.dumps({"active": ["1"]}), encoding="utf-8")
        event = {"tool_name": "Write", "tool_input": {"file_path": str(wt / "src/other.ts"), "content": "x"}, "cwd": str(wt)}
        env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_API_KEY"}
        env["HOME"] = str(cd.parent)
        env["JEV_LOG_DIR"] = str(wt / "logs")
        rc, out = capture(PYX + [str(cd / "jev" / "chain.py"), "pretool"], json.dumps(event), env)
        try:
            ok = json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
        except (ValueError, KeyError, TypeError):
            ok = False
        fails += say("PASS" if ok else "FAIL", "scope lock blocks an out-of-scope write")
    finally:
        shutil.rmtree(str(wt), ignore_errors=True)
    print("verify: %d failed" % fails)
    return fails


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("run", "preflight"):
        import run_cmd
        return run_cmd.main(argv[1:] + (["--preflight-only"] if argv[0] == "preflight" else []))
    ap = argparse.ArgumentParser(prog="dryas_install.py")
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True
    pi = sub.add_parser("install")
    pi.add_argument("--repo", required=True)
    pi.add_argument("--claude-dir", required=True)
    pi.add_argument("--components", required=True)
    pi.add_argument("--force", action="store_true")
    pi.add_argument("--yes", action="store_true")
    pi.add_argument("--dry-run", action="store_true")
    pu = sub.add_parser("uninstall")
    pu.add_argument("--claude-dir", required=True)
    pv = sub.add_parser("verify")
    pv.add_argument("--claude-dir", required=True)
    pv.add_argument("--components", required=True)
    a = ap.parse_args(argv)
    comps = [c for c in getattr(a, "components", "").split(",") if c]
    if a.cmd == "install":
        return install(Path(a.repo), Path(a.claude_dir), comps, home=Path.home(), force=a.force, dry=a.dry_run, yes=a.yes)
    if a.cmd == "uninstall":
        return uninstall(Path(a.claude_dir))
    return 1 if verify(Path(a.claude_dir), comps) else 0


if __name__ == "__main__":
    sys.exit(main())
