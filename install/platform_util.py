"""Cross-platform helpers for the installer: paths, tool lookup, directory links (symlink or Windows junction)."""
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

IS_WINDOWS = os.name == "nt"


def fwd(p) -> str:
    """Path as a string with forward slashes (valid in bash, Git Bash, cmd and Python on every OS)."""
    return str(p).replace("\\", "/")


def claude_env(cd, base=None) -> Dict[str, str]:
    """Env for running `claude` against config dir `cd`. The CLI reads its global config from
    $CLAUDE_CONFIG_DIR/.claude.json when the variable is set (else ~/.claude.json), so the default dir leaves it
    unset unless the caller's env already sets it."""
    env = dict(os.environ if base is None else base)
    if not env.get("CLAUDE_CONFIG_DIR") and Path(cd).expanduser().resolve() == (Path.home() / ".claude").resolve():
        env.pop("CLAUDE_CONFIG_DIR", None)
    else:
        env["CLAUDE_CONFIG_DIR"] = str(cd)
    return env


def claude_global_config(cd, base=None) -> Path:
    """The global config file (user-scope MCP servers) the CLI uses for `cd`."""
    if "CLAUDE_CONFIG_DIR" in claude_env(cd, base):
        return Path(cd) / ".claude.json"
    return Path.home() / ".claude.json"


def stale_jev(cd, base=None) -> Optional[str]:
    """Path of the deleted jev_mcp.py that a user-scope `jev` MCP server of the old copy install still runs, else None.
    Stale = its command/args name <a .claude dir>/jev/jev_mcp.py and that file is gone."""
    import json
    import re
    try:
        data = json.loads(claude_global_config(cd, base).read_text(encoding="utf-8"))
        srv = data["mcpServers"]["jev"]
        parts = [fwd(srv.get("command", ""))] + [fwd(x) for x in srv.get("args") or []]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    for part in parts:  # one whole argument is a path that may hold spaces
        if part.strip().endswith("/.claude/jev/jev_mcp.py"):
            return None if os.path.exists(part.strip()) else part.strip()
    m = re.search(r"\S*/\.claude/jev/jev_mcp\.py(?=\s|$)", " ".join(parts))  # e.g. a command line in `command`
    return m.group(0) if m and not os.path.exists(m.group(0)) else None


_PYTHON_EXE: Optional[str] = None


def python_exe() -> str:
    """Interpreter path for hooks: the path the installer was launched with (DRYAS_PYTHON_PATH) when it is the
    same major.minor as this one, else sys.executable (on macOS that can sit inside a movable Xcode.app)."""
    global _PYTHON_EXE
    if _PYTHON_EXE is not None:
        return _PYTHON_EXE
    result = fwd(sys.executable)
    try:
        launch = os.environ.get("DRYAS_PYTHON_PATH", "")
        if launch and os.path.isfile(launch):
            import subprocess
            out = subprocess.run([launch, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                                 capture_output=True, text=True, timeout=10).stdout.strip()
            if out == "%d.%d" % sys.version_info[:2]:
                result = fwd(launch)
    except Exception:
        pass
    _PYTHON_EXE = result
    return result


def space_free(p) -> Optional[str]:
    """p if it has no spaces; on Windows its 8.3 short form if that has none; else None."""
    s = str(p)
    if " " not in s:
        return s
    if IS_WINDOWS:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetShortPathNameW(s, buf, len(buf))
        if 0 < n < len(buf) and " " not in buf.value:
            return buf.value
    return None


def which(name: str) -> str:
    return shutil.which(name) or ""


def resolve_argv(argv: List[str]) -> List[str]:
    """argv with argv[0] resolved on PATH. On Windows this finds npm.cmd / claude.cmd, which CreateProcess would not."""
    if not argv:
        return list(argv)
    return [which(argv[0]) or argv[0]] + list(argv[1:])


def same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def read_rule_path(p) -> str:
    """Absolute path in Claude Code's Read() rule form: `//abs/posix`, `//c/Users/x` for `C:\\Users\\x`. String-only."""
    f = str(p).replace("\\", "/")
    if len(f) >= 2 and f[1] == ":" and f[0].isalpha():
        return "//" + f[0].lower() + "/" + f[2:].lstrip("/")
    return "//" + f.lstrip("/")


def make_dir_link(target: str, dest: str) -> str:
    """Link dest -> directory target. Returns "symlink", or "junction" on Windows without symlink rights."""
    try:
        os.symlink(target, dest, target_is_directory=True)
        return "symlink"
    except OSError:
        if not IS_WINDOWS:
            raise
    import _winapi
    _winapi.CreateJunction(str(target), str(dest))
    return "junction"


def read_dir_link(p: str) -> Optional[str]:
    try:
        t = os.readlink(p)
    except (OSError, ValueError):
        return None
    return t[4:] if t.startswith("\\\\?\\") else t


def remove_path(p: str) -> None:
    """Remove a file, a symlink or a junction. Never removes a real directory's contents."""
    if not os.path.lexists(p):
        return
    if IS_WINDOWS and read_dir_link(p) is not None:
        try:
            os.rmdir(p)  # directory symlinks and junctions on Windows
        except OSError:
            os.unlink(p)  # dangling links
    else:
        os.unlink(p)
