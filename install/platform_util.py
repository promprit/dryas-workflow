"""Cross-platform helpers for the installer: paths, tool lookup, directory links (symlink or Windows junction)."""
import json
import os
import shlex
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

IS_WINDOWS = os.name == "nt"


def fwd(p) -> str:
    """Path as a string with forward slashes (valid in bash, Git Bash, cmd and Python on every OS)."""
    return str(p).replace("\\", "/")


def _resolved(p) -> Path:
    return Path(p).expanduser().resolve()


def claude_env(cd, base=None) -> Dict[str, str]:
    """Env for running `claude` against config dir `cd`. The CLI reads its global config from
    $CLAUDE_CONFIG_DIR/.claude.json when the variable is set (else ~/.claude.json), so the default dir leaves it
    unset, unless the caller's env already sets it to that same dir. Any other dir sets it to `cd`."""
    env = dict(os.environ if base is None else base)
    exported = env.get("CLAUDE_CONFIG_DIR")
    default = _resolved(Path.home() / ".claude")
    if _resolved(cd) == default and not (exported and _resolved(exported) == default):
        env.pop("CLAUDE_CONFIG_DIR", None)
    else:
        env["CLAUDE_CONFIG_DIR"] = str(cd)
    return env


def claude_global_config(cd, base=None) -> Path:
    """The global config file (user-scope MCP servers) the CLI uses for `cd`."""
    if "CLAUDE_CONFIG_DIR" in claude_env(cd, base):
        return Path(cd) / ".claude.json"
    return Path.home() / ".claude.json"


def _is_managed(c: str, managed) -> bool:
    if not (c.startswith("/") or c[1:3] == ":/"):  # "python3 /x/jev_mcp.py" is a command line, not a path
        return False
    n = os.path.normcase(c)
    return n.endswith(os.path.normcase("/.claude/jev/jev_mcp.py")) or n in managed


def _tokens(parts: List[str]) -> List[str]:
    """Shell-style tokens of the command string, quotes removed; [] when it cannot be split."""
    try:
        toks = shlex.split(" ".join(parts), posix=not IS_WINDOWS)
    except ValueError:
        return []
    return [t.strip("\"'") if IS_WINDOWS else t for t in toks]


def stale_jev(cd, base=None) -> Optional[Tuple[str, Dict[str, str]]]:
    """(missing jev_mcp.py path, env for `claude mcp remove --scope user jev`) for a user-scope `jev` MCP server of the
    old copy install whose script is gone, else None. Installer-managed script = <a .claude dir>/jev/jev_mcp.py or
    <cd>/jev/jev_mcp.py. Looked up in cd's CLI config and, if that differs, in ~/.claude.json (where the old install
    registered it when CLAUDE_CONFIG_DIR was not exported); the env matches the config the entry was found in."""
    managed = {os.path.normcase(fwd(x) + "/jev/jev_mcp.py") for x in (cd, _resolved(cd))}
    home_cfg = Path.home() / ".claude.json"
    places = [(claude_global_config(cd, base), claude_env(cd, base))]
    if places[0][0] != home_cfg:
        places.append((home_cfg, {k: v for k, v in (os.environ if base is None else base).items()
                                  if k != "CLAUDE_CONFIG_DIR"}))
    for cfg, env in places:
        try:
            srv = json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]["jev"]
            parts = [fwd(srv.get("command", ""))] + [fwd(x) for x in srv.get("args") or []]
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        # each part is a whole path; a command given as one string ("python3 <path>") is split into tokens instead
        parts = [p.strip() for p in parts]
        for group in (parts, _tokens(parts)):
            script = next((c for c in group if _is_managed(c, managed)), None)
            if script is not None:
                if not os.path.exists(script):
                    return script, env
                break
    return None


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
