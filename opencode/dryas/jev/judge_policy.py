"""Project-local judge policy (docs/specs/2026-10-19-project-local-judge-design.md).

A committed `.dryas-judge` file at a project root keeps every judge call for sessions at or below that folder on
the local judge. Any marker means local, whatever it holds; the file is never read. Start folders: the given cwd,
the process folder (or the folder recorded at import if it is gone) and CLAUDE_PROJECT_DIR; any covered one means
local. A folder is covered when the marker sits in it or a parent on its logical (abspath) or resolved (realpath)
chain. An unexpected error while looking counts as a marker, and no start folder at all means local (fail closed).
Only positive answers are cached, so a marker added later is seen at the next call."""
import os
from typing import Iterator, Optional, Set

MARKER = ".dryas-judge"
_covered: Set[str] = set()


def _getcwd() -> Optional[str]:
    try:
        return os.getcwd()
    except OSError:
        return None


_PROCESS_START = _getcwd()


def clear_cache() -> None:
    _covered.clear()


def _marked(folder: str) -> bool:
    try:
        os.lstat(os.path.join(folder, MARKER))
        return True
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:  # e.g. a parent without search permission: fail closed
        return True


def _chain_marked(cur: str) -> bool:
    while True:
        if _marked(cur):
            return True
        parent = os.path.dirname(cur)
        if parent == cur:
            return False
        cur = parent


def _covers(start: str, seen: Set[str]) -> bool:
    key = os.path.abspath(start)  # no filesystem calls, so a cache hit stays free
    if key in _covered:
        return True
    for head in (key, os.path.realpath(key)):
        if head not in seen:  # cwd is usually the process folder: walk each chain once per call
            seen.add(head)
            if _chain_marked(head):
                _covered.add(key)
                return True
    return False


def _rest() -> Iterator[Optional[str]]:
    proc = _getcwd()
    yield proc if proc is not None else _PROCESS_START
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        yield env


def project_local(cwd: Optional[str] = None) -> bool:
    seen: Set[str] = set()
    if isinstance(cwd, str) and cwd and _covers(cwd, seen):
        return True
    for start in _rest():
        if start is None:
            return True  # no process folder to judge by: fail closed
        if _covers(start, seen):
            return True
    return False
