"""Memory tools on the Dryas MCP server (owned core, sub-project B): memory_search, memory_store, memory_list,
memory_forget and swarm_init, with Ruflo's argument names accepted (key/value, namespace). jev_mcp.py lists
TOOLS and routes NAMES here. MEM-5: when the store cannot be opened every tool answers with degraded: true
instead of failing, and swarm_init still returns an id so /orchestrate continues."""
import json
import os
import sqlite3
import sys
import time
import uuid
from typing import Any, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memdb
import memstore
import projns
import redact

_NS = {"type": "string", "description": "Main repo folder name; default: the current project's"}
TOOLS = [
    {"name": "memory_search",
     "description": ("Search Dryas memory in one namespace (default: this project). Returns the top results with a "
                     "reason each, plus learned patterns that mention a query word (file failure rates, files edited "
                     "together, the tier that finished a task type). Archived hook noise only with include_archive."),
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string"}, "namespace": _NS, "limit": {"type": "integer", "minimum": 1, "maximum": 20},
         "include_archive": {"type": "boolean"}}, "required": ["query"]}},
    {"name": "memory_store",
     "description": ("Store one task outcome (what worked, what failed) in Dryas memory. Secrets, diffs and bodies "
                     "over 4000 characters are refused (MEM-4). Ruflo's key/value are accepted as title/body."),
     "inputSchema": {"type": "object", "properties": {
         "title": {"type": "string"}, "body": {"type": "string"}, "key": {"type": "string"}, "value": {},
         "namespace": _NS, "kind": {"type": "string", "enum": list(memstore.STORE_KINDS)},
         "tags": {"type": "array", "items": {"type": "string"}}, "task_id": {"type": "string"},
         "commit": {"type": "string"}}}},
    {"name": "memory_list",
     "description": "List Dryas memory in one namespace, newest first (bodies cut to 300 characters).",
     "inputSchema": {"type": "object", "properties": {
         "namespace": _NS, "kind": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100},
         "offset": {"type": "integer", "minimum": 0}, "include_archive": {"type": "boolean"}}}},
    {"name": "memory_forget",
     "description": "Delete one memory by id. Notes mirror the Claude memory files: edit or delete the file instead.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "integer", "minimum": 1}, "namespace": _NS},
                     "required": ["id"]}},
    {"name": "swarm_init",
     "description": ("Open a task record for an orchestrated run and return its swarm id. Kept for Ruflo "
                     "compatibility: the topology is recorded, and the dispatch log stays the ledger of record."),
     "inputSchema": {"type": "object", "properties": {
         "topology": {"type": "string"}, "task": {"type": "string"},
         "scope": {"type": "array", "items": {"type": "string"}}, "maxAgents": {"type": "integer"},
         "strategy": {"type": "string"}, "namespace": _NS}}},
]
NAMES = frozenset(t["name"] for t in TOOLS)


def _ns(args: Dict[str, Any]) -> str:
    v = args.get("namespace")
    return projns.sanitize(v.strip()) if isinstance(v, str) and v.strip() else projns.project_ns()


def _int(v: Any, default: Optional[int], lo: int, hi: int) -> Optional[int]:
    if isinstance(v, bool):
        return default
    if isinstance(v, str) and v.strip().isdigit():
        v = int(v.strip())
    if not isinstance(v, int):
        return default
    return max(lo, min(v, hi))


def _opt(v: Any) -> Optional[str]:
    return str(v)[:200] if isinstance(v, (str, int)) and not isinstance(v, bool) and str(v).strip() else None


def _session() -> str:
    return os.environ.get("JEV_SESSION_ID") or "pid-%d" % os.getpid()


def _topology(args: Dict[str, Any]) -> str:
    t = args.get("topology")
    return t.strip()[:32] if isinstance(t, str) and t.strip() else "hierarchical"


def _swarm_id() -> str:
    return "swarm-" + uuid.uuid4().hex[:12]


def _degraded(name: str, ns: str, args: Dict[str, Any], err: Exception) -> Dict[str, Any]:
    out: Dict[str, Any] = {"degraded": True, "namespace": ns, "cause": type(err).__name__}
    if name in ("memory_search", "memory_list"):
        out["results"] = []
    elif name == "memory_store":
        out["stored"] = False
    elif name == "memory_forget":
        out["forgotten"] = False
    elif name == "swarm_init":
        out.update(swarmId=_swarm_id(), topology=_topology(args))
    return out


def _store(conn, ns: str, args: Dict[str, Any]) -> Tuple[Any, bool]:
    body = args.get("body", args.get("value"))
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
    if not isinstance(body, str) or not body.strip():
        return {"stored": False, "reason": "body (or value) is required"}, True
    title = args.get("title", args.get("key"))
    title = str(title) if isinstance(title, (str, int)) and not isinstance(title, bool) else body.strip().splitlines()[0][:80]
    tags = args.get("tags")
    try:
        r = memstore.store(conn, ns, title, body, kind=args.get("kind") if args.get("kind") in memstore.STORE_KINDS else "outcome",
                           tags=[t for t in tags if isinstance(t, str)] if isinstance(tags, list) else [],
                           task_id=_opt(args.get("task_id")), commit=_opt(args.get("commit")))
    except memstore.Rejected as e:
        return {"stored": False, "reason": str(e)}, True
    return dict(r, namespace=ns), False


def _call(conn, name: str, ns: str, args: Dict[str, Any]) -> Tuple[Any, bool]:
    if name == "memory_search":
        res = memstore.search(conn, ns, str(args.get("query") or ""), limit=_int(args.get("limit"), 3, 1, 20),
                              include_archive=args.get("include_archive") is True, session=_session())
        return dict(res, namespace=ns), False
    if name == "memory_store":
        return _store(conn, ns, args)
    if name == "memory_list":
        rows = memstore.list_entries(conn, ns, kind=_opt(args.get("kind")), limit=_int(args.get("limit"), 20, 1, 100),
                                     offset=_int(args.get("offset"), 0, 0, 10 ** 9),
                                     include_archive=args.get("include_archive") is True)
        return {"results": rows, "namespace": ns}, False
    if name == "memory_forget":
        mid = args.get("id")
        if isinstance(mid, str) and mid.strip().isdigit():
            mid = int(mid.strip())
        if isinstance(mid, bool) or not isinstance(mid, int) or mid < 1:
            return {"forgotten": False, "reason": "id must be a positive integer"}, True
        status = memstore.forget(conn, ns, mid)
        if status == "note":
            return {"forgotten": False, "reason": "this mirrors a Claude memory file; edit or delete the file and it "
                                                  "leaves the index at the next session start"}, True
        return {"forgotten": status == "forgotten", "status": status}, False
    if name == "swarm_init":
        sid, topo = _swarm_id(), _topology(args)
        scope = args.get("scope")
        scope = [redact.redact(s)[:200] for s in scope if isinstance(s, str)][:64] if isinstance(scope, list) else []
        with memdb.tx(conn):
            conn.execute("INSERT INTO tasks (task_id, ns, title, scope, started, meta) VALUES (?, ?, ?, ?, ?, ?)",
                         (sid, ns, redact.redact(str(args.get("task") or ""))[:200], json.dumps(scope), time.time(),
                          json.dumps({"topology": topo, "kind": "swarm"})))
        return {"swarmId": sid, "topology": topo, "namespace": ns}, False
    return {"error": "unknown memory tool"}, True


def call(name: str, args: Any) -> Tuple[Any, bool]:
    args = args if isinstance(args, dict) else {}
    ns = _ns(args)
    try:
        conn = memdb.connect()
    except (sqlite3.Error, OSError) as e:
        return _degraded(name, ns, args, e), False
    try:
        return _call(conn, name, ns, args)
    except sqlite3.Error as e:
        return _degraded(name, ns, args, e), False
    finally:
        conn.close()
