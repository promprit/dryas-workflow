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


def common_dir(start: str) -> Optional[str]:
    try:
        p = subprocess.run(["git", "-C", start, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                           capture_output=True, text=True, timeout=5)
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
