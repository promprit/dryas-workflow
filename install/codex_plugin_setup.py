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
from claude_md_block import insert_block, remove_block  # noqa: E402

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
    return bool(pu.which("python3")) and di.run(["python3", "-c", "import sys; sys.exit(sys.version_info < (3, 9))"]) == 0


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
    if not added or not entry or not entry.get("enabled") or entry.get("version") != want:
        print("error: %s is not installed and enabled at version %s in %s (plugin add exit %d); config not changed"
              % (ID, want, cdx, rc))
        return 1
    plugin_root = added.get("installedPath") or str(cache_root(cdx, want))
    # Task 6: migrate_legacy(cdx) goes here (before the config block: legacy `codex mcp remove jev` must not hit ours)
    fallback = di.PY if "jev" in comps and not python3_ok() else ""
    renv: Dict[str, str] = {}
    if "ruflo" in comps:
        mapping = ps._mapping(plugin_root, comps)
        renv = di.ruflo_env(repo, mapping)
        rec["data_files"] = sorted(set(rec.get("data_files", [])) |
                                   set(ruflo_runtime.install(repo, root, {}, mapping.get("RUFLO_CLI_DIST", ""))))
    cfg = cdx / "config.toml"
    body = toml_block(comps, plugin_root, root, renv, fallback)
    if body:
        insert_block(cfg, body, rec, "toml", TOML_START, TOML_END)
    elif rec.get("toml"):
        remove_block(cfg, rec, "toml", TOML_START, TOML_END)
        rec["toml"] = False
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
