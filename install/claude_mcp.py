"""Register or refresh the jev MCP server with the claude CLI."""
from typing import List

import platform_util as pu


def ensure_jev(cd, pyx: List[str], rec: dict, run, capture, dry: bool) -> None:
    path = pu.fwd(cd / "jev/jev_mcp.py")
    spec = list(pyx) + [path]
    add = ["claude", "mcp", "add", "--scope", "user", "jev", "--"] + spec
    rm = ["claude", "mcp", "remove", "--scope", "user", "jev"]
    rc, out = capture(["claude", "mcp", "get", "jev"])
    steps = [add]
    if rc == 0 and out.strip():
        if "jev/jev_mcp.py" not in out.replace("\\", "/"):
            print("kept your own jev MCP server (not managed by this installer)")
            return
        stored = rec.get("mcp_specs", {}).get("jev")
        if stored is not None:
            current = stored == spec
        else:
            current = pyx[0] in out and "-X utf8" in out
        if current:
            return
        steps = [rm, add]
    for argv in steps:
        if dry:
            print("would run: %s" % " ".join(argv))
        elif run(argv) != 0 and argv is add:
            print("warning: could not register the jev MCP server; re-run the installer to retry")
            return
    if not dry:
        if "jev" not in rec["mcp"]:
            rec["mcp"].append("jev")
        rec.setdefault("mcp_specs", {})["jev"] = spec
