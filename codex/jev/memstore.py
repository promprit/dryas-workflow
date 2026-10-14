"""Memory rows (owned core, sub-project B): store with the MEM-4 checks, search with one explainable ranking
on FTS5 and on the LIKE fallback, list, forget.

Ranking: the share of query terms matched (a term matches when it starts one of the row's words), then the
PageRank of the memory graph and how often a memory was used, both written by memlearn.consolidate. Every
result carries a reason string; search also returns the learned patterns whose key mentions a query term."""
import json
import os
import re
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memdb
import redact

MAX_TITLE = 200
MAX_BODY = 4000
STORE_KINDS = ("outcome", "fact", "retro")
RANK_WEIGHT = 0.3
HIT_WEIGHT = 0.1
CANDIDATES = 200
LIKE_CANDIDATES = 2000
MAX_TERMS = 16
_WORD = re.compile(r"[^\W_]+")
_DIFF = re.compile(r"^(?:diff --git |@@ -\d+(?:,\d+)? \+\d+|\+\+\+ [ab/]|--- a/|index [0-9a-f]{7,}\.\.[0-9a-f]{7,})", re.M)


class Rejected(ValueError):
    """MEM-4: this content may not be stored."""


def check(title: str, body: str) -> None:
    if not title.strip() and not body.strip():
        raise Rejected("nothing to store: title and body are empty")
    if len(title) > MAX_TITLE:
        raise Rejected("title is %d characters; keep it under %d" % (len(title), MAX_TITLE))
    if len(body) > MAX_BODY:
        raise Rejected("body is %d characters, the cap is %d: store what worked and what failed, not file contents"
                       % (len(body), MAX_BODY))
    if _DIFF.search(body):
        raise Rejected("body looks like a diff: store the outcome, not the patch")
    for text in (title, body):
        if redact.redact(text) != text:
            raise Rejected("contains a secret-shaped value (MEM-4); remove it and store again")


def store(conn, ns: str, title: str, body: str, kind: str = "outcome", tags: Iterable[str] = (),
          task_id: Optional[str] = None, commit: Optional[str] = None, source: str = "dryas",
          key: Optional[str] = None, created: Optional[float] = None, meta: Optional[Dict[str, Any]] = None,
          check_content: bool = True) -> Dict[str, Any]:
    title, body = (title or "").strip(), (body or "").strip()
    if check_content:
        check(title, body)
    h = memdb.content_hash(title, body)
    tag_list = [str(t)[:64] for t in (tags or ())][:20]
    with memdb.tx(conn):
        if key is None:
            same = conn.execute("SELECT id FROM memory WHERE ns = ? AND hash = ? AND kind != 'note' LIMIT 1",
                                (ns, h)).fetchone()
            if same:
                return {"id": same["id"], "stored": False, "duplicate": True}
        cur = conn.execute(
            'INSERT OR IGNORE INTO memory (ns, kind, title, body, tags, task_id, "commit", source, key, hash, meta, created) '
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ns, kind, title, body, json.dumps(tag_list), task_id, commit, source, key, h, json.dumps(meta or {}),
             time.time() if created is None else created))
        if cur.rowcount == 0:
            row = conn.execute("SELECT id FROM memory WHERE ns = ? AND source = ? AND key = ?", (ns, source, key)).fetchone()
            return {"id": row["id"], "stored": False, "duplicate": True}
        return {"id": cur.lastrowid, "stored": True, "duplicate": False}


def terms(query: str) -> List[str]:
    out: List[str] = []
    for t in _WORD.findall((query or "").lower()):
        if len(t) >= 2 and t not in out:
            out.append(t)
    return out[:MAX_TERMS]


def _iso(ts: Optional[float]) -> Optional[str]:
    return None if ts is None else time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(ts))


def _tags(text: Optional[str]) -> List[Any]:
    try:
        v = json.loads(text or "[]")
        return v if isinstance(v, list) else []
    except ValueError:
        return []


def _result(r, score: Optional[float], reason: str, body_cap: Optional[int] = None) -> Dict[str, Any]:
    body = r["body"] if body_cap is None else r["body"][:body_cap]
    return {"id": r["id"], "kind": r["kind"], "title": r["title"], "body": body, "tags": _tags(r["tags"]),
            "task_id": r["task_id"], "commit": r["commit"], "source": r["source"], "created": _iso(r["created"]),
            "score": None if score is None else round(score, 3), "reason": reason}


def _candidates(conn, ns: str, ts: List[str], include_archive: bool) -> List[Any]:
    arch = "" if include_archive else " AND m.kind != 'archive'"
    if conn.fts:  # terms are letters and digits only, so quoting makes each a plain prefix query
        q = " OR ".join('"%s"*' % t for t in ts)
        return conn.execute("SELECT m.* FROM memory_fts JOIN memory m ON m.id = memory_fts.rowid "
                            "WHERE memory_fts MATCH ? AND m.ns = ?" + arch + " ORDER BY bm25(memory_fts) LIMIT ?",
                            (q, ns, CANDIDATES)).fetchall()
    like = " OR ".join("(m.title LIKE ? OR m.body LIKE ? OR m.tags LIKE ?)" for _ in ts)
    args: List[Any] = [ns]
    for t in ts:
        args += ["%" + t + "%"] * 3
    return conn.execute("SELECT m.* FROM memory m WHERE m.ns = ?" + arch + " AND (" + like + ") "
                        "ORDER BY m.created DESC LIMIT ?", args + [LIKE_CANDIDATES]).fetchall()


def _ranks(conn, ns: str, ids: List[int]) -> Tuple[Dict[int, float], float]:
    top = conn.execute("SELECT MAX(CAST(value AS REAL)) FROM patterns WHERE ns = ? AND kind = 'rank'", (ns,)).fetchone()[0]
    if not ids or not top:
        return {}, 0.0
    marks = ",".join("?" * len(ids))
    rows = conn.execute("SELECT key, value FROM patterns WHERE ns = ? AND kind = 'rank' AND key IN (%s)" % marks,
                        [ns] + [str(i) for i in ids]).fetchall()
    return {int(r[0]): float(r[1]) for r in rows}, float(top)


def _reason(matched: int, total: int, rank: float, hits: int) -> str:
    out = "matched %d of %d terms" % (matched, total)
    if rank > 0:
        out += "; graph rank %.2f" % rank
    if hits:
        out += "; used %d times" % hits
    return out


def pattern_reason(kind: str, key: str, value: Optional[str], support: int) -> str:
    if kind == "file_fail":
        return "%s: %.0f%% of %d edits failed" % (key, float(value or 0) * 100, support)
    if kind == "coedit":
        a, _, b = key.partition("|")
        return "%s and %s were edited together in %d tasks" % (a, b, support)
    if kind == "tier":
        return "%s tasks finished at tier %s (%d tasks)" % (key, value, support)
    return "%s %s: %s (%d)" % (kind, key, value, support)


def patterns_for(conn, ns: str, ts: List[str], limit: int = 5) -> List[Dict[str, Any]]:
    if not ts:
        return []
    out = []
    for r in conn.execute("SELECT kind, key, value, support FROM patterns WHERE ns = ? AND kind IN "
                          "('file_fail', 'coedit', 'tier') ORDER BY support DESC, kind, key LIMIT 500", (ns,)):
        if any(t in r["key"].lower() for t in ts):
            out.append({"kind": r["kind"], "key": r["key"], "value": r["value"], "support": r["support"],
                        "reason": pattern_reason(r["kind"], r["key"], r["value"], r["support"])})
            if len(out) >= limit:
                break
    return out


def _touch(conn, ids: List[int], session: Optional[str]) -> None:
    if not ids or conn.readonly:
        return
    now = time.time()
    try:
        with memdb.tx(conn):
            conn.execute("UPDATE memory SET hits = hits + 1, accessed = ? WHERE id IN (%s)" % ",".join("?" * len(ids)),
                         [now] + ids)
            if session:
                conn.executemany("INSERT INTO access (session, memory_id, ts) VALUES (?, ?, ?)",
                                 [(session, i, now) for i in ids])
    except Exception:
        pass  # a busy store must not cost the caller its results


def search(conn, ns: str, query: str, limit: int = 3, include_archive: bool = False,
           session: Optional[str] = None) -> Dict[str, Any]:
    limit = max(1, min(int(limit), 20))
    ts = terms(query)
    if not ts:
        arch = "" if include_archive else " AND kind != 'archive'"
        rows = conn.execute("SELECT * FROM memory WHERE ns = ?" + arch + " ORDER BY created DESC, id DESC LIMIT ?",
                            (ns, limit)).fetchall()
        hits = [(0.0, r, "most recent (no search terms)") for r in rows]
    else:
        rows = _candidates(conn, ns, ts, include_archive)
        ranks, top = _ranks(conn, ns, [r["id"] for r in rows])
        scored = []
        for r in rows:
            words = set(_WORD.findall(("%s %s %s" % (r["title"], r["body"], r["tags"])).lower()))
            matched = sum(1 for t in ts if any(w.startswith(t) for w in words))
            if not matched:
                continue
            rank = ranks.get(r["id"], 0.0) / top if top else 0.0
            used = r["hits"] or 0
            score = matched / len(ts) + RANK_WEIGHT * rank + HIT_WEIGHT * min(used, 10) / 10.0
            scored.append((score, r, _reason(matched, len(ts), rank, used)))
        scored.sort(key=lambda x: (-x[0], -(x[1]["created"] or 0), x[1]["id"]))
        hits = scored[:limit]
    _touch(conn, [r["id"] for _, r, _ in hits], session)
    return {"results": [_result(r, s, why) for s, r, why in hits], "patterns": patterns_for(conn, ns, ts),
            "fts": bool(conn.fts)}


def list_entries(conn, ns: str, kind: Optional[str] = None, limit: int = 20, offset: int = 0,
                 include_archive: bool = False) -> List[Dict[str, Any]]:
    sql, args = "SELECT * FROM memory WHERE ns = ?", [ns]
    if kind:
        sql += " AND kind = ?"
        args.append(kind)
    elif not include_archive:
        sql += " AND kind != 'archive'"
    sql += " ORDER BY created DESC, id DESC LIMIT ? OFFSET ?"
    args += [max(1, min(int(limit), 100)), max(0, int(offset))]
    return [_result(r, None, "listed", body_cap=300) for r in conn.execute(sql, args)]


def forget(conn, ns: str, mem_id: int) -> str:
    row = conn.execute("SELECT kind, source, key FROM memory WHERE id = ? AND ns = ?", (mem_id, ns)).fetchone()
    if row is None:
        return "not found"
    if row["kind"] == "note":
        return "note"
    with memdb.tx(conn):
        conn.execute("DELETE FROM memory WHERE id = ?", (mem_id,))
        conn.execute("DELETE FROM access WHERE memory_id = ?", (mem_id,))
        conn.execute("DELETE FROM patterns WHERE ns = ? AND kind = 'rank' AND key = ?", (ns, str(mem_id)))
        if row["key"] is not None:  # an import must not bring it back
            conn.execute("INSERT OR REPLACE INTO forgotten (ns, source, key, ts) VALUES (?, ?, ?, ?)",
                         (ns, row["source"], row["key"], time.time()))
    return "forgotten"
