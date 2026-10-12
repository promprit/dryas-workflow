"""Set up Dryas in one Claude config dir: install the plugin, merge model/env/permissions, shared state in ~/.dryas.

  setup(repo, cd, comps, ...)   one dir; run once per account (install.sh --claude-dir <dir>)
  uninstall(cd, purge)          that dir only; ~/.dryas stays unless purge and no other account is listed
"""
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dryas_install as di  # noqa: E402
import platform_util as pu  # noqa: E402
import ruflo_helpers  # noqa: E402
import ruflo_runtime  # noqa: E402
import run_cmd  # noqa: E402
import settings_merge as sm  # noqa: E402

PLUGIN, MARKET = "dryas", "dryas-workflow"
ID = PLUGIN + "@" + MARKET
RECORD = ".dryas-plugin.json"
OPTIONAL = ("jev", "ruflo", "superpowers", "design", "pstack-picks")
WORKFLOW_DOC = ("docs/workflow.md", "docs/dryas-workflow.md")  # repo source -> data root target
REPO = Path(__file__).resolve().parents[1]


def norm(p) -> Path:
    # abspath first: Windows Python 3.9 resolve() mishandles a relative path that does not exist yet
    return Path(os.path.abspath(os.path.expanduser(str(p)))).resolve()


def claude_dir(arg: Optional[str]) -> Path:
    return norm(arg or os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def data_root() -> Path:
    return Path(os.environ.get("DRYAS_DATA_ROOT") or Path.home() / ".dryas")


def child_env(cd: Path) -> Dict[str, str]:
    return dict(os.environ, CLAUDE_CONFIG_DIR=str(cd))


def install_path(cd: Path) -> Optional[str]:
    try:
        data = json.loads((Path(cd) / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        entries = data.get("plugins", {}).get(ID, [])
        paths = [e.get("installPath") for e in entries if isinstance(e, dict) and e.get("installPath")]
        return paths[0] if paths else None
    except (OSError, ValueError, AttributeError):
        return None


def _load_json(p: Path, default):
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
        return v if isinstance(v, type(default)) else default
    except (OSError, ValueError):
        return default


def _save_json(p: Path, v) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, indent=2) + "\n", encoding="utf-8")


def write_chain_local(root: Path, comps: List[str], flowobserve: bool, repo: Optional[Path] = None) -> None:
    """Unselected components: disabled stages and listed in "off". Core stages are never touched.
    Keeps the user's own stage entries; malformed shapes are replaced."""
    p = Path(root) / "chain.local.json"
    loc = _load_json(p, {})
    loc["off"] = sorted(c for c in OPTIONAL if c not in comps)
    chain = json.loads((Path(repo or REPO) / "claude" / "jev" / "chain.json").read_text(encoding="utf-8"))
    stages = loc.get("stages") if isinstance(loc.get("stages"), dict) else {}
    loc["stages"] = stages
    for event, sts in chain.items():
        for st in sts:
            comp, name = st.get("component"), st.get("name")
            if not comp or comp == "core" or not name:
                continue
            if not isinstance(stages.get(event), dict):
                stages[event] = {}
            ev = stages[event]
            if name in ev and not isinstance(ev[name], dict):
                del ev[name]
            if comp == "flowobserve":  # a migrated or user setting stands unless --flowobserve was given
                if flowobserve or "enabled" not in ev.get(name, {}):
                    ev.setdefault(name, {})["enabled"] = bool(flowobserve)
            elif comp in comps:
                if name in ev:
                    ev[name].pop("enabled", None)
                    if not ev[name]:
                        del ev[name]
            else:
                ev.setdefault(name, {})["enabled"] = False
            if not ev:
                del stages[event]
    _save_json(p, loc)


def write_workflow_doc(repo: Path, root: Path) -> None:
    """Copy the repo's workflow reference into the data root, where the injected rules point; only when it differs."""
    src, dest = Path(repo) / WORKFLOW_DOC[0], Path(root) / WORKFLOW_DOC[1]
    try:
        data = src.read_bytes()
    except OSError:
        print("warning: %s not found; %s not updated" % (src, dest))
        return
    try:
        if dest.read_bytes() == data:
            return
    except OSError:
        pass
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def add_account(root: Path, cd: Path) -> None:
    p, cd = Path(root) / "accounts.json", str(norm(cd))
    acc = _load_json(p, {})
    dirs = [d for d in acc.get("claude_dirs", []) if isinstance(d, str)]
    if not any(pu.same_path(d, cd) for d in dirs):
        dirs.append(cd)
    acc["claude_dirs"] = dirs
    _save_json(p, acc)


def remove_account(root: Path, cd: Path) -> List[str]:
    p, cd = Path(root) / "accounts.json", str(norm(cd))
    acc = _load_json(p, {})
    dirs = [d for d in acc.get("claude_dirs", []) if isinstance(d, str) and not pu.same_path(d, cd)]
    if p.exists():
        acc["claude_dirs"] = dirs
        _save_json(p, acc)
    return dirs


def _mcp_python_warning() -> Optional[str]:
    if pu.which("python3"):
        return None
    return ("warning: the Jev MCP server starts with `python3`, which is not on your PATH. "
            "Install Python 3 so `python3` resolves (on Windows: enable the python3 alias or add it to PATH).")


def _mapping(plugin_root, comps: List[str], detected: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """di._mapping with CD = the installed plugin (not the config dir); Ruflo detection reused when given."""
    m = di._mapping([], Path.home(), Path(plugin_root))
    if "ruflo" in comps:
        m.update(detected if detected is not None else di.detect())
    return m


def _ruflo_files(repo: Path, root: Path, mapping: Dict[str, str], yes: bool) -> Optional[List[str]]:
    """Generate the patched helpers and install the Ruflo runtime under the data root; None = failed (reported)."""
    try:
        helpers = ruflo_helpers.patched_helpers(mapping.get("RUFLO_BIN", ""))
    except ruflo_helpers.PatchError as e:
        helpers = di._ruflo_fallback(e, mapping, yes)
        if helpers is None:
            return None
    except ruflo_helpers.HelperError as e:
        print("error: Ruflo helpers: %s" % getattr(e, "detail", e))
        return None
    return ruflo_runtime.install(repo, root, helpers, mapping.get("RUFLO_CLI_DIST", ""))


def setup(repo: Path, cd: Path, comps: List[str], yes: bool, key: str, flowobserve: bool, dry: bool = False) -> int:
    repo, cd, root = Path(repo).resolve(), norm(cd), data_root()
    try:
        sm.load_settings(cd / "settings.json")  # malformed settings.json stops here, before any command runs
    except SystemExit as e:
        print("error: %s: %s" % (cd / "settings.json", e))
        return 1
    rec_path = cd / RECORD
    rec = _load_json(rec_path, {}) or {"components": [], "settings_backup": None,
                                      "settings": {"env": {}, "allow": [], "deny": [], "hooks": [], "top": {}}}
    comps_all = sorted(set(rec.get("components", [])) | set(comps))
    detected = di.detect() if "ruflo" in comps_all else {}
    try:  # render old and new fragments once with a stand-in plugin root: unmapped placeholders abort here
        di._fragment(repo, comps_all, _mapping(rec.get("plugin_root") or repo / "claude", comps_all, detected))
    except ValueError as e:
        print("error: settings fragment: %s; nothing changed" % e)
        return 1
    env = child_env(cd)
    steps = [["claude", "plugin", "marketplace", "add", str(repo), "--scope", "user"],
             ["claude", "plugin", "install", ID, "--scope", "user", "-y"] + (["--config", "openrouter_key=" + key] if key else [])]
    for argv in steps:
        shown = [a if not a.startswith("openrouter_key=") else "openrouter_key=***" for a in argv]
        print("CLAUDE_CONFIG_DIR=%s %s" % (cd, " ".join(shown)))
        if dry:
            continue
        rc = di.run(argv, env=env)
        if rc != 0:
            print("error: `%s` failed (exit %d); %s not changed" % (" ".join(shown[:4]), rc, cd))
            return rc
    if dry:
        return 0
    plugin_root = install_path(cd)
    if not plugin_root:
        print("error: %s is not listed in %s; settings not changed" % (ID, cd / "plugins" / "installed_plugins.json"))
        return 1
    rc = run_cmd.thirdparty([c for c in comps if c in ("ruflo", "design", "superpowers")], yes, cd, env)
    if rc:
        return rc
    mapping = _mapping(plugin_root, comps_all, detected)  # covers old components too, so stale entries render
    if "ruflo" in comps:
        wrote = _ruflo_files(repo, root, mapping, yes)
        if wrote is None:
            return 1
        rec["data_files"] = sorted(set(rec.get("data_files", [])) | set(wrote))
    try:
        # comps_all=comps: entries of deselected components are stale and come out of settings.json
        ok = di.apply_settings(repo, cd, comps, rec, Path.home(), mapping=mapping, yes=yes, comps_all=comps)
    except ValueError as e:
        print("error: settings fragment: %s; settings not changed" % e)
        return 1
    if not ok:
        return 1
    rec["components"] = sorted(set(comps))
    rec["plugin_root"] = plugin_root
    _save_json(rec_path, rec)
    write_workflow_doc(repo, root)
    write_chain_local(root, comps, flowobserve, repo)
    add_account(root, cd)
    warn = _mcp_python_warning() if "jev" in comps else None
    if warn:
        print(warn)
    print("Dryas set up in %s (plugin at %s, state in %s)" % (cd, plugin_root, root))
    return 0


def verify(cd: Path, comps: List[str]) -> int:
    """PASS/FAIL/SKIP lines for one config dir's plugin install; returns the number of failures."""
    cd, fails = norm(cd), 0

    def say(status, name, detail=""):
        print("%s  %s%s" % (status, name, ("  (" + detail + ")") if detail else ""))
        return 1 if status == "FAIL" else 0

    listed = cd / "plugins" / "installed_plugins.json"
    root = install_path(cd)
    fails += say("PASS" if root else "FAIL", "%s listed in %s" % (ID, listed))
    if not root:
        print("verify: %d failed" % fails)
        return fails
    root = Path(root)
    rc, out = di.capture(di.PYX + [str(root / "jev" / "rules_inject.py")], "{}", timeout=60)
    try:
        ok = bool(json.loads(out)["hookSpecificOutput"]["additionalContext"])
    except (ValueError, KeyError, TypeError):
        ok = False
    fails += say("PASS" if ok else "FAIL", "rules hook prints SessionStart JSON")
    env = {"CLAUDE_PLUGIN_ROOT": pu.fwd(root), "DRYAS_PY": pu.fwd(di.PY)}
    fails += say("PASS" if di.scope_smoke(root / "jev" / "chain.py", env) else "FAIL",
                 "scope lock blocks an out-of-scope write")
    fails += say(*di.jev_tests(root / "jev" / "tests"))
    print("verify: %d failed" % fails)
    return fails


def uninstall(cd: Path, purge: bool) -> int:
    cd, root = norm(cd), data_root()
    rec_path = cd / RECORD
    if not rec_path.exists():
        print("nothing to uninstall in %s" % cd)
        return 0
    rec = _load_json(rec_path, {})
    spath = cd / "settings.json"
    try:
        cur = sm.load_settings(spath)  # malformed settings.json aborts before anything is removed
    except SystemExit as e:
        print("error: %s: %s; nothing removed" % (spath, e))
        return 1
    argv = ["claude", "plugin", "uninstall", ID, "--scope", "user", "--keep-data"]
    print("CLAUDE_CONFIG_DIR=%s %s" % (cd, " ".join(argv)))
    rc = di.run(argv, env=child_env(cd))
    if rc != 0:  # settings cleanup still runs
        print("warning: `claude plugin uninstall` failed (exit %d); remove %s by hand with /plugin" % (rc, ID))
    if spath.exists():
        new = sm.unmerge(cur, rec.get("settings", {}))
        if rec.get("settings_created") and new == {}:
            spath.unlink()
            print("removed %s (Dryas created it)" % spath)
        elif new != cur:
            spath.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
            print("removed Dryas entries from %s" % spath)
    rec_path.unlink()
    left = remove_account(root, cd)
    if purge and left:
        print("kept %s: still used by %s" % (root, ", ".join(left)))
    elif purge:
        if root.is_dir() and not root.is_symlink():
            shutil.rmtree(str(root))
            print("removed %s" % root)
        elif root.exists() or root.is_symlink():
            print("kept %s: not a plain directory" % root)
    print("uninstalled Dryas from %s" % cd)
    if rec.get("settings_backup"):
        print("settings backup from before the merge (manual fallback): %s" % rec["settings_backup"])
    return 0
