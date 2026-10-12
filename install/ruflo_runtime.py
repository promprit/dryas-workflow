"""Ruflo runtime in the shared data root (~/.dryas/ruflo): patched helpers and the MCP shim with its dist link.
Shared by every Claude config dir; rewritten only when content or the link target changed."""
import os
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

import platform_util as pu


def _write(dest: Path, data: bytes, mode: int, wrote: List[str]) -> None:
    if dest.is_file() and dest.read_bytes() == data:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    if os.name != "nt":
        os.chmod(str(dest), mode)  # portable-ok: guarded; keeps helper exec bit
    wrote.append(str(dest))


def install(repo: Path, root: Path, helpers: Dict[str, Tuple[bytes, int]], cli_dist: str) -> List[str]:
    base, wrote = Path(root) / "ruflo", []
    for name, (data, mode) in sorted(helpers.items()):
        _write(base / "helpers" / name, data, mode, wrote)
    src = Path(repo) / "claude" / "ruflo" / "mcp-shim" / "bin" / "cli.js"
    _write(base / "mcp-shim" / "bin" / "cli.js", src.read_bytes(), 0o755, wrote)
    link = base / "mcp-shim" / "dist"
    if cli_dist:
        cur = pu.read_dir_link(str(link))
        if cur is None or not pu.same_path(cur, cli_dist):
            if os.path.lexists(str(link)):
                pu.remove_path(str(link))
            pu.make_dir_link(cli_dist, str(link))
            wrote.append(str(link))
    return wrote
