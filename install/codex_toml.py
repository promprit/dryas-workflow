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


def lines(text: str) -> List[Tuple[str, Optional[Header]]]:
    st, out = {"ml": None, "depth": 0}, []  # type: ignore[var-annotated]
    for line in text.splitlines(True):
        hdr = None
        if st["ml"] is None and st["depth"] <= 0:
            st["depth"] = 0
            hdr = norm_header(line)
        if hdr is None:
            _scan(line, st)
        out.append((line, hdr))
    return out


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


def remove_trust(text: str, keys: List[str]) -> Tuple[str, List[str]]:
    """Drop the [hooks.state."<key>"] tables (to the next header; comments stay, they head the next table) and the
    "<key>" = {...} lines inside [hooks.state] for exactly these keys. A [hooks.state] header left with nothing under
    it and no [hooks.state.*] table left goes too (Codex writes one when it trusts a hook). Returns the new text (unchanged when nothing was found) and
    the keys not found."""
    want, found, out = set(keys), set(), []  # type: ignore[var-annotated]
    skip, section = False, None
    for line, hdr in lines(text):
        if hdr:
            section = None if hdr[1] else hdr[0]
            path = hdr[0]
            skip = not hdr[1] and len(path) == 3 and path[:2] == STATE and path[2] in want
            if skip:
                found.add(path[2])
                continue
        elif skip:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        elif section == STATE:
            k = _inline_key(line)
            if k in want:
                found.add(k)
                continue
        out.append(line)
    if not found:
        return text, list(keys)
    rows, keep = lines("".join(out)), []
    subs = any(h and len(h[0]) > 2 and h[0][:2] == STATE for _, h in rows)
    for i, (line, hdr) in enumerate(rows):
        if hdr == (STATE, False) and not subs:
            j = i + 1
            while j < len(rows) and not rows[j][1] and not rows[j][0].strip():
                j += 1
            if j == len(rows) or rows[j][1]:  # nothing but blank lines under it
                continue
        keep.append(line)
    new = re.sub(r"\n{3,}", "\n\n", "".join(keep))
    new = new.rstrip("\n") + "\n" if new.strip() else ""
    return new, [k for k in keys if k not in found]
