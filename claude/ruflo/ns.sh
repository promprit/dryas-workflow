# Sourced by run.sh / cli.sh / mcp-shim: ruflo_ns prints the data namespace for the current project.
# = folder name of the MAIN repo (so worktrees like <repo>/.worktrees/main map to <repo>); falls back to
# the basename of the project dir when not a git repo / bare repo. Sanitized to [A-Za-z0-9._-].
ruflo_ns() {
  _d="${CLAUDE_PROJECT_DIR:-$PWD}"
  _c=$(git -C "$_d" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
  case "$_c" in
    */.git) _n=$(basename "$(dirname "$_c")") ;;
    *) _n=$(basename "$_d") ;;
  esac
  _n=$(printf '%s' "$_n" | tr -c 'A-Za-z0-9._-' '_')
  case "$_n" in ''|.|..) _n=_unknown ;; esac
  printf '%s' "$_n"
}

# Prints the Ruflo data root; returns 1 when it is missing (SSD unplugged / not installed).
# RUFLO_SSD_ROOT (tests) keeps the old layout: <root>/_caches. Otherwise DRYAS_DATA_ROOT, default $HOME/.dryas.
ruflo_root() {
  if [ -n "${RUFLO_SSD_ROOT:-}" ]; then
    [ -d "$RUFLO_SSD_ROOT" ] || return 1
    printf '%s' "$RUFLO_SSD_ROOT/_caches"
  else
    _r="${DRYAS_DATA_ROOT:-$HOME/.dryas}"
    [ -d "$_r" ] || return 1
    printf '%s' "$_r"
  fi
}
