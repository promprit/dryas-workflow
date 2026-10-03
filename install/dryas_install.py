#!/usr/bin/env python3
"""Dryas Workflow installer core: copy files, render chain, merge settings, CLAUDE.md block, MCP, record, uninstall."""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ruflo_helpers  # noqa: E402
import settings_merge as sm  # noqa: E402

RECORD = ".dryas-installed.json"
SKIP = {"settings.fragment.json", "CLAUDE.md.template"}
START, END = "<!-- dryas:start -->", "<!-- dryas:end -->"
PY = "/usr/bin/python3"
SHIM_LINK = "ruflo/mcp-shim/dist"
KEY_LINE = ("Jev needs OPENROUTER_API_KEY in your shell profile: export OPENROUTER_API_KEY=...  "
            "(not stored by this installer)")


def run(argv: List[str]) -> int:
    try:
        return subprocess.call(argv)
    except OSError:
        return 127


def capture(argv: List[str], input_text: Optional[str] = None, env: Optional[dict] = None) -> Tuple[int, str]:
    try:
        p = subprocess.run(argv, input=input_text, capture_output=True, text=True, env=env)
    except OSError:
        return 127, ""
    return p.returncode, p.stdout


def confirm(prompt: str) -> bool:
    try:
        return input(prompt + " [y/N] ").strip().lower() == "y"
    except EOFError:
        return False


def detect() -> Dict[str, str]:
    def sh(c):
        return subprocess.run(["/bin/sh", "-lc", c], capture_output=True, text=True).stdout.strip()
    nm = sh("npm root -g")
    return {"RUFLO_BIN": sh("command -v ruflo"), "RUFLO_JS": os.path.join(nm, "ruflo", "bin", "ruflo.js"),
            "RUFLO_NODE_FALLBACK": sh("command -v node"), "RUFLO_NODE_MODULES": os.path.join(nm, "ruflo", "node_modules"),
            "RUFLO_CLI_DIST": os.path.join(nm, "ruflo", "node_modules", "@claude-flow", "cli", "dist")}


def load_record(cd: Path) -> dict:
    p = cd / RECORD
    if p.exists():
        return json.loads(p.read_text())
    return {"components": [], "files": {}, "settings": {"env": {}, "allow": [], "deny": [], "hooks": [], "top": {}},
            "settings_backup": None, "claude_md": False, "mcp": []}


def save_record(cd: Path, rec: dict) -> None:
    (cd / RECORD).write_text(json.dumps(rec, indent=2) + "\n")


def _plan_files(repo: Path, comps: List[str]):
    src = repo / "claude"
    for f in sorted(p for p in src.rglob("*") if p.is_file() or p.is_symlink()):
        rel = f.relative_to(src).as_posix()
        if rel in SKIP or (rel.startswith("ruflo/") and "ruflo" not in comps):
            continue
        yield rel, f
    wf = repo / "docs" / "workflow.md"
    if wf.exists():
        yield "docs/dryas-workflow.md", wf


def _chain_bytes(f: Path, comps: List[str]) -> bytes:
    c = json.loads(f.read_text())
    for stages in c.values():
        for st in stages:
            comp = st.get("component")
            if comp and comp != "core" and comp not in comps:
                st["enabled"] = False
    return (json.dumps(c, indent=2) + "\n").encode()


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
         data: Optional[bytes] = None, link: Optional[str] = None, mode_src: Optional[Path] = None) -> None:
    dest = cd / rel
    backup = None
    if os.path.lexists(str(dest)):
        if link is not None:
            same = dest.is_symlink() and os.readlink(str(dest)) == link
        else:
            same = not dest.is_symlink() and dest.is_file() and dest.read_bytes() == data
        if same:
            return
        ours = rel in rec["files"]
        if dest.is_dir() and not dest.is_symlink():
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
            dest.unlink()
        else:
            b = cd / (".dryas-backup-" + ts) / rel
            b.parent.mkdir(parents=True, exist_ok=True)
            os.replace(str(dest), str(b))
            backup = str(b)
    elif dry:
        rep["new"].append(rel)
        return
    _mkdirs(cd, dest.parent, rec)
    if link is not None:
        os.symlink(link, str(dest))
    else:
        dest.write_bytes(data)
        if mode_src is not None:
            shutil.copymode(str(mode_src), str(dest))
    rec["files"][rel] = {"backup": backup}
    rep["written"].append(rel)


def copy_files(repo: Path, cd: Path, comps: List[str], rec: dict, force: bool, ts: str, dry: bool = False,
               mapping: Optional[Dict[str, str]] = None) -> dict:
    rep = {"new": [], "replace": [], "written": [], "skipped": []}
    for rel, f in _plan_files(repo, comps):
        if f.is_symlink():
            _put(cd, rel, rec, force, ts, rep, dry, link=os.readlink(str(f)))
        elif rel == "jev/chain.json":
            _put(cd, rel, rec, force, ts, rep, dry, data=_chain_bytes(f, comps), mode_src=f)
        else:
            _put(cd, rel, rec, force, ts, rep, dry, data=f.read_bytes(), mode_src=f)
    if "ruflo" in comps:
        target = (mapping or {}).get("RUFLO_CLI_DIST")
        if target:
            _put(cd, SHIM_LINK, rec, force, ts, rep, dry, link=target)
        else:
            print("warning: could not find the Ruflo CLI dist folder; %s not linked" % SHIM_LINK)
    return rep


def claude_md(cd: Path, template_text: str, rec: dict) -> None:
    p = cd / "CLAUDE.md"
    block = START + "\n" + template_text.strip() + "\n" + END + "\n"
    if not p.exists():
        rec["claude_md_created"] = True
        text = ""
    else:
        rec.setdefault("claude_md_created", False)
        text = p.read_text()
    if START in text and END in text:
        new = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", lambda m: block, text, count=1, flags=re.S)
    else:
        sep = ""
        if text and not text.endswith("\n\n"):
            sep = "\n" if text.endswith("\n") else "\n\n"
        rec["claude_md_sep"] = sep
        new = text + sep + block
    if new != text:
        p.write_text(new)
    rec["claude_md"] = True


def _remove_claude_md(cd: Path, rec: dict) -> None:
    p = cd / "CLAUDE.md"
    if not rec.get("claude_md") or not p.exists():
        return
    text = p.read_text()
    body = re.escape(START) + r".*?" + re.escape(END) + r"\n?"
    sep = rec.get("claude_md_sep", "")
    new, n = re.subn(re.escape(sep) + body, "", text, count=1, flags=re.S) if sep else (text, 0)
    if not n:
        new = re.sub(body, "", text, count=1, flags=re.S)
    if rec.get("claude_md_created") and not new.strip():
        p.unlink()
    elif new != text:
        p.write_text(new)


def _mapping(comps: List[str], home: Path) -> Dict[str, str]:
    m = {"HOME": str(home), "DRYAS_DATA_ROOT": os.environ.get("DRYAS_DATA_ROOT", str(home / ".dryas"))}
    if "ruflo" in comps:
        m.update(detect())
    return m


def _fragment(repo: Path, comps: List[str], mapping: Dict[str, str]) -> dict:
    p = repo / "claude" / "settings.fragment.json"
    if not p.exists():
        return {}
    by_comp = json.loads(p.read_text())
    frag = {}
    for c in comps:
        if by_comp.get(c):
            frag = sm.merge(frag, by_comp[c])[0]
    return sm.render(frag, mapping)


def _unique(p: Path) -> Path:
    n, cand = 0, p
    while cand.exists():
        n += 1
        cand = p.with_name("%s-%d" % (p.name, n))
    return cand


def apply_settings(repo: Path, cd: Path, comps: List[str], rec: dict, home: Path, ts: str = "",
                   mapping: Optional[Dict[str, str]] = None, dry: bool = False) -> None:
    mapping = mapping if mapping is not None else _mapping(comps, home)
    frag = _fragment(repo, comps, mapping)
    path = cd / "settings.json"
    cur = sm.load_settings(path)
    merged, added, conflicts = sm.merge(cur, frag)
    for c in conflicts:
        print("kept your value for %s" % c)
    diff = sm.diff_text(cur, merged)
    if not diff:
        print("settings.json: nothing to change")
        return
    print(diff)
    if dry:
        print("dry run: settings.json not changed")
        return
    if not confirm("Apply these settings changes?"):
        print("settings.json not changed")
        return
    if path.exists():
        b = _unique(cd / ("settings.json.dryas-bak-" + (ts or _ts())))
        shutil.copy2(str(path), str(b))
        if not rec.get("settings_backup"):
            rec["settings_backup"] = str(b)
        rec.setdefault("settings_created", False)
    else:
        rec["settings_created"] = True
    path.write_text(json.dumps(merged, indent=2) + "\n")
    acc = rec.setdefault("settings", {})
    for k, v in added.items():
        if isinstance(v, list):
            acc.setdefault(k, []).extend(x for x in v if x not in acc.get(k, []))
        else:
            acc.setdefault(k, {}).update(v)


def _ts() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def install(repo: Path, cd: Path, comps: List[str], home: Path, force: bool = False, dry: bool = False) -> int:
    repo, cd, home, ts = Path(repo), Path(cd), Path(home), _ts()
    sm.load_settings(cd / "settings.json")  # malformed settings.json aborts here, before any write
    mapping = _mapping(comps, home)
    _fragment(repo, comps, mapping)  # unmapped placeholders abort here too
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
    rec = load_record(cd)
    if dry:
        print("dry run: nothing will be written")
    elif not cd.exists():
        cd.mkdir(parents=True)
        rec["claude_dir_created"] = True
    rep = copy_files(repo, cd, comps, rec, force, ts, dry, mapping)
    for n, (data, mode) in helpers.items():
        _put(cd, "ruflo/helpers/" + n, rec, force, ts, rep, dry, data=data)
        os.chmod(str(cd / "ruflo" / "helpers" / n), mode)
    tpl = repo / "claude" / "CLAUDE.md.template"
    if dry:
        for rel in rep["new"]:
            print("would add: %s" % rel)
        for rel in rep["replace"]:
            print("would replace: %s" % rel)
        if tpl.exists():
            print("would add or update the Dryas block in CLAUDE.md")
    elif tpl.exists():
        claude_md(cd, tpl.read_text(), rec)
    apply_settings(repo, cd, comps, rec, home, ts, mapping, dry)
    if "ruflo" in comps:
        root = Path(mapping["DRYAS_DATA_ROOT"])
        if dry:
            print("would create data root: %s" % root)
        elif not root.exists():
            root.mkdir(parents=True)
            rec["data_root_created"] = True
            rec["data_root"] = str(root)
    if "jev" in comps and "jev" not in rec["mcp"]:
        argv = ["claude", "mcp", "add", "--scope", "user", "jev", "--", PY, str(cd / "jev/jev_mcp.py")]
        if dry:
            print("would run: %s" % " ".join(argv))
        elif run(argv) == 0:
            rec["mcp"].append("jev")
        else:
            print("warning: could not register the jev MCP server; re-run the installer to retry")
    for rel in rep["skipped"]:
        print("kept your file: %s (use --force to replace, original is backed up)" % rel)
    if dry:
        return 0
    rec["components"] = sorted(set(rec["components"]) | set(comps))
    save_record(cd, rec)
    print("installed %d file(s) into %s" % (len(rep["written"]), cd))
    if "jev" in comps:
        print(KEY_LINE)
    return 0


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
        if os.path.lexists(str(dest)) and (dest.is_symlink() or not dest.is_dir()):
            dest.unlink()
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
    _remove_claude_md(cd, rec)
    if spath.exists():
        new = sm.unmerge(cur, rec.get("settings", {}))
        if rec.get("settings_created") and new == {}:
            spath.unlink()
        elif new != cur:
            spath.write_text(json.dumps(new, indent=2) + "\n")
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


def thirdparty(comps: List[str], yes: bool, home: Optional[Path] = None) -> int:
    table = json.loads((HERE / "components.json").read_text())
    sel = [c for c in comps if c in table]
    cmds = [argv for c in sel for argv in table[c]["commands"]]
    if cmds:
        print("Third-party installs:")
        for argv in cmds:
            print("  " + " ".join(argv))
        if yes or confirm("Run these?"):
            for argv in cmds:
                rc = run(argv)
                if rc != 0:
                    print("failed (exit %d): %s" % (rc, " ".join(argv)))
                    return rc
        else:
            print("skipped third-party installs")
    p = Path(home or Path.home()) / ".claude" / "plugins" / "installed_plugins.json"
    try:
        plugins = json.loads(p.read_text()).get("plugins", {})
    except (OSError, ValueError):
        plugins = {}
    for c in sel:
        want, name = table[c]["version"], table[c]["plugin"]
        have = [e.get("version") for e in plugins.get(name, []) if isinstance(e, dict)]
        if want not in have:
            print("warning: %s is %s; Dryas Workflow is tested with %s"
                  % (name, ", ".join(str(h) for h in have) or "not installed", want))
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
    elif run([PY, "-c", "import pytest"]) != 0:
        fails += say("SKIP", "Jev tests", "install pytest to run the Jev tests")
    else:
        fails += say("PASS" if run([PY, "-m", "pytest", "-q", str(tdir)]) == 0 else "FAIL", "Jev tests")
    if "jev" in comps:
        rc, out = capture(["claude", "mcp", "list"])
        fails += say("PASS" if "jev:" in out else "FAIL", "jev MCP server registered")
    if "ruflo" in comps:
        probs = ruflo_helpers.check(cd / "ruflo" / "helpers")
        fails += say("FAIL" if probs else "PASS", "Ruflo helpers patched", "; ".join(probs))
    hook = cd / "hooks" / "pretool-chain.sh"
    wt = Path(tempfile.mkdtemp())
    try:
        (wt / ".orchestrate").mkdir()
        (wt / ".orchestrate" / "PLAN.md").write_text(SMOKE_PLAN)
        (wt / ".orchestrate" / "active.json").write_text(json.dumps({"active": ["1"]}))
        event = {"tool_name": "Write", "tool_input": {"file_path": str(wt / "src/other.ts"), "content": "x"}, "cwd": str(wt)}
        env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_API_KEY"}
        env["HOME"] = str(cd.parent)
        env["JEV_LOG_DIR"] = str(wt / "logs")
        rc, out = capture(["/bin/sh", str(hook)], json.dumps(event), env)
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
    pt = sub.add_parser("thirdparty")
    pt.add_argument("--components", required=True)
    pt.add_argument("--yes", action="store_true")
    pu = sub.add_parser("uninstall")
    pu.add_argument("--claude-dir", required=True)
    pv = sub.add_parser("verify")
    pv.add_argument("--claude-dir", required=True)
    pv.add_argument("--components", required=True)
    a = ap.parse_args(argv)
    comps = [c for c in getattr(a, "components", "").split(",") if c]
    if a.cmd == "install":
        return install(Path(a.repo), Path(a.claude_dir), comps, home=Path.home(), force=a.force, dry=a.dry_run)
    if a.cmd == "thirdparty":
        return thirdparty(comps, a.yes)
    if a.cmd == "uninstall":
        return uninstall(Path(a.claude_dir))
    return 1 if verify(Path(a.claude_dir), comps) else 0


if __name__ == "__main__":
    sys.exit(main())
