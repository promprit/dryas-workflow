"""<!-- NAME --> ... <!-- /NAME --> blocks in shipped text, kept or dropped by selected components."""
import re
from typing import Iterable, Tuple

GATED: Tuple[str, ...] = ("pstack-picks",)
_MARK = re.compile(r"^<!-- (/?)(%s) -->\n?" % "|".join(re.escape(g) for g in GATED), re.M)


def gate_blocks(text: str, comps: Iterable[str]) -> str:
    """Keep the body of each <!-- NAME --> ... <!-- /NAME --> block when NAME is selected, else drop it."""
    on, out, pos, open_name = set(comps), [], 0, None
    for m in _MARK.finditer(text):
        closing, name = m.group(1) == "/", m.group(2)
        if closing != (open_name is not None) or (closing and name != open_name):
            raise ValueError("unbalanced <!-- %s%s --> marker" % (m.group(1), name))
        if not closing:
            out.append(text[pos:m.start()])
            open_name = name
        else:
            if open_name in on:
                out.append(text[pos:m.start()])
            open_name = None
        pos = m.end()
    if open_name is not None:
        raise ValueError("unclosed <!-- %s --> marker" % open_name)
    out.append(text[pos:])
    return "".join(out)
