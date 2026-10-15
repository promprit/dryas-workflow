"""Import Ruflo memory into the Dryas store (owned core, sub-project B).

The Ruflo database is opened read-only and never changed. Every row is imported with source 'ruflo', its
namespace, timestamps and hit count, and the embedding kept as a blob for a later semantic provider. The
commands, feedback and session namespaces (hook noise) become kind 'archive', left out of default recall.
Idempotent: a row is keyed by its Ruflo id, and a row forgotten in Dryas is not brought back. Bodies pass
through redact.py (MEM-4); the report counts the redactions."""
import json
import os
import sqlite3
import sys
import time
import urllib.request
from collections import Counter
from typing import Any, Dict, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memdb
import paths
import projns
import redact

ARCHIVE_NS = ("commands", "feedback", "session")
MAX_BODY = 64 * 1024
BATCH = 1000
COLUMNS = ("id", "key", "namespace", "content", "type", "embedding", "tags", "metadata", "created_at",
           "updated_at", "last_accessed_at", "access_count", "status")


def default_source() -> str:
    return os.path.join(paths.ruflo_dir(), "memory", "agentdb-memory.db")


def _secs(v: Any) -> Any:
    """Ruflo writes milliseconds; older rows may hold seconds."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f / 1000.0 if f > 1e11 else f


def _tags(v: Any) -> Tuple[str, bool]:
    """Tags as a JSON list, each redacted; True when a redaction changed one."""
    try:
        parsed = json.loads(v) if isinstance(v, str) else None
    except ValueError:
        parsed = None
    raw = [str(t) for t in parsed][:20] if isinstance(parsed, list) else []
    clean = [redact.redact(t) for t in raw]
    return json.dumps([t[:64] for t in clean]), clean != raw


def _ns(r: Dict[str, Any]) -> str:
    return projns.sanitize(str(r["namespace"]) if r["namespace"] else "default")


def _row(r: Dict[str, Any]) -> Tuple[Tuple[Any, ...], bool]:
    ns = _ns(r)
    content = str(r["content"] or "")[:MAX_BODY]
    body = redact.redact(content)
    raw_title = str(r["key"] or "")[:200]
    title = redact.redact(raw_title)
    tags, tags_changed = _tags(r["tags"])
    emb = r["embedding"]
    emb = emb.encode("utf-8") if isinstance(emb, str) else emb
    raw_meta = r["metadata"]
    meta_text = redact.redact(raw_meta) if isinstance(raw_meta, str) else raw_meta
    meta = json.dumps(dict(ruflo_id=r["id"], type=r["type"], status=r["status"], updated=_secs(r["updated_at"]),
                           metadata=meta_text))
    created = _secs(r["created_at"]) or time.time()
    try:
        hits = int(r["access_count"] or 0)
    except (TypeError, ValueError):
        hits = 0
    return ((ns, "archive" if ns in ARCHIVE_NS else "outcome", title, body, tags, "ruflo", str(r["id"]),
             memdb.content_hash(title, body), emb, meta, created, _secs(r["last_accessed_at"]), hits),
            body != content or title != raw_title or meta_text != raw_meta or tags_changed)


def import_ruflo(conn, src: str) -> Dict[str, Any]:
    if not os.path.isfile(src):
        raise FileNotFoundError(src)
    s = sqlite3.connect("file:%s?mode=ro" % urllib.request.pathname2url(os.path.abspath(src)), uri=True)
    try:
        cols = [c[1] for c in s.execute("PRAGMA table_info(memory_entries)")]
        if "id" not in cols:
            raise ValueError("no Ruflo memory_entries table in %s" % src)
        sel = ", ".join(c if c in cols else "NULL AS %s" % c for c in COLUMNS)
        before = conn.execute("SELECT COUNT(*) FROM memory WHERE source = 'ruflo'").fetchone()[0]
        have = {(n, k): h for n, k, h in conn.execute("SELECT ns, key, hash FROM memory WHERE source = 'ruflo'")}
        src_ids = set()
        src_counts: Counter = Counter()
        redacted = updated = 0
        cur = s.execute("SELECT %s FROM memory_entries" % sel)
        while True:
            batch = cur.fetchmany(BATCH)
            if not batch:
                break
            rows = []
            for b in batch:
                r = dict(zip(COLUMNS, b))
                src_counts[_ns(r)] += 1
                vals, red = _row(r)
                rows.append(vals)
                src_ids.add((vals[0], vals[6]))
                redacted += red
            with memdb.tx(conn):
                gone = {(n, k) for n, k in conn.execute("SELECT ns, key FROM forgotten WHERE source = 'ruflo'")}
                for v in rows:
                    ident = (v[0], v[6])
                    if ident in gone:
                        continue
                    if ident not in have:
                        conn.execute(
                            "INSERT OR IGNORE INTO memory (ns, kind, title, body, tags, source, key, hash, embedding, "
                            "meta, created, accessed, hits) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", v)
                    elif have[ident] != v[7]:
                        conn.execute("UPDATE memory SET title = ?, body = ?, tags = ?, hash = ?, embedding = ?, meta = ? "
                                     "WHERE ns = ? AND source = 'ruflo' AND key = ?",
                                     (v[2], v[3], v[4], v[7], v[8], v[9], v[0], v[6]))
                        updated += 1
                    have[ident] = v[7]
    finally:
        s.close()
    present = {(n, k) for n, k in conn.execute("SELECT ns, key FROM memory WHERE source = 'ruflo'")}
    present |= {(n, k) for n, k in conn.execute("SELECT ns, key FROM forgotten WHERE source = 'ruflo'")}
    dst = {n: c for n, c in conn.execute("SELECT ns, COUNT(*) FROM memory WHERE source = 'ruflo' GROUP BY ns")}
    forgot = {n: c for n, c in conn.execute("SELECT ns, COUNT(*) FROM forgotten WHERE source = 'ruflo' GROUP BY ns")}
    missing = Counter(n for n, k in src_ids - present)
    nss = {n: {"source": c, "imported": dst.get(n, 0), "forgotten": forgot.get(n, 0), "missing": missing.get(n, 0)}
           for n, c in sorted(src_counts.items())}
    after = conn.execute("SELECT COUNT(*) FROM memory WHERE source = 'ruflo'").fetchone()[0]
    return {"namespaces": nss, "new": after - before, "updated": updated, "redacted": redacted,
            "ok": not any(v["missing"] for v in nss.values())}
