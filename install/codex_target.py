"""Legacy Codex copy install (before the plugin): uninstall only, plus the names the plugin setup still shares.

Record: <codex dir>/.dryas-installed.json. That install wrote an AGENTS.md block, ~/.agents/skills copies, hooks.json
entries and MCP servers (`codex mcp add`, or a config.toml block); its Jev code was a runtime copy in ~/.claude.
codex_plugin_setup.migrate_legacy removes both; installing this way is gone.
"""
import json
import os
import shutil
from pathlib import Path
from typing import Callable, List

import settings_merge as sm
from claude_md_block import remove_block

RECORD = ".dryas-installed.json"
TOML_START, TOML_END = "# >>> dryas-workflow >>>", "# <<< dryas-workflow <<<"
RUFLO_ENV_KEYS = ("DRYAS_DATA_ROOT", "RUFLO_JS", "RUFLO_NO_AUTO_ENABLE", "RUFLO_DAEMON_AUTOSTART", "RUFLO_MCP_SKIP_NPX",
                  "CLAUDE_FLOW_MEMORY_PATH", "CLAUDE_FLOW_DB_PATH", "CLAUDE_FLOW_SWARM_DIR", "RUFLO_STATE_DIR")
SP_HINT = ("Superpowers was not found for Codex. Install it with the Codex steps in the Superpowers README "
           "(https://github.com/obra/superpowers); this installer does not fetch it.")


def codex_dir() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))


def skills_dir(home: Path) -> Path:
    return Path(home) / ".agents" / "skills"


def _load(cdx: Path) -> dict:
    p = cdx / RECORD
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"skills": [], "skill_backups": {}, "hooks": {"hooks": []}, "mcp": {}, "toml_servers": {}}


def _q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)  # a JSON string is a valid TOML basic string


def uninstall_codex(cdx: Path, home: Path, run: Callable[[List[str]], int]) -> int:
    cdx, home = Path(cdx), Path(home)
    if not (cdx / RECORD).exists():
        return 0
    rec = _load(cdx)
    remove_block(cdx / "AGENTS.md", rec, "agents_md")
    sd = skills_dir(home)
    for name in rec.get("skills", []):
        b = rec.get("skill_backups", {}).get(name)
        if b and not os.path.exists(b):
            continue  # restored by an earlier, interrupted run: what is there now is the user's skill
        shutil.rmtree(str(sd / name), ignore_errors=True)
        if b:
            shutil.move(b, str(sd / name))
    for d in (sd, sd.parent):
        if d.is_dir() and not os.listdir(str(d)):
            d.rmdir()
    hp = cdx / "hooks.json"
    if hp.exists():
        cur = sm.load_settings(hp)
        new = sm.unmerge(cur, rec.get("hooks", {}))
        if rec.get("hooks_created") and new == {}:
            hp.unlink()
        elif new != cur:
            hp.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
    for name, how in rec.get("mcp", {}).items():
        if how == "cli":
            run(["codex", "mcp", "remove", name])
    if rec.get("toml"):
        remove_block(cdx / "config.toml", rec, "toml", TOML_START, TOML_END)
    for bd in cdx.glob(".dryas-backup-*"):
        shutil.rmtree(str(bd), ignore_errors=True)
    (cdx / RECORD).unlink()
    if rec.get("dir_created") and cdx.is_dir() and not os.listdir(str(cdx)):
        cdx.rmdir()
    print("uninstalled the Codex target")
    return 0
