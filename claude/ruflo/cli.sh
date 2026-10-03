#!/bin/sh
# RUFLO_HOOK_CLI_OVERRIDE target for the ruflo-core plugin hooks: runs the pinned ruflo CLI inside
# a per-project dir under the data root (DRYAS_DATA_ROOT) so `.claude-flow/` never lands in a project tree.
# Silent no-op (stdin drained, exit 0) when the data root (DRYAS_DATA_ROOT) or the binary is missing; never exits 2; no npx.
# RUFLO_SSD_ROOT / RUFLO_BIN are test overrides.
. "$(dirname "$0")/ns.sh"
noop() { cat >/dev/null; exit 0; }
ROOT=$(ruflo_root) || noop
BIN="${RUFLO_BIN:-$(command -v ruflo 2>/dev/null || true)}"
[ -n "$BIN" ] && [ -x "$BIN" ] || noop
ns=$(ruflo_ns)
dir="$ROOT/ruflo/$ns"
mkdir -p "$dir" && cd "$dir" || noop
export RUFLO_NO_AUTO_ENABLE=1
# a CLI start must never autostart the background daemon (headless claude sessions cost tokens)
export RUFLO_DAEMON_AUTOSTART=0
# getProjectCwd() in the CLI prefers CLAUDE_FLOW_CWD over process.cwd()
export CLAUDE_FLOW_CWD="$dir"
"$BIN" "$@"
exit 0
