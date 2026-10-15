#!/usr/bin/env python3
"""Copy the runtime the Codex plugin needs from claude/ (the source of truth) into codex/.
Codex installs a plugin by copying it and drops symlinks, so these are real copies.
  python tools/sync_codex_plugin.py           write codex/jev and codex/pstack
  python tools/sync_codex_plugin.py --check   list drift, exit 1 if any (CI)
The skills both editions ship (SKILLS) are hand-written per harness, so --check compares the names they share
instead of bytes: pstack files, Jev and Ruflo tools, Jev questions, threshold keys and plan-file conventions must be
named by both, except the harness-specific ones listed in SKILL_ALLOW. sync never rewrites a skill.
The process skills (PROCESS_SKILLS) are one source in claude/skills: sync renders them into codex/skills (harness
blocks kept or dropped, Claude names rewritten), and --check also fails when a Codex instruction carried over from 1.x
(HARNESS_REQUIRED) is missing from a rendered copy.
"""
import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

REPO = Path(__file__).resolve().parents[1]
TREES = (("claude/jev", "codex/jev"), ("claude/pstack", "codex/pstack"))
CACHE_DIRS = {"__pycache__", ".pytest_cache"}
SKIP_DIRS = {"tests", "logs", "compact"} | CACHE_DIRS  # logs/compact are gitignored runtime dirs
SKIP_FILES = {".gitignore"}
SKILLS = ("orchestrate", "interrogate", "benchmark-checklist")
# a token is a name both skill editions must share; the file's prose around it may differ freely
SHARED = re.compile(r"pstack/[A-Za-z0-9_./-]+\.md"                        # shipped pstack files
                    r"|\.orchestrate/[A-Za-z0-9_]+\.[a-z]+"               # plan-file conventions
                    r"|none \((?:review|cleanup)\)"
                    r"|\b(?:jev_judge|log_(?:escalation|override|dispatch|review|merge)|memory_search|memory_store|swarm_init)\b"
                    r"|\b(?:commit|interrogate|dispatch|escalation)\.[a-z_]+\b"  # threshold keys
                    r"|\b(?:needs_[a-z_]+|safe_to_commit|failing_test_exists|specific)\b")  # Jev questions
# harness-specific names: which edition may name each one alone (claude: tiers and the Agent tool; codex: one ladder)
SKILL_ALLOW: Dict[str, Dict[str, Set[str]]] = {
    "orchestrate": {
        "claude": {"needs_opus", "needs_sonnet", "dispatch.haiku_default", "escalation.haiku_failures_before_sonnet",
                   "escalation.sonnet_failures_before_opus", "escalation.opus_failures_before_fable",
                   "escalation.executor_confidence_below", "swarm_init",
                   "pstack/principles/guard-the-context-window.md", "pstack/principles/prove-it-works.md"},
        "codex": {"needs_stronger_model"},
    },
}
PROCESS_SKILLS = ("brainstorm", "worktree", "debug", "verify", "plan", "review-request", "review-receive", "tdd")
SKILL_FILES = ("UPSTREAM.md", "LICENSE-superpowers")
HARNESS_REQUIRED: Dict[str, Tuple[str, ...]] = {
    "brainstorm": ("get the user's approval of a design",),
    "worktree": ("git worktree add ../<repo>-<topic> -b <branch>",),
    "debug": ("<dryas-root>/pstack/principles/fix-root-causes.md",),
    "verify": ("run the tests and read the output",),
    "plan": ("`docs/superpowers/plans/` if the project uses that", "$dryas:orchestrate"),
    "review-request": ("Change nothing unless asked", "Codex sub-agent"),
}
COMMANDS = ("orchestrate", "wplan", "wreview", "commit", "tune", "handoff", "interrogate", "retro")
COMMAND_RE = re.compile(r"(?<![\w$/.<-])/(" + "|".join(COMMANDS) + r")\b(?![/\w-]|\.\w)")
_HARNESS = re.compile(r"^<!-- (/?)(claude|codex) -->\n?", re.M)
_FRONT = re.compile(r"\A---\n(.*?\n)---\n", re.S)
_CODEX_NAMES = (
    (re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}"), "<dryas-root>"),
    (re.compile(r"mcp__plugin_dryas_jev__"), ""),
    (re.compile(r"(?<![\w$/.@-])dryas:([a-z][a-z-]*)"), r"$dryas:\1"),
    (COMMAND_RE, r"$dryas:\1"),
)


def _files(base: Path) -> Iterator[Tuple[Path, Path]]:
    if not base.is_dir():
        return
    for f in sorted(base.rglob("*")):
        rel = f.relative_to(base)
        if f.is_dir() or any(p in SKIP_DIRS for p in rel.parts[:-1]) or f.suffix == ".pyc" or f.name in SKIP_FILES:
            continue
        yield rel, f


def plan(repo: Path) -> Dict[str, Path]:
    """Target rel path (posix, from the repo root) -> source file."""
    return {(Path(dst) / rel).as_posix(): f for src, dst in TREES for rel, f in _files(Path(repo) / src)}


def _same(a: Path, b: Path) -> bool:
    x, y = a.read_bytes(), b.read_bytes()
    if x == y:
        return True
    try:  # CRLF-tolerant only for text; binary files compare exactly
        return x.decode("utf-8").replace("\r\n", "\n") == y.decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError:
        return False


def _existing(repo: Path) -> List[str]:
    """Every file under the codex/ trees (strays in skipped dirs included) except caches."""
    out = []
    for _, dst in TREES:
        base = Path(repo) / dst
        if base.is_dir():
            for f in sorted(base.rglob("*")):
                rel = f.relative_to(base)
                if f.is_dir() or f.suffix == ".pyc" or any(p in CACHE_DIRS for p in rel.parts[:-1]):
                    continue
                out.append((Path(dst) / rel).as_posix())
    return out


def harness_blocks(text: str, harness: str) -> str:
    """Keep the body of each <!-- HARNESS --> ... <!-- /HARNESS --> block for `harness`, drop the other's."""
    out, pos, open_name = [], 0, None
    for m in _HARNESS.finditer(text):
        closing, name = m.group(1) == "/", m.group(2)
        if closing != (open_name is not None) or (closing and name != open_name):
            raise ValueError("unbalanced <!-- %s%s --> marker" % (m.group(1), name))
        if not closing:
            out.append(text[pos:m.start()])
            open_name = name
        else:
            if open_name == harness:
                out.append(text[pos:m.start()])
            open_name = None
        pos = m.end()
    if open_name is not None:
        raise ValueError("unclosed <!-- %s --> marker" % open_name)
    out.append(text[pos:])
    return "".join(out)


def render_skill(text: str, harness: str) -> str:
    out = harness_blocks(text, harness)
    if harness != "codex":
        return out
    m = _FRONT.match(out)
    if m:  # Codex reads name and description only
        keep = [l for l in m.group(1).splitlines(True) if l.startswith(("name:", "description:"))]
        out = "---\n" + "".join(keep) + "---\n" + out[m.end():]
    for pat, rep in _CODEX_NAMES:
        out = pat.sub(rep, out)
    return out


def _lf(p: Path) -> str:
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


def user_invoked(repo: Path, name: str) -> Optional[bool]:
    for p in (Path(repo) / "claude/skills" / name / "SKILL.md", Path(repo) / "claude/commands" / (name + ".md")):
        if p.is_file():
            m = _FRONT.match(_lf(p))
            return bool(m and re.search(r"^disable-model-invocation:\s*true\s*$", m.group(1), re.M))
    return None


def openai_yaml(implicit: bool) -> str:
    return "policy:\n  allow_implicit_invocation: %s\n" % ("true" if implicit else "false")


def invocation_drift(repo: Path) -> List[str]:
    """One line per Codex skill whose implicit-invocation policy disagrees with its Claude counterpart."""
    out = []
    base = Path(repo) / "codex/skills"
    for d in sorted(base.iterdir()) if base.is_dir() else []:
        if not (d / "SKILL.md").is_file():
            continue
        y = d / "agents/openai.yaml"
        ui = user_invoked(repo, d.name)
        if not y.is_file():  # no policy file: Codex allows implicit invocation, which only a user-invoked skill forbids
            if ui:
                out.append("skill %s: codex agents/openai.yaml is missing" % d.name)
            continue
        m = re.search(r"^\s*allow_implicit_invocation:\s*(true|false)\s*$", y.read_text(encoding="utf-8"), re.M)
        if m is None:
            out.append("skill %s: codex agents/openai.yaml sets no allow_implicit_invocation" % d.name)
        elif ui is None:
            out.append("skill %s: no Claude counterpart" % d.name)
        elif (m.group(1) == "true") == ui:
            out.append("skill %s: codex allow_implicit_invocation is %s, claude says %s"
                       % (d.name, m.group(1), "user-invoked" if ui else "model-invoked"))
    return out


def skill_plan(repo: Path) -> Dict[str, str]:
    """Target rel path under codex/skills -> its text, for every process skill and provenance file in claude/skills."""
    src, out = Path(repo) / "claude/skills", {}
    for name in SKILL_FILES:
        if (src / name).is_file():
            out["codex/skills/" + name] = _lf(src / name)
    for name in PROCESS_SKILLS:
        for f in sorted((src / name).glob("*.md")) if (src / name).is_dir() else []:
            try:
                text = render_skill(_lf(f), "codex")
            except ValueError as e:
                raise ValueError("%s: %s" % (f.relative_to(repo).as_posix(), e))
            out["codex/skills/%s/%s" % (name, f.name)] = text
        if (src / name).is_dir():
            out["codex/skills/%s/agents/openai.yaml" % name] = openai_yaml(not user_invoked(repo, name))
    return out


def _skill_existing(repo: Path) -> List[str]:
    base, out = Path(repo) / "codex/skills", []
    out += ["codex/skills/" + n for n in SKILL_FILES if (base / n).is_file()]
    for name in PROCESS_SKILLS:
        if (base / name).is_dir():
            out += ["codex/skills/%s/%s" % (name, f.relative_to(base / name).as_posix())
                    for f in sorted((base / name).rglob("*")) if f.is_file()]
    return out


def harness_drift(repo: Path) -> List[str]:
    """One line per carried-over Codex instruction missing from a rendered process skill."""
    out = []
    for name, phrases in sorted(HARNESS_REQUIRED.items()):
        f = Path(repo) / "claude/skills" / name / "SKILL.md"
        if not f.is_file():
            continue
        text = render_skill(_lf(f), "codex")
        out += ['skill %s: the Codex copy lacks "%s"' % (name, p) for p in phrases if p not in text]
    return out


def drift(repo: Path) -> List[str]:
    want, out = plan(repo), []
    for rel, src in want.items():
        dest = Path(repo) / rel
        if not dest.is_file():
            out.append("missing " + rel)
        elif not _same(src, dest):
            out.append("differs " + rel)
    out += ["extra " + rel for rel in _existing(repo) if rel not in want]
    rendered = skill_plan(repo)
    for rel, text in rendered.items():
        dest = Path(repo) / rel
        if not dest.is_file():
            out.append("missing " + rel)
        elif _lf(dest) != text:
            out.append("differs " + rel)
    out += ["extra " + rel for rel in _skill_existing(repo) if rel not in rendered]
    return sorted(out)


_MCP = re.compile(r"mcp__plugin_[A-Za-z0-9_-]+?__")  # Claude names MCP tools with the plugin prefix


def _tokens(path: Path) -> Set[str]:
    return set(SHARED.findall(_MCP.sub("", path.read_text(encoding="utf-8")))) if path.is_file() else set()


def skill_drift(repo: Path) -> List[str]:
    """One line per shared name only one edition names (unless allowed) and per allowance no longer needed."""
    out = []
    for name in SKILLS:
        files = {h: Path(repo) / h / "skills" / name / "SKILL.md" for h in ("claude", "codex")}
        if not any(f.is_file() for f in files.values()):
            continue  # a tree without the skill (tests, partial checkouts) has nothing to compare
        tok = {h: _tokens(f) for h, f in files.items()}
        allow = SKILL_ALLOW.get(name, {})
        for mine, other in (("claude", "codex"), ("codex", "claude")):
            only = tok[mine] - tok[other]
            ok = allow.get(mine, set())
            out += ["skill %s: %s names %s but %s does not" % (name, mine, t, other) for t in sorted(only - ok)]
            out += ["skill %s: SKILL_ALLOW[%r] lists %s, which no longer differs" % (name, mine, t) for t in sorted(ok - only)]
    return sorted(out)


def sync(repo: Path) -> List[str]:
    """Make codex/ match claude/; return the changed rel paths."""
    want, rendered, changed = plan(repo), skill_plan(repo), []
    for line in drift(repo):
        kind, rel = line.split(" ", 1)
        dest = Path(repo) / rel
        if kind == "extra":
            dest.unlink()
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if rel in rendered:
                dest.write_bytes(rendered[rel].encode("utf-8"))
            else:
                shutil.copy2(str(want[rel]), str(dest))
        changed.append(rel)
    return changed


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--repo", default=str(REPO))
    a = ap.parse_args(argv)
    repo = Path(a.repo)
    try:
        return _run(repo, a.check)
    except ValueError as e:
        print("error: %s" % e)
        return 1


def _run(repo: Path, check: bool) -> int:
    if check:
        bad = drift(repo)
        for line in bad:
            print(line)
        if bad:
            print("codex/ is out of date: run python tools/sync_codex_plugin.py and commit the result")
        skills = skill_drift(repo)
        for line in skills:
            print(line)
        if skills:
            print("codex/skills drifted from claude/skills: edit the Codex skill by hand, or list a harness-specific "
                  "name in SKILL_ALLOW in tools/sync_codex_plugin.py")
        harness = harness_drift(repo)
        for line in harness:
            print(line)
        if harness:
            print("a Codex instruction carried over from 1.x is missing: restore it in claude/skills, inside a "
                  "<!-- codex --> block if it is Codex-only (see HARNESS_REQUIRED in tools/sync_codex_plugin.py)")
        inv = invocation_drift(repo)
        for line in inv:
            print(line)
        if inv:
            print("set disable-model-invocation in claude/ and allow_implicit_invocation in "
                  "codex/skills/<name>/agents/openai.yaml to agree")
        return 1 if bad or skills or harness or inv else 0
    for rel in sync(repo):
        print("synced " + rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
