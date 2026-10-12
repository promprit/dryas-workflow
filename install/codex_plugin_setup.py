"""Set up the Dryas Codex plugin in one CODEX_HOME: marketplace, plugin, config block, hook trust, shared state.

  setup(repo, cdx, comps, yes)   one CODEX_HOME; run once per Codex account (install.sh --harness codex --codex-dir DIR)
  verify(cdx, comps)             PASS/FAIL/SKIP lines (Task 5)
  uninstall(cdx)                 that CODEX_HOME only (Task 7)
"""
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import codex_target as ct  # noqa: E402
import dryas_install as di  # noqa: E402
import platform_util as pu  # noqa: E402
import plugin_setup as ps  # noqa: E402
import ruflo_runtime  # noqa: E402

PLUGIN, MARKET = "dryas", "dryas-workflow"
ID = PLUGIN + "@" + MARKET
RECORD = ".dryas-codex-plugin.json"
MIN_CODEX = (0, 162, 1)
TOML_START, TOML_END = "# >>> dryas plugin >>>", "# <<< dryas plugin <<<"
ENV_VARS = ("OPENROUTER_API_KEY", "DRYAS_OPENROUTER_KEY", "DRYAS_DATA_ROOT")


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


HEADER_RE = re.compile(r"^\s*(\[{1,2})([^\]=\[]+)(\]{1,2})\s*(#.*)?$")
KEY_RE = re.compile(r"""\s*("(?:[^"\\]|\\.)*"|'[^']*'|[A-Za-z0-9_-]+)\s*(?:\.|$)""")
KeyPath = Tuple[str, ...]


def norm_header(line: str) -> Optional[Tuple[KeyPath, bool]]:
    """(key path, is array-of-tables) of a TOML table header line; None = not a header. Whitespace, quotes around
    plain keys and a trailing comment do not matter: [ a . "b" ] # x  ==  [a.b]."""
    m = HEADER_RE.match(line)
    if not m or len(m.group(1)) != len(m.group(3)):
        return None
    inner, keys, pos = m.group(2), [], 0
    while pos < len(inner):
        k = KEY_RE.match(inner, pos)
        if not k or k.end() == pos:
            return None
        tok = k.group(1)
        try:
            keys.append(json.loads(tok) if tok.startswith('"') else tok.strip("'"))
        except ValueError:
            return None
        pos = k.end()
    return (tuple(keys), len(m.group(1)) == 2) if keys else None


def _scan(line: str, st: dict) -> None:
    """Track multi-line strings and open brackets across lines (a header can only start outside both)."""
    i = 0
    while i < len(line):
        if st["ml"]:
            j = line.find(st["ml"], i)
            if j < 0:
                return
            st["ml"], i = None, j + 3
            continue
        c = line[i]
        if line[i:i + 3] in ('"' * 3, "'" * 3):
            st["ml"], i = line[i:i + 3], i + 3
        elif c in "\"'":
            j = i + 1
            while j < len(line) and line[j] != c:
                j += 2 if c == '"' and line[j] == "\\" else 1
            i = j + 1
        elif c == "#":
            return
        else:
            st["depth"] += (c in "[{") - (c in "]}")
            i += 1


def _lines(text: str) -> List[Tuple[str, Optional[Tuple[KeyPath, bool]]]]:
    st, out = {"ml": None, "depth": 0}, []  # type: ignore[var-annotated]
    for line in text.splitlines(True):
        hdr = None
        if st["ml"] is None and st["depth"] <= 0:
            st["depth"] = 0
            hdr = norm_header(line)
        if hdr is None:
            _scan(line, st)
        out.append((line, hdr))
    return out


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
    # Task 6: migrate_legacy(cdx) goes here (before the config block: legacy `codex mcp remove jev` must not hit ours)
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
    # Task 5: trust_hooks(cdx, rec, yes) goes here
    ps.write_workflow_doc(repo, root)
    ps.write_chain_local(root, comps, None, repo, None)
    ps.add_account(root, cdx, "codex_dirs")
    rec.update(components=sorted(set(comps)), version=want, plugin_root=plugin_root)
    ps._save_json(rec_path, rec)
    if not any((ct.skills_dir(Path.home()) / n).exists() for n in ("superpowers", "brainstorming")):
        print(ct.SP_HINT)
    if "jev" in comps and not (os.environ.get("OPENROUTER_API_KEY") or "").strip():
        print("note: Jev reads OPENROUTER_API_KEY from the shell Codex runs in; set it in your shell profile.")
    print("Dryas set up in %s (plugin at %s, state in %s)" % (cdx, plugin_root, root))
    return 0
