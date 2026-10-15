# Dryas in cloud sessions (sub-project E)

Date: 2026-10-15. Status: design approved in conversation (sections 1–4); this spec awaits Promprit's review.
Builds on: the owned core (`docs/superpowers/specs/2026-10-14-owned-core-design.md`), sub-projects A1, A2, B, C merged into `spec/owned-core`; starts after plan D merges.

## Goal

One Dryas command makes any GitHub repo work in claude.ai/code cloud sessions with the Dryas workflow and the cloud-capable skills, with no setup inside the cloud environment.

Success: after `dryas cloud init` and a commit, a fresh cloud session on that repo loads the Dryas rules, offers `/orchestrate`, `/wplan`, `/wreview`, `/commit`, `/tune` and `/handoff`, runs the hook chain (scope lock → gate → memory → observer), asks before `git checkout -- .`, and runs `/tune`, all with the local judge, no Jev key and no network.

## Facts this design relies on (claude.ai/code docs, 2026-10-14)

- A cloud session builds from the repo and loads committed `.claude/skills`, `.claude/agents`, `.claude/commands`, hooks in `.claude/settings.json`, `.mcp.json` and `CLAUDE.md`, with no trust prompt.
- It does not install plugins from committed `enabledPlugins` or `extraKnownMarketplaces`.
- The network allowlist and secrets are set per environment and cannot be committed. `openrouter.ai` is blocked by default.
- The home directory is not kept between sessions. `CLAUDE_CODE_REMOTE=true` is set.
- The owned core is Python stdlib only (no Node, Ruflo or Superpowers), so it can run from files in the repo.

## Decisions

- **Approach: copy into the repo.** A pinned, version-stamped copy of the Dryas core is written into the repo. Rejected: a session-start bootstrap that downloads Dryas (network-dependent, slower, may run after skills are read) and a per-environment setup script (manual, not reviewable).
- **No Jev by default in the cloud.** Jev is an explicit per-environment opt-in.
- **Memory across cloud sessions is opt-in** and travels as committed, redacted markdown notes, never as a hidden database.
- **`update-my-vault` is excluded** (its vault and sources are on the Mac). Also excluded: `fo-iterm`, `claude-hud`.
- **Third-party skills are copied only with a confirmed licence**, with the licence text and a NOTICE line.

## 1. What goes into the repo

| Path | Contents |
|---|---|
| `.dryas/` | Runtime only: `jev/` (judge, scope lock, memory, tune; no tests), `pstack/`, `bin/dryas-py`, `VERSION` (Dryas version, commit, files hash), `manifest.json`, `NOTICE`. About 0.6 MB. |
| `.claude/skills/`, `.claude/agents/`, `.claude/commands/` | Dryas core skills, the `executor` agent, the commands `/orchestrate`, `/wplan`, `/wreview`, `/commit`, `/tune`, `/handoff`, `/dryas-cloud`. |
| `.claude/settings.json` | Merged, not overwritten: Dryas hooks pointing at `$CLAUDE_PROJECT_DIR/.dryas/jev/cloud_hook.py`, plus one allow rule. **No Dryas `env` entries** (amended 2026-10-15, approved by Promprit): on a Mac with the plugin installed, a project `env` value would also reach the plugin's own hooks and MCP server. `cloud_hook.py` sets `CLAUDE_PLUGIN_ROOT=<repo>/.dryas` and `DRYAS_DATA_ROOT=<repo>/.dryas/state` before every hook, and that is the only way hooks get them. |
| `.mcp.json` | Merged: the `jev` MCP server (judge, log tools, memory tools) run from `.dryas/`, with its own `env` block: `CLAUDE_PLUGIN_ROOT` and `DRYAS_DATA_ROOT` under `${CLAUDE_PROJECT_DIR:-.}/.dryas`. |
| `CLAUDE.md` | A marked Dryas rules block, inserted or replaced between markers; the repo's own text is untouched. |
| `.gitignore` | Gains `.dryas/state/`. |

Paths are always relative to `$CLAUDE_PROJECT_DIR`, so the same files work on the Mac and in the cloud. A name that clashes with the repo's own skill or command stops the run; `--prefix` renames the Dryas copies.

Not copied: Ruflo, Superpowers, Codex files, the Mac-only skills, MCP servers that need npm or network (Playwright, Context7, GitHub).

## 2. Behaviour in a cloud session

- **Judge.** `judge.provider: auto` resolves to `local` when `CLAUDE_CODE_REMOTE=true`, even if a key is present (change in `providers.resolve`). Opt-in per environment: `DRYAS_JUDGE=jev`, an `OPENROUTER_API_KEY` secret and `openrouter.ai` on the allowlist.
- **State.** `DRYAS_DATA_ROOT` is `.dryas/state/` (git-ignored): Jev logs, threshold overrides, scope-lock files. Nothing depends on state from an earlier session.
- **Memory, opt-in (`--persist-memory`).** At session end B's memory exports a short markdown summary (lessons, decisions, task outcomes, `/tune` per-task rows) into `.dryas/memory/notes/`, redacted with `redact.py`. Session start imports the notes. They are committed with the work and reviewable in pull requests. Off by default.
- **Python.** Cloud images have `python3`; `bin/dryas-py` falls back as today. Every hook exits 0 on internal errors; the gate then asks.
- **Network.** None for the core; `openrouter.ai` only for an environment that opted into Jev.

## 3. Skills and licences

`.dryas/manifest.json` lists every copied file with source, version, licence and hash; it drives `check`, `update` and `remove`.

| Group | Skills | Licence | Rule |
|---|---|---|---|
| Dryas core | orchestrate, brainstorm, plan, review-request, review-receive, tdd, debug, verify, worktree, interrogate, wplan, wreview, commit, tune, handoff; executor agent | MIT (Dryas) | Always copied |
| Design (`--with-design`) | ui-ux-pro-max and its sub-skills (design, design-system, banner-design, brand, slides, ui-styling) | MIT | Copied with LICENSE and a NOTICE line |
| | impeccable | Apache-2.0 (stated in its SKILL.md) | Copied with the Apache-2.0 text and a NOTICE line |
| Own skills (`--with-own <name>`) | skills in the user's `~/.claude/skills` with no licence file | the user's | Only when named one by one; each is scanned with `redact.py` and any hit stops the copy until confirmed |
| Excluded | update-my-vault, fo-iterm, claude-hud, Ruflo, Superpowers, Playwright, Context7, GitHub MCP | n/a | Listed as "not copied" with the reason |

A skill whose licence cannot be confirmed is not copied. Copied helper scripts must be stdlib only; anything needing pip packages is not copied.

## 4. The command

`tools/dryas_cloud.py` (stdlib), exposed as `install.sh --repo <path>` / `install.ps1 -Repo <path>`, `dryas cloud init|check|update|remove`, and `/dryas-cloud`. It reuses `render.py`, `claude_md_block.py`, `settings_merge.py`, `claude_mcp.py` and `components.json`.

- **init / update.** Preflight: a git work tree, Python 3.9+, no uncommitted changes in the paths it will write (else `--force`). It always prints a dry run (every file to add, change or remove, with sizes) and writes only with `--yes`. Update replaces only files the manifest owns; hand edits are reported as drift and kept unless `--force`. It never commits; it prints the `git add` line and a suggested message.
- **check.** Drift against the manifest; scan of copied files for `~/`, `/Users/`, `/Volumes/` and `${CLAUDE_PLUGIN_ROOT}` outside `.dryas/`; stdlib-only scan of copied scripts; version against the Dryas checkout; licence and NOTICE entries. Non-zero exit on any problem, so a repo's CI can run it.
- **remove.** Deletes only manifest-owned files (hand-edited ones are listed and kept), takes the Dryas entries out of `settings.json` and `.mcp.json`, removes the `CLAUDE.md` block.

## Error handling

- An unreadable or malformed `settings.json` or `.mcp.json` stops the run; it never overwrites a file it cannot parse.
- Name clashes stop the run with the list and a `--prefix` hint.
- Unconfirmed licences and non-stdlib scripts are skipped and reported.
- In the cloud, hooks exit 0 on internal errors and the gate asks.

## Testing

- `install/tests/`: init into a temp git repo, then check passes; a hand edit is reported as drift; update keeps it unless `--force`; remove leaves the repo diff-clean against before init; merges keep existing `settings.json` and `.mcp.json` entries; clash, malformed JSON and Mac-path scan each fail; a design copy carries its LICENSE and NOTICE line; the dry run changes nothing.
- Simulated cloud run: init a temp repo, run its hooks with `CLAUDE_CODE_REMOTE=true`, an empty `HOME` and no Jev key. The judge resolves to local, state lands in `.dryas/state/`, and a gate and scope-lock sequence behaves as on the Mac.
- `tools/inventory.py`: a "cloud" binding table; every core component is copied or excluded with a reason.
- Manual acceptance, once: init a small real repo, push it, open a claude.ai/code session, confirm the rules load, `/orchestrate` exists, the gate asks on `git checkout -- .`, and `/tune` runs.

## Out of scope

- Installing plugins in cloud sessions (not supported by the platform).
- `update-my-vault` in the cloud.
- MCP servers that need npm or network.
- Syncing state between the Mac and cloud sessions other than the opt-in memory notes.

## Order

Sub-project E. It starts after plan D merges, because D changes the installer, the hook chain and the docs that E copies.
