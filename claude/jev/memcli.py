#!/usr/bin/env python3
"""Dryas memory CLI (owned core, sub-project B). The `dryas memory ...` wrapper (sub-project D) runs this.

  memcli.py [--db PATH] import-ruflo [--from PATH]   import Ruflo memory read-only; exit 1 if a source row
                                                     is missing from the store, 2 if there is no Ruflo memory
  memcli.py [--db PATH] consolidate [--ns NS] [--wait S]
                                                     run consolidation (no deadline) for one or every namespace;
                                                     takes a lock beside the store, so a second run exits at once
                                                     (or waits up to S seconds); a failure counts against the
                                                     namespace's pending marker
  memcli.py [--db PATH] stats [--ns NS]              rows per namespace and kind
--db (or DRYAS_DB) picks the store; the default is ~/.dryas/dryas.db."""
import argparse
import os
import sqlite3
import sys
import time
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import consolidate_bg
import jevlog
import memdb
import memlearn
import ruflo_import


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="dryas memory")
    ap.add_argument("--db")
    sub = ap.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import-ruflo", help="import Ruflo memory (read-only source)")
    imp.add_argument("--from", dest="src")
    st = sub.add_parser("stats", help="rows per namespace and kind")
    st.add_argument("--ns")
    co = sub.add_parser("consolidate", help="dedupe, graph and patterns, outside a hook")
    co.add_argument("--ns")
    co.add_argument("--wait", type=float, default=0, help="seconds to wait for a running consolidation")
    a = ap.parse_args(argv)
    if a.cmd == "consolidate":
        root = os.path.dirname(os.path.abspath(a.db or memdb.db_path()))  # one lock per store
        os.makedirs(root, exist_ok=True)
        fd = consolidate_bg.wait_acquire(root, a.wait)
        if fd is None:
            print("consolidation already running")
            return 0
        conn = None
        try:
            conn = memdb.connect(a.db)
            names = [a.ns] if a.ns else sorted(set(consolidate_bg.pending(conn)) | {r[0] for r in conn.execute(
                "SELECT ns FROM memory UNION SELECT ns FROM edits UNION SELECT ns FROM tasks")})
            for ns in names:
                consolidate_bg.heartbeat(root)
                t = time.monotonic()
                try:
                    r = memlearn.consolidate(conn, ns)
                except (sqlite3.Error, OSError, ValueError) as e:
                    jevlog.append("memory", dict(stage="consolidate", ns=ns, ok=False,
                                                 ms=int((time.monotonic() - t) * 1000), error=type(e).__name__))
                    print("%-24s failed: %s" % (ns, e), file=sys.stderr)
                    consolidate_bg.record_failure(conn, ns)
                    continue
                jevlog.append("memory", dict(stage="consolidate", ns=ns, ok=True, ms=int((time.monotonic() - t) * 1000)))
                consolidate_bg.clear_pending(conn, ns)
                print("%-24s %5d deduped %6d edges %5d ranked %5d patterns" % (
                    ns, r["deduped"], r["edges"], r["ranked"], r["patterns"]))
        except (sqlite3.Error, OSError, ValueError) as e:
            print("consolidate failed: %s" % e, file=sys.stderr)
            return 1
        finally:
            if conn is not None:
                conn.close()
            consolidate_bg.release(root, fd)
        return 0
    if a.cmd == "import-ruflo":
        src = a.src or ruflo_import.default_source()
        if not os.path.isfile(src):
            print("no Ruflo memory at %s; nothing to import" % src)
            return 2
        conn = None
        try:
            conn = memdb.connect(a.db)
            rep = ruflo_import.import_ruflo(conn, src)
        except (sqlite3.Error, OSError, ValueError) as e:
            print("import failed: %s" % e, file=sys.stderr)
            return 1
        finally:
            if conn is not None:
                conn.close()
        for ns, c in rep["namespaces"].items():
            print("%-24s %7d source %7d imported %5d forgotten%s" % (
                ns, c["source"], c["imported"], c["forgotten"], " (archive)" if ns in ruflo_import.ARCHIVE_NS else ""))
        print("%d new rows, %d updated, %d rows redacted: %s" % (
            rep["new"], rep["updated"], rep["redacted"], "verified" if rep["ok"] else "MISSING ROWS"))
        return 0 if rep["ok"] else 1
    conn = None
    try:
        conn = memdb.connect(a.db)
        sql = "SELECT ns, kind, COUNT(*) FROM memory" + (" WHERE ns = ?" if a.ns else "") + " GROUP BY ns, kind ORDER BY ns, kind"
        for ns, kind, n in conn.execute(sql, (a.ns,) if a.ns else ()):
            print("%-24s %-8s %7d" % (ns, kind, n))
    except (sqlite3.Error, OSError, ValueError) as e:
        print("stats failed: %s" % e, file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
