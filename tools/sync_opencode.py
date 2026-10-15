#!/usr/bin/env python3
"""Render the OpenCode edition (opencode/) from claude/ and codex/, its sources of truth.
  python tools/sync_opencode.py           write opencode/
  python tools/sync_opencode.py --check   list drift and leaked Claude or Codex names, exit 1 if any (CI)
tools/sync_codex_plugin.py runs this too. opencode/ is laid out as installed into an OpenCode config dir. The shim
(opencode/plugin/) and the SKILL.md of the HAND skills are written by hand; this tool never touches them.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_codex_plugin as scp  # noqa: E402

REPO = scp.REPO
MARK = "<!-- dryas-managed -->"
TREES = (("claude/jev", "opencode/dryas/jev"), ("claude/pstack", "opencode/dryas/pstack"))
HAND = ("orchestrate", "interrogate", "benchmark-checklist")  # opencode/skill/dryas-<name>/SKILL.md, hand-written
CLAUDE_ONLY = ("ruflo-tools.md",)  # skill reference files OpenCode has no use for (no Ruflo on OpenCode)
THIN = ("orchestrate", "interrogate")  # commands that only load the skill of the same name
FROM_CODEX = ("wplan", "wreview", "commit", "tune", "retro")  # commands rendered from codex/skills/<name>
TIERS = ("fast", "standard", "strong", "frontier")
JEV_TOOLS = ("jev_judge|log_override|log_escalation|log_dispatch|log_review|log_merge|memory_search|memory_store|"
             "memory_list|memory_forget|swarm_init")
_NAMES = (
    (re.compile(r'"\$\{CLAUDE_PLUGIN_ROOT\}/bin/dryas-py"'), '"<dryas-py>" -X utf8'),
    (re.compile(r"(?:\$\{CLAUDE_PLUGIN_ROOT\}|<dryas-root>)/skills/([a-z][a-z-]*)/"), r"<dryas-root>/../skill/dryas-\1/"),
    (re.compile(r"(?:\$\{CLAUDE_PLUGIN_ROOT\}|<dryas-root>)/commands/"), "<dryas-root>/../command/"),
    (re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}"), "<dryas-root>"),
    (re.compile(r"mcp__plugin_dryas_jev__"), "jev_"),
    (re.compile(r" \(server `jev`\)"), ""),
    (re.compile(r"`(" + JEV_TOOLS + r")`"), r"`jev_\1`"),
    (re.compile(r"the Dryas hooks are not trusted: tell the user to run /hooks in Codex and stop"),
     "the Dryas plugin did not load: tell the user to re-run install.sh --harness opencode and stop"),
    (re.compile(r"\$dryas:(" + "|".join(scp.COMMANDS) + r")\b"), r"/\1"),
    (re.compile(r"\$dryas:([a-z][a-z-]*)"), r"dryas-\1"),
    (re.compile(r"(?<![\w$/.@-])dryas:([a-z][a-z-]*)"), r"dryas-\1"),
    (re.compile(r"Codex sub-agents?"), "OpenCode subagents"),
    (re.compile(r"\bCodex\b"), "OpenCode"),
)
_LEAK = re.compile(r"\$dryas:|mcp__|\$\{CLAUDE_PLUGIN_ROOT\}|^<!-- /?(?:claude|codex|opencode) -->", re.M)
RULES_TAIL = (
    "## OpenCode notes\n"
    "- Executors are the subagents `dryas-executor-fast`, `dryas-executor-standard`, `dryas-executor-strong` and "
    "`dryas-executor-frontier` (dispatch them with the task tool). Logs and thresholds keep the slot names `haiku`, "
    "`sonnet`, `opus` and `fable` for them.\n"
    "- Not yet on OpenCode: context-window warnings, compaction keep/restore, `/handoff` and the memory hooks "
    "(plan 2 of the edition). Call `jev_memory_search` and `jev_memory_store` yourself.\n")


def names(text: str) -> str:
    for pat, rep in _NAMES:
        text = pat.sub(rep, text)
    return text


def _field(text: str, key: str) -> str:
    m = scp._FRONT.match(text)
    f = re.search(r"^%s:\s*(.*)$" % re.escape(key), m.group(1), re.M) if m else None
    return f.group(1).strip().strip('"') if f else ""


def _body(text: str) -> str:
    m = scp._FRONT.match(text)
    return text[m.end():] if m else text


def render_skill(text: str, name: str) -> str:
    text = scp.harness_blocks(text, "opencode")
    return ("---\nname: dryas-%s\ndescription: %s\n---\n%s\n" % (name, json.dumps(names(_field(text, "description"))), MARK)
            + names(_body(text)))


def render_command(name: str, codex_skill: str) -> str:
    desc = json.dumps(names(_field(codex_skill, "description")))
    if name in THIN:
        body = "Load the `dryas-%s` skill with the skill tool and follow it for: $ARGUMENTS\n" % name
    else:
        body = names(_body(codex_skill)).strip() + "\n\nArguments: $ARGUMENTS\n"
    return "---\ndescription: %s\n---\n%s\n%s" % (desc, MARK, body)


def render_agent(executor: str, tier: str) -> str:
    desc = json.dumps("%s Tier: %s." % (_field(executor, "description"), tier))
    return "---\ndescription: %s\nmode: subagent\nmodel: {{MODEL}}\n---\n%s\n" % (desc, MARK) + names(_body(executor))


def render_rules(codex_rules: str) -> str:
    text = re.sub(r"## Not available in Codex\n.*\Z", "", codex_rules, flags=re.S).rstrip() + "\n\n"
    return names(text) + RULES_TAIL


def plan(repo: Path) -> Dict[str, Union[Path, str]]:
    """Target rel path (posix, from the repo root) -> source file (copied) or text (rendered)."""
    repo, out = Path(repo), {}  # type: ignore[var-annotated]
    for src, dst in TREES:
        for rel, f in scp._files(repo / src):
            out[(Path(dst) / rel).as_posix()] = f
    out["opencode/dryas/AGENTS.md.template"] = render_rules(scp._lf(repo / "codex/AGENTS.md.template"))
    skills = repo / "claude/skills"
    for n in scp.SKILL_FILES:
        if (skills / n).is_file():
            out["opencode/skill/" + n] = scp._lf(skills / n)
    for name in scp.PROCESS_SKILLS + HAND:
        for f in sorted((skills / name).glob("*.md")) if (skills / name).is_dir() else []:
            if (name in HAND and f.name == "SKILL.md") or f.name in CLAUDE_ONLY:
                continue
            try:
                text = scp._lf(f)
                out["opencode/skill/dryas-%s/%s" % (name, f.name)] = (
                    render_skill(text, name) if f.name == "SKILL.md" else names(scp.harness_blocks(text, "opencode")))
            except ValueError as e:
                raise ValueError("%s: %s" % (f.relative_to(repo).as_posix(), e))
    for name in THIN + FROM_CODEX:
        out["opencode/command/%s.md" % name] = render_command(name, scp._lf(repo / "codex/skills" / name / "SKILL.md"))
    executor = scp._lf(repo / "claude/agents/executor.md")
    for tier in TIERS:
        out["opencode/agent/dryas-executor-%s.md" % tier] = render_agent(executor, tier)
    return out


def _existing(repo: Path) -> List[str]:
    """Every file in the generated part of opencode/ (strays included), except caches and hand-written files."""
    base, out = Path(repo) / "opencode", []
    hand = {"dryas-" + h for h in HAND}
    for sub in ("dryas", "skill", "command", "agent"):
        for f in sorted((base / sub).rglob("*")) if (base / sub).is_dir() else []:
            parts = f.relative_to(base).parts
            if f.is_dir() or f.suffix == ".pyc" or any(p in scp.CACHE_DIRS for p in parts):
                continue
            if parts[0] == "skill" and len(parts) == 3 and parts[1] in hand and parts[2] == "SKILL.md":
                continue
            out.append(f.relative_to(Path(repo)).as_posix())
    return out


def drift(repo: Path) -> List[str]:
    want, out = plan(repo), []
    for rel, src in want.items():
        dest = Path(repo) / rel
        if not dest.is_file():
            out.append("missing " + rel)
        elif (scp._lf(dest) != src) if isinstance(src, str) else not scp._same(src, dest):
            out.append("differs " + rel)
    out += ["extra " + rel for rel in _existing(repo) if rel not in want]
    return sorted(out)


def leaks(repo: Path) -> List[str]:
    """One line per rendered file that still names a Claude or Codex construct."""
    out = []
    for rel, src in sorted(plan(repo).items()):
        m = _LEAK.search(src) if isinstance(src, str) else None
        if m:
            out.append("leak %s: %s" % (rel, m.group(0)))
    return out


def sync(repo: Path) -> List[str]:
    want, changed = plan(repo), []
    for line in drift(repo):
        kind, rel = line.split(" ", 1)
        dest = Path(repo) / rel
        if kind == "extra":
            dest.unlink()
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            src = want[rel]
            if isinstance(src, str):
                dest.write_bytes(src.encode("utf-8"))
            else:
                shutil.copy2(str(src), str(dest))
        changed.append(rel)
    return changed


def run(repo: Path, check: bool) -> int:
    if not check:
        for rel in sync(repo):
            print("synced " + rel)
        return 0
    bad = drift(repo) + leaks(repo)
    for line in bad:
        print(line)
    if bad:
        print("opencode/ is out of date or leaks names: fix the source or tools/sync_opencode.py, run "
              "python tools/sync_opencode.py and commit the result")
    return 1 if bad else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--repo", default=str(REPO))
    a = ap.parse_args(argv)
    try:
        return run(Path(a.repo), a.check)
    except ValueError as e:
        print("error: %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
