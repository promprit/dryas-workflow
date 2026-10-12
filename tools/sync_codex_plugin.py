#!/usr/bin/env python3
"""Copy the runtime the Codex plugin needs from claude/ (the source of truth) into codex/.
Codex installs a plugin by copying it and drops symlinks, so these are real copies.
  python tools/sync_codex_plugin.py           write codex/jev and codex/pstack
  python tools/sync_codex_plugin.py --check   list drift, exit 1 if any (CI)
"""
import argparse
import shutil
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
TREES = (("claude/jev", "codex/jev"), ("claude/pstack", "codex/pstack"))
CACHE_DIRS = {"__pycache__", ".pytest_cache"}
SKIP_DIRS = {"tests", "logs", "compact"} | CACHE_DIRS  # logs/compact are gitignored runtime dirs
SKIP_FILES = {".gitignore"}


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
        return 1 if bad else 0
    for rel in sync(repo):
        print("synced " + rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
