#!/bin/sh
# Tests for ~/.claude/ruflo/run.sh. Usage: sh test_run.sh   (RUN=path overrides the script under test)
RUN="${RUN:-$HOME/.claude/ruflo/run.sh}"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail=0
ok() { echo "PASS $1"; }
bad() { echo "FAIL $1"; fail=1; }
cat > "$T/echo.js" <<'JS'
let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{process.stdout.write('GOT:'+d+'|DIR:'+process.env.RUFLO_DATA_ROOT+'|NAE:'+process.env.RUFLO_NO_AUTO_ENABLE);process.exit(2)})
JS
mkdir -p "$T/ssd"

# 1 SSD missing -> silent exit 0, stdin drained
out=$(echo payload | RUFLO_SSD_ROOT="$T/nonexistent" /bin/sh "$RUN" node "$T/echo.js" 2>&1); rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && ok "ssd-missing exits 0 silently" || bad "ssd-missing rc=$rc out=[$out]"

# 2 helper missing -> silent exit 0
out=$(echo payload | RUFLO_SSD_ROOT="$T/ssd" /bin/sh "$RUN" node "$T/nope.js" 2>&1); rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && ok "helper-missing exits 0 silently" || bad "helper-missing rc=$rc out=[$out]"

# 3 command missing -> silent exit 0
out=$(echo payload | RUFLO_SSD_ROOT="$T/ssd" /bin/sh "$RUN" no-such-cmd-xyz "$T/echo.js" 2>&1); rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && ok "command-missing exits 0 silently" || bad "command-missing rc=$rc out=[$out]"

# 4 present helper: runs, stdin passed, stdout unchanged, child exit 2 mapped to 0, data dir + env set
out=$(printf 'hello-stdin' | CLAUDE_PROJECT_DIR=/x/myproj RUFLO_SSD_ROOT="$T/ssd" /bin/sh "$RUN" node "$T/echo.js" 2>&1); rc=$?
exp="GOT:hello-stdin|DIR:$T/ssd/_caches/ruflo/myproj|NAE:1"
[ $rc -eq 0 ] && [ "$out" = "$exp" ] && ok "helper runs, stdin passed, never exits 2" || bad "present rc=$rc out=[$out] exp=[$exp]"
[ -d "$T/ssd/_caches/ruflo/myproj" ] && ok "per-project cache dir created" || bad "cache dir missing"

# 5 env mode: no cwd/data-root change
out=$(printf 'e' | RUFLO_DATA_MODE=env RUFLO_SSD_ROOT="$T/ssd" /bin/sh "$RUN" node "$T/echo.js" 2>&1)
[ "$out" = "GOT:e|DIR:undefined|NAE:1" ] && ok "env mode leaves data root unset" || bad "env mode out=[$out]"
H="$HOME/.claude/ruflo/helpers"

# 6 session-restore never spawns npx (fake npx on PATH writes a marker)
mkdir -p "$T/fakebin" "$T/proj6"
printf '#!/bin/sh\ntouch "%s/npx-marker"\n' "$T" > "$T/fakebin/npx"; chmod +x "$T/fakebin/npx"
echo '{}' | PATH="$T/fakebin:$PATH" CLAUDE_PROJECT_DIR="$T/proj6" RUFLO_SSD_ROOT="$T/ssd" /bin/sh "$RUN" node "$H/hook-handler.cjs" session-restore >/dev/null 2>&1
sleep 1
[ ! -e "$T/npx-marker" ] && ok "session-restore does not spawn npx" || bad "npx was spawned"

# 7 auto-memory import is read-only on ~/.claude/projects/*/memory (temp HOME)
P="$T/proj7"; mkdir -p "$P"
KEY=$(printf '%s' "$P" | sed 's|[/_:]|-|g')
MD="$T/home/.claude/projects/$KEY/memory"; mkdir -p "$MD"
printf '# Memory\n\n## Fact one\nSome remembered fact for the test.\n' > "$MD/MEMORY.md"
snap() { (cd "$MD" && find . -type f | sort | while read f; do shasum "$f"; done; find . | sort); }
before=$(snap)
imp=$(echo '{}' | HOME="$T/home" CLAUDE_PROJECT_DIR="$P" RUFLO_SSD_ROOT="$T/ssd" /bin/sh "$RUN" node "$H/auto-memory-hook.mjs" import 2>&1)
after=$(snap)
[ "$before" = "$after" ] && ok "import leaves memory dir byte-identical" || bad "memory dir changed"
echo "$imp" | /usr/bin/grep -q "Imported [1-9]" && ok "import actually read the memory file" || bad "import read nothing: $imp"

# 8 node fallback when node is not on PATH
printf '#!/bin/sh\necho FALLBACK:$1\n' > "$T/fakenode"; chmod +x "$T/fakenode"
echo 'x' > "$T/h.js"
out=$(echo p | env -i PATH="/usr/bin:/bin" RUFLO_NODE_FALLBACK="$T/fakenode" RUFLO_SSD_ROOT="$T/ssd" /bin/sh "$RUN" node "$T/h.js" 2>&1)
[ "$out" = "FALLBACK:$T/h.js" ] && ok "node fallback used when node not on PATH" || bad "fallback out=[$out]"
out=$(echo p | env -i PATH="/usr/bin:/bin" RUFLO_NODE_FALLBACK="$T/nonexistent-node" RUFLO_SSD_ROOT="$T/ssd" /bin/sh "$RUN" node "$T/h.js" 2>&1); rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && ok "no node and no fallback: silent exit 0" || bad "nofallback rc=$rc out=[$out]"

# ---- cli.sh (RUFLO_HOOK_CLI_OVERRIDE target)
CLI="$HOME/.claude/ruflo/cli.sh"
printf '#!/bin/sh\necho "PWD:$(pwd -P)|CWDENV:$CLAUDE_FLOW_CWD|ARGS:$*|IN:$(cat)"\nexit 2\n' > "$T/fakeruflo"; chmod +x "$T/fakeruflo"
out=$(echo p | RUFLO_SSD_ROOT="$T/nossd" RUFLO_BIN="$T/fakeruflo" /bin/sh "$CLI" hooks x 2>&1); rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && ok "cli.sh no-ops without SSD" || bad "cli.sh nossd rc=$rc out=[$out]"
out=$(echo p | RUFLO_SSD_ROOT="$T/ssd" RUFLO_BIN="$T/nobin" /bin/sh "$CLI" hooks x 2>&1); rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && ok "cli.sh no-ops without binary" || bad "cli.sh nobin rc=$rc out=[$out]"
out=$(echo stdin-data | CLAUDE_PROJECT_DIR=/x/projcli RUFLO_SSD_ROOT="$T/ssd" RUFLO_BIN="$T/fakeruflo" /bin/sh "$CLI" hooks post-command -c ls 2>&1); rc=$?
RP=$(cd "$T/ssd/_caches/ruflo/projcli" && pwd -P)
exp="PWD:$RP|CWDENV:$T/ssd/_caches/ruflo/projcli|ARGS:hooks post-command -c ls|IN:stdin-data"
[ $rc -eq 0 ] && [ "$out" = "$exp" ] && ok "cli.sh runs in per-project cache dir, passes args+stdin, maps exit 2 to 0" || bad "cli.sh run rc=$rc out=[$out]"

# end-to-end: plugin hook (post-command) with the override, real pinned ruflo CLI, temp git repo
PLUG="$HOME/.claude/plugins/cache/ruflo/ruflo-core/0.2.6"
if [ -d "$PLUG" ] && [ -x "${RUFLO_BIN:-$(command -v ruflo)}" ]; then
  G="$T/gitrepo"; mkdir -p "$G"; (cd "$G" && git init -q)
  (cd "$G" && echo '{"tool_name":"Bash","tool_input":{"command":"echo e2e-secret-cmd"},"tool_response":{"exit_code":0}}' | \
    CLAUDE_PROJECT_DIR="$G" CLAUDE_PLUGIN_ROOT="$PLUG" RUFLO_SSD_ROOT="$T/ssd" \
    RUFLO_HOOK_CLI_OVERRIDE="/bin/sh $CLI" RUFLO_HOOK_SKIP_NPX=1 \
    node -e "process.argv=[process.argv[0],'x','post-command'];require(require('path').join(process.env.CLAUDE_PLUGIN_ROOT,'scripts','ruflo-hook.cjs'))") >/dev/null 2>&1
  [ ! -e "$G/.claude-flow" ] && [ ! -e "$G/.swarm" ] && ok "e2e: no .claude-flow/.swarm in project repo" || bad "e2e: project tree polluted: $(ls -a "$G")"
  [ -d "$T/ssd/_caches/ruflo/gitrepo" ] && ok "e2e: cache dir used" || bad "e2e: cache dir missing"
  echo "  e2e cache contents: $(cd "$T/ssd/_caches/ruflo/gitrepo" && find . -type f | head -5 | tr '\n' ' ')"
else echo "SKIP e2e (plugin or ruflo binary absent)"; fi

# ---- namespace = main repo folder name (worktree-safe)
. "$HOME/.claude/ruflo/ns.sh"
mkdir -p "$T/x/myrepo" "$T/plain"; (cd "$T/x/myrepo" && git init -q && git -c user.email=a@b -c user.name=t commit -q --allow-empty -m i && mkdir -p .worktrees && git worktree add -q .worktrees/main -b wt-main)
n=$(CLAUDE_PROJECT_DIR="$T/x/myrepo/.worktrees/main" ruflo_ns); [ "$n" = "myrepo" ] && ok "ns of worktree .worktrees/main = myrepo" || bad "worktree ns=[$n]"
n=$(CLAUDE_PROJECT_DIR="$T/x/myrepo" ruflo_ns); [ "$n" = "myrepo" ] && ok "ns of main checkout = myrepo" || bad "main ns=[$n]"
n=$(CLAUDE_PROJECT_DIR="$T/plain" ruflo_ns); [ "$n" = "plain" ] && ok "ns of non-git dir = plain" || bad "plain ns=[$n]"
mkdir -p "$T/we ird"; n=$(CLAUDE_PROJECT_DIR="$T/we ird" ruflo_ns); [ "$n" = "we_ird" ] && ok "ns sanitized" || bad "sanitize ns=[$n]"
out=$(echo i | CLAUDE_PROJECT_DIR="$T/x/myrepo/.worktrees/main" RUFLO_SSD_ROOT="$T/ssd" RUFLO_BIN="$T/fakeruflo" /bin/sh "$CLI" hooks y 2>&1)
case "$out" in *"CWDENV:$T/ssd/_caches/ruflo/myrepo|"*) ok "cli.sh uses main-repo ns for a worktree";; *) bad "cli.sh worktree ns out=[$out]";; esac
out=$(echo i | CLAUDE_PROJECT_DIR="$T/x/myrepo/.worktrees/main" RUFLO_SSD_ROOT="$T/ssd" /bin/sh "$RUN" node "$T/echo.js" 2>&1)
case "$out" in *"DIR:$T/ssd/_caches/ruflo/myrepo|"*) ok "run.sh uses main-repo ns for a worktree";; *) bad "run.sh worktree ns out=[$out]";; esac

# ---- MCP shim: fails loudly (exit 1) without SSD
SHIM="$HOME/.claude/ruflo/mcp-shim/bin/cli.js"
out=$(RUFLO_SSD_ROOT="$T/nossd" node "$SHIM" mcp start </dev/null 2>&1); rc=$?
[ $rc -eq 1 ] && ok "mcp shim exits 1 when SSD missing" || bad "mcp shim nossd rc=$rc"

# ---- realistic: plugin MCP launcher (stdio, memory_store) + plugin hook via override, cwd = temp git repo
if [ -d "$PLUG" ]; then
  R2="$T/e2erepo"; mkdir -p "$R2" "$T/ssd2"; (cd "$R2" && git init -q)
  node "$HOME/.claude/ruflo/test_mcp.cjs" "$R2" "$T/ssd2" >"$T/mcp.out" 2>&1; mrc=$?
  [ $mrc -eq 0 ] && ok "mcp: initialize + memory_store answered" || bad "mcp e2e rc=$mrc $(cat "$T/mcp.out")"
  (cd "$R2" && echo '{"tool_name":"Bash","tool_input":{"command":"echo hi"},"tool_response":{"exit_code":0}}' | \
    CLAUDE_PROJECT_DIR="$R2" CLAUDE_PLUGIN_ROOT="$PLUG" RUFLO_SSD_ROOT="$T/ssd2" RUFLO_HOOK_CLI_OVERRIDE="/bin/sh $CLI" \
    node -e "process.argv=[process.argv[0],'x','post-command'];require(require('path').join(process.env.CLAUDE_PLUGIN_ROOT,'scripts','ruflo-hook.cjs'))") >/dev/null 2>&1
  left=$(ls -A "$R2" | /usr/bin/grep -v '^\.git$')
  [ -z "$left" ] && ok "mcp+hook: project repo has only .git (no ruvector.db/.claude-flow/.swarm)" || bad "project polluted: $left"
  [ -f "$T/ssd2/_caches/ruflo/e2erepo/ruvector.db" ] && ok "mcp: ruvector.db landed in cache dir" || bad "ruvector.db not in cache"
fi
exit $fail
