#!/usr/bin/env python3
"""Deny-term scan: fail when any file name or text line contains a listed term.
Prints file:line only (never the term). Terms of 4 chars or fewer match on alphanumeric
boundaries; longer terms match as substrings; case-insensitive. The term list is private
and lives outside this repo ($DRYAS_DENY_TERMS, default ~/.claude/release/deny-terms.txt)."""
import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Pattern

DEFAULT_TERMS = os.path.expanduser("~/.claude/release/deny-terms.txt")


def load_terms(path: Path) -> List[str]:
    out = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        t = raw.strip()
        if t and not t.startswith("#"):
            out.append(t)
    return out


def compile_terms(terms: List[str]) -> List[Pattern]:
    pats = []
    for t in terms:
        e = re.escape(t)
        if len(t) <= 4:
            e = r"(?<![A-Za-z0-9])" + e + r"(?![A-Za-z0-9])"
        pats.append(re.compile(e, re.IGNORECASE))
    return pats


def scan(root: Path, terms: List[str]) -> List[str]:
    root = Path(root)
    pats = compile_terms(terms)
    hits = []
    for f in sorted(root.rglob("*")):
        rel = f.relative_to(root).as_posix()
        if ".git" in rel.split("/"):
            continue
        if any(p.search(rel) for p in pats):
            hits.append(rel + ":0")
        if not f.is_file() or f.is_symlink():
            continue
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(lines, 1):
            if any(p.search(line) for p in pats):
                hits.append("%s:%d" % (rel, i))
    return sorted(set(hits), key=hits.index)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--terms", default=os.environ.get("DRYAS_DENY_TERMS", DEFAULT_TERMS))
    a = ap.parse_args(argv)
    if not os.path.isfile(a.terms):
        print("deny terms not found; scan skipped")
        return 0
    hits = scan(Path(a.root), load_terms(Path(a.terms)))
    for h in hits:
        print(h)
    if hits:
        print("deny-term scan: %d hit(s); fix or rewrite before publishing" % len(hits), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
