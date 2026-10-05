#!/bin/sh
# Dryas Workflow installer for macOS, Linux and WSL. Finds Python >= 3.9 and runs install/dryas_install.py.
# Usage: install.sh [--no-jev] [--no-ruflo] [--no-superpowers] [--no-design] [--yes] [--force] [--dry-run]
#                   [--uninstall] [--preflight-only] [--harness claude|codex|both]   See docs/install.md.
# DRYAS_PYTHON overrides the interpreter.
set -eu
REPO=$(cd "$(dirname "$0")/.." && pwd)
for c in ${DRYAS_PYTHON:-} python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
    exec "$c" "$REPO/install/dryas_install.py" run --repo "$REPO" "$@"
  fi
done
echo "Missing: Python >= 3.9. Install it and re-run (this installer never installs system packages)." >&2
exit 1
