"""Today's Codex copy install (codex_target.install_codex output shape), written by hand: install_codex is gone.

legacy(home, cdx, claude_copy=False, comps=("core", "jev")) builds:
  <home>/.agents/skills/orchestrate/SKILL.md          a Dryas skill copy
  <cdx>/AGENTS.md                                     user text + the Dryas block
  <cdx>/hooks.json                                    one Dryas PreToolUse entry (created by the install)
  <cdx>/.dryas-installed.json                         the Codex record (jev MCP registered with `codex mcp add`)
  <home>/.claude/jev/chain.py + .dryas-installed.json the runtime copy (claude_copy=True: a live Claude copy install)
Returns the ~/.claude path.
"""
import json
from pathlib import Path

import codex_target as ct
import dryas_install as di

HOOK = ["PreToolUse", "Bash|apply_patch|Edit|Write", '"py" -X utf8 "/h/.claude/jev/chain.py" pretool --harness codex']
AGENTS = "mine\n\n<!-- dryas:start -->\nold rules\n<!-- dryas:end -->\n"


def legacy(home: Path, cdx: Path, claude_copy: bool = False, comps=("core", "jev")) -> Path:
    home, cdx = Path(home), Path(cdx)
    sd = ct.skills_dir(home)
    (sd / "orchestrate").mkdir(parents=True)
    (sd / "orchestrate" / "SKILL.md").write_text("old", encoding="utf-8")
    cdx.mkdir(parents=True, exist_ok=True)
    (cdx / "AGENTS.md").write_text(AGENTS, encoding="utf-8")
    (cdx / "hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": HOOK[1], "hooks": [
        {"type": "command", "command": HOOK[2], "timeout": 20}]}]}}), encoding="utf-8")
    (cdx / ct.RECORD).write_text(json.dumps({
        "components": list(comps), "skills": ["orchestrate"], "skill_backups": {},
        "hooks": {"hooks": [HOOK]}, "hooks_created": True, "mcp": {"jev": "cli"}, "toml_servers": {},
        "agents_md": True, "agents_md_created": False, "agents_md_sep": "\n"}), encoding="utf-8")
    cd = home / ".claude"
    (cd / "jev").mkdir(parents=True)
    (cd / "jev" / "chain.py").write_text("", encoding="utf-8")
    rec = {"files": {"jev/chain.py": {}}, "dirs": ["jev"], "components": list(comps), "settings": {}, "mcp": []}
    if claude_copy:
        rec["claude_md"] = True
    (cd / di.RECORD).write_text(json.dumps(rec), encoding="utf-8")
    return cd
