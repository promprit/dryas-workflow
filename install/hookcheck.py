"""Checks on the hook commands the installer recorded."""
import os
import re
from typing import List

_QUOTED = re.compile(r'"([^"]+)"')


def hook_problems(recorded_hooks: List[list]) -> List[str]:
    """Problems with the installer's own hook commands: /bin/sh, or a quoted path that does not exist."""  # portable-ok: detector for old hooks
    probs = []
    for ev, _m, cmd in recorded_hooks:
        if '/bin/sh' in cmd:  # portable-ok: detector for old hooks
            probs.append("%s uses /bin/sh" % ev)  # portable-ok: detector for old hooks
        for p in _QUOTED.findall(cmd):
            if ("/" in p or "\\" in p) and not os.path.exists(p):
                probs.append("%s: missing %s" % (ev, p))
    return probs
