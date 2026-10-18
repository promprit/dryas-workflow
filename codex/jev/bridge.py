"""Bridge tools on the jev MCP server (docs/specs/2026-10-18-cross-account-bridge-design.md): list_peers and
send_message. A message is one file in <data root>/inbox/<recipient sessionId>/; bridge_deliver.py shows it to the
recipient at its next prompt or Bash/Write/Edit call. Nothing goes over the network and no model is called."""
import json
import os
import re
import secrets
import shutil
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge_deliver as bd
import bridge_peers as bp
import jevlog
import paths
import redact

MAX_BYTES = 8192
MAX_WAITING = 50
RATE_N, RATE_WINDOW = 20, 600
PRUNE_EVERY, KEEP, TMP_AGE = 3600, 7 * 86400, 3600
REPLY_ID = re.compile(r"^m-[0-9a-f]{12}$")

TOOLS = [
    {"name": "list_peers",
     "description": ("List live Claude Code sessions on this machine across every account in Dryas accounts.json: "
                     "name, sessionId, account, cwd, status, idle_for, same_account. For same-account peers prefer "
                     "native SendMessage (it reaches idle sessions); use send_message for other accounts."),
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "send_message",
     "description": ("Leave a message for a session on any account. to: its name or a sessionId prefix of 8+ "
                     "characters. The recipient sees it at its next prompt or Bash/Write/Edit call, not while idle. "
                     "At most 8 KB; secrets are redacted. reply_to: the id of the message you answer."),
     "inputSchema": {"type": "object", "properties": {"to": {"type": "string"}, "text": {"type": "string"},
                                                      "reply_to": {"type": "string"}},
                     "required": ["to", "text"]}},
]
NAMES = frozenset(t["name"] for t in TOOLS)


def _mkdir(p: str) -> None:
    os.makedirs(p, mode=0o700, exist_ok=True)
    if os.path.islink(p):
        raise OSError("inbox folder is a symlink: %s" % p)


def _unlink(p: str) -> None:
    try:
        os.unlink(p)
    except OSError:
        pass


def _write(folder: str, name: str, obj: Any) -> None:
    """obj as JSON in folder/name: a private temp file renamed into place, so a reader never sees half a file.
    On Windows the rename is retried 5 times (antivirus or a reader holding the file)."""
    tmp = os.path.join(folder, ".tmp-" + secrets.token_hex(4))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, json.dumps(obj, ensure_ascii=False).encode("utf-8"))
    finally:
        os.close(fd)
    delay = 0.05
    for attempt in range(6):
        try:
            os.replace(tmp, os.path.join(folder, name))
            return
        except OSError:
            if os.name != "nt" or attempt == 5:
                _unlink(tmp)
                raise
            time.sleep(delay)
            delay *= 2


def _recent_sends(sid: str, now: float) -> List[float]:
    try:
        with open(os.path.join(paths.inbox_root(), ".rate", sid + ".json"), encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(raw, list):
        return []
    return [t for t in raw if isinstance(t, (int, float)) and not isinstance(t, bool) and now - t < RATE_WINDOW]


def _refuse(reason: str, **log: Any) -> Tuple[Dict[str, Any], bool]:
    jevlog.append("bridge", dict(log, event="refused", reason=reason[:200]))
    return {"error": reason}, True


def _label(s: Dict[str, Any]) -> str:
    return str(s["name"] or s["sessionId"][:8])


def send(args: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    text = args.get("text")
    if not isinstance(text, str) or not text.strip():
        return _refuse("text is empty")
    text = redact.redact(text)
    size = len(text.encode("utf-8"))
    if size > MAX_BYTES:
        return _refuse("too long, %d bytes; send a file path instead" % size)
    dirs, _ = bp.account_dirs()
    me = bp.me(dirs)
    if not me:
        return _refuse("cannot tell which session this is")
    to = args.get("to").strip() if isinstance(args.get("to"), str) else ""
    if not to:
        return _refuse("to is required")
    sessions = bp.read_sessions(dirs)
    alive, _ = bp.live(sessions)
    peer, err = bp.resolve(to, sessions, bp.pool(alive, me), {s["sessionId"] for s in alive})
    if err or peer is None:
        if to == me["name"] or (len(to) >= 8 and me["sessionId"].startswith(to.lower())):
            return _refuse("that is this session")
        return _refuse(err or "no peer", **{"from": me["sessionId"]})
    reply_to = args.get("reply_to")
    if reply_to is not None and (not isinstance(reply_to, str) or not REPLY_ID.match(reply_to)):
        return _refuse("bad reply_to")
    now = time.time()
    recent = _recent_sends(me["sessionId"], now)
    if len(recent) >= RATE_N:
        return _refuse("rate limit, %d sent in 10 min" % len(recent), **{"from": me["sessionId"]})
    folder = paths.inbox_dir(peer["sessionId"])
    _mkdir(paths.inbox_root())
    _mkdir(folder)
    if len(bd.waiting(folder)) >= MAX_WAITING:
        return _refuse("inbox full: %s has not taken a turn" % _label(peer), to=peer["sessionId"])
    rate = os.path.join(paths.inbox_root(), ".rate")
    _mkdir(rate)
    _write(rate, me["sessionId"] + ".json", (recent + [now])[-RATE_N:])  # counted first: a failed write still costs
    mid = "m-" + secrets.token_hex(6)
    _write(folder, "%d-%s.json" % (int(now * 1000), secrets.token_hex(4)), {
        "v": 1, "id": mid, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "from": {"sessionId": me["sessionId"], "name": str(me["name"] or ""), "account": bp.account(me["_dir"]),
                 "cwd": str(me["cwd"] or "")},
        "to": peer["sessionId"], "reply_to": reply_to, "text": text})
    jevlog.append("bridge", {"event": "sent", "id": mid, "from": me["sessionId"], "to": peer["sessionId"],
                             "bytes": size, "reply_to": reply_to})
    out = {"id": mid, "to": {"name": peer["name"], "sessionId": peer["sessionId"], "account": bp.account(peer["_dir"])},
           "delivery": "next turn of the recipient", "recipient_status": str(peer["status"] or "")}
    if peer["status"] == "idle":
        out["note"] = "%s is idle: it sees this when its user next types or it next runs a tool" % _label(peer)
    return out, False


def _files(folder: str) -> List[Tuple[str, float]]:
    out = []
    for base, _dirs, names in os.walk(folder):
        for n in names:
            p = os.path.join(base, n)
            try:
                out.append((p, os.lstat(p).st_mtime))
            except OSError:
                pass
    return out


def prune(now: Optional[float] = None) -> None:
    """At most once an hour: delivered/ and bad/ files after 7 days, an ended session's inbox once its newest file is
    7 days old, temp files after 1 hour, and the send counts of ended sessions."""
    root = paths.inbox_root()
    if not os.path.isdir(root) or os.path.islink(root):
        return
    now = time.time() if now is None else now
    stamp = os.path.join(root, ".last_prune")
    try:
        if now - os.path.getmtime(stamp) < PRUNE_EVERY:
            return
    except OSError:
        pass
    with open(stamp, "a", encoding="utf-8"):
        pass
    os.utime(stamp, (now, now))
    alive = {s["sessionId"] for s in bp.live(bp.read_sessions(bp.account_dirs()[0]))[0]}
    files = folders = 0
    for name in os.listdir(root):
        p = os.path.join(root, name)
        if os.path.islink(p) or not os.path.isdir(p):
            continue
        if name == ".rate":
            for f in os.listdir(p):
                if f[:-5] not in alive:
                    _unlink(os.path.join(p, f))
                    files += 1
            continue
        if not bd.UUID.match(name):
            continue
        found = _files(p)
        if name not in alive and all(now - m > KEEP for _, m in found):
            shutil.rmtree(p, ignore_errors=True)
            folders += 1
            continue
        for f, m in found:
            sub, n = os.path.basename(os.path.dirname(f)), os.path.basename(f)
            if (sub in ("delivered", "bad") and now - m > KEEP) or (n.startswith(".tmp-") and now - m > TMP_AGE):
                _unlink(f)
                files += 1
    jevlog.append("bridge", {"event": "pruned", "files": files, "folders": folders})


def call(name: str, args: Any) -> Tuple[Any, bool]:
    args = args if isinstance(args, dict) else {}
    if paths.copy_root():
        return {"error": "not supported in a cloud copy"}, True
    try:
        if name == "list_peers":
            out: Tuple[Any, bool] = (bp.list_peers(), False)
        elif name == "send_message":
            out = send(args)
        else:
            return {"error": "unknown bridge tool"}, True
        try:
            prune()
        except OSError:
            pass
        return out
    except OSError as e:
        jevlog.append("bridge", {"event": "refused", "reason": "os error " + type(e).__name__})
        return {"error": "inbox not writable (%s)" % type(e).__name__}, True
