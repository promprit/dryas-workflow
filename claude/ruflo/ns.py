"""Ruflo data namespace and data root. Same rules as mcp-shim/bin/cli.js (shared vectors: tests/ns_cases.json).

Namespace = folder name of the MAIN repo (worktrees map to their main repo), else the basename of the
project dir; sanitized to [A-Za-z0-9._-] per character. Data root: DRYAS_DATA_ROOT, default ~/.dryas
(RUFLO_SSD_ROOT, tests only: <root>/_caches).
"""
import os
import re
import subprocess
from typing import List, Optional

_BAD = re.compile(r"[^A-Za-z0-9._-]")


def _parts(p: str) -> List[str]:
    return p.replace("\\", "/").rstrip("/").split("/")


def ns_from(start: str, common_dir: Optional[str]) -> str:
    name = None
    if common_dir:
        c = _parts(common_dir)
        if len(c) >= 2 and c[-1] == ".git" and c[-2]:
            name = c[-2]
    if name is None:
        name = _parts(start)[-1]
    name = _BAD.sub("_", name)
    return "_unknown" if name in ("", ".", "..") else name


def common_dir(start: str) -> Optional[str]:
    try:
        p = subprocess.run(["git", "-C", start, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    out = p.stdout.strip()
    return out if p.returncode == 0 and out else None


def ruflo_ns(start: Optional[str] = None) -> str:
    start = start or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return ns_from(start, common_dir(start))


def ruflo_root() -> Optional[str]:
    t = os.environ.get("RUFLO_SSD_ROOT")
    if t:
        return os.path.join(t, "_caches") if os.path.isdir(t) else None
    r = os.environ.get("DRYAS_DATA_ROOT") or os.path.join(os.path.expanduser("~"), ".dryas")
    return r if os.path.isdir(r) else None
