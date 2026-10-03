#!/usr/bin/env python3
"""Parse PLAN.md ('## Task N:' sections) for the orchestrator and the scope lock.

CLI: planfile.py section PLAN.md N | planfile.py scope PLAN.md N
"""
import os
import re
import sys
from typing import Dict, List, Pattern

_HEAD = re.compile(r"^## Task (\d+):", re.M)


def sections(text: str) -> Dict[str, str]:
    marks = list(_HEAD.finditer(text))
    out: Dict[str, str] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out[m.group(1)] = text[m.start():end].rstrip() + "\n"
    return out


def scope(section: str) -> List[str]:
    globs: List[str] = []
    inside = False
    for line in section.splitlines():
        if line.startswith("Scope:"):
            inside = True
            continue
        if not inside:
            continue
        s = line.strip()
        if not s:
            continue
        if s.startswith("- "):
            globs.append(s[2:].strip().strip("`"))
        else:
            break
    return globs


def _glob_re(glob: str) -> Pattern[str]:
    if glob.startswith("./"):
        glob = glob[2:]
    out = ""
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif glob.startswith("**", i):
            out += ".*"
            i += 2
        elif glob[i] == "*":
            out += "[^/]*"
            i += 1
        elif glob[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(glob[i])
            i += 1
    return re.compile(out + r"\Z")


def in_scope(rel_path: str, globs: List[str]) -> bool:
    rel = rel_path.replace(os.sep, "/")
    if rel.startswith("./"):
        rel = rel[2:]
    return any(_glob_re(g).match(rel) for g in globs)


def main(argv: List[str]) -> int:
    if len(argv) != 4 or argv[1] not in ("section", "scope"):
        sys.stderr.write("usage: planfile.py section|scope PLAN.md N\n")
        return 2
    with open(argv[2], encoding="utf-8") as f:
        sec = sections(f.read()).get(argv[3])
    if sec is None:
        sys.stderr.write("no Task %s in %s\n" % (argv[3], argv[2]))
        return 1
    sys.stdout.write(sec if argv[1] == "section" else "\n".join(scope(sec)) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
