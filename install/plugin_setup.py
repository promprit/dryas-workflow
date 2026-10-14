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
OFFICIAL_SOURCE = "anthropics/claude-plugins-official"  # marketplace of the superpowers dependency
SUPERPOWERS = "superpowers@claude-plugins-official"
RECORD = ".dryas-plugin.json"
OPTIONAL = ("jev", "ruflo", "superpowers", "design", "pstack-picks")
WORKFLOW_DOC = ("docs/workflow.md", "docs/dryas-workflow.md")  # repo source -> data root target
REPO = Path(__file__).resolve().parents[1]
KEY_VARS = ("OPENROUTER_API_KEY", "DRYAS_OPENROUTER_KEY")


def norm(p) -> Path:
    # abspath first: Windows Python 3.9 resolve() mishandles a relative path that does not exist yet
    return Path(os.path.abspath(os.path.expanduser(str(p)))).resolve()


def claude_dir(arg: Optional[str]) -> Path:
    return norm(arg or os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def data_root() -> Path:
    return Path(os.path.expanduser(os.environ.get("DRYAS_DATA_ROOT") or str(Path.home() / ".dryas")))


def child_env(cd: Path) -> Dict[str, str]:
    return pu.claude_env(cd)


def env_prefix(cd: Path) -> str:
    """"CLAUDE_CONFIG_DIR=<cd> " for printed commands, empty when the default dir leaves it unset."""
    return "CLAUDE_CONFIG_DIR=%s " % cd if "CLAUDE_CONFIG_DIR" in child_env(cd) else ""


def plugin_entry(cd: Path) -> Optional[dict]:
    """dryas@dryas-workflow as `claude plugin list --json` reports it for cd ({} = not listed); None = the call failed."""
    rc, out = di.capture(["claude", "plugin", "list", "--json"], env=child_env(cd), timeout=120)
    try:
        data = json.loads(out) if rc == 0 else None
    except ValueError:
        data = None
    if not isinstance(data, list):
        return None
    return next((p for p in data if isinstance(p, dict) and p.get("id") == ID), {})


def install_path(cd: Path) -> Optional[str]:
    """The plugin root Claude Code runs (CLAUDE_PLUGIN_ROOT): readFromFolder, since a directory marketplace loads
    the plugin in place from the clone; else installPath. installed_plugins.json when the CLI call fails."""
    return _root(cd, plugin_entry(cd))


def _root(cd: Path, entry: Optional[dict]) -> Optional[str]:
    if entry is not None:
        return entry.get("readFromFolder") or entry.get("installPath") or None
    return _recorded_path(cd)


def load_errors(entry: Optional[dict]) -> List[str]:
    """Why dryas does not load, from its plugin list entry; [] = enabled, no errors."""
    if entry is None:
        return ["`claude plugin list --json` failed"]
    if not entry:
        return ["not listed by `claude plugin list`"]
    errs = [str(e) for e in entry.get("errors") or []]
    return errs + ([] if entry.get("enabled") else ["not enabled (run /plugin and enable dryas)"])


def _recorded_path(cd: Path) -> Optional[str]:
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


def write_chain_local(root: Path, comps: List[str], flowobserve: Optional[bool], repo: Optional[Path] = None,
                      cd: Optional[Path] = None) -> None:
    """Unselected components: disabled stages and listed in "off". Core stages are never touched.
    Keeps the user's own stage entries; malformed shapes are replaced. Shared by all accounts and Codex:
    a changed "off" set is reported when another account (other than cd) or Codex uses it."""
    p = Path(root) / "chain.local.json"
    loc = _load_json(p, {})
    old = loc.get("off")
    loc["off"] = sorted(c for c in OPTIONAL if c not in comps)
    _shared_warning(root, old, loc["off"], cd)
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
            if comp == "flowobserve":  # None keeps a migrated or user setting; --flowobserve / --no-flowobserve set it
                if flowobserve is not None or "enabled" not in ev.get(name, {}):
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


def _dirs(acc: dict, key: str) -> List[str]:
    """The string entries of a list in accounts.json; a value that is not a list counts as empty."""
    v = acc.get(key, [])
    return [d for d in v if isinstance(d, str)] if isinstance(v, list) else []


def _codex_dirs(root: Path) -> List[str]:
    return _dirs(_load_json(Path(root) / "accounts.json", {}), "codex_dirs")


def _codex_legacy() -> Optional[str]:
    """Where a legacy Codex copy install (or its ~/.claude runtime copy) is recorded; None = none."""
    import codex_target as ct
    for p in (ct.codex_dir() / ct.RECORD, Path.home() / ".claude" / di.RECORD):
        if p.exists():
            return str(p)
    return None


def _codex_installed() -> Optional[str]:
    """A Codex Dryas install that reads the same data root and chain.local.json: the first CODEX_HOME listed in
    accounts.json ("Codex in <dir>"), else a legacy record's path; None = none."""
    dirs = _codex_dirs(norm(data_root()))
    return ("Codex in %s" % dirs[0]) if dirs else _codex_legacy()


def _shared_warning(root: Path, old, new: List[str], cd: Optional[Path] = None) -> None:
    """chain.local.json is shared by every account and Codex: say what a change of the "off" set does to them.
    cd: the Claude config dir or CODEX_HOME being set up (not named)."""
    if not isinstance(old, list) or sorted(old) == new:
        return
    acc = _load_json(Path(root) / "accounts.json", {})

    def others(key):
        return [d for d in _dirs(acc, key) if not (cd and pu.same_path(d, norm(cd)))]
    users = others("claude_dirs") + ["Codex in %s" % d for d in others("codex_dirs")]
    if not _dirs(acc, "codex_dirs") and _codex_legacy():
        users.append("Codex")
    if not users:
        return
    on, off = sorted(set(old) - set(new)), sorted(set(new) - set(old))
    what = "; ".join(x for x in ("turns on " + ", ".join(on) if on else "", "turns off " + ", ".join(off) if off else "") if x)
    print("warning: component choices are shared (%s): this %s for %s too"
          % (Path(root) / "chain.local.json", what, ", ".join(users)))


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


def add_account(root: Path, cd: Path, key: str = "claude_dirs") -> None:
    """Record a config dir under `key` in accounts.json ("claude_dirs" or "codex_dirs"); other keys are kept."""
    p, cd = Path(root) / "accounts.json", str(norm(cd))
    acc = _load_json(p, {})
    dirs = _dirs(acc, key)
    if not any(pu.same_path(d, cd) for d in dirs):
        dirs.append(cd)
    acc[key] = dirs
    _save_json(p, acc)


def remove_account(root: Path, cd: Path, key: str = "claude_dirs") -> List[str]:
    p, cd = Path(root) / "accounts.json", str(norm(cd))
    acc = _load_json(p, {})
    dirs = [d for d in _dirs(acc, key) if not pu.same_path(d, cd)]
    if p.exists():
        acc[key] = dirs
        _save_json(p, acc)
    return dirs


def forget_account(root: Path, cd: Path, key: str = "claude_dirs") -> None:
    """remove_account, but only while accounts.json is readable (else it is left as it is, with a warning)."""
    acc = Path(root) / "accounts.json"
    try:
        known = isinstance(json.loads(acc.read_text(encoding="utf-8")), dict)
    except (OSError, ValueError):
        known = False
    if known:
        remove_account(root, cd, key)
    elif acc.exists():
        print("warning: %s is unreadable; left as it is" % acc)


def native_rules(frag: dict, root) -> dict:
    """Windows: Claude Code may substitute ${CLAUDE_PLUGIN_ROOT} with backslashes, so each Bash allow rule naming the
    plugin root (forward slashes, pu.fwd) is added again with the root in native form; the rest of the path is kept,
    as in the command text "${CLAUDE_PLUGIN_ROOT}/jev/tune.py". Returns a new fragment."""
    fw = pu.fwd(root)
    nat = fw.replace("/", "\\")
    allow = list(frag.get("permissions", {}).get("allow", []))
    extra = [r.replace(fw + "/", nat + "/") for r in allow if r.startswith("Bash(") and fw + "/" in r]
    out = dict(frag)
    out["permissions"] = dict(frag.get("permissions", {}), allow=allow + [r for r in extra if r not in allow])
    return out


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


def repair_stale_jev(cd: Path, env: Dict[str, str], dry: bool) -> None:
    """Remove the user-scope `jev` MCP server of the old copy install once its jev_mcp.py is gone."""
    found = pu.stale_jev(cd, env)
    if not found:
        return
    path, env = found
    argv = ["claude", "mcp", "remove", "--scope", "user", "jev"]
    print("note: removing the jev MCP server left by the old copy install (%s no longer exists)" % path)
    print("%s%s" % ("CLAUDE_CONFIG_DIR=%s " % env["CLAUDE_CONFIG_DIR"] if env.get("CLAUDE_CONFIG_DIR") else "", " ".join(argv)))
    if dry:
        return
    rc = di.run(argv, env=env)
    if rc != 0:
        print("warning: `%s` failed (exit %d); remove the stale jev MCP server by hand" % (" ".join(argv), rc))


def setup(repo: Path, cd: Path, comps: List[str], yes: bool, key: str, flowobserve: Optional[bool] = None, dry: bool = False) -> int:
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
    if "superpowers" not in comps:
        print("note: Superpowers is not installed; the Dryas process skills cover the loop "
              "(its conflicting skills stay denied if you add it later).")
    # claude-plugins-official hosts the optional superpowers component; an install whose old superpowers dependency
    # never resolved still installs it below.
    steps = [["claude", "plugin", "marketplace", "add", OFFICIAL_SOURCE, "--scope", "user"],
             ["claude", "plugin", "marketplace", "add", str(repo), "--scope", "user"],
             ["claude", "plugin", "install", ID, "--scope", "user", "-y"] + (["--config", "openrouter_key=" + key] if key else [])]
    for argv in steps:
        shown = [a if not a.startswith("openrouter_key=") else "openrouter_key=***" for a in argv]
        print("%s%s" % (env_prefix(cd), " ".join(shown)))
        if dry:
            continue
        rc = di.run(argv, env=env)
        if rc != 0:
            print("error: `%s` failed (exit %d); %s not changed" % (" ".join(shown[:4]), rc, cd))
            return rc
    if dry:
        repair_stale_jev(cd, env, dry)
        return 0
    entry = plugin_entry(cd)
    # an earlier install whose dependency never resolved: re-installing dryas does not retry it, so install it here
    deps = [d.get("dependency") for d in (entry or {}).get("errorDetails") or []
            if isinstance(d, dict) and d.get("type") == "dependency-unsatisfied" and d.get("dependency")]
    for dep in deps:
        argv = ["claude", "plugin", "install", dep, "--scope", "user", "-y"]
        print("%s%s" % (env_prefix(cd), " ".join(argv)))
        di.run(argv, env=env)
    if deps:
        entry = plugin_entry(cd)
    plugin_root = _root(cd, entry)
    if not plugin_root:
        print("error: %s is not installed in %s; settings not changed" % (ID, cd))
        return 1
    errs = load_errors(entry)
    if errs:
        print("error: %s does not load in %s: %s; settings not changed" % (ID, cd, "; ".join(errs)))
        return 1
    repair_stale_jev(cd, env, dry)
    ran = []  # what thirdparty installed: recorded so uninstall can offer to remove it
    rc = run_cmd.thirdparty([c for c in comps if c in ("ruflo", "design", "superpowers")], yes, cd, env, ran=ran)
    old = [c for c in rec.get("thirdparty", []) if isinstance(c, list)]
    rec["thirdparty"] = old + [c for c in ran if c not in old]
    if rc:
        _save_json(rec_path, rec)  # a partial run is still recorded
        return rc
    mapping = _mapping(plugin_root, comps_all, detected)  # covers old components too, so stale entries render
    if "ruflo" in comps:
        wrote = _ruflo_files(repo, root, mapping, yes)
        if wrote is None:
            return 1
        rec["data_files"] = sorted(set(rec.get("data_files", [])) | set(wrote))
    try:
        # comps_all=comps: entries of deselected components are stale and come out of settings.json
        ok = di.apply_settings(repo, cd, comps, rec, Path.home(), mapping=mapping, yes=yes, comps_all=comps,
                               post=(lambda f: native_rules(f, plugin_root)) if pu.IS_WINDOWS else None)
    except ValueError as e:
        print("error: settings fragment: %s; settings not changed" % e)
        return 1
    if not ok:
        return 1
    rec["components"] = sorted(set(comps))
    rec["plugin_root"] = plugin_root
    _save_json(rec_path, rec)
    write_workflow_doc(repo, root)
    write_chain_local(root, comps, flowobserve, repo, cd)
    add_account(root, cd)
    if "jev" in comps and not key and not any((os.environ.get(k) or "").strip() for k in KEY_VARS):
        print("note: Jev needs an OpenRouter key: set OPENROUTER_API_KEY in your shell profile, or run "
              "/plugin configure %s in Claude Code (or re-run with --openrouter-key)." % ID)
    print("Dryas set up in %s (plugin at %s, state in %s)" % (cd, plugin_root, root))
    return 0


def verify(cd: Path, comps: List[str]) -> int:
    """PASS/FAIL/SKIP lines for one config dir's plugin install; returns the number of failures."""
    cd, fails = norm(cd), 0

    def say(status, name, detail=""):
        print("%s  %s%s" % (status, name, ("  (" + detail + ")") if detail else ""))
        return 1 if status == "FAIL" else 0

    entry = plugin_entry(cd)
    root = _root(cd, entry)
    fails += say("PASS" if root else "FAIL", "%s listed in %s" % (ID, cd), root or "")
    errs = load_errors(entry) if root else []
    if root:
        fails += say("FAIL" if errs else "PASS", "dryas loads without errors", "; ".join(errs))
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


OWNED = ("accounts.json", "chain.local.json", "docs", "jev", "ruflo")  # what setup writes under the data root


def _within(a: Path, b: Path) -> bool:
    """True when a equals b or is an ancestor of b."""
    a, b = os.path.normcase(str(a)), os.path.normcase(str(b))
    return b == a or b.startswith(a.rstrip("\\/") + os.sep)


def _purge_refusal(root: Path, cd: Path) -> Optional[str]:
    if root.parent == root:
        return "a filesystem root"
    try:
        cwd = Path.cwd()
    except OSError:  # the current folder was deleted
        cwd = None
    for name, p in (("your home folder", Path.home()), ("the current folder", cwd), ("the config dir", cd)):
        if p is not None and _within(root, norm(p)):
            return "it contains " + name
    return None


def _rm_error(func, path, exc):
    try:  # read-only file: make writable and retry once
        if os.name != "nt":
            os.chmod(path, 0o700)
        func(path)
    except OSError:
        print("kept %s, remove by hand" % path)


def _rm_owned(p: Path) -> None:
    if p.is_symlink() or (p.exists() and not p.is_dir()):
        p.unlink()
    elif p.is_dir():
        link = p / "mcp-shim" / "dist"  # dir link (junction on Windows) to the Ruflo CLI: unlink it, never follow
        if os.path.islink(str(link)) or pu.read_dir_link(str(link)) is not None:
            pu.remove_path(str(link))  # a real dist directory is removed with the rest by rmtree
        shutil.rmtree(str(p), onerror=_rm_error)
    if not os.path.lexists(str(p)):
        print("removed %s" % p)


KEEP = "docs/dryas-local.md"  # the user's own notes: --purge never deletes them


def _remove_extras(cd: Path, rec: dict, extras: List[List[str]]) -> None:
    """Run the confirmed third-party removal commands (failures warn, the uninstall goes on); say how to remove
    what stays: the plugins not removed and the marketplaces, which are never removed here."""
    for argv in extras:
        print(shown(cd, argv))
        rc = di.run(argv, env=child_env(cd))
        if rc != 0:
            print("warning: `%s` failed (exit %d); remove it by hand" % (" ".join(argv), rc))
    left = [c for c in extras_commands(rec, False) if c not in extras]
    if left:
        print("kept the third-party plugins setup installed; to remove them:")
        for argv in left:
            print("  " + shown(cd, argv))
    npm = [c for c in extras_commands(rec, True) if c[:1] == ["npm"] and c not in extras]
    if npm:
        print("kept the global npm package(s) setup installed (every account and Codex share them); to remove them: %s"
              % "; ".join(" ".join(c) for c in npm))
    markets = extras_marketplaces(rec)
    if markets:
        print("their marketplaces stay registered (harmless); to remove them: %s"
              % "; ".join(shown(cd, ["claude", "plugin", "marketplace", "remove", m]) for m in markets))


def _purge(root: Path) -> None:
    for name in OWNED:
        p = root / name
        if name == "docs" and p.is_dir() and not p.is_symlink():
            for child in sorted(p.iterdir()):
                if child.name != Path(KEEP).name:
                    _rm_owned(child)
            try:
                p.rmdir()
                print("removed %s" % p)
            except OSError:
                print("kept %s (your notes)" % (root / KEEP))
        elif os.path.lexists(str(p)):
            _rm_owned(p)
    try:
        root.rmdir()
        print("removed %s" % root)
    except OSError:
        left = sorted(str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*") if not p.is_dir())
        print("kept %s (%s)" % (root, "your notes" if left == [KEEP] else "contains files Dryas did not create"))


def purge_shared() -> bool:
    """--purge without a Claude config dir (Codex-only uninstall): remove the data root only when accounts.json is
    readable and lists no Claude config dir and no CODEX_HOME, and no legacy Codex copy install uses it."""
    raw = data_root()
    root = norm(raw)
    if not os.path.lexists(str(raw)):
        return False
    try:
        acc = json.loads((root / "accounts.json").read_text(encoding="utf-8"))
        if not isinstance(acc, dict) or any(not isinstance(acc.get(k, []), list) for k in ("claude_dirs", "codex_dirs")):
            raise ValueError("not an object with lists")
    except (OSError, ValueError):
        print("kept %s: the list of accounts using it is missing or unreadable" % root)
        return False
    left = [d for k in ("claude_dirs", "codex_dirs") for d in _dirs(acc, k)]
    legacy = _codex_legacy()
    if left:
        why = "still used by " + ", ".join(left)
    elif legacy:
        why = "a Codex copy install uses it (%s); uninstall it first (install.sh --uninstall --harness codex)" % legacy
    else:
        why = "it is a symlink" if raw.is_symlink() else _purge_refusal(root, Path.home() / ".codex")
    if why:
        print("kept %s: %s" % (root, why))
        return False
    _purge(root)
    return True


def shown(cd: Path, argv: List[str]) -> str:
    """A command line as printed: `claude` ones carry the CLAUDE_CONFIG_DIR prefix of cd."""
    return "%s%s" % (env_prefix(cd) if argv[:1] == ["claude"] else "", " ".join(argv))


def extras_commands(rec: dict, last_account: bool) -> List[List[str]]:
    """The commands that undo the third-party installs setup recorded in rec["thirdparty"] (components.json runs):
    `claude plugin uninstall <id>` for each plugin it installed and, only for the last account (the package is
    machine-wide), `npm uninstall -g <pkg>` for each global npm install. Marketplaces are not removed here: a
    marketplace the user installed other plugins from must stay (see extras_marketplaces)."""
    ran = [c for c in rec.get("thirdparty", []) if isinstance(c, list) and all(isinstance(x, str) for x in c)]
    out = []
    for c in ran:
        if c[:3] == ["claude", "plugin", "install"] and len(c) > 3 and ["claude", "plugin", "uninstall", c[3]] not in out:
            out.append(["claude", "plugin", "uninstall", c[3]])
    if last_account:
        for c in ran:
            if c[:3] == ["npm", "install", "-g"] and len(c) > 3 and ["npm", "uninstall", "-g", c[3]] not in out:
                out.append(["npm", "uninstall", "-g", c[3]])
    return out


def extras_marketplaces(rec: dict) -> List[str]:
    """The marketplaces (the `@<name>` of each recorded plugin install) setup added; left for the user to remove."""
    names = []
    for c in rec.get("thirdparty", []):
        if isinstance(c, list) and c[:3] == ["claude", "plugin", "install"] and len(c) > 3 and "@" in str(c[3]):
            m = str(c[3]).split("@", 1)[1]
            if m and m not in names:
                names.append(m)
    return names


def other_accounts(cd: Path, cdx: Optional[Path] = None) -> List[str]:
    """Config dirs and Codex homes listed in accounts.json other than cd (and cdx, uninstalled in the same run)."""
    acc = _load_json(norm(data_root()) / "accounts.json", {})
    cd = norm(cd)
    # entries are stored resolved, but compare resolved anyway: a symlinked temp dir (macOS /var), an 8.3 short
    # name (Windows) or a hand-edited entry must not count as another account forever
    out = [d for d in _dirs(acc, "claude_dirs") if not pu.same_path(str(norm(d)), str(cd))]
    out += [d for d in _dirs(acc, "codex_dirs") if not (cdx is not None and pu.same_path(str(norm(d)), str(norm(cdx))))]
    return out


def purge_plan() -> List[str]:
    """What --purge deletes under the data root (when no other account or Codex home uses it), one path per line."""
    root = norm(data_root())
    paths = []
    for name in OWNED:
        p = root / name
        if name == "docs" and p.is_dir() and not p.is_symlink():
            paths += [c for c in sorted(p.iterdir()) if c.name != Path(KEEP).name]
        elif os.path.lexists(str(p)):
            paths.append(p)
    if not paths:
        return []
    return ["with --purge, when no other Claude config dir or Codex home uses %s:" % root] + \
        ["  %s" % p for p in paths] + ["  (kept: %s)" % (root / KEEP)]


def uninstall_plan(cd: Path, purge: bool) -> List[str]:
    """What uninstall(cd, purge) removes, one line each; [] when there is nothing to remove (no record)."""
    cd = norm(cd)
    rec_path = cd / RECORD
    if not rec_path.exists():
        return []
    rec = _load_json(rec_path, {})
    out = [shown(cd, ["claude", "plugin", "uninstall", ID, "--scope", "user", "--keep-data"])]
    spath = cd / "settings.json"
    if spath.exists():
        out.append(("%s (Dryas created it)" % spath) if rec.get("settings_created")
                   else "the Dryas entries (model, env, permissions, hooks) in %s" % spath)
    out.append(str(rec_path))
    acc = norm(data_root()) / "accounts.json"
    if acc.exists():
        out.append("the entry for %s in %s" % (cd, acc))
    return out + (purge_plan() if purge else [])


def uninstall(cd: Path, purge: bool, extras: Optional[List[List[str]]] = None) -> int:
    """extras: third-party removal commands (from extras_commands) to run after the plugin uninstall; None or []
    leaves the third-party tools in place and prints how to remove them."""
    cd, raw = norm(cd), data_root()
    root = norm(raw)
    rec_path = cd / RECORD
    if not rec_path.exists():
        print("nothing to uninstall in %s" % cd)
        forget_account(root, cd)  # a stale entry must not block --purge forever
        return 0
    rec = _load_json(rec_path, {})
    spath = cd / "settings.json"
    try:
        cur = sm.load_settings(spath)  # malformed settings.json aborts before anything is removed
    except SystemExit as e:
        print("error: %s: %s; nothing removed" % (spath, e))
        return 1
    if not isinstance(cur, dict):
        print("error: %s is not a JSON object; nothing removed" % spath)
        return 1
    argv = ["claude", "plugin", "uninstall", ID, "--scope", "user", "--keep-data"]
    print("%s%s" % (env_prefix(cd), " ".join(argv)))
    rc = di.run(argv, env=child_env(cd))
    if rc != 0:  # settings cleanup still runs
        print("warning: `claude plugin uninstall` failed (exit %d); remove %s by hand with /plugin" % (rc, ID))
    _remove_extras(cd, rec, extras or [])
    added = rec.get("settings") if isinstance(rec, dict) else None
    if not isinstance(added, dict):
        print("warning: %s is unreadable or has no settings entry; %s left untouched and the record kept" % (rec_path, spath))
    else:
        if spath.exists():
            new = sm.unmerge(cur, added)
            if rec.get("settings_created") and new == {}:
                spath.unlink()
                print("removed %s (Dryas created it)" % spath)
            elif new != cur:
                spath.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
                print("removed Dryas entries from %s" % spath)
        rec_path.unlink()
    acc_path = root / "accounts.json"
    try:
        known = isinstance(json.loads(acc_path.read_text(encoding="utf-8")), dict)
    except (OSError, ValueError):
        known = False
    left = None  # None = account list unknown
    if not isinstance(added, dict):  # this dir may still use Dryas: it stays listed
        print("kept %s in %s" % (cd, acc_path))
    elif known:
        left = remove_account(root, cd)
    elif acc_path.exists():
        print("warning: %s is unreadable; left as it is" % acc_path)
    if purge:
        why = None
        if not isinstance(added, dict):
            why = "%s is unreadable, so this dir may still use it" % rec_path
        elif left is None:
            why = "the list of accounts using it is missing or unreadable"
        elif left:
            why = "still used by " + ", ".join(left)
        elif _codex_installed():
            why = "your Codex Dryas install uses it (%s); uninstall Codex first or in the same run (--harness both)" \
                % _codex_installed()
        else:
            why = "it is a symlink" if raw.is_symlink() else _purge_refusal(root, cd)
        if why:
            print("kept %s: %s" % (root, why))
        else:
            _purge(root)
    print("uninstalled Dryas from %s" % cd)
    if rec.get("settings_backup"):
        print("settings backup from before the merge (manual fallback): %s" % rec["settings_backup"])
    return 0
