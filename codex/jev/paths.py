# claude/jev/paths.py
"""The one place that knows where Dryas keeps state. Shared by every Claude config dir (account):
$DRYAS_DATA_ROOT (default ~/.dryas; <copy>/state in a repo copy made by dryas cloud). JEV_* env overrides win. Never raises."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


_PROJECT = re.compile(r"\$(?:\{CLAUDE_PROJECT_DIR(?::-[^}]*)?\}|CLAUDE_PROJECT_DIR(?![A-Za-z0-9_]))")


def _env_path(var: str) -> str:
    """An env path. A repo copy's .mcp.json gives the jev server "${CLAUDE_PROJECT_DIR:-.}/.dryas/state"; if a client
    passes it unexpanded, $CLAUDE_PROJECT_DIR, ${CLAUDE_PROJECT_DIR} and ${CLAUDE_PROJECT_DIR:-...} are expanded here,
    and "" (unset) is returned when CLAUDE_PROJECT_DIR is not set, so data_root() falls back to the copy's own
    state folder. Any other "$" (a Windows profile name) is kept as it is."""
    v = os.environ.get(var) or ""
    if _PROJECT.search(v):
        proj = os.environ.get("CLAUDE_PROJECT_DIR") or ""
        return _PROJECT.sub(lambda m: proj, v) if proj else ""
    return v


def copy_root() -> str:
    """The .dryas folder when this code runs from a repo copy made by `dryas cloud` (owned core E), else ""."""
    root = os.path.dirname(HERE)
    if os.path.basename(root) == ".dryas" and os.path.isfile(os.path.join(root, "manifest.json")):
        return root
    return ""


def data_root() -> str:
    env = _env_path("DRYAS_DATA_ROOT")
    if env:
        return env
    copy = copy_root()
    return os.path.join(copy, "state") if copy else os.path.join(os.path.expanduser("~"), ".dryas")


def jev_dir() -> str:
    return os.path.join(data_root(), "jev")


def _env_or(var: str, default: str) -> str:
    return os.environ.get(var) or default


def log_dir() -> str:
    return _env_or("JEV_LOG_DIR", os.path.join(jev_dir(), "logs"))


def thresholds_file() -> str:
    return _env_or("JEV_THRESHOLDS", os.path.join(jev_dir(), "thresholds.json"))


def handoff_dir() -> str:
    return _env_or("JEV_HANDOFF_DIR", os.path.join(jev_dir(), "handoff"))


def compact_dir() -> str:
    return _env_or("JEV_COMPACT_DIR", os.path.join(jev_dir(), "compact"))


def chain_local() -> str:
    return _env_or("JEV_CHAIN_LOCAL", os.path.join(data_root(), "chain.local.json"))


def accounts_file() -> str:
    return os.path.join(data_root(), "accounts.json")


def inbox_root() -> str:
    """Cross-account bridge messages: <data root>/inbox/<recipient sessionId>/."""
    return os.path.join(data_root(), "inbox")


def inbox_dir(sid: str) -> str:
    return os.path.join(inbox_root(), sid)


def ruflo_dir() -> str:
    return os.path.join(data_root(), "ruflo")


def projects_dir() -> str:
    """Transcripts of the account this hook runs for."""
    if os.environ.get("JEV_PROJECTS_DIR"):
        return os.environ["JEV_PROJECTS_DIR"]
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    return os.path.join(cfg, "projects") if cfg else os.path.join(os.path.expanduser("~"), ".claude", "projects")


def plugin_root() -> str:
    return _env_path("CLAUDE_PLUGIN_ROOT") or os.path.dirname(HERE)


def python() -> str:
    return os.environ.get("DRYAS_PY") or sys.executable
