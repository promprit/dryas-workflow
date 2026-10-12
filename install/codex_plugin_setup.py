"""Set up the Dryas Codex plugin in one CODEX_HOME: marketplace, plugin, config block, hook trust, shared state.

  setup(repo, cdx, comps, yes)   one CODEX_HOME; run once per Codex account (install.sh --harness codex --codex-dir DIR)
  verify(cdx, comps)             PASS/FAIL/SKIP lines; returns the number of FAILs
  uninstall(cdx)                 that CODEX_HOME only: plugin, trust, our config tables, its accounts entry
  migrate_legacy(cdx, home)      today's Codex copy install in cdx, and its runtime copy in home/.claude, removed
"""
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import codex_appserver as ca  # noqa: E402
import codex_target as ct  # noqa: E402
import codex_toml as tt  # noqa: E402
import dryas_install as di  # noqa: E402
import migrate  # noqa: E402
import platform_util as pu  # noqa: E402
import plugin_setup as ps  # noqa: E402
import ruflo_runtime  # noqa: E402
import settings_merge as sm  # noqa: E402

HERE = Path(__file__).resolve().parent

PLUGIN, MARKET = "dryas", "dryas-workflow"
ID = PLUGIN + "@" + MARKET
RECORD = ".dryas-codex-plugin.json"
MIN_CODEX = (0, 162, 1)
TOML_START, TOML_END = "# >>> dryas plugin >>>", "# <<< dryas plugin <<<"
ENV_VARS = ("OPENROUTER_API_KEY", "DRYAS_OPENROUTER_KEY", "DRYAS_DATA_ROOT")
TRUST_HINT = "Open Codex and run /hooks to review the Dryas hooks; until then the scope lock and Jev hooks do not run."


def codex_home(arg: Optional[str]) -> Path:
    return ps.norm(arg or os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def child_env(cdx: Path) -> Dict[str, str]:
    return dict(os.environ, CODEX_HOME=str(cdx))


def codex_version(text: str) -> Optional[Tuple[int, ...]]:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def python3_ok() -> bool:
    """Plugin MCP and hooks run `python3` (no shell for MCP): it must be on PATH and 3.9+."""
    if not pu.which("python3"):
        return False
    rc, _ = di.capture(["python3", "-c", "import sys; sys.exit(sys.version_info < (3, 9))"], timeout=30)
    return rc == 0


def _json(argv: List[str], cdx: Path):
    rc, out = di.capture(argv, env=child_env(cdx), timeout=120)
    try:
        return json.loads(out) if rc == 0 else None
    except ValueError:
        return None


def marketplaces(cdx: Path) -> Optional[Dict[str, str]]:
    data = _json(["codex", "plugin", "marketplace", "list", "--json"], cdx)
    items = data.get("marketplaces") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return None
    return {m["name"]: str(m.get("root") or m.get("source") or "") for m in items if isinstance(m, dict) and m.get("name")}


def plugin_entry(cdx: Path) -> Optional[dict]:
    data = _json(["codex", "plugin", "list", "--json"], cdx)
    if not isinstance(data, dict) or not isinstance(data.get("installed"), list):
        return None
    return next((p for p in data["installed"] if isinstance(p, dict) and p.get("pluginId") == ID), {})


def manifest_version(repo: Path) -> str:
    return json.loads((Path(repo) / "codex" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]


def cache_root(cdx: Path, version: str) -> Path:
    return Path(cdx) / "plugins" / "cache" / MARKET / PLUGIN / version


def toml_block(comps: List[str], plugin_root, data_root, ruflo_env: Dict[str, str], fallback_py: str) -> str:
    q, lines = ct._q, []  # type: ignore[var-annotated]
    if "jev" not in comps:
        lines += ['[plugins."%s".mcp_servers.jev]' % ID, "enabled = false", ""]
    elif fallback_py:
        args = ["-X", "utf8", pu.fwd(Path(plugin_root) / "jev" / "jev_mcp.py")]
        lines += ["[mcp_servers.jev]", "command = %s" % q(pu.fwd(fallback_py)),
                  "args = [%s]" % ", ".join(q(a) for a in args),
                  "env_vars = [%s]" % ", ".join(q(v) for v in ENV_VARS), ""]
    if "ruflo" in comps:
        args = [pu.fwd(Path(data_root) / "ruflo" / "mcp-shim" / "bin" / "cli.js"), "mcp", "start"]
        env = {k: ruflo_env[k] for k in ct.RUFLO_ENV_KEYS if k in ruflo_env}
        lines += ["[mcp_servers.ruflo]", 'command = "node"', "args = [%s]" % ", ".join(q(a) for a in args)]
        if env:
            lines.append("env = { %s }" % ", ".join("%s = %s" % (k, q(v)) for k, v in sorted(env.items())))
        lines.append("")
    return "\n".join(lines).strip()


KeyPath = tt.KeyPath
norm_header, _lines = tt.norm_header, tt.lines  # shared with codex_toml (trust removal)


def _sections(text: str) -> Dict[KeyPath, List[str]]:
    """Plain tables (not [[arrays]]): key path -> the lines under the header (first occurrence)."""
    secs, cur = {}, None  # type: ignore[var-annotated]
    for line, hdr in _lines(text):
        if hdr:
            cur = None if hdr[1] or hdr[0] in secs else hdr[0]
            if cur is not None:
                secs[cur] = []
        elif cur is not None:
            secs[cur].append(line)
    return secs


def _code(line: str) -> str:
    """The line without a trailing comment (a # inside a quoted string stays)."""
    q, i = "", 0
    while i < len(line):
        c = line[i]
        if q:
            if c == "\\" and q == '"':
                i += 1
            elif c == q:
                q = ""
        elif c in "\"'":
            q = c
        elif c == "#":
            return line[:i]
        i += 1
    return line


def _sig(lines: List[str]) -> List[str]:
    """Key lines compared without whitespace and comments: Codex may re-render a table it moves."""
    return [s for s in (re.sub(r"\s+", "", _code(ln)) for ln in lines) if s]


def _show(path: KeyPath) -> str:
    return "[%s]" % ".".join(k if re.match(r"^[A-Za-z0-9_-]+$", k) else json.dumps(k) for k in path)


def _under(path: KeyPath, owned) -> bool:
    return any(path[:len(o)] == o for o in owned)  # sub-tables and [[arrays]] go with their parent


OUR_TABLES = (("plugins", ID, "mcp_servers", "jev"), ("mcp_servers", "jev"), ("mcp_servers", "ruflo"))


def owned_tables(text: str, recorded: Optional[str]) -> Tuple[set, List[KeyPath]]:
    """(tables setup wrote and may replace, recorded tables changed since). With a record (`recorded` is the body
    last written, not None): exactly its tables, each only while its keys still match what was written. Lost record:
    our known tables that the markers still enclose. Codex drops a marker comment in front of an [mcp_servers.*]
    table when it rewrites that group (0.162.1), so a lone start marker counts to the end of the file and a lone end
    marker back over the directly preceding tables of ours."""
    if recorded is not None:
        have, owned, changed = _sections(text), set(), []
        for path, lines in _sections(recorded).items():
            if path in have:
                if _sig(have[path]) == _sig(lines):
                    owned.add(path)
                else:
                    changed.append(path)
        return owned, changed
    rows = _lines(text)
    marks = [ln.strip() for ln, _ in rows]
    owned, inside, has_start = set(), False, TOML_START in marks
    for i, (_, hdr) in enumerate(rows):
        if marks[i] == TOML_START:
            inside = True
        elif marks[i] == TOML_END:
            if not has_start:
                for _, prev in reversed(rows[:i]):
                    if prev:
                        if prev[0] not in OUR_TABLES:
                            break
                        owned.add(prev[0])
            inside = False
        elif inside and hdr and hdr[0] in OUR_TABLES:
            owned.add(hdr[0])
    return owned, []


def rewrite_config(text: str, body: str, owned) -> str:
    """Pure: config.toml text without the marker lines and the tables in `owned` (key paths; with their keys,
    sub-tables and [[arrays]]; comments are kept, they head the next table), then our block appended at the end
    when `body` is set."""
    out, skip = [], False
    for line, hdr in _lines(text):
        s = line.strip()
        if s in (TOML_START, TOML_END):
            continue
        if hdr:
            skip = _under(hdr[0], owned)
            if skip:
                continue
        if skip and not s.startswith("#"):
            continue
        out.append(line)
    new = "".join(out).rstrip("\r\n")
    if body:
        new += ("\n\n" if new.strip() else "") + TOML_START + "\n" + body.strip() + "\n" + TOML_END
    return new + "\n" if new.strip() else ""


def write_config_block(cfg: Path, body: str, rec: dict) -> bool:
    """Write, rewrite or remove our tables in config.toml. Only tables setup wrote (and nobody changed since) are
    touched; tables Codex or the user add, often right after ours inside the markers, stay. False = nothing written:
    a table we would write is already there and is not ours (reported)."""
    try:
        with open(cfg, encoding="utf-8", newline="") as fh:
            text = fh.read()
    except OSError:
        text = None
    cur = text or ""
    owned, changed = owned_tables(cur, rec.get("toml_body"))
    for path in changed:
        print("warning: %s in %s was changed after Dryas setup wrote it; leaving it as it is" % (_show(path), cfg))
    ours = [h[0] for _, h in _lines(body) if h]
    others = [h[0] for _, h in _lines(cur) if h and not _under(h[0], owned)]
    clash = sorted(set(_show(o) for o in others for w in ours if o[:len(w)] == w))
    if clash:
        print("warning: %s already has %s, not written by Dryas setup" % (cfg, ", ".join(clash)))
        return False
    new = rewrite_config(cur, body, owned) if body or owned else cur
    if new != cur:
        if text is None:
            rec["toml_created"] = True
        cfg.parent.mkdir(parents=True, exist_ok=True)
        with open(cfg, "w", encoding="utf-8", newline="") as fh:
            fh.write(new)
    rec["toml"] = bool(body)
    if body:
        rec["toml_body"] = body.strip()
    else:
        rec.pop("toml_body", None)
    return True


def _event(e: dict) -> str:
    parts = str(e.get("key", "")).split(":")
    return str(e.get("eventName") or (parts[2] if len(parts) > 2 else "?"))


def trust_hooks(cdx: Path, rec: dict, yes: bool) -> bool:
    """Trust the Dryas plugin hooks Codex lists as untrusted or modified, after consent (`yes` answers it), the way
    /hooks does. rec["trusted"] gains {key: hash} for every Dryas hook seen trusted or trusted now (earlier keys
    stay: uninstall removes them). False = something is still untrusted; the /hooks hint was printed."""
    env = child_env(cdx)
    rec["trusted"] = dict(rec.get("trusted") or {})
    try:
        entries = ca.list_hooks(env, str(Path.home()))
    except ca.AppServerError as e:
        print("warning: could not read Codex hooks (%s)" % e)
        print(TRUST_HINT)
        return False
    mine = [e for e in entries if e.get("pluginId") == ID and e.get("key")]
    if not mine:
        print("warning: Codex lists no Dryas hooks in %s" % cdx)
        print(TRUST_HINT)
        return False

    def record(es: List[dict]) -> None:
        rec["trusted"].update({e["key"]: e.get("currentHash") for e in es})

    record([e for e in mine if e.get("trustStatus") == "trusted"])
    todo = ca.untrusted(mine, ID)
    if not todo:
        return True
    print("Codex runs plugin hooks only after you trust them. Dryas hooks in %s:" % cdx)
    for e in todo:
        print("  %s (%s): %s" % (_event(e), e.get("trustStatus"), e.get("command") or e.get("key")))
    if not (yes or di.confirm("Trust these Dryas hooks?")):
        print(TRUST_HINT)
        return False
    try:
        ca.write_trust(env, todo, plugin_id=ID)
    except ca.AppServerError as e:
        print("warning: could not write hook trust (%s)" % e)
        print(TRUST_HINT)
        return False
    record(todo)
    print("Trusted %d Dryas hook%s in %s" % (len(todo), "" if len(todo) == 1 else "s", cdx))
    return True


def legacy_components(cdx: Path) -> Optional[List[str]]:
    """Components of today's Codex copy install in cdx (None when there is none)."""
    p = Path(cdx) / ct.RECORD
    if not p.exists():
        return None
    try:
        comps = json.loads(p.read_text(encoding="utf-8")).get("components", [])
    except (OSError, ValueError, AttributeError):
        comps = []
    return sorted(set(["core"] + [str(c) for c in comps if isinstance(c, str)]))


class LegacyError(Exception):
    pass


def _runtime_users(cdx: Path, home: Path) -> List[Path]:
    """Other CODEX_HOMEs whose copy install still runs the ~/.claude runtime copy (it was always the default one)."""
    out = []
    for d in (ps.norm(Path(home) / ".codex"), codex_home(None)):
        if not pu.same_path(d, ps.norm(cdx)) and (d / ct.RECORD).exists() and d not in out:
            out.append(d)
    return out


def _check_legacy_items(rec: dict) -> None:
    """The element shapes ct.uninstall_codex relies on; a skill name must name one folder in ~/.agents/skills."""
    for n in rec.get("skills", []):
        if not isinstance(n, str) or n in ("", ".", "..") or "/" in n or "\\" in n or ":" in n:
            raise ValueError('"skills" holds %s, not a skill folder name' % json.dumps(n))
    for n, b in rec.get("skill_backups", {}).items():
        if b is not None and not isinstance(b, str):
            raise ValueError('"skill_backups" for %s is not a path' % json.dumps(n))
    hk = rec.get("hooks", {}).get("hooks", [])
    if not isinstance(hk, list) or not all(
            isinstance(h, list) and len(h) == 3 and isinstance(h[0], str) and isinstance(h[2], str)
            and (h[1] is None or isinstance(h[1], str)) for h in hk):
        raise ValueError('"hooks" is not a list of [event, matcher, command]')
    if not all(isinstance(v, str) for v in rec.get("mcp", {}).values()):
        raise ValueError('"mcp" values are not strings')


def legacy_problem(cdx: Path, home: Path) -> str:
    """Why the legacy Codex copy install (or its ~/.claude runtime copy) cannot be removed safely; "" = it can.
    Checked before setup changes anything."""
    cdx, cd = Path(cdx), Path(home) / ".claude"
    p = cdx / ct.RECORD
    if p.exists():
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(rec, dict):
                raise ValueError("not a JSON object")
            for k, t in (("skills", list), ("skill_backups", dict), ("hooks", dict), ("mcp", dict)):
                if not isinstance(rec.get(k, t()), t):
                    raise ValueError('"%s" is not a %s' % (k, t.__name__))
            _check_legacy_items(rec)
        except (OSError, ValueError) as e:
            return "%s cannot be read (%s)" % (p, e)
        try:
            sm.load_settings(cdx / "hooks.json")
        except SystemExit:
            return "%s is not valid JSON" % (cdx / "hooks.json")
    if (cd / di.RECORD).exists() and not migrate.is_copy_install(cd):
        err = migrate.check(cd)
        if err:
            return "the Codex runtime copy in %s: %s" % (cd, err)
    return ""


def migrate_legacy(cdx: Path, home: Path, dry: bool = False) -> List[str]:
    """Today's Codex copy install -> nothing (the plugin replaces it): uninstall it from cdx, then drop the Codex-only
    runtime copy in home/.claude after moving any state it still holds to the data root (as the Claude migration does;
    a re-run does not merge twice). A live Claude copy install there is left for the Claude migration. Raises
    LegacyError when a step fails; re-running setup resumes (the legacy record goes last)."""
    cdx, home = Path(cdx), Path(home)
    msgs = []  # type: List[str]
    if (cdx / ct.RECORD).exists():
        if dry:
            msgs.append("would remove the Codex copy install in %s (the plugin replaces it)" % cdx)
        else:
            print("Removing the Codex copy install in %s (the plugin replaces it)" % cdx)
            try:
                ct.uninstall_codex(cdx, home, lambda argv: di.run(argv, env=child_env(cdx)))
            except (Exception, SystemExit) as e:  # any failure: keep the record, the user gets "fix and re-run"
                raise LegacyError("removing the Codex copy install in %s failed: %s" % (cdx, e))
            msgs.append("removed the Codex copy install in %s" % cdx)
    cd = home / ".claude"
    if (cd / di.RECORD).exists():
        users = _runtime_users(cdx, home)
        if migrate.is_copy_install(cd):
            msgs.append("Claude Code still uses the copy install in %s; kept (install.sh --harness claude or both "
                        "moves it to the plugin)" % cd)
        elif users:
            msgs.append("kept the Codex runtime copy in %s: the Codex copy install in %s still uses it; run setup "
                        "for that CODEX_HOME too" % (cd, ", ".join(map(str, users))))
        elif dry:
            msgs.append("would remove the Codex runtime copy in %s (no longer needed)" % cd)
        else:
            if migrate.migrate(cd, ps.data_root(), runtime_copy=True):
                raise LegacyError("removing the Codex runtime copy in %s failed" % cd)
            msgs.append("removed the Codex runtime copy in %s (no longer needed; state is in %s)" % (cd, ps.data_root()))
    for m in msgs:
        print(m)
    return msgs


def _keep_record(path: Path, rec: dict) -> None:
    """On a failed run, keep what uninstall must undo (a created CODEX_HOME, an added marketplace)."""
    if rec.get("dir_created") or rec.get("marketplace_added"):
        ps._save_json(path, rec)


def _say_run(argv: List[str], cdx: Path, dry: bool) -> int:
    print("CODEX_HOME=%s %s" % (cdx, " ".join(argv)))
    return 0 if dry else di.run(argv, env=child_env(cdx))


def setup(repo: Path, cdx: Path, comps: List[str], yes: bool, dry: bool = False) -> int:
    repo, cdx, root = Path(repo).resolve(), codex_home(str(cdx)), ps.data_root()
    rc, out = di.capture(["codex", "--version"], env=child_env(cdx), timeout=60)
    ver = codex_version(out)
    if ver is None or ver < MIN_CODEX:
        print("error: Dryas needs Codex CLI %s or newer (found: %s); nothing changed"
              % (".".join(map(str, MIN_CODEX)), out.strip() or "no codex --version"))
        return 1
    problem = legacy_problem(cdx, Path.home())
    if problem:
        print("error: %s; fix or remove it and re-run (nothing changed)" % problem)
        return 1
    want = manifest_version(repo)
    mk = marketplaces(cdx) if cdx.exists() else {}  # Codex refuses a CODEX_HOME that does not exist: nothing registered
    if mk is None:
        print("error: `codex plugin marketplace list` failed in %s; nothing changed" % cdx)
        return 1
    if MARKET in mk and not pu.same_path(mk[MARKET], str(repo)):
        print("error: marketplace %s in %s is registered from %s, not %s; remove it with "
              "`codex plugin marketplace remove %s` and re-run (nothing changed)" % (MARKET, cdx, mk[MARKET], repo, MARKET))
        return 1
    rec_path = cdx / RECORD
    rec = ps._load_json(rec_path, {}) or {"components": [], "trusted": {}, "marketplace_added": False}
    if not cdx.exists() and not dry:
        cdx.mkdir(parents=True)
        rec["dir_created"] = True
    if MARKET not in mk:
        rc = _say_run(["codex", "plugin", "marketplace", "add", str(repo)], cdx, dry)
        if rc:
            print("error: `codex plugin marketplace add` failed (exit %d); %s not changed" % (rc, cdx))
            _keep_record(rec_path, rec)
            return rc
        rec["marketplace_added"] = True
    print("CODEX_HOME=%s codex plugin add %s --json" % (cdx, ID))
    if dry:
        migrate_legacy(cdx, Path.home(), dry=True)
        return 0
    rc, out = di.capture(["codex", "plugin", "add", ID, "--json"], env=child_env(cdx), timeout=300)
    try:
        added = json.loads(out) if rc == 0 else {}
    except ValueError:
        added = {}
    entry = plugin_entry(cdx)
    if not isinstance(added, dict) or not added or not entry or not entry.get("enabled") or entry.get("version") != want:
        print("error: %s is not installed and enabled at version %s in %s (plugin add exit %d); config not changed"
              % (ID, want, cdx, rc))
        _keep_record(rec_path, rec)
        return 1
    plugin_root = added.get("installedPath") or str(cache_root(cdx, want))
    try:  # before the config block: the legacy `codex mcp remove jev` must not hit a [mcp_servers.jev] of ours
        migrate_legacy(cdx, Path.home())
    except LegacyError as e:
        _keep_record(rec_path, rec)
        print("error: %s. The plugin is installed but not set up; fix the error above and re-run setup "
              "(it resumes)" % e)
        return 1
    fallback = di.PY if "jev" in comps and not python3_ok() else ""
    renv: Dict[str, str] = {}
    block_comps = list(comps)
    if "ruflo" in comps:
        mapping = ps._mapping(plugin_root, comps)
        dist = mapping.get("RUFLO_CLI_DIST", "")
        if dist and os.path.isdir(dist):
            renv = di.ruflo_env(repo, mapping)
            rec["data_files"] = sorted(set(rec.get("data_files", [])) |
                                       set(ruflo_runtime.install(repo, root, {}, dist)))
        else:
            block_comps.remove("ruflo")
            print("warning: Ruflo is not installed (no %s); [mcp_servers.ruflo] not written. Install it with "
                  "`npm install -g ruflo` and re-run setup" % (dist or "ruflo under `npm root -g`"))
    if not write_config_block(cdx / "config.toml", toml_block(block_comps, plugin_root, root, renv, fallback), rec):
        _keep_record(rec_path, rec)
        print("error: Dryas config entries were not written to %s (see the warning above): remove or rename those "
              "tables and re-run setup; the plugin is installed but not fully set up" % (cdx / "config.toml"))
        return 2
    if fallback:
        print("note: python3 3.9+ is not on PATH; Jev MCP runs with %s (re-run setup after each update)" % fallback)
    trust_hooks(cdx, rec, yes)
    ps._save_json(rec_path, rec)  # trust is written: uninstall must be able to remove it even if a later step fails
    ps.write_workflow_doc(repo, root)
    ps.write_chain_local(root, comps, None, repo, cdx)  # the shared-choices warning names the other accounts only
    ps.add_account(root, cdx, "codex_dirs")
    rec.update(components=sorted(set(comps)), version=want, plugin_root=plugin_root)
    ps._save_json(rec_path, rec)
    if not any((ct.skills_dir(Path.home()) / n).exists() for n in ("superpowers", "brainstorming")):
        print(ct.SP_HINT)
    if "jev" in comps and not (os.environ.get("OPENROUTER_API_KEY") or "").strip():
        print("note: Jev reads OPENROUTER_API_KEY from the shell Codex runs in; set it in your shell profile.")
    print("Dryas set up in %s (plugin at %s, state in %s)" % (cdx, plugin_root, root))
    return 0


def _remove_config(cfg: Path, rec: dict) -> None:
    """Drop the recorded trust keys and the tables setup wrote (only while unchanged) from config.toml; everything
    else in the file stays as it is."""
    try:
        with open(cfg, encoding="utf-8", newline="") as fh:
            text = fh.read()
    except FileNotFoundError:
        return
    except OSError as e:
        print("warning: %s cannot be read (%s); remove the Dryas entries by hand" % (cfg, e))
        return
    owned, changed = owned_tables(text, rec.get("toml_body"))
    for path in changed:
        print("warning: %s in %s was changed after Dryas setup wrote it; left as it is" % (_show(path), cfg))
    new = text
    if owned or any(ln.strip() in (TOML_START, TOML_END) for ln, _ in _lines(text)):
        new = rewrite_config(text, "", owned)  # also drops lone markers: nothing later may claim what they enclose
    # trust after the markers are gone: Codex writes [hooks.state] and the trust tables in front of our end marker
    new, missing = tt.remove_trust(new, sorted(rec.get("trusted") or {}))
    if len(missing) < len(rec.get("trusted") or {}):
        print("removed the Dryas hook trust from %s" % cfg)
    if new == text:
        return
    if not new.strip() and rec.get("toml_created"):
        cfg.unlink()
        print("removed %s (Dryas created it)" % cfg)
        return
    with open(cfg, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
    if owned:
        print("removed the Dryas tables from %s" % cfg)


def uninstall(cdx: Path) -> int:
    """Dryas out of one CODEX_HOME: the plugin, the marketplace (when setup added it), the recorded hook trust and
    the config tables setup wrote, the accounts.json entry, the record. A legacy Codex copy install there goes the
    way setup migrates it (a live Claude copy install is kept). Other CODEX_HOMEs and the data root stay."""
    cdx, home, root = codex_home(str(cdx)), Path.home(), ps.data_root()
    problem = legacy_problem(cdx, home)
    if problem:
        print("error: %s; fix or remove it and re-run (nothing changed)" % problem)
        return 1
    try:
        migrate_legacy(cdx, home)
    except LegacyError as e:
        print("error: %s. Fix the error above and re-run the uninstall (it resumes)" % e)
        return 1
    rec_path = cdx / RECORD
    if not rec_path.exists():
        print("no Dryas plugin install recorded in %s" % cdx)
        return 0
    rec = ps._load_json(rec_path, {})
    if not rec or not isinstance(rec.get("trusted", {}), dict):
        print("error: %s cannot be read; nothing removed (fix or remove it and re-run)" % rec_path)
        return 1
    rc = _say_run(["codex", "plugin", "remove", ID], cdx, False)
    if rc:
        print("warning: `codex plugin remove` failed (exit %d); remove %s by hand (codex plugin remove %s)"
              % (rc, ID, ID))
    if rec.get("marketplace_added"):
        mk = marketplaces(cdx)
        if mk is None:
            print("warning: `codex plugin marketplace list` failed; if %s is still listed, remove it with "
                  "`codex plugin marketplace remove %s`" % (MARKET, MARKET))
        elif MARKET in mk:
            rc = _say_run(["codex", "plugin", "marketplace", "remove", MARKET], cdx, False)
            if rc:
                print("warning: `codex plugin marketplace remove` failed (exit %d); remove %s by hand" % (rc, MARKET))
    _remove_config(cdx / "config.toml", rec)
    try:
        (cdx / "plugins" / "cache" / MARKET).rmdir()  # Codex leaves the empty marketplace folder behind
    except OSError:
        pass
    acc = root / "accounts.json"
    try:
        known = isinstance(json.loads(acc.read_text(encoding="utf-8")), dict)
    except (OSError, ValueError):
        known = False
    if known:
        ps.remove_account(root, cdx, "codex_dirs")
    elif acc.exists():
        print("warning: %s is unreadable; left as it is" % acc)
    rec_path.unlink()
    if rec.get("dir_created") and cdx.is_dir() and not os.listdir(str(cdx)):
        cdx.rmdir()
    print("uninstalled Dryas from %s" % cdx)
    return 0


def _ev(name: str) -> str:
    return re.sub(r"[_\s]", "", str(name)).lower()  # PreToolUse, preToolUse and pre_tool_use are one event


def expected_hook_events(repo: Path = HERE.parent) -> List[str]:
    """Hook events the plugin ships (codex/hooks/hooks.json), as Codex's hooks/list names them (camelCase)."""
    data = json.loads((Path(repo) / "codex" / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    return sorted(ev[:1].lower() + ev[1:] for ev in data.get("hooks", {}))


def verify(cdx: Path, comps: List[str]) -> int:
    """PASS/FAIL/SKIP lines for one CODEX_HOME; returns the number of FAILs."""
    cdx = codex_home(str(cdx))
    env, fails = child_env(cdx), 0

    def say(status: str, name: str, detail: str = "") -> int:
        print("%s  %s%s" % (status, name, ("  (" + detail + ")") if detail else ""))
        return 1 if status == "FAIL" else 0

    entry = plugin_entry(cdx) if cdx.is_dir() else None
    rec = ps._load_json(cdx / RECORD, {}) or {}
    ok = bool(entry) and bool(entry.get("enabled"))
    detail = str(cdx)
    if ok and rec.get("version") and entry.get("version") != rec["version"]:
        ok, detail = False, "%s: version %s, setup recorded %s; re-run setup" % (cdx, entry.get("version"), rec["version"])
    fails += say("PASS" if ok else "FAIL", "%s installed and enabled" % ID, detail)
    if not ok:
        return fails
    root = Path(rec.get("plugin_root") or cache_root(cdx, str(entry.get("version"))))
    if "jev" in comps:
        data = _json(["codex", "mcp", "list", "--json"], cdx)
        names = [s.get("name") for s in (data if isinstance(data, list) else []) if isinstance(s, dict)]
        fails += say("PASS" if "jev" in names else "FAIL", "Codex Jev MCP server listed")
    try:
        mine = [e for e in ca.list_hooks(env, str(Path.home())) if e.get("pluginId") == ID]
        bad = ["%s (%s)" % (_event(e), e.get("trustStatus")) for e in mine if e.get("trustStatus") != "trusted"]
        seen = {_ev(_event(e)) for e in mine}
        missing = [ev for ev in expected_hook_events() if _ev(ev) not in seen]
        detail = (["not trusted: %s. %s" % (", ".join(bad), TRUST_HINT)] if bad else []) + \
            (["missing: %s (Codex does not list them; re-run setup)" % ", ".join(missing)] if missing else [])
        fails += say("FAIL" if detail else "PASS", "Dryas hooks trusted", " ".join(detail))
    except ca.AppServerError as e:
        fails += say("FAIL", "Dryas hooks trusted", "%s. %s" % (e, TRUST_HINT))
    rc, out = di.capture(["codex", "debug", "prompt-input", "hi"], env=env, timeout=120)
    if rc:
        fails += say("SKIP", "Dryas skills listed", "codex debug prompt-input failed")
    else:
        fails += say("PASS" if "dryas:orchestrate" in out else "FAIL", "Dryas skills listed")
    rc, out = di.capture(di.PYX + [str(root / "jev" / "rules_inject.py"), "--harness", "codex"], "{}",
                         env=dict(env, PLUGIN_ROOT=str(root)), timeout=60)
    try:
        ok = "Dryas paths:" in json.loads(out)["hookSpecificOutput"]["additionalContext"]
    except (ValueError, KeyError, TypeError):
        ok = False
    fails += say("PASS" if ok else "FAIL", "rules hook prints SessionStart JSON")
    fails += say("PASS" if di.scope_smoke(root / "jev" / "chain.py", {}, harness="codex") else "FAIL",
                 "scope lock blocks an out-of-scope apply_patch")
    legacy = (cdx / ct.RECORD).exists()
    fails += say("FAIL" if legacy else "PASS", "no legacy Codex copy install",
                 "re-run install.sh --harness codex to migrate" if legacy else "")
    return fails
