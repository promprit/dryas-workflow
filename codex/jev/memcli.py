#!/usr/bin/env python3
"""Dryas memory CLI (owned core, sub-project B). The `dryas memory ...` wrapper (sub-project D) runs this.

  memcli.py [--db PATH] import-ruflo [--from PATH]   import Ruflo memory read-only; exit 1 if a namespace's
                                                     count does not verify, 2 if there is no Ruflo memory
  memcli.py [--db PATH] stats [--ns NS]              rows per namespace and kind
--db (or DRYAS_DB) picks the store; the default is ~/.dryas/dryas.db."""
import argparse
import os
import sqlite3
import sys
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memdb
import ruflo_import


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="dryas memory")
    ap.add_argument("--db")
    sub = ap.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import-ruflo", help="import Ruflo memory (read-only source)")
    imp.add_argument("--from", dest="src")
    st = sub.add_parser("stats", help="rows per namespace and kind")
    st.add_argument("--ns")
    a = ap.parse_args(argv)
    if a.cmd == "import-ruflo":
        src = a.src or ruflo_import.default_source()
        if not os.path.isfile(src):
            print("no Ruflo memory at %s; nothing to import" % src)
            return 2
        conn = memdb.connect(a.db)
        try:
            rep = ruflo_import.import_ruflo(conn, src)
        except (sqlite3.Error, ValueError) as e:
            print("import failed: %s" % e, file=sys.stderr)
            return 1
        finally:
            conn.close()
        for ns, c in rep["namespaces"].items():
            print("%-24s %7d source %7d imported %5d forgotten%s" % (
                ns, c["source"], c["imported"], c["forgotten"], " (archive)" if ns in ruflo_import.ARCHIVE_NS else ""))
        print("%d new rows, %d bodies redacted: %s" % (rep["new"], rep["redacted"],
                                                        "verified" if rep["ok"] else "COUNT MISMATCH"))
        return 0 if rep["ok"] else 1
    conn = memdb.connect(a.db)
    try:
        sql = "SELECT ns, kind, COUNT(*) FROM memory" + (" WHERE ns = ?" if a.ns else "") + " GROUP BY ns, kind ORDER BY ns, kind"
        for ns, kind, n in conn.execute(sql, (a.ns,) if a.ns else ()):
            print("%-24s %-8s %7d" % (ns, kind, n))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
