"""Project-local judge policy (docs/specs/2026-10-19-project-local-judge-design.md).

A committed `.dryas-judge` file at a project root keeps every judge call for sessions at or below that folder on
the local judge. Any marker means local, whatever it holds; the file is never read. An unexpected error while
looking counts as a marker (fail closed). Results are cached per start folder for the life of the process."""
import os
from typing import Dict, Optional

MARKER = ".dryas-judge"
_cache: Dict[str, bool] = {}


def clear_cache() -> None:
    _cache.clear()


def _start(cwd: Optional[str]) -> Optional[str]:
    if isinstance(cwd, str) and cwd:
        return cwd
    try:
        return os.getcwd()
    except OSError:
        return None


def _marked(folder: str) -> bool:
    try:
        os.lstat(os.path.join(folder, MARKER))
        return True
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:  # e.g. a parent without search permission: fail closed
        return True


def project_local(cwd: Optional[str] = None) -> bool:
    start = _start(cwd)
    if start is None:
        return False
    key = os.path.abspath(start)  # no filesystem calls, so a cache hit stays free
    hit = _cache.get(key)
    if hit is not None:
        return hit
    cur, hit = os.path.realpath(key), False
    while True:
        if _marked(cur):
            hit = True
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    _cache[key] = hit
    return hit
