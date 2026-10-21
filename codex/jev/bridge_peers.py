"""Bridge discovery and identity (docs/specs/2026-10-18-cross-account-bridge-design.md §4): live Claude Code sessions
in every config dir listed in accounts.json or found under ~/.claude*. Reads only <dir>/sessions/*.json and only the fields in FIELDS; *.key
files are never opened. A missing or broken file is skipped, never raised."""
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
FIELDS = ("pid", "procStart", "sessionId", "name", "cwd", "status", "updatedAt", "kind")
PEER_KEYS = ("name", "sessionId", "account", "cwd", "status", "idle_for", "same_account", "kind", "dryas")
HINT = ("same-account peers: native SendMessage reaches them even when idle; use send_message for other accounts"
        "; a peer with dryas false cannot receive bridge messages (install Dryas on its account)")
_ME: Dict[str, Any] = {}  # this MCP server's own session's pid and config dir, kept once found


def own_dir() -> str:
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def discovered_dirs() -> List[str]:
    """Config dirs found by scanning the home folder: ~/.claude, ~/.claude-* and ~/.claude.* that are real
    directories (not symlinks) with a sessions folder. Sorted; [] on any error."""
    home = os.path.expanduser("~")
    try:
        names = sorted(os.listdir(home))
    except OSError:
        return []
    out = []
    for n in names:
        d = os.path.join(home, n)
        if (n == ".claude" or n.startswith(".claude-") or n.startswith(".claude.")) and not os.path.islink(d) \
                and os.path.isdir(os.path.join(d, "sessions")):
            out.append(d)
    return out


def has_dryas(d: str) -> bool:
    return os.path.isfile(os.path.join(d, ".dryas-plugin.json"))


def _with_discovered(dirs: List[str]) -> List[str]:
    seen = {os.path.realpath(d) for d in dirs}
    for d in discovered_dirs():
        if os.path.realpath(d) not in seen:
            seen.add(os.path.realpath(d))
            dirs.append(d)
    return dirs


def account_dirs() -> Tuple[List[str], Optional[str]]:
    """The config dirs to search, each once (accounts.json first, then discovered ones), and a note when
    accounts.json could not be used."""
    try:
        with open(paths.accounts_file(), encoding="utf-8") as f:
            raw = json.load(f).get("claude_dirs")
        dirs: List[str] = []
        seen: Set[str] = set()
        for d in raw:
            if isinstance(d, str) and d.strip() and os.path.normpath(d) not in seen:
                seen.add(os.path.normpath(d))
                dirs.append(d)
        if dirs:
            return _with_discovered(dirs), None
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return _with_discovered([own_dir()]), "accounts.json unreadable; found accounts by scanning ~/.claude*"


def account(d: str) -> str:
    """An account's label: the config dir's base name (".claude-two"), never the full path."""
    return os.path.basename(os.path.normpath(d))


def _read(path: str, d: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    s = {k: raw.get(k) for k in FIELDS}
    pid, sid = s["pid"], s["sessionId"]
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0 or not isinstance(sid, str) or not UUID.match(sid):
        return None
    s["_dir"] = d
    return s


def read_sessions(dirs: List[str]) -> List[Dict[str, Any]]:
    """Live-looking records of every dir, one per pid and start time: a copied sessions folder lists the same process
    again, and the first dir (listed before discovered) wins."""
    out = []
    seen: Set[Tuple[int, str]] = set()
    for d in dirs:
        sd = os.path.join(d, "sessions")
        try:
            names = sorted(os.listdir(sd))
        except OSError:
            continue
        for n in names:
            if n.endswith(".json"):
                s = _read(os.path.join(sd, n), d)
                key = (s["pid"], _norm_time(s["procStart"])) if s else None
                if s and key not in seen:
                    seen.add(key)
                    out.append(s)
    return out


def pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":  # os.kill would terminate the process on Windows
        import ctypes
        k = ctypes.windll.kernel32
        k.OpenProcess.restype = ctypes.c_void_p
        k.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        k.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _norm_time(s: Any) -> str:
    return " ".join(s.split()) if isinstance(s, str) else ""


def start_times(pids: List[int]) -> Optional[Dict[int, str]]:
    """pid -> start time as Claude Code writes procStart ("Sun Oct 18 12:00:22 2026", UTC), from one ps call.
    None when ps cannot be used (Windows, not installed, failed)."""
    if os.name == "nt":
        return None
    if not pids:
        return {}
    try:
        r = subprocess.run(["ps", "-o", "pid=,lstart=", "-p", ",".join(str(p) for p in pids)], capture_output=True,
                           text=True, env=dict(os.environ, TZ="UTC", LC_ALL="C"), timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    out = {}
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[0].isdigit():
            out[int(parts[0])] = " ".join(parts[1:6])
    if not out and r.returncode not in (0, 1):
        return None
    return out


def live(sessions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Sessions whose pid runs and whose process started at procStart (a reused pid does not count). A session
    without a procStart is checked by pid only."""
    running = [s for s in sessions if pid_running(s["pid"])]
    st = start_times(sorted({s["pid"] for s in running}))
    if st is None:
        return running, "start time not checked"
    kept, missing, skipped = [], 0, 0
    for s in running:
        want = _norm_time(s["procStart"])
        if not want:
            missing += 1
            kept.append(s)
        elif st.get(s["pid"]) == want:
            kept.append(s)
        else:
            skipped += 1
    notes = []
    if missing:
        notes.append("start time missing for %d session(s); checked by pid only" % missing)
    if skipped:
        notes.append("%d session(s) skipped: start time did not match (ended or pid reused)" % skipped)
    return kept, "; ".join(notes) or None


def _ancestors(limit: int = 4) -> List[int]:
    out, pid = [], os.getppid()
    while pid > 1 and len(out) < limit:
        out.append(pid)
        if os.name == "nt":
            break
        try:
            r = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True, timeout=2)
            pid = int(r.stdout.strip() or 0)
        except (OSError, ValueError, subprocess.SubprocessError):
            break
    return out


def me(dirs: List[str]) -> Optional[Dict[str, Any]]:
    """This MCP server's own session: sessions/<pid>.json of its parent process, or of up to 3 further ancestors
    (a wrapper between Claude Code and the server). Only where it was found is kept: the file is re-read on every
    call, so a /clear (new sessionId, same pid) is followed."""
    if "pid" in _ME:
        s = _read(os.path.join(_ME["dir"], "sessions", "%d.json" % _ME["pid"]), _ME["dir"])
        if s and s["pid"] == _ME["pid"]:
            return s
        _ME.clear()
    for pid in _ancestors():
        for d in dirs:
            s = _read(os.path.join(d, "sessions", "%d.json" % pid), d)
            if s and s["pid"] == pid:
                _ME["pid"], _ME["dir"] = pid, d
                return s
    return None


def pool(alive: List[Dict[str, Any]], me_: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The sessions a caller can reach: interactive, and not the caller itself."""
    return [s for s in alive if s["kind"] == "interactive" and not (me_ and s["sessionId"] == me_["sessionId"])]


def _peer(s: Dict[str, Any], mine: str, now: float) -> Dict[str, Any]:
    upd = s["updatedAt"]
    idle = int(max(0.0, now - upd / 1000.0)) if isinstance(upd, (int, float)) and not isinstance(upd, bool) else None
    return {"name": str(s["name"] or "")[:120], "sessionId": s["sessionId"], "account": account(s["_dir"]),
            "cwd": str(s["cwd"] or "")[:500], "status": str(s["status"] or "")[:16], "idle_for": idle,
            "same_account": os.path.normpath(s["_dir"]) == mine, "kind": str(s["kind"] or ""),
            "dryas": has_dryas(s["_dir"])}


def list_peers(now: Optional[float] = None) -> Dict[str, Any]:
    dirs, note = account_dirs()
    me_ = me(dirs)
    alive, note2 = live(read_sessions(dirs))
    mine = os.path.normpath(me_["_dir"] if me_ else own_dir())
    t = time.time() if now is None else now
    out: Dict[str, Any] = {"peers": [_peer(s, mine, t) for s in pool(alive, me_)], "hint": HINT}
    notes = [n for n in (note, note2) if n]
    if notes:
        out["note"] = "; ".join(notes)
    return out


def resolve(to: str, sessions: List[Dict[str, Any]], candidates: List[Dict[str, Any]],
            alive_ids: Set[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """The one candidate `to` names: an exact name first, else a sessionId prefix of 8 or more characters."""
    def match(group: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        hit = [s for s in group if s["name"] == to]
        if not hit and len(to) >= 8:
            hit = [s for s in group if s["sessionId"].startswith(to.lower())]
        return hit

    hit = match(candidates)
    if len(hit) == 1:
        return hit[0], None
    if hit:
        return None, "%r matches %d sessions: %s" % (to, len(hit), "; ".join(
            "%s %s %s %s" % (s["name"], s["sessionId"][:8], account(s["_dir"]), s["cwd"]) for s in hit))
    rest = match(sessions)
    gone = [s for s in rest if s["sessionId"] not in alive_ids]
    if gone:
        return None, "%s is not running" % (gone[0]["name"] or gone[0]["sessionId"][:8])
    if rest:
        return None, "%s is not an interactive session" % (rest[0]["name"] or rest[0]["sessionId"][:8])
    return None, "no live session named or starting with %r" % to
