# claude/jev/paths.py
"""The one place that knows where Dryas keeps state. Shared by every Claude config dir (account):
$DRYAS_DATA_ROOT (default ~/.dryas). JEV_* env overrides win. Never raises."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def data_root() -> str:
    return os.environ.get("DRYAS_DATA_ROOT") or os.path.join(os.path.expanduser("~"), ".dryas")


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


def ruflo_dir() -> str:
    return os.path.join(data_root(), "ruflo")


def projects_dir() -> str:
    """Transcripts of the account this hook runs for."""
    if os.environ.get("JEV_PROJECTS_DIR"):
        return os.environ["JEV_PROJECTS_DIR"]
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    return os.path.join(cfg, "projects") if cfg else os.path.join(os.path.expanduser("~"), ".claude", "projects")


def plugin_root() -> str:
    return os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(HERE)


def python() -> str:
    return os.environ.get("DRYAS_PY") or sys.executable
