"""Codex target: AGENTS.md block, skills, hooks.json entries and MCP servers, recorded for exact uninstall.

Record: <codex dir>/.dryas-installed.json. The Jev code itself lives in the Claude directory (installed by
dryas_install.install, with claude=False when only Codex is selected) and is shared by both harnesses.
"""
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import hookcheck
import settings_merge as sm
import upgrade
from claude_md_block import insert_block, remove_block

RECORD = ".dryas-installed.json"
SKILLS = ("orchestrate", "wreview", "wplan", "commit", "tune")
TOML_START, TOML_END = "# >>> dryas-workflow >>>", "# <<< dryas-workflow <<<"
RUFLO_ENV_KEYS = ("DRYAS_DATA_ROOT", "RUFLO_JS", "RUFLO_NO_AUTO_ENABLE", "RUFLO_DAEMON_AUTOSTART", "RUFLO_MCP_SKIP_NPX",
                  "CLAUDE_FLOW_MEMORY_PATH", "CLAUDE_FLOW_DB_PATH", "CLAUDE_FLOW_SWARM_DIR", "RUFLO_STATE_DIR")
SP_HINT = ("Superpowers was not found for Codex. Install it with the Codex steps in the Superpowers README "
           "(https://github.com/obra/superpowers); this installer does not fetch it.")
Server = Tuple[str, List[str], Dict[str, str]]


def codex_dir() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))


def skills_dir(home: Path) -> Path:
    return Path(home) / ".agents" / "skills"


def _load(cdx: Path) -> dict:
    p = cdx / RECORD
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"skills": [], "skill_backups": {}, "hooks": {"hooks": []}, "mcp": {}, "toml_servers": {}}


def _save(cdx: Path, rec: dict) -> None:
    (cdx / RECORD).write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")


def servers(comps: List[str], mapping: Dict[str, str], ruflo_env: Dict[str, str]) -> Dict[str, Server]:
    out: Dict[str, Server] = {}
    if "jev" in comps:
        out["jev"] = (mapping["PY"], ["-X", "utf8", mapping["CD"] + "/jev/jev_mcp.py"], {})
    if "ruflo" in comps:
        out["ruflo"] = ("node", [mapping["CD"] + "/ruflo/mcp-shim/bin/cli.js", "mcp", "start"],
                        {k: ruflo_env[k] for k in RUFLO_ENV_KEYS if k in ruflo_env})
    return out


def _q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)  # a JSON string is a valid TOML basic string


def toml_body(srv: Dict[str, list]) -> str:
    lines: List[str] = []
    for name, (cmd, args, env) in sorted(srv.items()):
        lines += ["[mcp_servers.%s]" % name, "command = %s" % _q(cmd), "args = [%s]" % ", ".join(_q(a) for a in args)]
        if env:
            lines.append("env = { %s }" % ", ".join("%s = %s" % (k, _q(v)) for k, v in env.items()))
        lines.append("")
    return "\n".join(lines).strip()


def _user_has_table(text: str, name: str) -> bool:
    outside = re.sub(re.escape(TOML_START) + r".*?" + re.escape(TOML_END), "", text, flags=re.S)
    n = re.escape(name)
    pat = r"^\s*(\[mcp_servers\.(%s|\"%s\"|'%s')\]|mcp_servers\.(%s|\"%s\"))" % (n, n, n, n, n)
    return re.search(pat, outside, re.M) is not None


def _ts() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def install_codex(repo: Path, cdx: Path, home: Path, comps: List[str], mapping: Dict[str, str],
                  ruflo_env: Dict[str, str], run: Callable[[List[str]], int], force: bool = False,
                  dry: bool = False) -> int:
    repo, cdx, home = Path(repo), Path(cdx), Path(home)
    srv = servers(comps, mapping, ruflo_env)
    if dry:
        print("would add or update the Dryas block in %s" % (cdx / "AGENTS.md"))
        print("would install Codex skills into %s: %s" % (skills_dir(home), ", ".join(SKILLS)))
        print("would merge Codex hooks into %s" % (cdx / "hooks.json"))
        for name in srv:
            print("would register the %s MCP server for Codex" % name)
        return 0
    rec = _load(cdx)
    if not cdx.exists():
        cdx.mkdir(parents=True)
        rec.setdefault("dir_created", True)
    rec.setdefault("dir_created", False)
    tpl = (repo / "codex" / "AGENTS.md.template").read_text(encoding="utf-8")
    insert_block(cdx / "AGENTS.md", sm.render_tokens(tpl, mapping), rec, "agents_md")
    sd = skills_dir(home)
    for name in SKILLS:
        dest = sd / name
        mine = name in rec["skills"]
        if dest.exists() and not mine:
            if not force:
                print("kept your skill: %s (use --force to replace, original is backed up)" % dest)
                continue
            b = cdx / (".dryas-backup-" + _ts()) / "skills" / name
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest), str(b))
            rec["skill_backups"][name] = str(b)
        dest.mkdir(parents=True, exist_ok=True)
        text = (repo / "codex" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        (dest / "SKILL.md").write_text(sm.render_tokens(text, mapping), encoding="utf-8")
        if not mine:
            rec["skills"].append(name)
    if "core" in comps:
        frag = sm.render(json.loads((repo / "codex" / "hooks.fragment.json").read_text(encoding="utf-8")), mapping)
        hp = cdx / "hooks.json"
        rec.setdefault("hooks_created", not hp.exists())
        cur = sm.load_settings(hp)
        stale = upgrade.stale_settings(rec["hooks"], frag)
        if upgrade.has_any(stale):
            cur = sm.unmerge(cur, stale)
            rec["hooks"] = upgrade.subtract(rec["hooks"], stale)
        merged, added, _ = sm.merge(cur, frag)
        if merged != sm.load_settings(hp):
            hp.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        rec["hooks"]["hooks"] += [h for h in added["hooks"] if h not in rec["hooks"]["hooks"]]
    cfg = cdx / "config.toml"
    text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    fallback: Dict[str, list] = {}
    specs = rec.setdefault("mcp_specs", {})
    for name, (cmd, args, env) in srv.items():
        spec = [cmd, list(args), dict(env)]
        if name in rec["mcp"]:
            old = specs.get(name)
            specs[name] = spec
            if old is None or old == spec:
                continue
            if rec["mcp"][name] == "toml":
                fallback[name] = spec
                continue
            run(["codex", "mcp", "remove", name])
        elif _user_has_table(text, name):
            print("kept your [mcp_servers.%s] in %s" % (name, cfg))
            continue
        specs[name] = spec
        argv = ["codex", "mcp", "add", name]
        for k, v in env.items():
            argv += ["--env", "%s=%s" % (k, v)]
        if run(argv + ["--", cmd] + args) == 0:
            rec["mcp"][name] = "cli"
        else:
            fallback[name] = spec
    if fallback:
        rec["toml_servers"].update(fallback)
        insert_block(cfg, toml_body(rec["toml_servers"]), rec, "toml", TOML_START, TOML_END)
        for name in fallback:
            rec["mcp"][name] = "toml"
            print("registered %s in %s (codex mcp add was not available)" % (name, cfg))
    if not any((sd / n).exists() for n in ("superpowers", "brainstorming")):
        print(SP_HINT)
    _save(cdx, rec)
    print("installed the Codex target into %s" % cdx)
    return 0


def uninstall_codex(cdx: Path, home: Path, run: Callable[[List[str]], int]) -> int:
    cdx, home = Path(cdx), Path(home)
    if not (cdx / RECORD).exists():
        return 0
    rec = _load(cdx)
    remove_block(cdx / "AGENTS.md", rec, "agents_md")
    sd = skills_dir(home)
    for name in rec.get("skills", []):
        shutil.rmtree(str(sd / name), ignore_errors=True)
        b = rec.get("skill_backups", {}).get(name)
        if b and os.path.exists(b):
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


SMOKE_PLAN = "## Task 1: a\nGoal: g\nScope:\n- src/feature/**\nDone:\n- d\n"


def verify_codex(cdx: Path, home: Path, comps: List[str], capture: Callable, cd: Path) -> int:
    fails = 0

    def say(ok: bool, name: str, detail: str = "") -> int:
        print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  (" + detail + ")") if detail else ""))
        return 0 if ok else 1

    rec = _load(cdx)
    fails += say("<!-- dryas:start -->" in ((cdx / "AGENTS.md").read_text(encoding="utf-8") if (cdx / "AGENTS.md").exists() else ""),
                 "Codex AGENTS.md block")
    missing = [n for n in rec.get("skills", []) if not (skills_dir(home) / n / "SKILL.md").exists()]
    fails += say(not missing, "Codex skills present", ", ".join(missing))
    hp = hookcheck.hook_problems(rec.get("hooks", {}).get("hooks", []))
    fails += say(not hp, "Codex hook commands", "; ".join(hp))
    cli = [n for n, how in rec.get("mcp", {}).items() if how == "cli"]
    if cli:
        rc, out = capture(["codex", "mcp", "list"])
        absent = [n for n in cli if not re.search(r"\b%s\b" % re.escape(n), out)]
        fails += say(not absent, "Codex MCP servers registered", ", ".join(absent))
    if "core" in comps:
        wt = Path(tempfile.mkdtemp())
        try:
            (wt / ".orchestrate").mkdir()
            (wt / ".orchestrate" / "PLAN.md").write_text(SMOKE_PLAN, encoding="utf-8")
            (wt / ".orchestrate" / "active.json").write_text(json.dumps({"active": ["1"]}), encoding="utf-8")
            patch = "*** Begin Patch\n*** Add File: src/other.ts\n+x\n*** End Patch\n"
            event = {"tool_name": "apply_patch", "tool_input": {"command": patch}, "cwd": str(wt)}
            env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_API_KEY"}
            env["JEV_LOG_DIR"] = str(wt / "logs")
            rc, out = capture([sys.executable, "-X", "utf8", str(Path(cd) / "jev" / "chain.py"), "pretool", "--harness", "codex"],
                              json.dumps(event), env)
            try:
                ok = json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
            except (ValueError, KeyError, TypeError):
                ok = False
            fails += say(ok, "Codex scope lock blocks an out-of-scope apply_patch")
        finally:
            shutil.rmtree(str(wt), ignore_errors=True)
    return fails
