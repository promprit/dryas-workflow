"""Memory consolidation outside the hook budget (owned core D). A lock keeps runs from overlapping; a kv marker
lets the next session start retry a namespace whose consolidation was skipped inside a hook."""
import os
import subprocess
import sys
import time
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memdb
import paths

LOCK_NAME = "consolidate.lock"
STALE_S = 600
PREFIX = "consolidate_pending:"
HERE = os.path.dirname(os.path.abspath(__file__))


def _create(p: str) -> Optional[int]:
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError:
        return None
    os.write(fd, str(os.getpid()).encode("ascii"))
    return fd


def _age(p: str) -> Optional[float]:
    try:
        return time.time() - os.path.getmtime(p)
    except OSError:
        return None


def _take_over(p: str) -> Optional[int]:
    """Replace a stale lock. A guard file serialises takers and the age is checked again under it, so when two
    runs find the same stale lock only one replaces it; the other sees the fresh lock and gets None."""
    guard = p + ".takeover"
    g = _create(guard)
    if g is None:
        age = _age(guard)
        if age is not None and age > STALE_S:  # a taker crashed inside the guard; the next run can try again
            try:
                os.remove(guard)
            except OSError:
                pass
        return None
    try:
        age = _age(p)
        if age is not None and age <= STALE_S:
            return None  # another run took over first
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
        return _create(p)
    except OSError:
        return None
    finally:
        os.close(g)
        try:
            os.remove(guard)
        except OSError:
            pass


def acquire(root: str) -> Optional[int]:
    p = os.path.join(root, LOCK_NAME)
    fd = _create(p)
    if fd is not None:
        return fd
    age = _age(p)
    if age is None:
        return _create(p)  # released between the two calls
    return _take_over(p) if age > STALE_S else None


def release(root: str, fd: int) -> None:
    p = os.path.join(root, LOCK_NAME)
    try:
        mine = os.path.samestat(os.fstat(fd), os.stat(p))  # a run that outlived STALE_S may have lost the file
    except OSError:
        mine = False
    try:
        os.close(fd)
    except OSError:
        pass
    if mine:
        try:
            os.remove(p)
        except OSError:
            pass


def mark_pending(conn, ns: str) -> None:
    with memdb.tx(conn):
        conn.execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", (PREFIX + ns, str(time.time())))


def pending(conn) -> List[str]:
    return [r[0][len(PREFIX):] for r in conn.execute("SELECT key FROM kv WHERE key GLOB ? ORDER BY key",
                                                     (PREFIX + "*",))]


def clear_pending(conn, ns: str) -> None:
    with memdb.tx(conn):
        conn.execute("DELETE FROM kv WHERE key = ?", (PREFIX + ns,))


def spawn(ns: Optional[str]) -> bool:
    """Start `memcli.py consolidate [--ns NS]` detached, stdio to devnull; never waits for it."""
    argv = [paths.python(), "-X", "utf8", os.path.join(HERE, "memcli.py"), "consolidate"] + (["--ns", ns] if ns else [])
    kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    try:
        subprocess.Popen(argv, **kw)
        return True
    except OSError:
        return False
