#!/bin/sh
# Dryas Workflow installer. See docs/install.md.
# Usage: install.sh [--no-jev] [--no-ruflo] [--no-superpowers] [--no-design] [--yes] [--force] [--dry-run] [--uninstall] [--preflight-only]
set -eu
REPO=$(cd "$(dirname "$0")/.." && pwd)
CD="$HOME/.claude"
PY=/usr/bin/python3
JEV=1 RUFLO=1 SP=1 DESIGN=1 YES="" FORCE="" DRY="" UNINSTALL="" PREFLIGHT_ONLY=""
for a in "$@"; do
  case "$a" in
    --no-jev) JEV=0 ;; --no-ruflo) RUFLO=0 ;; --no-superpowers) SP=0 ;; --no-design) DESIGN=0 ;;
    --yes) YES=--yes ;; --force) FORCE=--force ;; --dry-run) DRY=--dry-run ;;
    --uninstall) UNINSTALL=1 ;; --preflight-only) PREFLIGHT_ONLY=1 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done
missing=""
command -v claude >/dev/null 2>&1 || missing="$missing claude(Claude Code CLI)"
[ -x "$PY" ] && "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null || missing="$missing /usr/bin/python3>=3.9"
command -v git >/dev/null 2>&1 || missing="$missing git"
if [ "$RUFLO" = 1 ]; then
  command -v node >/dev/null 2>&1 || missing="$missing node"
  command -v npm >/dev/null 2>&1 || missing="$missing npm"
fi
if [ -n "$missing" ]; then echo "Missing:$missing. Install them and re-run (this installer never installs system packages)."; exit 1; fi
case "$HOME" in *" "*)
  if [ "$RUFLO" = 1 ]; then echo "Your HOME contains a space; Ruflo's hook override cannot handle that. Re-run with --no-ruflo."; exit 1; fi ;;
esac
[ -n "$PREFLIGHT_ONLY" ] && { echo "preflight ok"; exit 0; }
if [ -n "$UNINSTALL" ]; then exec "$PY" "$REPO/install/dryas_install.py" uninstall --claude-dir "$CD"; fi
COMPS=core
[ "$JEV" = 1 ] && COMPS="$COMPS,jev"
[ "$RUFLO" = 1 ] && COMPS="$COMPS,ruflo"
[ "$SP" = 1 ] && COMPS="$COMPS,superpowers"
[ "$DESIGN" = 1 ] && COMPS="$COMPS,design"
[ -n "$DRY" ] || "$PY" "$REPO/install/dryas_install.py" thirdparty --components "$COMPS" $YES
"$PY" "$REPO/install/dryas_install.py" install --repo "$REPO" --claude-dir "$CD" --components "$COMPS" $FORCE $YES $DRY
[ -n "$DRY" ] || "$PY" "$REPO/install/dryas_install.py" verify --claude-dir "$CD" --components "$COMPS"
