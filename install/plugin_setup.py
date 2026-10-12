"""Set up Dryas in one Claude config dir: install the plugin, merge model/env/permissions, shared state in ~/.dryas.

  setup(repo, cd, comps, ...)   one dir; run once per account (install.sh --claude-dir <dir>)
  uninstall(cd, purge)          that dir only; ~/.dryas stays unless purge and no other account is listed
"""
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dryas_install as di  # noqa: E402
import platform_util as pu  # noqa: E402
import ruflo_helpers  # noqa: E402
import ruflo_runtime  # noqa: E402
import run_cmd  # noqa: E402

PLUGIN, MARKET = "dryas", "dryas-workflow"
ID = PLUGIN + "@" + MARKET
RECORD = ".dryas-plugin.json"
OPTIONAL = ("jev", "ruflo", "superpowers", "design", "pstack-picks")
WORKFLOW_DOC = ("docs/workflow.md", "docs/dryas-workflow.md")  # repo source -> data root target


def claude_dir(arg: Optional[str]) -> Path:
    return Path(arg or os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


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


def write_chain_local(root: Path, comps: List[str], flowobserve: bool) -> None:
    """Unselected components: disabled stages and listed in "off". Core stages are never touched.
    Keeps the user's own stage entries."""
    p = Path(root) / "chain.local.json"
    loc = _load_json(p, {})
    loc["off"] = sorted(c for c in OPTIONAL if c not in comps)
    chain = json.loads((Path(__file__).resolve().parents[1] / "claude" / "jev" / "chain.json").read_text(encoding="utf-8"))
    stages = loc.get("stages") if isinstance(loc.get("stages"), dict) else {}
    loc["stages"] = stages
    for event, sts in chain.items():
        for st in sts:
            comp, name = st.get("component"), st.get("name")
            if not comp or comp == "core" or not name:
                continue
            ev = stages.setdefault(event, {})
            if comp == "flowobserve":
                ev.setdefault(name, {})["enabled"] = bool(flowobserve)
            elif comp in comps:
                if isinstance(ev.get(name), dict):
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
    data = src.read_bytes()
    try:
        if dest.read_bytes() == data:
            return
    except OSError:
        pass
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def add_account(root: Path, cd: Path) -> None:
    p = Path(root) / "accounts.json"
    acc = _load_json(p, {})
    dirs = [d for d in acc.get("claude_dirs", []) if isinstance(d, str)]
    if str(cd) not in dirs:
        dirs.append(str(cd))
    acc["claude_dirs"] = dirs
    _save_json(p, acc)


def remove_account(root: Path, cd: Path) -> List[str]:
    p = Path(root) / "accounts.json"
    acc = _load_json(p, {})
    dirs = [d for d in acc.get("claude_dirs", []) if isinstance(d, str) and d != str(cd)]
    if p.exists():
        acc["claude_dirs"] = dirs
        _save_json(p, acc)
    return dirs


def _mcp_python_warning() -> Optional[str]:
    if pu.which("python3"):
        return None
    return ("warning: the Jev MCP server starts with `python3`, which is not on your PATH. "
            "Install Python 3 so `python3` resolves (on Windows: enable the python3 alias or add it to PATH).")


def _mapping(plugin_root: str, comps: List[str]) -> Dict[str, str]:
    return di._mapping(comps, Path.home(), Path(plugin_root))  # CD = the installed plugin, not the config dir


def setup(repo: Path, cd: Path, comps: List[str], yes: bool, key: str, flowobserve: bool, dry: bool = False) -> int:
    repo, cd, root = Path(repo).resolve(), Path(cd), data_root()
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
    mapping = _mapping(plugin_root, comps)
    if "ruflo" in comps:
        try:
            helpers = ruflo_helpers.patched_helpers(mapping.get("RUFLO_BIN", ""))
        except ruflo_helpers.HelperError as e:
            print("error: Ruflo helpers: %s" % getattr(e, "detail", e))
            return 1
        ruflo_runtime.install(repo, root, helpers, mapping.get("RUFLO_CLI_DIST", ""))
    rec_path = cd / RECORD
    rec = _load_json(rec_path, {}) or {"components": [], "settings_backup": None,
                                      "settings": {"env": {}, "allow": [], "deny": [], "hooks": [], "top": {}}}
    ok = di.apply_settings(repo, cd, comps, rec, Path.home(), mapping=mapping, yes=yes,
                           comps_all=sorted(set(rec.get("components", [])) | set(comps)))
    if not ok:
        return 1
    rec["components"] = sorted(set(comps))
    rec["plugin_root"] = plugin_root
    _save_json(rec_path, rec)
    write_workflow_doc(repo, root)
    write_chain_local(root, comps, flowobserve)
    add_account(root, cd)
    warn = _mcp_python_warning() if "jev" in comps else None
    if warn:
        print(warn)
    print("Dryas set up in %s (plugin at %s, state in %s)" % (cd, plugin_root, root))
    return 0


def uninstall(cd: Path, purge: bool) -> int:
    raise NotImplementedError  # Task 10
