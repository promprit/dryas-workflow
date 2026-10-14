"""Session-end consolidation (owned core, sub-project B): dedupe, the memory graph, PageRank, and the
explainable statistics that memory_search returns and the local judge's history signal reads.

Graph nodes are memories ("m:<id>") and files ("f:<path>"). Edges: two memories recalled in the same session
(co-access), two files edited in the same task or, without a task, the same session (co-edit), and a memory
and the files its task edited. Pattern rows of kinds rank, file_fail, coedit and tier are replaced for the
namespace on every run."""
import heapq
import os
import re
import sys
import time
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memdb

MIN_EDITS = 3
MIN_SUPPORT = 2
MAX_GROUP = 50  # files or memories per group that form pairs; caps the n^2 growth of one huge task
ACCESS_DAYS = 180
EDIT_DAYS = 365
MAX_EDITS = 20000  # newest rows read per run
MAX_ACCESS = 20000
MAX_EDGES = 50000  # heaviest edges that take part in PageRank
MAX_RANK_ROWS = 5000
MAX_COEDIT_ROWS = 5000
CHECK_PAIRS = 20000  # pair increments between deadline checks in the pair loops
KINDS = ("rank", "file_fail", "coedit", "tier")
_TYPE = re.compile(r"\s*([A-Za-z]+)")


def pagerank(edges: Dict[Tuple[str, str], float], damping: float = 0.85, iters: int = 100,
             tol: float = 1e-10, check=None) -> Dict[str, float]:
    nbrs: Dict[str, Dict[str, float]] = defaultdict(dict)
    for (a, b), w in edges.items():
        if a == b or w <= 0:
            continue
        nbrs[a][b] = nbrs[a].get(b, 0.0) + w
        nbrs[b][a] = nbrs[b].get(a, 0.0) + w
    nodes = sorted(nbrs)
    n = len(nodes)
    if not n:
        return {}
    rank = {v: 1.0 / n for v in nodes}
    out_w = {v: sum(nbrs[v].values()) for v in nodes}
    for _ in range(iters):
        if check is not None:
            check()
        new = {v: (1.0 - damping) / n for v in nodes}
        for v in nodes:
            share = damping * rank[v] / out_w[v]
            for u, w in nbrs[v].items():
                new[u] += share * w
        delta = sum(abs(new[v] - rank[v]) for v in nodes)
        rank = new
        if delta < tol:
            break
    return rank


def task_type(title: str) -> str:
    m = _TYPE.match(title or "")
    return m.group(1).lower() if m else "other"


def _dedupe(conn, ns: str, check=None) -> int:
    where = "ns = ? AND kind NOT IN ('note', 'archive') AND source != 'ruflo'"
    removed = 0
    for (h,) in conn.execute("SELECT hash FROM memory WHERE " + where + " GROUP BY hash HAVING COUNT(*) > 1",
                             (ns,)).fetchall():
        rows = conn.execute("SELECT id, hits FROM memory WHERE " + where + " AND hash = ? ORDER BY created, id",
                            (ns, h)).fetchall()
        if check is not None:
            check()
        keep, rest = rows[0][0], [r[0] for r in rows[1:]]
        marks = ",".join("?" * len(rest))
        conn.execute("UPDATE memory SET hits = ? WHERE id = ?", (sum(r[1] or 0 for r in rows), keep))
        conn.execute("UPDATE access SET memory_id = ? WHERE memory_id IN (%s)" % marks, [keep] + rest)
        conn.execute("DELETE FROM memory WHERE id IN (%s)" % marks, rest)
        removed += len(rest)
    return removed


def _pairs(items: Set[str]) -> List[Tuple[str, str]]:
    return list(combinations(sorted(items)[:MAX_GROUP], 2))


class _Late(Exception):
    pass


def consolidate(conn, ns: str, now: Optional[float] = None, deadline: Optional[float] = None) -> Dict[str, Any]:
    """deadline is a time.monotonic() value; past it the run rolls back and reports skipped."""
    now = time.time() if now is None else now

    def check() -> None:
        if deadline is not None and time.monotonic() > deadline:
            raise _Late()
    try:
        return _consolidate(conn, ns, now, check)
    except _Late:
        return {"skipped": "deadline", "deduped": 0, "edges": 0, "ranked": 0, "patterns": 0}


def _consolidate(conn, ns: str, now: float, check) -> Dict[str, int]:
    with memdb.tx(conn):
        deduped = _dedupe(conn, ns, check)
        conn.execute("DELETE FROM access WHERE ts < ?", (now - ACCESS_DAYS * 86400,))
        edges: Counter = Counter()

        by_session: Dict[str, Set[str]] = defaultdict(set)
        for s, mid in conn.execute("SELECT a.session, a.memory_id FROM access a JOIN memory m ON m.id = a.memory_id "
                                   "WHERE m.ns = ? ORDER BY a.ts DESC LIMIT ?", (ns, MAX_ACCESS)).fetchall():
            by_session[s].add("m:%d" % mid)
        check()
        pending = 0
        for ids in by_session.values():
            for pair in _pairs(ids):
                edges[pair] += 1
                pending += 1
                if pending >= CHECK_PAIRS:
                    check()
                    pending = 0
        check()

        groups: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
        totals: Counter = Counter()
        fails: Counter = Counter()
        for s, t, f, ok in conn.execute("SELECT session, task_id, file, ok FROM edits WHERE ns = ? AND ts >= ? "
                                        "ORDER BY ts DESC LIMIT ?", (ns, now - EDIT_DAYS * 86400, MAX_EDITS)).fetchall():
            groups[("task", t) if t else ("session", s or "")].add(f)
            totals[f] += 1
            fails[f] += 0 if ok else 1
        check()
        coedit: Counter = Counter()
        pending = 0
        for files in groups.values():
            for a, b in _pairs(files):
                coedit[(a, b)] += 1
                edges[("f:" + a, "f:" + b)] += 1
                pending += 1
                if pending >= CHECK_PAIRS:
                    check()
                    pending = 0
        check()
        for mid, tid in conn.execute("SELECT id, task_id FROM memory WHERE ns = ? AND task_id IS NOT NULL", (ns,)):
            for f in sorted(groups.get(("task", tid), ()))[:MAX_GROUP]:
                edges[tuple(sorted(("m:%d" % mid, "f:" + f)))] += 1
        check()

        heavy = edges.items()
        if len(edges) > MAX_EDGES:
            heavy = heapq.nsmallest(MAX_EDGES, heavy, key=lambda kv: (-kv[1], kv[0]))
        check()
        ranks = pagerank(dict(heavy), check=check)
        degree: Counter = Counter()
        for a, b in dict(heavy):
            degree[a] += 1
            degree[b] += 1
        tiers: Dict[str, Counter] = defaultdict(Counter)
        for title, tier in conn.execute("SELECT title, tier_end FROM tasks WHERE ns = ? AND tier_end IS NOT NULL "
                                        "AND ended IS NOT NULL", (ns,)):
            tiers[task_type(title)][tier] += 1

        rows: List[Tuple[Any, ...]] = []
        top = sorted(((v, r) for v, r in ranks.items() if v.startswith("m:")), key=lambda vr: (-vr[1], vr[0]))
        # support is the degree in the capped graph (MAX_EDGES heaviest edges) on capped stores
        rows += [(ns, "rank", v[2:], "%.6f" % r, degree[v], now) for v, r in sorted(top[:MAX_RANK_ROWS])]
        ranked = len(rows)
        rows += [(ns, "file_fail", f, "%.4f" % (fails[f] / float(n)), n, now) for f, n in sorted(totals.items())
                 if n >= MIN_EDITS]
        kept = sorted(((p, c) for p, c in coedit.items() if c >= MIN_SUPPORT), key=lambda pc: (-pc[1], pc[0]))
        rows += [(ns, "coedit", "%s|%s" % pair, "", c, now) for pair, c in sorted(kept[:MAX_COEDIT_ROWS])]
        for typ, c in sorted(tiers.items()):
            tier, n = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            if n >= MIN_SUPPORT:
                rows.append((ns, "tier", typ, tier, n, now))
        check()
        conn.execute("DELETE FROM patterns WHERE ns = ? AND kind IN (%s)" % ",".join("?" * len(KINDS)), (ns,) + KINDS)
        conn.executemany("INSERT INTO patterns (ns, kind, key, value, support, updated) VALUES (?, ?, ?, ?, ?, ?)", rows)
    return {"deduped": deduped, "edges": len(edges), "ranked": ranked, "patterns": len(rows)}
