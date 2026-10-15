#!/bin/sh
# Dryas Workflow installer for macOS, Linux and WSL. Finds Python >= 3.9 and runs install/dryas_install.py.
# Usage: install.sh [--no-jev] [--no-ruflo] [--no-superpowers] [--no-design] [--no-pstack-picks] [--yes] [--force] [--dry-run]
#                   [--uninstall] [--purge] [--preflight-only] [--harness claude|codex|both|opencode|all]
#                   [--claude-dir DIR] [--codex-dir DIR] [--opencode-dir DIR] [--tier-fast|--tier-standard|--tier-strong|--tier-frontier PROVIDER/MODEL]
#                   [--flowobserve|--no-flowobserve] [--openrouter-key KEY]   See docs/install.md.
#        install.sh --repo PATH [--yes] [--force] [--prefix P] [--with-design] [--with-own NAME] [--persist-memory]
#                   sets the repo at PATH up for claude.ai/code cloud sessions (tools/dryas_cloud.py init; docs/cloud-sessions.md)
# Claude Code: run once per config dir (--claude-dir; default $CLAUDE_CONFIG_DIR, else ~/.claude).
# Codex: run once per CODEX_HOME (--codex-dir; default $CODEX_HOME, else ~/.codex).
# OpenCode: run once per config dir (--opencode-dir; default $XDG_CONFIG_HOME/opencode, else ~/.config/opencode).
# Jev reads $OPENROUTER_API_KEY from the shell; --openrouter-key also stores a key as the plugin option.
# DRYAS_PYTHON overrides the interpreter.
set -eu
REPO=$(cd "$(dirname "$0")/.." && pwd)
CLOUD=0  # a --repo of your own: set that repo up for cloud sessions instead of installing the plugin
for arg in "$@"; do
  case "$arg" in --repo|--repo=*) CLOUD=1 ;; esac
done
for c in ${DRYAS_PYTHON:-} python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
    DRYAS_PYTHON_PATH="$(command -v "$c")"
    export DRYAS_PYTHON_PATH
    if [ "$CLOUD" = 1 ]; then
      exec "$c" "$REPO/tools/dryas_cloud.py" init "$@"
    fi
    exec "$c" "$REPO/install/dryas_install.py" run --repo "$REPO" "$@"
  fi
done
echo "Missing: Python >= 3.9. Install it and re-run (this installer never installs system packages)." >&2
exit 1
