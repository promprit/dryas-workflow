"""Memory namespace: the folder name of the MAIN repo (worktrees map to it), else the basename of the start
dir, sanitized to [A-Za-z0-9._-] per character. Same rules and test vectors as claude/ruflo/ns.py
(claude/ruflo/tests/ns_cases.json), so Dryas memory and Ruflo memory agree on namespaces. A separate module
name because claude/jev and claude/ruflo are both on sys.path in one pytest run."""
import os
import re
import subprocess
from typing import List, Optional

_BAD = re.compile(r"[^A-Za-z0-9._-]")


def _parts(p: str) -> List[str]:
    return p.replace("\\", "/").rstrip("/").split("/")


def sanitize(name: str) -> str:
    name = _BAD.sub("_", name)
    return "_unknown" if name in ("", ".", "..") else name


def ns_from(start: str, common_dir: Optional[str]) -> str:
    name = None
    if common_dir:
        c = _parts(common_dir)
        if len(c) >= 2 and c[-1] == ".git" and c[-2]:
            name = c[-2]
    if name is None:
        name = _parts(start)[-1]
    return sanitize(name)


def _walk_common_dir(start: str) -> Optional[str]:
    """The git common dir read from the first .git entry upward from start; None when there is none."""
    d = os.path.realpath(start)
    while True:
        g = os.path.join(d, ".git")
        if os.path.isdir(g):
            return g
        if os.path.isfile(g):
            with open(g, encoding="utf-8") as f:
                line = f.readline().strip()
            if not line.startswith("gitdir:"):
                return None
            x = os.path.realpath(os.path.join(d, line[len("gitdir:"):].strip()))
            cd = os.path.join(x, "commondir")
            if os.path.isfile(cd):
                with open(cd, encoding="utf-8") as f:
                    return os.path.realpath(os.path.join(x, f.read().strip()))
            return x
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def common_dir(start: str) -> Optional[str]:
    """Read .git entries first (no subprocess inside a checkout); ask git only when none is found."""
    try:
        found = _walk_common_dir(start)
    except OSError:
        found = None
    if found:
        return found
    try:
        p = subprocess.run(["git", "-C", start, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                           capture_output=True, text=True, timeout=1)
    except (OSError, subprocess.SubprocessError):
        return None
    out = p.stdout.strip()
    return out if p.returncode == 0 and out else None


def main_root(start: str) -> Optional[str]:
    """The main repo's root (a worktree maps to it); None outside git or for a bare repo."""
    c = common_dir(start)
    if c and _parts(c)[-1] == ".git":
        return os.path.dirname(c.replace("\\", "/").rstrip("/"))
    return None


def project_ns(start: Optional[str] = None) -> str:
    start = start or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return ns_from(start, common_dir(start))
