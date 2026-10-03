#!/bin/sh
# Run one lifted Ruflo hook helper: run.sh node <helper-file> <args...>
# Silent no-op (stdin drained, exit 0) when the data root (DRYAS_DATA_ROOT), the command or the helper file is missing.
# Never exits 2 (a hook must not block); the helper's stdout passes through, its exit code is dropped.
# RUFLO_SSD_ROOT overrides the data root (tests). RUFLO_DATA_MODE=cwd (default) runs the helper in a
# per-project dir under <data root>/ruflo and sets RUFLO_DATA_ROOT there; =env runs in place.
. "$(dirname "$0")/ns.sh"
noop() { cat >/dev/null; exit 0; }
ROOT=$(ruflo_root) || noop
# node fallback: hooks may run with a PATH lacking nvm's node
if [ "${1:-}" = "node" ] && ! command -v node >/dev/null 2>&1; then
  NODE_FALLBACK="${RUFLO_NODE_FALLBACK:-}"
  [ -n "$NODE_FALLBACK" ] && [ -x "$NODE_FALLBACK" ] || noop
  shift; set -- "$NODE_FALLBACK" "$@"
fi
command -v "${1:-}" >/dev/null 2>&1 || noop
[ -f "${2:-}" ] || noop
export RUFLO_NO_AUTO_ENABLE=1
# auto-memory-hook.mjs needs @claude-flow/memory; resolve it from the pinned global ruflo install.
RUFLO_NM="${RUFLO_NODE_MODULES:-}"
if [ -z "$RUFLO_NM" ] && _rb=$(command -v ruflo 2>/dev/null); then RUFLO_NM="$(dirname "$_rb")/../lib/node_modules/ruflo/node_modules"; fi
[ -n "$RUFLO_NM" ] && [ -d "$RUFLO_NM" ] && export NODE_PATH="$RUFLO_NM${NODE_PATH:+:$NODE_PATH}"
if [ "${RUFLO_DATA_MODE:-cwd}" = "cwd" ]; then
  ns=$(ruflo_ns)
  dir="$ROOT/ruflo/$ns"
  mkdir -p "$dir" && cd "$dir" || noop
  export RUFLO_DATA_ROOT="$dir"
fi
"$@"
exit 0
