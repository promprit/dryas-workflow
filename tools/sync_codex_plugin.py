#!/usr/bin/env python3
"""Copy the runtime the Codex plugin needs from claude/ (the source of truth) into codex/.
Codex installs a plugin by copying it and drops symlinks, so these are real copies.
  python tools/sync_codex_plugin.py           write codex/jev and codex/pstack
  python tools/sync_codex_plugin.py --check   list drift, exit 1 if any (CI)
The skills both editions ship (SKILLS) are hand-written per harness, so --check compares the names they share
instead of bytes: pstack files, Jev and Ruflo tools, Jev questions, threshold keys and plan-file conventions must be
named by both, except the harness-specific ones listed in SKILL_ALLOW. sync never rewrites a skill.
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


def drift(repo: Path) -> List[str]:
    want, out = plan(repo), []
    for rel, src in want.items():
        dest = Path(repo) / rel
        if not dest.is_file():
            out.append("missing " + rel)
        elif not _same(src, dest):
            out.append("differs " + rel)
    out += ["extra " + rel for rel in _existing(repo) if rel not in want]
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
    want, changed = plan(repo), []
    for line in drift(repo):
        kind, rel = line.split(" ", 1)
        dest = Path(repo) / rel
        if kind == "extra":
            dest.unlink()
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(want[rel]), str(dest))
        changed.append(rel)
    return changed


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--repo", default=str(REPO))
    a = ap.parse_args(argv)
    repo = Path(a.repo)
    if a.check:
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
        return 1 if bad or skills else 0
    for rel in sync(repo):
        print("synced " + rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
