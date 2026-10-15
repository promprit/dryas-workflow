"""Text rewrites for the files `dryas cloud` copies into a repo (owned core E).

A repo copy has no plugin. Its runtime is in .dryas/, its skills, commands and agent under .claude/, its state in
.dryas/state/. So copied markdown gets:
- repo-relative paths (a cloud session, and every worktree of it, starts at the repo root);
- the project's names instead of the plugin's (`dryas:plan` -> `plan`, `mcp__plugin_dryas_jev__x` -> `mcp__jev__x`);
- the Claude harness blocks and the selected component blocks only.

--prefix renames the Dryas copies and the /commands that name them."""
import re
import sys
from pathlib import Path
from typing import Dict, Iterable

ROOT = Path(__file__).resolve().parents[1]
for _d in (ROOT / "tools", ROOT / "install", ROOT / "claude" / "jev"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
from cloud_check import HOME_STATE  # noqa: E402
import render  # noqa: E402  (gate_blocks: <!-- pstack-picks --> blocks)
from sync_codex_plugin import harness_blocks  # noqa: E402

PLUGIN = "${CLAUDE_PLUGIN_ROOT}"
_SUB = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/(skills|agents|commands)/([A-Za-z0-9_-]+)")
LEAD = ("Dryas {version} runs from this repo's `.dryas/` folder, a pinned copy made by `dryas cloud` (`/{check}` "
        "verifies it). Its skills, commands and executor agent are project files under `.claude/`, its state is in "
        "`.dryas/state/` (git-ignored), and the judge is local unless this environment opted into Jev.")


class Names:
    """The copy's names for the Dryas skills, commands and agents, with --prefix applied."""

    def __init__(self, prefix: str, skills: Iterable[str], commands: Iterable[str], agents: Iterable[str]) -> None:
        self.prefix = prefix
        self.skills, self.commands, self.agents = tuple(skills), tuple(commands), tuple(agents)
        known = sorted(set(self.skills) | set(self.commands) | set(self.agents), key=len, reverse=True)
        self.plugin_names = (re.compile(r"(?<![\w$/.@-])dryas:(%s)(?![\w-])" % "|".join(map(re.escape, known)))
                             if known else None)
        cmds = sorted(self.commands, key=len, reverse=True)
        self.slash = (re.compile(r"(?<![\w$/.<-])/(%s)(?![/\w-]|\.\w)" % "|".join(map(re.escape, cmds)))
                      if cmds else None)

    def name(self, n: str) -> str:
        return self.prefix + n


def rewrite(text: str, names: Names, comps: Iterable[str]) -> str:
    """A Dryas markdown file as the repo copy ships it."""
    text = render.gate_blocks(harness_blocks(text, "claude"), list(comps))
    text = _SUB.sub(lambda m: ".claude/%s/%s" % (m.group(1), names.name(m.group(2))), text)
    text = text.replace(PLUGIN, ".dryas")
    text = text.replace("~/.dryas/docs/", ".dryas/docs/")
    text = HOME_STATE.sub(".dryas/state", text)
    text = text.replace("mcp__plugin_dryas_jev", "mcp__jev")
    if names.plugin_names is not None:
        text = names.plugin_names.sub(lambda m: names.name(m.group(1)), text)
    if names.prefix and names.slash is not None:
        text = names.slash.sub(lambda m: "/" + names.name(m.group(1)), text)
    return text


def set_name(text: str, name: str) -> str:
    """Set the front matter `name:` of a SKILL.md or agent file; text without front matter is returned as it is."""
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---", 3)
    if end < 0:
        return text
    return re.sub(r"(?m)^name:[^\n]*$", "name: " + name, text[:end], count=1) + text[end:]


NOTES_RULE = "Before your final commit, include .dryas/memory/notes/ in it."


def claude_md_body(template: str, names: Names, comps: Iterable[str], version: str, persist_memory: bool = False) -> str:
    """The rules block for the repo's CLAUDE.md: one paragraph on the copy, then the rules as the copy reads them."""
    lead = LEAD.format(version=version, check=names.name("dryas-cloud") + " check")
    body = lead + "\n\n" + rewrite(template, names, comps).strip() + "\n"
    return body + "\n" + NOTES_RULE + "\n" if persist_memory else body


def third_party(text: str, skills_rel: str, renames: Dict[str, str]) -> str:
    """A design skill's markdown: `${CLAUDE_PLUGIN_ROOT}/<skills folder>/<name>` becomes `.claude/skills/<new name>`.
    Other plugin-root paths stay, so the caller sees that the skill needs files outside its folder."""
    rel = (skills_rel[2:] if skills_rel.startswith("./") else skills_rel).strip("/")
    pat = re.compile(re.escape(PLUGIN + "/" + rel + "/") + r"([A-Za-z0-9_-]+)")
    return pat.sub(lambda m: ".claude/skills/" + renames.get(m.group(1), m.group(1)), text)
