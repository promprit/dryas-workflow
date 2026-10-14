---
name: worktree
description: Use when starting multi-step work or before running a plan. Creates or confirms the task's own git worktree and branch (one agent per worktree), sets it up, and checks a clean test baseline before any change.
---
On Codex, create it with `git worktree add ../<repo>-<topic> -b <branch>` and work from that folder. On Codex this is the location; skip Directory selection.

# Worktree

Make sure the work happens in an isolated workspace. Detect existing isolation first, then use the harness's native worktree tool, then fall back to git. Never fight the harness.

One agent per worktree: this session owns it alone. Never reuse a worktree another session works in; parallel loops on one project each get their own worktree and branch. `.orchestrate/` is ignored globally and never committed.

Announce at start: "I'm using the worktree skill to set up an isolated workspace."

## Detect existing isolation

Before creating anything, check whether you are already in an isolated workspace:

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
BRANCH=$(git branch --show-current)
```

**Submodule guard:** `GIT_DIR != GIT_COMMON` is also true inside a git submodule. Before concluding "already in a worktree", check you are not in one:

```bash
# prints a path inside a submodule: treat it as a normal repo
git rev-parse --show-superproject-working-tree 2>/dev/null
```

**`GIT_DIR != GIT_COMMON` and not a submodule:** you are already in a linked worktree. Do NOT create another; go to Project setup. Report the branch state:
- On a branch: "Already in isolated workspace at `<path>` on branch `<name>`."
- Detached HEAD: "Already in isolated workspace at `<path>` (detached HEAD, externally managed). Branch creation needed at finish time."

**`GIT_DIR == GIT_COMMON` (or a submodule):** you are in a normal checkout. If your instructions already state a worktree preference, honor it without asking; the Dryas rules state one ("Every multi-step task runs in its own git worktree"). Otherwise ask for consent first:

> "Would you like me to set up an isolated worktree? It protects your current branch from changes."

If the user declines, work in place and go to Project setup.

This step is done when you have stated one of: already isolated (with the branch report), creating one, or working in place.

## Create the worktree

Two mechanisms, in this order.

**1. Native worktree tool (preferred).** If you have one (a tool such as a worktree-create tool, a `worktree` command or a `--worktree` flag), use it and go to Project setup. Native tools handle placement, branch creation and cleanup; running `git worktree add` when a native tool exists creates phantom state the harness cannot see or manage. Use the git fallback only when there is no native tool.

**2. Git fallback.** Only when no native tool applies.

**Directory selection**, in priority order (explicit user preference always beats what is on disk):
1. A worktree directory declared in your instructions: use it without asking.
2. An existing project-local directory:
   ```bash
   ls -d .worktrees 2>/dev/null     # preferred (hidden)
   ls -d worktrees 2>/dev/null      # alternative
   ```
   If found, use it; if both exist, `.worktrees` wins.
3. No other guidance: default to `.worktrees/` at the project root.

**Safety check (project-local directories only).** The directory MUST be git-ignored before you create a worktree in it:

```bash
git check-ignore -q .worktrees 2>/dev/null || git check-ignore -q worktrees 2>/dev/null
```

If it is not ignored, add it to `.gitignore`, commit that change, then proceed. This prevents committing the worktree's contents into the repository.

**Create:**

```bash
path="$LOCATION/$BRANCH_NAME"
git worktree add "$path" -b "$BRANCH_NAME"
cd "$path"
```

**Sandbox fallback:** if `git worktree add` fails with a permission error (sandbox denial), tell the user the sandbox blocked worktree creation and that you are working in the current directory instead; then run setup and the baseline in place.

## Project setup

Detect and run the project's setup:

```bash
# Node.js (the lockfile names the package manager: pnpm-lock.yaml -> pnpm install)
if [ -f package.json ]; then npm install; fi
# Rust
if [ -f Cargo.toml ]; then cargo build; fi
# Python
if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
if [ -f pyproject.toml ]; then poetry install; fi
# Go
if [ -f go.mod ]; then go mod download; fi
```

No manifest (no `package.json`, `Cargo.toml` and so on): skip the dependency install. Setup is done when the install command exits 0 (or there was nothing to install).

## Clean baseline

Run the project's tests before any change, so the workspace starts clean:

```bash
# the project's own command
npm test / cargo test / pytest / go test ./...
```

**Tests fail:** report the failures and ask whether to proceed or investigate. **Tests pass:** report ready.

### Report

```
Worktree ready at <full-path>
Tests passing (<N> tests, 0 failures)
Ready to implement <feature-name>
```

## Reference

- When a situation is unclear (submodule, both directory names exist, sandbox denial, another session in the worktree), read `<dryas-root>/skills/worktree/reference.md` § Quick reference.
- When tempted to skip detection, the ignore check or the baseline, read `<dryas-root>/skills/worktree/reference.md` § Common rationalizations.
