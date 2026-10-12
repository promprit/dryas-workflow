"""Codex config.toml as text (Python 3.9 has no TOML parser): table headers, and removing Dryas hook-trust entries.

  norm_header(line)        (key path, is [[array]]) of a header line; None = not a header
  lines(text)              [(line, header or None)]; headers inside multi-line strings or arrays do not count
  remove_trust(text, keys) drop exactly the recorded trust keys; returns (new text, keys not found)
"""
import json
import re
from typing import List, Optional, Tuple

HEADER_RE = re.compile(r"^\s*(\[{1,2})([^\]=\[]+)(\]{1,2})\s*(#.*)?$")
KEY_RE = re.compile(r"""\s*("(?:[^"\\]|\\.)*"|'[^']*'|[A-Za-z0-9_-]+)\s*(?:\.|$)""")
KeyPath = Tuple[str, ...]
Header = Tuple[KeyPath, bool]
STATE: KeyPath = ("hooks", "state")


def norm_header(line: str) -> Optional[Header]:
    """(key path, is array-of-tables) of a TOML table header line; None = not a header. Whitespace, quotes around
    plain keys and a trailing comment do not matter: [ a . "b" ] # x  ==  [a.b]."""
    m = HEADER_RE.match(line)
    if not m or len(m.group(1)) != len(m.group(3)):
        return None
    inner, keys, pos = m.group(2), [], 0
    while pos < len(inner):
        k = KEY_RE.match(inner, pos)
        if not k or k.end() == pos:
            return None
        tok = k.group(1)
        try:
            keys.append(json.loads(tok) if tok.startswith('"') else tok.strip("'"))
        except ValueError:
            return None
        pos = k.end()
    return (tuple(keys), len(m.group(1)) == 2) if keys else None


def _scan(line: str, st: dict) -> None:
    """Track multi-line strings and open brackets across lines (a header can only start outside both)."""
    i = 0
    while i < len(line):
        if st["ml"]:
            j = line.find(st["ml"], i)
            if j < 0:
                return
            st["ml"], i = None, j + 3
            continue
        c = line[i]
        if line[i:i + 3] in ('"' * 3, "'" * 3):
            st["ml"], i = line[i:i + 3], i + 3
        elif c in "\"'":
            j = i + 1
            while j < len(line) and line[j] != c:
                j += 2 if c == '"' and line[j] == "\\" else 1
            i = j + 1
        elif c == "#":
            return
        else:
            st["depth"] += (c in "[{") - (c in "]}")
            i += 1


def rows(text: str) -> List[Tuple[str, Optional[Header], bool]]:
    """(line, header or None, free): free = the line starts outside a multi-line string and outside brackets."""
    st, out = {"ml": None, "depth": 0}, []  # type: ignore[var-annotated]
    for line in text.splitlines(True):
        hdr, free = None, st["ml"] is None and st["depth"] <= 0
        if free:
            st["depth"] = 0
            hdr = norm_header(line)
        if hdr is None:
            _scan(line, st)
        out.append((line, hdr, free))
    return out


def lines(text: str) -> List[Tuple[str, Optional[Header]]]:
    return [(line, hdr) for line, hdr, _ in rows(text)]


_INLINE = re.compile(r"""^\s*("(?:[^"\\]|\\.)*"|'[^']*'|[A-Za-z0-9_-]+)\s*=""")


def _inline_key(line: str) -> Optional[str]:
    m = _INLINE.match(line)
    if not m:
        return None
    tok = m.group(1)
    try:
        return json.loads(tok) if tok.startswith('"') else tok.strip("'")
    except ValueError:
        return None


def _ours(path: KeyPath, want) -> bool:
    return len(path) >= 3 and path[:2] == STATE and path[2] in want  # with its sub-tables and [[arrays]]


def remove_trust(text: str, keys: List[str]) -> Tuple[str, List[str]]:
    """Drop the [hooks.state."<key>"] tables (with their sub-tables, to the next header; comments stay, they head the
    next table) and the "<key>" = {...} lines inside [hooks.state] for exactly these keys. A [hooks.state] header left
    with nothing under it and no [hooks.state.*] table left goes too (Codex writes one when it trusts a hook). Only
    blank lines next to a removed span are collapsed; newline style and the final newline are kept. Returns the new
    text (unchanged when nothing was found) and the keys not found."""
    want, found = set(keys), set()  # type: ignore[var-annotated]
    rs = rows(text)
    gone = [False] * len(rs)
    skip, section = False, None
    for i, (line, hdr, free) in enumerate(rs):
        if hdr:
            section = None if hdr[1] else hdr[0]
            skip = _ours(hdr[0], want)
            if skip:
                found.add(hdr[0][2])
                gone[i] = True
        elif skip:
            gone[i] = not (free and line.strip().startswith("#"))
        elif section == STATE and free:
            k = _inline_key(line)
            if k in want:
                found.add(k)
                gone[i] = True
    if not found:
        return text, list(keys)
    subs = any(h and len(h[0]) > 2 and h[0][:2] == STATE for i, (_, h, _f) in enumerate(rs) if not gone[i])
    for i, (line, hdr, free) in enumerate(rs):
        if hdr == (STATE, False) and not subs:
            j = i + 1
            while j < len(rs) and not rs[j][1] and (gone[j] or (rs[j][2] and not rs[j][0].strip())):
                j += 1
            if j == len(rs) or rs[j][1]:  # nothing left under it
                for k in range(i, j):
                    gone[k] = True

    def blank(k: int) -> bool:
        return rs[k][2] and not rs[k][0].strip()
    i = 0
    while i < len(rs):  # each removed span: keep at most one blank line around it, none at the start or end
        if not gone[i]:
            i += 1
            continue
        j = i
        while j < len(rs) and gone[j]:
            j += 1
        before, k = [], i - 1
        while k >= 0 and not gone[k] and blank(k):
            before.append(k)
            k -= 1
        after, m = [], j
        while m < len(rs) and not gone[m] and blank(m):
            after.append(m)
            m += 1
        edge = k < 0 or m == len(rs)
        for x in (before + after)[0 if edge else 1:]:
            gone[x] = True
        i = j
    new = "".join(line for x, (line, _, _f) in enumerate(rs) if not gone[x])
    nl = "\r\n" if "\r\n" in text else "\n"
    if not new.strip():
        new = ""
    elif text.endswith(("\n", "\r")):
        new = new if new.endswith(("\n", "\r")) else new + nl
    else:
        new = new.rstrip("\r\n")
    return new, [k for k in keys if k not in found]
