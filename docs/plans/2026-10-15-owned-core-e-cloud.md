# Owned core, plan E: Dryas in cloud sessions — Implementation Plan

> **For agentic workers:** run with `/orchestrate` on this file (Dryas). Each `## Task N:` section is self-contained: its Goal/Scope/Done/Failing-test lines are the `.orchestrate/PLAN.md` contract; Interfaces and Steps follow. Steps use checkbox (`- [ ]`) syntax.

**Goal:** One command, `dryas cloud init`, makes any GitHub repo work in claude.ai/code cloud sessions with the Dryas workflow. It writes a pinned, version-stamped copy of the Dryas core into the repo. After a commit, a fresh cloud session loads the Dryas rules and offers `/orchestrate`, `/wplan`, `/wreview`, `/commit`, `/tune` and `/handoff`. It runs the hook chain (scope lock → gate → memory → observer), asks before `git checkout -- .`, and runs `/tune`, all with the local judge, no Jev key and no network.

**Architecture:** The CLI `tools/dryas_cloud.py` (`init | check | update | remove`) builds a file plan, then prints a dry run, then writes only with `--yes`. The plan comes from `tools/cloud_plan.py`, which rewrites copied text with `tools/cloud_text.py`. Repo config comes from `tools/cloud_config.py`: `.claude/settings.json`, `.mcp.json`, the `CLAUDE.md` block and `.gitignore`. These reuse `render.py`, `claude_md_block.py`, `settings_merge.py` and `components.json`. Three new modules run inside the copy:
- `claude/jev/cloud_hook.py`: the hook entry that points the runtime at `.dryas/` and `.dryas/state/`;
- `claude/jev/cloud_check.py`: drift, path, stdlib and licence checks, runnable inside a cloud session and in a repo's CI;
- `claude/jev/memnotes.py`: opt-in session notes.

`providers.resolve` makes `auto` local in a cloud session. `paths.py` expands a literal `$CLAUDE_PROJECT_DIR`. `reference/cloud-bindings.json`, checked by `tools/inventory.py --check`, lists every core component as copied, opt-in or excluded, with a reason.

**Tech Stack:** Python 3.9+ stdlib, `unittest.TestCase` classes run by pytest, POSIX sh and PowerShell wrappers.

**Spec:** `docs/superpowers/specs/2026-10-15-cloud-sessions-design.md` (sub-project E), all of it: Goal and success line, Facts, Decisions, §1–§4, Error handling, Testing, Out of scope. Its decisions are approved; this plan does not reopen them.

**Start:** E's build starts from `spec/owned-core` **after plan D (`docs/plans/2026-10-15-owned-core-d-integration.md`, branch `feat/owned-core-d`) merges**. E's worktree branches from `spec/owned-core` at the D merge commit. Before anything else, Task 1 checks every D interface E calls and fails loudly if a name is missing. If Task 1 fails, stop the plan and report; do not adapt later tasks to a different D.

**Baseline:** on `spec/owned-core` at `d2496cc` (before D), `python3 -m pytest -q claude/jev/tests install/tests` → **1603 passed, 1 skipped**. `python3 tools/inventory.py --check` → `387 baseline entries, 0 problems`, and `python3 tools/sync_codex_plugin.py --check` → exit 0. On the D merge (`e28218e`) it is **1742 passed, 2 skipped**, and inventory and sync are still clean; Task 1 re-records the count in its commit message. A dry run of this plan's code on `e28218e` (in a scratch copy) gave 1856 passed, 3 skipped, with inventory at 0 problems and sync exiting 0. E adds 115 tests: 38 in `claude/jev/tests` and 77 in `install/tests`. One Windows-only test is skipped on macOS and Linux, and on Windows the POSIX-only tests are skipped instead.

## Global Constraints

- Python 3.9+ stdlib only. Tests are `unittest.TestCase` classes. Isolate the environment with `p = mock.patch.dict(os.environ, {...}); p.start(); self.addCleanup(p.stop)` (no `enterContext`).
- **Additive only.** Test files that exist when E starts (`git ls-files claude/jev/tests install/tests` at the D merge) are never edited; new tests go in new files. `python3 tools/inventory.py --check` prints `0 problems` at the end of every task. Every existing hook, stage, MCP tool, flag, log field and `/tune` line keeps its name and meaning.
- Log records are built with `dict(...)` or literals, never `rec.update(...)`.
- **No Dryas `env` entries in `.claude/settings.json`** (spec §1, as amended). A project `env` value would also reach the plugin's own hooks and MCP server on a Mac where the plugin is installed. Hooks get `CLAUDE_PLUGIN_ROOT` and `DRYAS_DATA_ROOT` only from `cloud_hook.py`, and the `jev` MCP server only from its own `env` block in `.mcp.json`.
- **Never write an absolute Mac path into a copied file.** Paths in copied files are repo-relative (`.dryas/...`, `.claude/...`), `$CLAUDE_PROJECT_DIR` in hook commands, or `${CLAUDE_PROJECT_DIR:-.}` in `.mcp.json`. `cloud_check.check` fails a copy that names `/Users/` or `/Volumes/`.
- Docs and examples stay generic: the pre-commit deny-term scan rejects private venture names. Model names appear only inside backticks (`install/tests/test_tier_docs.py`).
- `codex/jev` is generated from `claude/jev` by `python3 tools/sync_codex_plugin.py`. Only Task 12 runs it. Tasks 2–5 add or change `claude/jev` files and leave `codex/jev` stale, so `sync --check` and `install/tests/test_codex_plugin_sync.py` fail from Task 2 until Task 12 by design. Done lines before Task 12 therefore name test files, not the whole `install/tests`.
- No literal `"/tmp/` path, no `shell=True`, and every `os.chmod` sits in a file that also checks `os.name` (`install/tests/test_portability.py`). Files stay under 500 lines. Largest after this plan: `tools/inventory.py` about 425, `tools/dryas_cloud.py` about 400, `tools/cloud_plan.py` about 360.
- Hooks never fail a tool call: `cloud_hook.py` exits 0 on an internal error, and for the PreToolUse chain it answers `ask`.
- Shell probes that contain discarding commands (`git checkout -- .`) are asked or denied by the live gate. Keep such strings inside test files written with the Write tool, never on a Bash command line.
- **Executors never work around the live gate or scope lock.** If a hook asks or denies during a task, stop and report it; never re-route the write through another tool or command.
- Commits: conventional messages, explicit paths, never push.

## Rules and the tests that pin them

1. **In a cloud session the judge is local by default, even with a key; Jev only on opt-in** (`DRYAS_JUDGE=jev` plus a key): `test_auto_is_local_in_a_cloud_session_even_with_a_key`, `test_cloud_session_never_calls_jev`, `test_opt_in_uses_jev` (Task 2), `test_judge_is_local_and_state_stays_in_the_repo` (Task 11).
2. **State lives in `.dryas/state/` and nothing depends on an earlier session:** `test_env_points_at_the_copy` (Task 3), `test_judge_is_local_and_state_stays_in_the_repo` (Task 11).
3. **No Mac path in any copied file; plugin paths and home state are rewritten:** `test_shipped_files_leave_no_plugin_trace` (Task 6), `test_every_planned_file_passes_the_scan` (Task 8), `test_mac_path_in_a_copied_file_fails_check` (Task 9).
4. **The dry run changes nothing; only `--yes` writes; nothing is committed:** `test_dry_run_changes_nothing`, `test_init_then_check_passes` (Task 9).
5. **Merge, never overwrite. A file that is not valid JSON stops the run:** `test_merge_keeps_the_users_entries_and_undo_restores_bytes`, `test_unparseable_settings_raise`, `test_malformed_mcp_raises` (Task 7), `test_merges_keep_existing_entries`, `test_malformed_config_stops_the_run` (Task 9).
6. **A name clash stops the run with a `--prefix` hint:** `test_clash_stops_with_prefix_hint` (Task 9).
7. **Hand edits are drift; update keeps them unless `--force`:** `test_hand_edit_is_drift_and_update_keeps_it` (Task 9).
8. **Remove leaves the repo as it was before init:** `test_remove_restores_the_repo` (Task 9).
9. **A licence must be confirmed or the skill is not copied. Copies carry the licence text and a NOTICE line:** `test_unconfirmed_licence_is_skipped`, `test_licensed_design_skills_are_copied_with_their_licence` (Task 8), `test_design_copy_carries_licence_and_notice` (Task 9).
10. **Copied scripts are stdlib only:** `test_skill_needing_pip_package_is_skipped` (Task 8), `test_non_stdlib_import` (Task 5).
11. **Own skills are copied only when named, and a redact hit stops one until confirmed:** `test_secret_shaped_text_stops_the_copy_until_confirmed` (Task 8).
12. **Hooks exit 0 on internal errors, and the gate then asks:** `test_internal_error_asks_for_pretool` (Task 3).
13. **Memory notes are opt-in, redacted, and imported at the next session start:** `test_export_writes_a_redacted_note`, `test_main_without_notes_dir_does_nothing` (Task 4), `test_memory_notes_round_trip_between_sessions` (Task 11).
14. **The copy behaves like the Mac install:** the same gate and scope-lock decisions come back, `test_scope_lock_and_gate_match_the_mac` (Task 11).
15. **A copy puts no Dryas `env` into `.claude/settings.json`, and remove leaves the repo's own `env` exactly as it was:** `test_fragment_sets_no_env`, `test_settings_env_is_never_touched` (Task 7), `test_init_writes_no_dryas_env_and_remove_keeps_env` (Task 9), `test_dryas_env_in_settings_is_a_problem` (Task 5).
16. **Every core component is copied, opt-in or excluded with a reason:** `test_table_covers_every_core_component` (Task 12), plus `inventory.py --check`.

## Review Focus

1. **A repo path with a space.** The hook commands quote `$CLAUDE_PROJECT_DIR`, so they must run from a folder like `my repo`. Pinned by every test in `test_cloud_session.py` (Task 11), whose repo is `my repo`.
2. **A `CLAUDE.md` with CRLF line endings and no final newline.** The block goes in and comes out byte-exact. Pinned by `test_block_round_trip_keeps_the_repos_text` (Task 7).
3. **Running init twice.** The second run refuses and names `update`, and writes nothing. Pinned by `test_second_init_refuses` (Task 9).
4. **A repo whose own `.claude/settings.json` already has an `env` block, even one that names `DRYAS_DATA_ROOT`.** Dryas neither reads nor changes it, and remove gives back the same bytes. Pinned by `test_settings_env_is_never_touched` (Task 7) and `test_init_writes_no_dryas_env_and_remove_keeps_env` (Task 9).
5. **A session id with path characters.** The notes file stays inside the notes folder. Pinned by `test_session_id_cannot_escape_the_notes_dir` (Task 4).

## Decisions taken in this plan (spec ambiguities)

- **Where the Dryas env comes from (spec §1 as amended, approved by Promprit).** `.claude/settings.json` gets no `env` entries, and every process gets the copy's paths another way:
  - **Hooks:** `cloud_hook.py` sets `CLAUDE_PLUGIN_ROOT=<copy>` and `DRYAS_DATA_ROOT=<copy>/state` before every hook.
  - **The `jev` MCP server:** its `.mcp.json` entry has its own `env` with `${CLAUDE_PROJECT_DIR:-.}/.dryas` and `.../state`. The server reads these only through `paths.data_root()` and `paths.plugin_root()` (`jevlog`, `thresholds`, `memdb`). Claude Code expands `${VAR:-default}` in `.mcp.json`. If a value arrives unexpanded, `paths._env_path` expands `$CLAUDE_PROJECT_DIR`, `${CLAUDE_PROJECT_DIR}` and `${CLAUDE_PROJECT_DIR:-...}` itself. When the variable is unset it returns "", so `paths` falls back to `copy_root()`, which gives `<copy>/state`.
  - **Scripts a skill runs** (`.dryas/bin/dryas-py .dryas/jev/tune.py report`): no env is needed, because `paths.copy_root()` puts their state in `<copy>/state` and their plugin root at `.dryas`. In a cloud session there is no user-level `DRYAS_DATA_ROOT` to override that. On a Mac with the plugin, the user's own `DRYAS_DATA_ROOT` wins, which is the plugin's state, as intended.

  Other `$` characters, such as Windows profile names, are kept.
- **Which hooks.** `.claude/settings.json` gets every hook from the plugin's `claude/hooks/hooks.json` as D leaves it. Each command is re-pointed through `"$CLAUDE_PROJECT_DIR/.dryas/jev/cloud_hook.py" <script> <args>`. The exception is `rules_inject.py`: the `CLAUDE.md` block carries the rules in a copy, and injecting them as well would load them twice.
- **The same files on the Mac.** When the user has Dryas installed (`~/.dryas/chain.local.json` exists) and the session is not a cloud session (`CLAUDE_CODE_REMOTE` is not `true`), the plugin's hooks already run. So `cloud_hook.py` does nothing there, and the chain does not run twice. `DRYAS_CLOUD_HOOKS=1` forces it on, `=0` off. **Resolved (was open for Promprit):** because the copy puts no `env` in `.claude/settings.json`, nothing it writes reaches the plugin's own hooks or MCP server on the Mac. The copy's `jev` server is a separate project-scope server with its own `env`.
- **The path scan.** The spec says to scan for `~/`, `/Users/`, `/Volumes/` and `${CLAUDE_PLUGIN_ROOT}` outside `.dryas/`. The always-copied core skills contain harmless `~/` prose, such as a `~/project/...` example and `~/.config/git/ignore`. A literal `~/` scan would therefore fail every fresh copy and contradict "init then check passes". The rule applied:
  - `/Users/` and `/Volumes/` are problems in every copied file;
  - `~/.dryas` and `${CLAUDE_PLUGIN_ROOT}` are problems outside `.dryas/`;
  - any `~/` is a problem in Dryas's own `.claude/settings.json` and `.mcp.json` entries, where a path would run.

  One Mac path in the runtime, the `handoff.py` docstring example, becomes a `/home/x` example (Task 5).
- **Paths in copied markdown** are repo-relative: `.dryas/bin/dryas-py`, `.claude/skills/plan/reference.md`, `.dryas/state/jev/thresholds.json`. A cloud session, and every worktree of it, starts at the repo root, and permission patterns then match the commands as written. Hook commands use `$CLAUDE_PROJECT_DIR`, and `.mcp.json` uses `${CLAUDE_PROJECT_DIR:-.}`.
- **Names.** `dryas:<skill>` becomes `<skill>`, `mcp__plugin_dryas_jev__x` becomes `mcp__jev__x` (the project-scope server is `jev`), and `subagent_type: dryas:executor` becomes `executor`. `--prefix` applies to every copied skill, command and agent, design and own skills included, and to `/command` mentions in copied text.
- **Exact lists.** The skills, commands and agent are exactly the spec's lists. `benchmark-checklist` is not in the spec's §3 core list, and D's `/retro` is not in §1, so neither is copied. Both appear as `exclude:` rows with a reason in the cloud table. The checklist file itself ships in `.dryas/pstack/`.
- **Extra files in `.dryas/`:**
  - `docs/workflow.md` → `.dryas/docs/dryas-workflow.md`, because the rules point at that doc;
  - `.dryas/licenses/` (the Dryas MIT licence, the Superpowers MIT licence that the process skills derive from, design licences);
  - `.dryas/memory/notes/.gitkeep` with `--persist-memory`.
- **`.gitignore`** gains `.dryas/state/` (spec), `.dryas/**/__pycache__/` (hooks import the copy's Python) and `.orchestrate/`. On the Mac, orchestration scratch is ignored only globally, and a cloud session has no global ignore.
- **Design licences.** The licence text is read from the installed plugin folder, or else from its marketplace clone under `<claude dir>/plugins/marketplaces/<marketplace>/`.
  - MIT is confirmed by a `LICENSE` that starts with `MIT License`.
  - Apache-2.0 is confirmed only when the skill's front matter says so and the Apache 2.0 text is found.
  - A plugin `NOTICE`/`NOTICE.md` is carried too, as Apache-2.0 asks.
  - The design plugin ids come from `install/components.json`.
- **Own skills.** A skill with a licence file is not an "own" skill and is skipped. A `redact.py` hit stops that skill until `--confirm-own NAME`, and the report names `file:line`, never the value. The spec's excluded names are refused.
- **The `mem-notes` stage** uses component `core` with `requires_path: "$CD/memory/notes"`. D's `test_memory_stages_shipped` pins the exact set of `memory`-component stages. The path makes the stage a no-op everywhere except a copy made with `--persist-memory`.
- **`claude_mcp.py` is not imported.** It registers a user-scope server through the `claude` CLI, which a committed `.mcp.json` does not need. `cloud_config.mcp_entry` mirrors its argv shape (`python -X utf8 .../jev/jev_mcp.py`).
- **`/dryas-cloud`** runs `check` anywhere, including inside a cloud session from the copy. `init`, `update` and `remove` need a Dryas checkout, so in a cloud session the command says so and stops.
- **remove** deletes `.dryas/state/` and `__pycache__` folders, which are generated and git-ignored. It keeps the memory notes (the user's work) and hand-edited files. **update** can add options but not drop them; to drop one, run remove and then init.
- **Preflight** also refuses a subfolder of a repo, because cloud sessions read `.claude/` and `CLAUDE.md` at the repo root.

## Coordination with plan D

Re-checked against D as merged (`e28218e`):
- Task 1's seven checks all pass.
- `tools/inventory.py --list` has exactly the entries the cloud table in Task 12 classifies, including `chain_stage:post:gate-outcome:core`, `command:claude:retro` and `component:optional:memory`.
- The only table rows not yet in the inventory are the two E adds itself (`chain_stage:session-end:mem-notes:core`, `command:claude:dryas-cloud`).

E starts after D merges. Every point below is a file D changes, or an interface D defines that E calls as D's plan defines it.

- **`claude/jev/chain.json`** (D Tasks 1, 7). E Task 4 appends one stage, `mem-notes`, to D's `session-end` list after `mem-session-end`. Its component is `core`, because D's `test_memory_stages_shipped` pins the set of `memory` stages.
- **`claude/hooks/hooks.json`** (D Task 1). E reads it and never edits it. `cloud_config.hooks` re-points each command, and Task 1 pins the command shape D uses: `"${DRYAS_PY:-python3}" -X utf8 "${CLAUDE_PLUGIN_ROOT}/jev/<script>.py" <args>`.
- **`claude/bin/dryas`, `claude/bin/dryas.cmd`** (D Task 4). E Task 10 adds a `cloud` case beside D's `memory` case. D's `test_dryas_wrapper.py` still holds: an unknown word prints `usage:` and exits 2. In `dryas.cmd`, E adds `exit /b %ERRORLEVEL%` after D's last memory line (`:plain`), so that it does not fall through into the new `:cloud` label. Checked against the merged D (e28218e): D's `:memory` block runs a plain `shift` and then uses `%~dp0`. That is a D defect on Windows, reported separately; E does not touch it.
- **`install/install.sh`, `install/install.ps1`.** No D Scope lists them, but D Task 12's end-to-end test runs them. E Task 10 adds a branch that sends a user-supplied `--repo`/`-Repo` to `tools/dryas_cloud.py init`. Every other run reaches D's `dryas_install.py run --repo "$REPO" ...` exactly as before. Keep any header lines D added.
- **`install/components.json`** (D Task 3 keeps its keys). E reads the `design` install commands for the plugin ids.
- **`claude/jev/memhooks.py`** (D Task 2). E calls `notes_dir` (which honours `DRYAS_NOTES_DIR`), `index_notes(conn, ns, d)` and `STAGES`, and does not edit the file.
- **`claude/jev/tune.py`, `tune_tasks.py`** (D Tasks 2, 7, 8). E calls only `tune.read(name, log_dir=None)` and `tune_tasks.rows(gate, dispatch, esc, mcp)`.
- **`claude/CLAUDE.md.template`** (D Tasks 5, 14) and **`docs/workflow.md`** (D Task 10). E copies whatever D leaves through `cloud_text.rewrite`. Task 6's test runs the rewrite on the real files and fails on any plugin path, `~/.dryas`, plugin name or Codex block left over.
- **`reference/README.md`** (D Task 11 rewrites it). E Task 12 adds one Bindings row after D's version.
- **`GLOSSARY.md`** (D Task 9). E Task 12 adds one `- **repo copy**: ...` line under `## Terms`, in D's format.
- **`.out-of-scope/`** (D Task 9). E adds no entry, because D's `test_out_of_scope_entries` pins the exact list.
- **`tools/sync_codex_plugin.py`** (D Tasks 5, 9). E imports `harness_blocks` only. `dryas-cloud` is not added to `COMMANDS`, because cloud sessions are Claude Code only.
- **`claude/settings.fragment.json`, `install/run_cmd.py`, `install/plugin_setup.py`** (D Tasks 3, 4). E edits none of them. The copy's settings come from `cloud_config`. `run_cmd`'s own `--repo` (the Dryas checkout, passed by `install.sh`) is untouched, because `install.sh` routes the user's `--repo` before that call.
- **Version 2.0.0** (D Task 15). `.dryas/VERSION` and the manifest read `claude/.claude-plugin/plugin.json`. E bumps no version.
- **`claude/jev/paths.py`, `providers.py`, `handoff.py`.** D's file map does not touch them; E edits them in Tasks 2 and 5.
- **`codex/jev/**`.** D regenerates it, and E regenerates it once more in Task 12.

## File map

Create:
- `claude/jev/cloud_hook.py`, `claude/jev/memnotes.py`, `claude/jev/cloud_check.py`
- `tools/cloud_text.py`, `tools/cloud_config.py`, `tools/cloud_plan.py`, `tools/dryas_cloud.py`
- `claude/commands/dryas-cloud.md`, `reference/cloud-bindings.json`, `docs/cloud-sessions.md`
- tests:
  - `claude/jev/tests/test_cloud_judge.py`, `test_paths_cloud.py`, `test_cloud_hook.py`, `test_memnotes.py`, `test_cloud_check.py`
  - `install/tests/test_cloud_prereqs.py`, `cloud_fixtures.py` (a helper, not a test), `test_cloud_text.py`, `test_cloud_config.py`, `test_cloud_plan.py`, `test_dryas_cloud.py`, `test_cloud_entry.py`, `test_cloud_session.py`, `test_cloud_bindings.py`
- generated: `codex/jev/{cloud_hook,memnotes,cloud_check}.py`

Modify:
- `claude/jev/{providers.py,paths.py,handoff.py,chain.json}`
- `install/install.sh`, `install/install.ps1`, `claude/bin/dryas`, `claude/bin/dryas.cmd`
- `tools/inventory.py`, `reference/README.md`, `GLOSSARY.md`
- generated `codex/jev/*` copies

What a repo gets from `dryas cloud init`:
- `.dryas/` holds `jev/`, `pstack/`, `bin/dryas-py`, `docs/dryas-workflow.md`, `licenses/`, `NOTICE`, `VERSION` and `manifest.json`, plus `memory/notes/` with `--persist-memory`;
- `.claude/` holds `skills/<core>/`, `commands/<core>.md` and `agents/executor.md`;
- `.claude/settings.json`, `.mcp.json`, `CLAUDE.md` and `.gitignore` are merged.

## Order

| Group | Tasks | Runs after | Why |
|---|---|---|---|
| 1 | 1 | D merged | checks D's interfaces before anything is built on them |
| 2 | 2, 3, 4, 5, 6, 7 (parallel) | 1 | disjoint new files; Scope globs do not overlap |
| 3 | 8 | all of group 2 | the plan copies `cloud_hook.py`, `memnotes.py`, `cloud_check.py` and calls `cloud_check` and `cloud_text` |
| 4 | 9 | 8 | the CLI drives `cloud_plan` and `cloud_config` |
| 5 | 10, 11 (parallel) | 9 | entry points and the simulated cloud session; disjoint Scopes |
| 6 | 12 | 10, 11 | cloud binding table, inventory check, docs, Codex sync, full suite |

Scopes in group 2:
- Task 2: `claude/jev/providers.py`, `claude/jev/paths.py` and their two tests;
- Task 3: `claude/jev/cloud_hook.py` and its test;
- Task 4: `claude/jev/memnotes.py`, `claude/jev/chain.json` and its test;
- Task 5: `claude/jev/cloud_check.py`, `claude/jev/handoff.py` and its test;
- Task 6: `tools/cloud_text.py` and its test;
- Task 7: `tools/cloud_config.py` and its test.

In group 5, Task 10 owns `install/install.{sh,ps1}`, `claude/bin/dryas{,.cmd}` and its test, and Task 11 owns only `install/tests/test_cloud_session.py`.

---

## Task 1: Re-verify plan D's interfaces
Goal: before E builds anything, prove that every D interface E calls exists under the name D's plan gives it, and record the post-D test baseline.
Scope:
- install/tests/test_cloud_prereqs.py
Done:
- `python3 -m pytest -q install/tests/test_cloud_prereqs.py` passes (7 tests)
- `python3 -m pytest -q claude/jev/tests install/tests` passes; the count is in the commit message
- `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: install/tests/test_cloud_prereqs.py :: DInterfacesTest :: test_observe_kinds_and_memory_stages

This is a check task. On a tree where D has merged, the test passes as soon as it is written. On a tree without D it fails, which is its purpose. **If any test here fails, stop and report the failing name. Do not edit the test to pass, and do not adapt later tasks to a different D.**

**Interfaces:**
- Consumes (D): `chain.OBSERVE_KINDS`, `chain.observe`, and the chain stages `post/mem-edit`, `post/gate-outcome`, `subagent-stop/mem-task`, `session-start/mem-session-start`, `session-end/mem-session-end` and `precompact/mem-session-end`. The `claude/hooks/hooks.json` routes for PostToolUse, PostToolUseFailure, SubagentStop, SessionStart, SessionEnd and PreCompact, all with the command shape `"${DRYAS_PY:-python3}" -X utf8 "${CLAUDE_PLUGIN_ROOT}/jev/<script>.py" <args>`. `run_cmd.OPTIONAL` containing `memory`, the `claude/bin/dryas` `memory)` case, and plugin version `2.x`.
- Consumes (pre-D, kept by D): `memhooks.notes_dir`, `memhooks.index_notes(conn, ns, d)`, `memhooks.STAGES`, `tune.read(name, log_dir=None)`, `tune_tasks.rows(gate, dispatch, esc, mcp)`, `claude_md_block.insert_block/remove_block`, `render.chain_bytes/gate_blocks`, `settings_merge.merge/unmerge`, `sync_codex_plugin.harness_blocks`, and `install/components.json` keys `design`, `ruflo`, `superpowers`, with `design` installing `impeccable@impeccable` and `ui-ux-pro-max@ui-ux-pro-max-skill`.
- Produces: nothing new; a guard that later tasks rely on.

- [ ] **Step 1: Write the test** `install/tests/test_cloud_prereqs.py`:

```python
"""Plan E (Dryas in cloud sessions) starts on plan D as merged. Each check names a D interface E calls. A failure
means D is not merged or renamed something: stop and report it; do not adapt E's tasks."""
import inspect
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for _d in (ROOT / "claude" / "jev", ROOT / "install", ROOT / "tools"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
SHAPE = '"${DRYAS_PY:-python3}" -X utf8 "${CLAUDE_PLUGIN_ROOT}/jev/'


class DInterfacesTest(unittest.TestCase):
    def test_observe_kinds_and_memory_stages(self):
        import chain
        for kind in ("post", "subagent-stop", "session-start", "session-end", "precompact"):
            self.assertIn(kind, chain.OBSERVE_KINDS)
        self.assertTrue(callable(chain.observe))
        c = json.loads((ROOT / "claude/jev/chain.json").read_text(encoding="utf-8"))
        have = {(kind, s.get("name")) for kind, stages in c.items() for s in stages}
        for want in (("post", "mem-edit"), ("post", "gate-outcome"), ("subagent-stop", "mem-task"),
                     ("session-start", "mem-session-start"), ("session-end", "mem-session-end"),
                     ("precompact", "mem-session-end")):
            self.assertIn(want, have)

    def test_plugin_hooks_keep_one_shape(self):
        h = json.loads((ROOT / "claude/hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
        cmds = [(ev, x["command"]) for ev, groups in h.items() for g in groups for x in g["hooks"]]
        for ev, cmd in cmds:
            self.assertTrue(cmd.startswith(SHAPE), (ev, cmd))
        routed = {(ev, cmd[len(SHAPE):]) for ev, cmd in cmds}
        for want in (("PreToolUse", 'chain.py" pretool'), ("UserPromptSubmit", 'chain.py" prompt'),
                     ("PostToolUse", 'chain.py" post'), ("PostToolUseFailure", 'chain.py" post'),
                     ("SubagentStop", 'chain.py" subagent-stop'), ("SessionStart", 'chain.py" session-start'),
                     ("SessionEnd", 'chain.py" session-end'), ("PreCompact", 'chain.py" precompact')):
            self.assertIn(want, routed)

    def test_memory_hooks_read_the_notes_dir(self):
        import memhooks
        for stage in ("session-start", "session-end"):
            self.assertIn(stage, memhooks.STAGES)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with mock.patch.dict(os.environ, {"DRYAS_NOTES_DIR": d}):
            self.assertEqual(memhooks.notes_dir(d), d)
        self.assertEqual(list(inspect.signature(memhooks.index_notes).parameters), ["conn", "ns", "d"])

    def test_tune_rows_and_log_reader(self):
        import tune
        import tune_tasks
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        self.assertEqual(tune_tasks.rows([], [], [], []), {})
        self.assertEqual(tune.read("no-such-log", d), [])

    def test_design_component_and_installer_slots(self):
        import run_cmd
        self.assertIn("memory", run_cmd.OPTIONAL)
        comp = json.loads((ROOT / "install/components.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(comp), ["design", "ruflo", "superpowers"])
        installs = [c[3] for c in comp["design"]["commands"] if c[:3] == ["claude", "plugin", "install"]]
        self.assertEqual(sorted(installs), ["impeccable@impeccable", "ui-ux-pro-max@ui-ux-pro-max-skill"])

    def test_dryas_wrapper_and_version(self):
        self.assertIn("memory)", (ROOT / "claude/bin/dryas").read_text(encoding="utf-8"))
        self.assertIn("memory", (ROOT / "claude/bin/dryas.cmd").read_text(encoding="utf-8"))
        v = json.loads((ROOT / "claude/.claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
        self.assertTrue(v.startswith("2."), v)

    def test_shared_helpers_e_reuses(self):
        import claude_md_block
        import render
        import settings_merge
        import sync_codex_plugin
        for f in (claude_md_block.insert_block, claude_md_block.remove_block, render.chain_bytes, render.gate_blocks,
                  settings_merge.merge, settings_merge.unmerge, sync_codex_plugin.harness_blocks):
            self.assertTrue(callable(f))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python3 -m pytest -q install/tests/test_cloud_prereqs.py`. Expected on the D merge: **7 passed**. On any failure, stop and report the test name and its message.
- [ ] **Step 3: Record the baseline.** Run `python3 -m pytest -q claude/jev/tests install/tests` and note `N passed, M skipped`. Run `python3 tools/inventory.py --check` and expect `0 problems`.
- [ ] **Step 4: Commit** `git add install/tests/test_cloud_prereqs.py`, then `git commit -m "test(cloud): pin the plan D interfaces plan E calls" -m "Baseline on the D merge: N passed, M skipped."`, with the real numbers.

---

## Task 2: Local judge by default in cloud sessions; env-safe paths
Goal: in a cloud session `judge.provider: auto` resolves to `local` even with a key unless `DRYAS_JUDGE=jev`, and `paths` expands a literal `$CLAUDE_PROJECT_DIR` and keeps a repo copy's state in `<copy>/state`.
Scope:
- claude/jev/providers.py
- claude/jev/paths.py
- claude/jev/tests/test_cloud_judge.py
- claude/jev/tests/test_paths_cloud.py
Done:
- `python3 -m pytest -q claude/jev/tests/test_cloud_judge.py claude/jev/tests/test_paths_cloud.py claude/jev/tests/test_providers.py claude/jev/tests/test_paths.py claude/jev/tests/test_gate.py claude/jev/tests/test_gate_providers.py claude/jev/tests/test_route_providers.py claude/jev/tests/test_jev_mcp_providers.py` passes
- `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: claude/jev/tests/test_cloud_judge.py :: CloudJudgeTest :: test_auto_is_local_in_a_cloud_session_even_with_a_key

**Interfaces:**
- Produces: `providers._cloud_without_jev() -> bool`. It is True when `CLAUDE_CODE_REMOTE` is `true` (any case) and `DRYAS_JUDGE` is not `jev`. `providers.resolve(th, injected)` is unchanged except that `auto` resolves to `local` while `_cloud_without_jev()` holds, unless a judge function is injected (tests). An explicit `judge.provider` is kept.
- Produces: `paths._env_path(var) -> str`, `paths.copy_root() -> str` (the `.dryas` folder when the code runs from a copy that has `manifest.json`, else `""`), and `paths.data_root()` / `paths.plugin_root()` built on them.
- Consumed by Task 3 (`cloud_hook.py` sets the env that these read), Task 7 (the `.mcp.json` `env` block, which may arrive as `${CLAUDE_PROJECT_DIR:-.}/...`), scripts that skills run from the copy (no env: `copy_root()`), and Task 11.

- [ ] **Step 1: Write the failing tests.** `claude/jev/tests/test_cloud_judge.py`:

```python
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jev_client  # noqa: F401  (imported so mock.patch can find jev_client.judge)
import providers

AUTO = {"judge": {"provider": "auto", "shadow": "auto"}}
LOCAL = {"answers": {"safe": {"value": True, "confidence": 0.9}}, "reasons": ["local"]}


class CloudJudgeTest(unittest.TestCase):
    def env(self, **kw):
        base = {"CLAUDE_CODE_REMOTE": "", "DRYAS_JUDGE": ""}
        base.update(kw)
        p = mock.patch.dict(os.environ, base)
        p.start()
        self.addCleanup(p.stop)

    def key(self, present):
        p = mock.patch.object(providers, "_has_key", return_value=present)
        p.start()
        self.addCleanup(p.stop)

    def test_auto_is_local_in_a_cloud_session_even_with_a_key(self):
        self.env(CLAUDE_CODE_REMOTE="true")
        self.key(True)
        self.assertEqual(providers.resolve(AUTO, False), ("local", "none"))

    def test_cloud_session_never_calls_jev(self):
        self.env(CLAUDE_CODE_REMOTE="TRUE")
        self.key(True)
        with mock.patch("jev_client.judge", side_effect=AssertionError("network call")):
            out = providers.ask({}, {}, LOCAL, AUTO)
        self.assertEqual((out["provider"], out["shadow_provider"]), ("local", "none"))
        self.assertEqual(out["answers"], LOCAL["answers"])
        self.assertNotIn("fallback", out)

    def test_opt_in_uses_jev(self):
        self.env(CLAUDE_CODE_REMOTE="true", DRYAS_JUDGE="jev")
        self.key(True)
        self.assertEqual(providers.resolve(AUTO, False), ("jev", "local"))

    def test_opt_in_without_a_key_stays_local(self):
        self.env(CLAUDE_CODE_REMOTE="true", DRYAS_JUDGE="jev")
        self.key(False)
        self.assertEqual(providers.resolve(AUTO, False), ("local", "none"))

    def test_explicit_provider_is_kept_in_the_cloud(self):
        self.env(CLAUDE_CODE_REMOTE="true")
        self.key(True)
        self.assertEqual(providers.resolve({"judge": {"provider": "jev", "shadow": "none"}}, False), ("jev", "none"))

    def test_outside_the_cloud_nothing_changes(self):
        self.env(CLAUDE_CODE_REMOTE="false")
        with mock.patch.object(providers, "_has_key", return_value=True):
            self.assertEqual(providers.resolve(AUTO, False), ("jev", "local"))
        with mock.patch.object(providers, "_has_key", return_value=False):
            self.assertEqual(providers.resolve(AUTO, False), ("local", "none"))
        self.assertEqual(providers.resolve(AUTO, True), ("jev", "local"))


if __name__ == "__main__":
    unittest.main()
```

`claude/jev/tests/test_paths_cloud.py`:

```python
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

JEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JEV)
import paths

PROBE = "import sys; sys.path.insert(0, sys.argv[1]); import paths; print(paths.copy_root()); print(paths.data_root())"


class EnvPathTest(unittest.TestCase):
    def env(self, **kw):
        p = mock.patch.dict(os.environ, kw)
        p.start()
        self.addCleanup(p.stop)

    def test_literal_project_dir_is_expanded(self):
        self.env(DRYAS_DATA_ROOT="$CLAUDE_PROJECT_DIR/.dryas/state", CLAUDE_PLUGIN_ROOT="${CLAUDE_PROJECT_DIR}/.dryas",
                 CLAUDE_PROJECT_DIR="work/repo", JEV_LOG_DIR="")
        self.assertEqual(paths.data_root(), "work/repo/.dryas/state")
        self.assertEqual(paths.plugin_root(), "work/repo/.dryas")
        self.assertEqual(paths.log_dir(), os.path.join("work/repo/.dryas/state", "jev", "logs"))

    def test_mcp_default_form_is_expanded(self):
        self.env(DRYAS_DATA_ROOT="${CLAUDE_PROJECT_DIR:-.}/.dryas/state", CLAUDE_PLUGIN_ROOT="${CLAUDE_PROJECT_DIR:-.}/.dryas",
                 CLAUDE_PROJECT_DIR="work/repo")
        self.assertEqual(paths.data_root(), "work/repo/.dryas/state")
        self.assertEqual(paths.plugin_root(), "work/repo/.dryas")
        self.env(CLAUDE_PROJECT_DIR="")
        self.assertEqual(paths.plugin_root(), os.path.dirname(JEV))  # unset: the code's own folder, never "."

    def test_unset_project_dir_falls_back(self):
        self.env(DRYAS_DATA_ROOT="$CLAUDE_PROJECT_DIR/.dryas/state", CLAUDE_PLUGIN_ROOT="$CLAUDE_PROJECT_DIR/.dryas",
                 CLAUDE_PROJECT_DIR="", JEV_LOG_DIR="")
        self.assertEqual(paths.data_root(), os.path.join(os.path.expanduser("~"), ".dryas"))
        self.assertEqual(paths.plugin_root(), os.path.dirname(JEV))

    def test_other_dollar_values_are_kept(self):
        self.env(DRYAS_DATA_ROOT=os.path.join("C:", "profiles", "a$b", ".dryas"), CLAUDE_PLUGIN_ROOT="")
        self.assertEqual(paths.data_root(), os.path.join("C:", "profiles", "a$b", ".dryas"))
        self.assertEqual(paths.plugin_root(), os.path.dirname(JEV))


class CopyRootTest(unittest.TestCase):
    def test_a_repo_copy_keeps_state_beside_itself(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        jev = os.path.join(d, ".dryas", "jev")
        os.makedirs(jev)
        shutil.copy(os.path.join(JEV, "paths.py"), jev)
        env = {k: v for k, v in os.environ.items() if k not in ("DRYAS_DATA_ROOT", "CLAUDE_PLUGIN_ROOT")}

        def probe():
            p = subprocess.run([sys.executable, "-c", PROBE, jev], capture_output=True, text=True, env=env, timeout=30)
            return p.stdout.splitlines()

        self.assertEqual(probe()[0], "")  # no manifest: not a copy, the default data root applies
        with open(os.path.join(d, ".dryas", "manifest.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        self.assertEqual(probe(), [os.path.join(d, ".dryas"), os.path.join(d, ".dryas", "state")])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python3 -m pytest -q claude/jev/tests/test_cloud_judge.py claude/jev/tests/test_paths_cloud.py`. Expected: FAIL. With a key, `resolve` returns `("jev", "local")` in the cloud, `data_root` returns the literal `$CLAUDE_PROJECT_DIR/...` string, and `paths.copy_root` is not defined.

- [ ] **Step 3: Implement `claude/jev/providers.py`.** Add this sentence to the end of the module docstring: `In a claude.ai/code cloud session (CLAUDE_CODE_REMOTE=true) "auto" is local even with a key, unless the environment opted into Jev with DRYAS_JUDGE=jev (owned core E).` After `_has_key`, add:

```python
def _cloud_without_jev() -> bool:
    """A cloud session that did not opt into Jev: no OpenRouter call, whatever key the environment holds."""
    remote = os.environ.get("CLAUDE_CODE_REMOTE", "").strip().lower() == "true"
    return remote and os.environ.get("DRYAS_JUDGE", "").strip().lower() != "jev"
```

In `resolve`, replace

```python
        provider = "jev" if injected or _has_key() else "local"
```

with

```python
        provider = "jev" if injected or (not _cloud_without_jev() and _has_key()) else "local"
```

- [ ] **Step 4: Implement `claude/jev/paths.py`.** Add `import re` after `import os`. Replace `data_root()` and `plugin_root()` with the code below, and add `_PROJECT`, `_env_path` and `copy_root` above `data_root`:

```python
_PROJECT = re.compile(r"\$(?:\{CLAUDE_PROJECT_DIR(?::-[^}]*)?\}|CLAUDE_PROJECT_DIR(?![A-Za-z0-9_]))")


def _env_path(var: str) -> str:
    """An env path. A repo copy's .mcp.json gives the jev server "${CLAUDE_PROJECT_DIR:-.}/.dryas/state"; if a client
    passes it unexpanded, $CLAUDE_PROJECT_DIR, ${CLAUDE_PROJECT_DIR} and ${CLAUDE_PROJECT_DIR:-...} are expanded here,
    and "" (unset) is returned when CLAUDE_PROJECT_DIR is not set, so data_root() falls back to the copy's own
    state folder. Any other "$" (a Windows profile name) is kept as it is."""
    v = os.environ.get(var) or ""
    if _PROJECT.search(v):
        proj = os.environ.get("CLAUDE_PROJECT_DIR") or ""
        return _PROJECT.sub(lambda m: proj, v) if proj else ""
    return v


def copy_root() -> str:
    """The .dryas folder when this code runs from a repo copy made by `dryas cloud` (owned core E), else ""."""
    root = os.path.dirname(HERE)
    if os.path.basename(root) == ".dryas" and os.path.isfile(os.path.join(root, "manifest.json")):
        return root
    return ""


def data_root() -> str:
    env = _env_path("DRYAS_DATA_ROOT")
    if env:
        return env
    copy = copy_root()
    return os.path.join(copy, "state") if copy else os.path.join(os.path.expanduser("~"), ".dryas")
```

```python
def plugin_root() -> str:
    return _env_path("CLAUDE_PLUGIN_ROOT") or os.path.dirname(HERE)
```

Extend the module docstring's first sentence to: `... $DRYAS_DATA_ROOT (default ~/.dryas; <copy>/state in a repo copy made by dryas cloud).`

- [ ] **Step 5: Run** everything in Done. Every existing `paths`, `providers` and `gate` test passes unchanged.
- [ ] **Step 6: Commit** `git add claude/jev/providers.py claude/jev/paths.py claude/jev/tests/test_cloud_judge.py claude/jev/tests/test_paths_cloud.py`, then `git commit -m "feat(jev): local judge by default in cloud sessions; expand a literal CLAUDE_PROJECT_DIR"`.

---

## Task 3: The hook entry of a repo copy
Goal: `claude/jev/cloud_hook.py` runs any hook script of a repo copy with `CLAUDE_PLUGIN_ROOT`, `DRYAS_DATA_ROOT` and `DRYAS_NOTES_DIR` pointed at the copy, stays quiet where the plugin's hooks already run, and asks instead of failing on an internal error.
Scope:
- claude/jev/cloud_hook.py
- claude/jev/tests/test_cloud_hook.py
Done:
- `python3 -m pytest -q claude/jev/tests/test_cloud_hook.py install/tests/test_portability.py` passes (run it after the commit: the portability test scans tracked files)
- `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: claude/jev/tests/test_cloud_hook.py :: CloudHookTest :: test_env_points_at_the_copy

**Interfaces:**
- Produces: the command line `"${DRYAS_PY:-python3}" -X utf8 "$CLAUDE_PROJECT_DIR/.dryas/jev/cloud_hook.py" <script.py> [args...]` (Task 7 writes it into `.claude/settings.json`). It also produces `cloud_hook.wanted() -> bool`, `cloud_hook.remote() -> bool`, `cloud_hook.ASK` (the PreToolUse ask output) and `cloud_hook.main(argv) -> int`.
- Behaviour: `<script.py>` must be a file name beside `cloud_hook.py`, other than `cloud_hook.py` itself. It runs in-process (`runpy`) with `sys.argv = [<script path>, *args]`. The script's own exit code is kept.

- [ ] **Step 1: Write the failing test** `claude/jev/tests/test_cloud_hook.py`:

```python
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

JEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = ("import json, os, sys\n"
         "keys = ('CLAUDE_PLUGIN_ROOT', 'DRYAS_DATA_ROOT', 'DRYAS_NOTES_DIR', 'PYTHONDONTWRITEBYTECODE')\n"
         "print(json.dumps(dict(argv=sys.argv[1:], **{k: os.environ.get(k) for k in keys})))\n")


class CloudHookTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.copy = os.path.join(self.base, "repo", ".dryas")
        self.jev = os.path.join(self.copy, "jev")
        os.makedirs(self.jev)
        shutil.copy(os.path.join(JEV, "cloud_hook.py"), self.jev)
        self.home = os.path.join(self.base, "home")
        os.makedirs(self.home)

    def put(self, name, code):
        with open(os.path.join(self.jev, name), "w", encoding="utf-8") as f:
            f.write(code)

    def run_hook(self, *args, **env):
        e = {"PATH": os.environ.get("PATH", ""), "HOME": self.home, "USERPROFILE": self.home,
             "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
        e.update(env)
        p = subprocess.run([sys.executable, os.path.join(self.jev, "cloud_hook.py")] + list(args), input="{}",
                           capture_output=True, text=True, env=e, timeout=60)
        return p.returncode, p.stdout

    def test_env_points_at_the_copy(self):
        self.put("probe.py", PROBE)
        rc, out = self.run_hook("probe.py", "pretool", "x", CLAUDE_CODE_REMOTE="true", DRYAS_DATA_ROOT="elsewhere")
        self.assertEqual(rc, 0)
        got = json.loads(out)
        self.assertEqual(got["CLAUDE_PLUGIN_ROOT"], self.copy)
        self.assertEqual(got["DRYAS_DATA_ROOT"], os.path.join(self.copy, "state"))
        self.assertEqual(got["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertIsNone(got["DRYAS_NOTES_DIR"])
        self.assertEqual(got["argv"], ["pretool", "x"])
        self.assertTrue(os.path.isdir(os.path.join(self.copy, "state")))

    def test_notes_dir_is_set_when_the_repo_keeps_notes(self):
        os.makedirs(os.path.join(self.copy, "memory", "notes"))
        self.put("probe.py", PROBE)
        rc, out = self.run_hook("probe.py", CLAUDE_CODE_REMOTE="true")
        self.assertEqual(json.loads(out)["DRYAS_NOTES_DIR"], os.path.join(self.copy, "memory", "notes"))

    def test_quiet_on_a_machine_with_dryas_installed(self):
        os.makedirs(os.path.join(self.home, ".dryas"))
        open(os.path.join(self.home, ".dryas", "chain.local.json"), "w").close()
        self.put("probe.py", PROBE)
        self.assertEqual(self.run_hook("probe.py"), (0, ""))
        self.assertFalse(os.path.exists(os.path.join(self.copy, "state")))
        self.assertNotEqual(self.run_hook("probe.py", DRYAS_CLOUD_HOOKS="1")[1], "")
        self.assertNotEqual(self.run_hook("probe.py", CLAUDE_CODE_REMOTE="true")[1], "")
        self.assertEqual(self.run_hook("probe.py", CLAUDE_CODE_REMOTE="true", DRYAS_CLOUD_HOOKS="0"), (0, ""))

    def test_internal_error_asks_for_pretool(self):
        self.put("chain.py", "raise RuntimeError('boom')\n")
        rc, out = self.run_hook("chain.py", "pretool", CLAUDE_CODE_REMOTE="true")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertEqual(self.run_hook("chain.py", "session-end", CLAUDE_CODE_REMOTE="true"), (0, ""))

    def test_only_scripts_beside_it_run(self):
        for name in ("../x.py", "missing.py", "cloud_hook.py", "chain"):
            self.assertEqual(self.run_hook(name, "pretool", CLAUDE_CODE_REMOTE="true"), (0, ""), name)

    def test_exit_code_of_the_script_is_kept(self):
        self.put("probe.py", "import sys\nsys.exit(3)\n")
        self.assertEqual(self.run_hook("probe.py", CLAUDE_CODE_REMOTE="true")[0], 3)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python3 -m pytest -q claude/jev/tests/test_cloud_hook.py`. Expected: FAIL (`cloud_hook.py` does not exist, so `shutil.copy` raises `FileNotFoundError`).

- [ ] **Step 3: Implement** `claude/jev/cloud_hook.py`:

```python
#!/usr/bin/env python3
"""Hook entry of a repo copy of Dryas (`dryas cloud`, owned core E). The repo's .claude/settings.json runs

  "${DRYAS_PY:-python3}" -X utf8 "$CLAUDE_PROJECT_DIR/.dryas/jev/cloud_hook.py" <script.py> [args...]

for every hook the plugin's hooks.json has (rules_inject.py aside: the CLAUDE.md block carries the rules). It points
CLAUDE_PLUGIN_ROOT at the copy and DRYAS_DATA_ROOT at <copy>/state, sets DRYAS_NOTES_DIR when the repo keeps memory
notes (<copy>/memory/notes), turns off bytecode files, then runs jev/<script.py> in this process with its arguments.

Outside a cloud session (CLAUDE_CODE_REMOTE is not true), on a machine where Dryas is installed for the user
(~/.dryas/chain.local.json exists), the plugin's own hooks already run, so this entry does nothing.
DRYAS_CLOUD_HOOKS=1 forces it on, DRYAS_CLOUD_HOOKS=0 off.

It is the only place a hook gets these variables: the copy puts no env into .claude/settings.json, where it would
also reach the plugin's own hooks on a machine with the plugin installed.
It never fails a tool call: an internal error exits 0, and for the PreToolUse chain it answers "ask".
The script's own exit code is kept (the plugin runs the same script directly)."""
import json
import os
import runpy
import sys
from typing import List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASK = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                              "permissionDecisionReason": "[dryas-cloud] the Dryas hook chain could not run; "
                                                          "confirm this call yourself"}}


def remote() -> bool:
    return os.environ.get("CLAUDE_CODE_REMOTE", "").strip().lower() == "true"


def wanted() -> bool:
    force = os.environ.get("DRYAS_CLOUD_HOOKS", "").strip()
    if force in ("0", "1"):
        return force == "1"
    if remote():
        return True
    return not os.path.isfile(os.path.join(os.path.expanduser("~"), ".dryas", "chain.local.json"))


def _script(name: str) -> str:
    if not name.endswith(".py") or os.path.basename(name) != name or name == os.path.basename(__file__):
        raise ValueError("not a hook script: %r" % name[:64])
    path = os.path.join(HERE, name)
    if not os.path.isfile(path):
        raise ValueError("no such hook script: %r" % name[:64])
    return path


def main(argv: List[str]) -> int:
    name, args = (argv[1] if len(argv) > 1 else ""), argv[2:]
    pretool = name == "chain.py" and args[:1] == ["pretool"]
    try:
        if not wanted():
            return 0
        path = _script(name)
        os.environ["CLAUDE_PLUGIN_ROOT"] = ROOT
        os.environ["DRYAS_DATA_ROOT"] = os.path.join(ROOT, "state")
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"  # inherited by the chain's stage processes
        sys.dont_write_bytecode = True
        notes = os.path.join(ROOT, "memory", "notes")
        if os.path.isdir(notes):
            os.environ["DRYAS_NOTES_DIR"] = notes
        os.makedirs(os.environ["DRYAS_DATA_ROOT"], exist_ok=True)
        sys.argv = [path] + args
        sys.path.insert(0, HERE)
        runpy.run_path(path, run_name="__main__")
        return 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0
    except Exception:
        if pretool:
            sys.stdout.write(json.dumps(ASK))
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Run** `python3 -m pytest -q claude/jev/tests/test_cloud_hook.py`. Expected: 6 passed.
- [ ] **Step 5: Commit** `git add claude/jev/cloud_hook.py claude/jev/tests/test_cloud_hook.py`, then `git commit -m "feat(jev): cloud_hook.py, the hook entry of a repo copy"`.

---

## Task 4: Memory notes for cloud sessions (opt-in)
Goal: at session end, `memnotes.py export` writes the session's lessons, decisions, task outcomes and `/tune` per-task rows as one short redacted note into the repo's notes folder (only when it exists), which the next session start indexes through B's `memhooks.index_notes`.
Scope:
- claude/jev/memnotes.py
- claude/jev/chain.json
- claude/jev/tests/test_memnotes.py
Done:
- `python3 -m pytest -q claude/jev/tests/test_memnotes.py claude/jev/tests/test_memhooks.py claude/jev/tests/test_chain.py claude/jev/tests/test_chain_local.py claude/jev/tests/test_chain_observe.py` passes
- `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: claude/jev/tests/test_memnotes.py :: MemNotesTest :: test_export_writes_a_redacted_note

**Interfaces:**
- Consumes: `memdb.connect(path=None, busy_ms=...)` (rows are `sqlite3.Row`), `memdb.tx(conn)`, `memstore.store(conn, ns, title, body, kind="outcome", ..., created=None, check_content=True)`, the `sessions(id, ns, started, ended, summary)`, `tasks(task_id, ns, title, tier_start, tier_end, outcome, started, ended, ...)` and `memory(...)` tables, `memhooks.index_notes(conn, ns, d)`, `projns.project_ns(start)`, `tune.read(name)`, `tune_tasks.rows(gate, dispatch, esc, mcp)` (row keys `start_tier`, `final_tier`, `tokens`, `duration_ms`, `escalated`, `score`, `first_ts`), `redact.redact`, `jevlog.append`, `paths.plugin_root()`.
- Produces: `memnotes.notes_dir() -> str` (`$DRYAS_NOTES_DIR`, else `<plugin root>/memory/notes`), `memnotes.safe_id(sid) -> str`, `memnotes.session_since(conn, sid) -> float`, `memnotes.recent_rows(rows, since) -> dict`, `memnotes.render(conn, ns, sid, since, rows, now) -> str` (`""` when there is nothing to keep), `memnotes.export(conn, event, now=None) -> Optional[str]` (the note path) and `memnotes.main(argv=None) -> int` (always 0).
- Produces the chain stage, last in `session-end`, after D's `mem-session-end`: `{"name": "mem-notes", "component": "core", "cmd": ["$PY", "-X", "utf8", "$CD/jev/memnotes.py", "export"], "requires_path": "$CD/memory/notes", "observe": true, "timeout": 2}`.
- Note file: `<notes dir>/<YYYY-MM-DD>-<safe session id>.md`, front matter `name: Dryas session <date> <id>`, at most 16 KB.

- [ ] **Step 1: Write the failing test** `claude/jev/tests/test_memnotes.py`:

```python
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

JEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JEV)
import jevlog
import memdb
import memhooks
import memnotes
import memstore


class MemNotesTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.notes = os.path.join(self.d, "notes")
        os.makedirs(self.notes)
        self.cwd = os.path.join(self.d, "demo")
        os.makedirs(self.cwd)
        p = mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": self.d, "DRYAS_DB": os.path.join(self.d, "d.db"),
                                         "JEV_LOG_DIR": os.path.join(self.d, "logs"), "DRYAS_NOTES_DIR": self.notes,
                                         "JEV_SESSION_ID": "", "JEV_CWD": ""})
        p.start()
        self.addCleanup(p.stop)
        self.conn = memdb.connect()
        self.addCleanup(self.conn.close)
        self.ns = "demo"

    def start(self, sid="s1", ago=60.0):
        with memdb.tx(self.conn):
            self.conn.execute("INSERT INTO sessions (id, ns, started) VALUES (?, ?, ?)", (sid, self.ns, time.time() - ago))

    def export(self, sid="s1"):
        return memnotes.export(self.conn, {"session_id": sid, "cwd": self.cwd})

    def test_export_writes_a_redacted_note(self):
        self.start()
        memstore.store(self.conn, self.ns, "Retry flaky calls", "Use the retry helper. password = hunter2hunter2",
                       check_content=False)
        with memdb.tx(self.conn):
            self.conn.execute("INSERT INTO tasks (task_id, ns, title, tier_start, tier_end, outcome, started, ended) "
                              "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                              ("feat:1", self.ns, "Add the parser", "haiku", "sonnet", "merged", time.time() - 30,
                               time.time()))
        jevlog.append("dispatch", dict(task="feat:1", role="coder", tier="haiku", attempt=1, tokens=1200))
        path = self.export()
        self.assertEqual(os.path.dirname(path), self.notes)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("---\nname: Dryas session "))
        for want in ("## Lessons and decisions", "Retry flaky calls", "## Tasks",
                     "feat:1 Add the parser: merged (haiku -> sonnet)", "## Task numbers (/tune)", "start_tier=haiku",
                     "tokens=1200.0"):
            self.assertIn(want, text)
        self.assertNotIn("hunter2hunter2", text)

    def test_nothing_to_keep_writes_nothing(self):
        self.start()
        self.assertIsNone(self.export())
        self.assertEqual(os.listdir(self.notes), [])

    def test_earlier_sessions_are_left_out(self):
        memstore.store(self.conn, self.ns, "Old lesson", "From an earlier session.", created=time.time() - 3600)
        self.start()
        memstore.store(self.conn, self.ns, "New lesson", "From this session.")
        with open(self.export(), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("New lesson", text)
        self.assertNotIn("Old lesson", text)

    def test_session_id_cannot_escape_the_notes_dir(self):
        self.start("../../x y")
        memstore.store(self.conn, self.ns, "Lesson", "Body.")
        path = self.export("../../x y")
        self.assertEqual(os.path.dirname(path), self.notes)
        self.assertTrue(os.path.basename(path).endswith("-xy.md"), path)

    def test_note_is_indexed_by_the_next_session_start(self):
        self.start()
        memstore.store(self.conn, self.ns, "Retry flaky calls", "Use the retry helper.")
        self.export()
        self.assertEqual(memhooks.index_notes(self.conn, self.ns, self.notes)["indexed"], 1)
        row = self.conn.execute("SELECT title, body FROM memory WHERE kind = 'note'").fetchone()
        self.assertTrue(row["title"].startswith("Dryas session "))
        self.assertIn("Retry flaky calls", row["body"])

    def test_main_without_notes_dir_does_nothing(self):
        env = dict(os.environ, DRYAS_NOTES_DIR=os.path.join(self.d, "absent"), DRYAS_DB=os.path.join(self.d, "o.db"))
        p = subprocess.run([sys.executable, os.path.join(JEV, "memnotes.py"), "export"], input='{"session_id": "s1"}',
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        self.assertFalse(os.path.exists(os.path.join(self.d, "o.db")))


class ChainStageTest(unittest.TestCase):
    def test_mem_notes_stage_follows_the_session_summary(self):
        with open(os.path.join(JEV, "chain.json"), encoding="utf-8") as f:
            stages = json.load(f)["session-end"]
        names = [s["name"] for s in stages]
        self.assertGreater(names.index("mem-notes"), names.index("mem-session-end"))
        st = stages[names.index("mem-notes")]
        self.assertEqual(st["cmd"], ["$PY", "-X", "utf8", "$CD/jev/memnotes.py", "export"])
        self.assertEqual(st["requires_path"], "$CD/memory/notes")
        self.assertEqual((st["component"], st["observe"], st["timeout"]), ("core", True, 2))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python3 -m pytest -q claude/jev/tests/test_memnotes.py`. Expected: FAIL (`ModuleNotFoundError: memnotes`).

- [ ] **Step 3: Implement** `claude/jev/memnotes.py`:

```python
#!/usr/bin/env python3
"""Memory notes for cloud sessions (owned core E; opt-in with `dryas cloud init --persist-memory`).

  memnotes.py export   SessionEnd stage `mem-notes`: this session's lessons and decisions, task outcomes and
                       /tune per-task rows as one short markdown note; its free text is redacted with redact.py

The note goes to $DRYAS_NOTES_DIR (set by cloud_hook.py), else <plugin root>/memory/notes, and only when that folder
exists; chain.json runs the stage only when $CD/memory/notes exists, so a plugin install never writes one. The notes
are committed with the work and reviewed in pull requests; the next session start indexes them as memory notes
(memhooks.py session-start reads DRYAS_NOTES_DIR). Observe-only: prints nothing, exits 0, stays inside the 2 s hook
budget; a failure is one memory.jsonl line."""
import datetime
import json
import os
import re
import sys
import threading
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jevlog
import memdb
import paths
import projns
import redact
import tune
import tune_tasks

BUDGET_S = 1.8
BUSY_MS = 500
MAX_BYTES = 16 * 1024
MAX_ITEMS = 20
KINDS = ("outcome", "fact", "retro")
ROW_FIELDS = ("start_tier", "final_tier", "tokens", "duration_ms", "escalated", "score")
STDIN_MAX = 1024 * 1024
TS = "%Y-%m-%dT%H:%M:%S%z"  # jevlog's record time


def notes_dir() -> str:
    return os.environ.get("DRYAS_NOTES_DIR") or os.path.join(paths.plugin_root(), "memory", "notes")


def safe_id(sid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", sid)[:12] or "session"


def _line(v: Any, cap: int = 240) -> str:
    """One redacted line of free text (titles, bodies, the summary); numbers are written as they are."""
    return " ".join(redact.redact(str(v or "")).split())[:cap]


def session_since(conn, sid: str) -> float:
    r = conn.execute("SELECT started FROM sessions WHERE id = ?", (sid,)).fetchone()
    return float(r["started"]) if r and r["started"] else 0.0


def recent_rows(rows: Dict[str, Dict[str, Any]], since: float) -> Dict[str, Dict[str, Any]]:
    """The /tune per-task rows of tasks first dispatched in this session."""
    out = {}
    for task, row in rows.items():
        try:
            t = datetime.datetime.strptime(str(row.get("first_ts")), TS).timestamp()
        except ValueError:
            continue
        if t >= since - 1:
            out[task] = row
    return out


def render(conn, ns: str, sid: str, since: float, rows: Dict[str, Dict[str, Any]], now: float) -> str:
    """The note; "" when the session left nothing worth keeping."""
    mems = conn.execute("SELECT kind, title, body FROM memory WHERE ns = ? AND source = 'dryas' AND kind IN (?, ?, ?)"
                        " AND created >= ? ORDER BY created LIMIT ?", (ns,) + KINDS + (since, MAX_ITEMS)).fetchall()
    tasks = conn.execute("SELECT task_id, title, tier_start, tier_end, outcome FROM tasks WHERE ns = ? AND ended >= ?"
                         " ORDER BY ended LIMIT ?", (ns, since, MAX_ITEMS)).fetchall()
    if not (mems or tasks or rows):
        return ""
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    out: List[str] = ["---", "name: Dryas session %s %s" % (day, safe_id(sid)), "---", "", "# Dryas session " + day, ""]
    summary = conn.execute("SELECT summary FROM sessions WHERE id = ?", (sid,)).fetchone()
    if summary and summary["summary"]:
        out += [_line(summary["summary"]), ""]
    if mems:
        out += ["## Lessons and decisions", ""]
        out += ["- %s: %s. %s" % (m["kind"], _line(m["title"], 120), _line(m["body"])) for m in mems] + [""]
    if tasks:
        out += ["## Tasks", ""]
        out += ["- %s %s: %s (%s -> %s)" % (t["task_id"], _line(t["title"], 120), t["outcome"] or "open",
                                            t["tier_start"] or "?", t["tier_end"] or "?") for t in tasks] + [""]
    if rows:
        out += ["## Task numbers (/tune)", ""]
        for task in sorted(rows)[:MAX_ITEMS]:
            vals = ["%s=%s" % (f, rows[task][f]) for f in ROW_FIELDS if rows[task].get(f) is not None]
            out.append("- %s: %s" % (_line(task, 80), ", ".join(vals)))
        out.append("")
    data = "\n".join(out).encode("utf-8")[:MAX_BYTES]
    return data.decode("utf-8", "ignore").rstrip("\n") + "\n"


def export(conn, event: Dict[str, Any], now: Optional[float] = None) -> Optional[str]:
    """Write this session's note. Its path, or None when there is no notes folder or nothing to keep."""
    d = notes_dir()
    if not os.path.isdir(d):
        return None
    now = time.time() if now is None else now
    cwd = str(event.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    sid = str(event.get("session_id") or "unknown")
    since = session_since(conn, sid)
    rows = recent_rows(tune_tasks.rows(tune.read("gate"), tune.read("dispatch"), tune.read("escalations"),
                                       tune.read("mcp")), since)
    text = render(conn, projns.project_ns(cwd), sid, since, rows, now)
    if not text:
        return None
    path = os.path.join(d, "%s-%s.md" % (time.strftime("%Y-%m-%d", time.localtime(now)), safe_id(sid)))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def _watchdog() -> threading.Timer:
    def fire() -> None:
        jevlog.append("memory", dict(stage="mem-notes", error="Timeout", detail=""))
        os._exit(0)
    t = threading.Timer(BUDGET_S, fire)
    t.daemon = True
    t.start()
    return t


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    dog = _watchdog()
    try:
        if argv[:1] != ["export"]:
            raise ValueError("usage: memnotes.py export")
        event = json.loads(sys.stdin.buffer.read(STDIN_MAX).decode("utf-8", "replace") or "{}")
        if not isinstance(event, dict):
            raise ValueError("hook event is not an object")
        if os.path.isdir(notes_dir()):
            conn = memdb.connect(busy_ms=BUSY_MS)
            try:
                export(conn, event)
            finally:
                conn.close()
    except Exception as e:
        jevlog.append("memory", dict(stage="mem-notes", error=type(e).__name__, detail=str(e)[:200]))
    dog.cancel()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Add the chain stage.** In `claude/jev/chain.json`, append this object as the last element of the `"session-end"` list, after D's `mem-session-end`, keeping the file's one-object-per-line style:

```json
{"name": "mem-notes", "component": "core", "cmd": ["$PY", "-X", "utf8", "$CD/jev/memnotes.py", "export"], "requires_path": "$CD/memory/notes", "observe": true, "timeout": 2}
```

Component `core`, not `memory`: D's `test_chain_observe.py::ShippedChainTest::test_memory_stages_shipped` pins the exact set of `memory` stages. `requires_path` keeps the stage a no-op in the plugin, whose `$CD` has no `memory/notes`, and in a copy made without `--persist-memory`.

- [ ] **Step 5: Run** everything in Done. Expected: 7 new tests pass, and D's chain tests pass unchanged.
- [ ] **Step 6: Commit** `git add claude/jev/memnotes.py claude/jev/chain.json claude/jev/tests/test_memnotes.py`, then `git commit -m "feat(memory): opt-in memory notes for cloud sessions (mem-notes stage)"`.

---

## Task 5: Check a repo copy against its manifest
Goal: `claude/jev/cloud_check.py` reports, as functions and as a CLI that also runs inside a cloud session or CI, drift, Mac and plugin paths, non-stdlib imports, missing licences or NOTICE lines, a missing ignore line or rules block and a version mismatch, and the one Mac path in `handoff.py`'s docstring goes.
Scope:
- claude/jev/cloud_check.py
- claude/jev/handoff.py
- claude/jev/tests/test_cloud_check.py
Done:
- `python3 -m pytest -q claude/jev/tests/test_cloud_check.py claude/jev/tests/test_handoff.py` passes
- `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: claude/jev/tests/test_cloud_check.py :: CheckTest :: test_intact_copy_has_no_problems

**Interfaces:**
- Produces constants: `COPY = ".dryas"`, `MANIFEST = ".dryas/manifest.json"`, `NOTICE = ".dryas/NOTICE"`, `VERSION = ".dryas/VERSION"`, `START`/`END` (the `claude_md_block` markers), `MAC_PATH`, `HOME_STATE`, `PLUGIN_ROOT = "${CLAUDE_PLUGIN_ROOT}"`.
- Produces: `sha256(data: bytes) -> str`, `file_sha(path: str) -> Optional[str]`, `files_hash(shas: Dict[str, str]) -> str`, `load_manifest(repo: str) -> dict` (raises `OSError` when missing, `ValueError` when malformed), `drift(repo, files) -> {"missing": [...], "changed": [...]}`, `scan_text(rel, text) -> List[str]`, `is_stdlib(name) -> bool`, `nonstdlib_imports(text, siblings) -> List[str]`, `siblings(path) -> List[str]`, `own_version() -> Optional[str]`, `check(repo: str, version: Optional[str] = None) -> List[str]` and `main(argv=None) -> int` (1 when there are problems).
- Manifest shape, written by Task 9:
  - `{"format": 1, "dryas": {"version", "commit", "files_hash"}, "options": {...}, "files": {rel: {...}}, "config": {...}}`;
  - each file record has `sha256`, `source`, `group` (`dryas`, `design` or `own`), `version`, `licence`, `licence_file` and `notice`;
  - `config` has `settings: {added, original}`, `mcp: {entry, original}`, `claude_md: {...}` and `gitignore: {added, sep, created}`.

- [ ] **Step 1: Write the failing test** `claude/jev/tests/test_cloud_check.py`:

```python
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

JEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JEV)
import cloud_check as cc

LIC = ".dryas/licenses/LICENSE-dryas"
NOTE = "- Dryas 9.9.9 (MIT): " + LIC


class Copy:
    """A small repo copy written by hand: the shape `dryas cloud init` leaves."""

    def __init__(self, root):
        self.root = root
        self.files = {}

    def put(self, rel, text, **meta):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        e = dict(sha256=cc.sha256(text.encode("utf-8")), source="test", group="dryas", version="9.9.9", licence="MIT",
                 licence_file=LIC, notice=NOTE)
        e.update(meta)
        self.files[rel] = e

    def save(self, version="9.9.9", config=None):
        m = dict(format=1, dryas=dict(version=version, commit="c0ffee", files_hash="x"), options={}, files=self.files,
                 config=config or {})
        with open(os.path.join(self.root, cc.MANIFEST), "w", encoding="utf-8") as f:
            json.dump(m, f)


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.repo, True)
        self.copy = Copy(self.repo)
        self.copy.put(LIC, "MIT License\n")
        self.copy.put(cc.NOTICE, "Dryas 9.9.9, copied by dryas cloud.\n" + NOTE + "\n")
        self.copy.put(".dryas/jev/tool.py", "import json\nimport helper\n")
        self.copy.put(".dryas/jev/helper.py", "import os\n")
        self.copy.put(".claude/commands/tune.md", 'Run `".dryas/bin/dryas-py" ".dryas/jev/tune.py" report`.\n')
        self.copy.save()
        self.write(".gitignore", "node_modules/\n.dryas/state/\n")
        self.write("CLAUDE.md", "# Repo\n\n<!-- dryas:start -->\nDryas rules\n<!-- dryas:end -->\n")

    def write(self, rel, text):
        with open(os.path.join(self.repo, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def test_intact_copy_has_no_problems(self):
        self.assertEqual(cc.check(self.repo, "9.9.9"), [])

    def test_hand_edit_and_missing_file_are_drift(self):
        self.write(".claude/commands/tune.md", "changed\n")
        os.remove(os.path.join(self.repo, ".dryas/jev/helper.py"))
        probs = cc.check(self.repo)
        self.assertIn("drift (hand-edited): .claude/commands/tune.md", probs)
        self.assertIn("missing: .dryas/jev/helper.py", probs)

    def test_paths_that_only_work_on_the_mac(self):
        self.copy.put(".claude/skills/x/SKILL.md", "see /Users/someone/notes, ~/.dryas/jev/logs, ${CLAUDE_PLUGIN_ROOT}/jev\n")
        self.copy.put(".dryas/jev/doc.md", "default ~/.dryas and ${CLAUDE_PLUGIN_ROOT}\n")
        self.copy.save()
        probs = cc.check(self.repo)
        skill = [p for p in probs if p.startswith(".claude/skills/x/SKILL.md:1:")]
        self.assertEqual(len(skill), 3, probs)
        self.assertTrue(any("absolute Mac path" in p for p in skill))
        self.assertFalse(any(p.startswith(".dryas/jev/doc.md") for p in probs))

    def test_non_stdlib_import(self):
        self.copy.put(".dryas/jev/needs.py", "import json\nimport requests\n")
        self.copy.save()
        self.assertIn(".dryas/jev/needs.py: imports non-stdlib requests", cc.check(self.repo))

    def test_licence_and_notice(self):
        self.copy.put(".claude/skills/d/SKILL.md", "d\n", group="design", licence="Apache-2.0",
                      licence_file=".dryas/licenses/d-LICENSE", notice="- d 1.0 (Apache-2.0): .dryas/licenses/d-LICENSE")
        self.copy.save()
        probs = cc.check(self.repo)
        self.assertIn(".claude/skills/d/SKILL.md: licence file .dryas/licenses/d-LICENSE is missing", probs)
        self.assertIn(".claude/skills/d/SKILL.md: no NOTICE line '- d 1.0 (Apache-2.0): .dryas/licenses/d-LICENSE'",
                      probs)

    def test_repo_level_problems(self):
        self.write(".gitignore", "node_modules/\n")
        self.write("CLAUDE.md", "# Repo\n")
        probs = cc.check(self.repo, "9.9.10")
        self.assertIn(".gitignore: .dryas/state/ is not ignored", probs)
        self.assertIn("CLAUDE.md: the Dryas rules block is missing", probs)
        self.assertIn("copy is Dryas 9.9.9, this Dryas is 9.9.10: run dryas cloud update", probs)

    def test_home_path_in_dryas_config_entries(self):
        self.copy.save(config={"settings": {"added": {"env": {"X": "~/x"}}}, "mcp": {"entry": {"args": ["/Volumes/d"]}}})
        probs = cc.check(self.repo)
        self.assertIn(".claude/settings.json: a Dryas entry names a home or Mac path", probs)
        self.assertIn(".mcp.json: a Dryas entry names a home or Mac path", probs)

    def test_dryas_env_in_settings_is_a_problem(self):
        self.copy.save(config={"settings": {"added": {"env": {"DRYAS_DATA_ROOT": "x"}}}})
        self.assertIn(".claude/settings.json: Dryas entries set env (hooks get it from cloud_hook.py only)",
                      cc.check(self.repo))

    def test_no_copy(self):
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, True)
        self.assertEqual(cc.check(empty), ["no Dryas copy here (.dryas/manifest.json is missing); run dryas cloud init"])

    def test_cli_exit_codes(self):
        self.copy.save(version=cc.own_version() or "9.9.9")  # the CLI compares the copy with this Dryas's version
        cli = [sys.executable, os.path.join(JEV, "cloud_check.py"), "--repo", self.repo]
        p = subprocess.run(cli, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn("dryas cloud check: 0 problems", p.stdout)
        self.write(".claude/commands/tune.md", "changed\n")
        p = subprocess.run(cli, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 1)
        self.assertIn("drift (hand-edited): .claude/commands/tune.md", p.stdout)


class ScanTest(unittest.TestCase):
    def test_scan_rules(self):
        self.assertEqual(cc.scan_text("a/b.md", "src/Users/model.py, ~/project and ~/.config/git/ignore"), [])
        self.assertEqual(cc.scan_text(".dryas/jev/a.py", "p = '/Volumes/disk/x'"), [".dryas/jev/a.py:1: absolute Mac path"])

    def test_stdlib_detection(self):
        code = "import json, os.path\nfrom urllib import request\nfrom . import x\nimport helper\nimport numpy.linalg\n"
        self.assertEqual(cc.nonstdlib_imports(code, ["helper"]), ["numpy"])
        self.assertEqual(cc.nonstdlib_imports("def (:\n", []), ["<unparseable>"])
        for name in ("json", "sqlite3", "msvcrt", "fcntl", "__future__"):
            self.assertTrue(cc.is_stdlib(name), name)

    def test_files_hash_depends_on_path_and_content(self):
        a = cc.files_hash({"x": cc.sha256(b"1"), "y": cc.sha256(b"2")})
        self.assertEqual(a, cc.files_hash({"y": cc.sha256(b"2"), "x": cc.sha256(b"1")}))
        self.assertNotEqual(a, cc.files_hash({"x": cc.sha256(b"2"), "y": cc.sha256(b"1")}))

    def test_shipped_runtime_is_cloud_clean(self):
        """Everything dryas cloud copies from claude/jev and claude/pstack: no Mac path, stdlib only."""
        hits = []
        for base in ("jev", "pstack"):
            root = os.path.join(os.path.dirname(JEV), base)
            for d, dirs, files in os.walk(root):
                dirs[:] = [x for x in dirs if x not in ("tests", "__pycache__", "logs", "compact")]
                for f in files:
                    p = os.path.join(d, f)
                    rel = ".dryas/%s/%s" % (base, os.path.relpath(p, root).replace(os.sep, "/"))
                    try:
                        with open(p, encoding="utf-8") as fh:
                            text = fh.read()
                    except UnicodeDecodeError:
                        continue
                    hits += cc.scan_text(rel, text)
                    if f.endswith(".py"):
                        hits += ["%s: %s" % (rel, m) for m in cc.nonstdlib_imports(text, cc.siblings(p))]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python3 -m pytest -q claude/jev/tests/test_cloud_check.py`. Expected: FAIL (`ModuleNotFoundError: cloud_check`).

- [ ] **Step 3: Implement** `claude/jev/cloud_check.py`:

```python
#!/usr/bin/env python3
"""Check a repo copy of Dryas (`dryas cloud`, owned core E) against its manifest. Runs from the copy
(.dryas/jev/cloud_check.py, also inside a cloud session or a repo's CI) and from a Dryas checkout
(tools/dryas_cloud.py check, which adds the comparison with the checkout's files).

  cloud_check.py [--repo PATH]   one line per problem and exit 1; exit 0 when the copy is intact

Problems:
- a manifest file missing or hand-edited (drift);
- an absolute Mac path (a path under /Users or /Volumes) in any copied file;
- ~/.dryas or ${CLAUDE_PLUGIN_ROOT} in a copied file outside .dryas/;
- a home or Mac path in Dryas's .claude/settings.json or .mcp.json entries, or any env in its settings.json entries;
- a copied Python file that imports a non-stdlib module;
- a file without its licence file or NOTICE line;
- .dryas/state/ not git-ignored, or the CLAUDE.md block missing;
- when this Dryas knows its own version (plugin or checkout), a copy made by another version."""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
import sys
import sysconfig
from typing import Any, Dict, Iterable, List, Optional, Set

COPY = ".dryas"
MANIFEST = COPY + "/manifest.json"
NOTICE = COPY + "/NOTICE"
VERSION = COPY + "/VERSION"
START, END = "<!-- dryas:start -->", "<!-- dryas:end -->"
MAC_PATH = re.compile(r"(?<![\w.~-])/(?:Users|Volumes)/")
HOME_STATE = re.compile(r"~/\.dryas(?![\w-])")
PLUGIN_ROOT = "${CLAUDE_PLUGIN_ROOT}"
PLATFORM_STDLIB = frozenset(("msvcrt", "winreg", "_winapi", "winsound", "nt", "posix", "pwd", "grp", "fcntl",
                             "termios", "resource", "_overlapped", "__future__"))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            return sha256(f.read())
    except OSError:
        return None


def files_hash(shas: Dict[str, str]) -> str:
    """One hash over every copied file's path and content (for VERSION and the manifest)."""
    return sha256("".join("%s %s\n" % (k, shas[k]) for k in sorted(shas)).encode("utf-8"))


def load_manifest(repo: str) -> Dict[str, Any]:
    with open(os.path.join(repo, MANIFEST), encoding="utf-8") as f:
        m = json.load(f)
    if not isinstance(m, dict) or not isinstance(m.get("files"), dict):
        raise ValueError('%s has no "files" object' % MANIFEST)
    return m


def drift(repo: str, files: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {"missing": [], "changed": []}
    for rel in sorted(files):
        cur = file_sha(os.path.join(repo, rel))
        if cur is None:
            out["missing"].append(rel)
        elif cur != files[rel].get("sha256"):
            out["changed"].append(rel)
    return out


def scan_text(rel: str, text: str) -> List[str]:
    out = []
    inside = rel.startswith(COPY + "/")
    for n, line in enumerate(text.splitlines(), 1):
        if MAC_PATH.search(line):
            out.append("%s:%d: absolute Mac path" % (rel, n))
        if not inside and HOME_STATE.search(line):
            out.append("%s:%d: ~/.dryas (a repo copy keeps its state in .dryas/state/)" % (rel, n))
        if not inside and PLUGIN_ROOT in line:
            out.append("%s:%d: ${CLAUDE_PLUGIN_ROOT} (a repo copy has no plugin)" % (rel, n))
    return out


def is_stdlib(name: str) -> bool:
    if name in sys.builtin_module_names or name in PLATFORM_STDLIB:
        return True
    names = getattr(sys, "stdlib_module_names", None)
    if names is not None:
        return name in names
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return False
    if spec is None or spec.origin is None:
        return False
    if spec.origin in ("built-in", "frozen"):
        return True
    std = os.path.realpath(sysconfig.get_paths()["stdlib"])
    origin = os.path.realpath(spec.origin)
    return origin.startswith(std + os.sep) and "site-packages" not in origin


def nonstdlib_imports(text: str, siblings_: Iterable[str]) -> List[str]:
    """Top-level modules a Python file imports that are neither stdlib nor a file beside it."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return ["<unparseable>"]
    local = set(siblings_)
    bad: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            mods = [node.module]
        else:
            continue
        for m in mods:
            top = m.split(".")[0]
            if top not in local and not is_stdlib(top):
                bad.add(top)
    return sorted(bad)


def siblings(path: str) -> List[str]:
    d = os.path.dirname(path)
    try:
        names = os.listdir(d)
    except OSError:
        return []
    return [n[:-3] if n.endswith(".py") else n for n in names if n.endswith(".py") or os.path.isdir(os.path.join(d, n))]


def _read(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def own_version() -> Optional[str]:
    """This Dryas's version when it runs from the plugin or a checkout (claude/.claude-plugin/plugin.json); None when it
    runs from a repo copy, which has no plugin manifest."""
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".claude-plugin", "plugin.json")
    try:
        with open(p, encoding="utf-8") as f:
            v = json.load(f).get("version")
        return v if isinstance(v, str) else None
    except (OSError, ValueError, AttributeError):
        return None


def check(repo: str, version: Optional[str] = None) -> List[str]:
    try:
        m = load_manifest(repo)
    except OSError:
        return ["no Dryas copy here (%s is missing); run dryas cloud init" % MANIFEST]
    except ValueError as e:
        return ["%s is unreadable (%s)" % (MANIFEST, e)]
    files = m["files"]
    d = drift(repo, files)
    probs = ["missing: %s" % r for r in d["missing"]] + ["drift (hand-edited): %s" % r for r in d["changed"]]
    notice = set((_read(os.path.join(repo, NOTICE)) or "").splitlines())
    for rel in sorted(files):
        e = files[rel] if isinstance(files[rel], dict) else {}
        path = os.path.join(repo, rel)
        text = _read(path)
        if text is not None:
            probs += scan_text(rel, text)
            if rel.endswith(".py"):
                bad = nonstdlib_imports(text, siblings(path))
                if bad:
                    probs.append("%s: imports non-stdlib %s" % (rel, ", ".join(bad)))
        if not e.get("licence"):
            probs.append("%s: no licence recorded" % rel)
        lic = e.get("licence_file")
        if e.get("group") != "own" and not (lic and os.path.isfile(os.path.join(repo, lic))):
            probs.append("%s: licence file %s is missing" % (rel, lic or "(none)"))
        if e.get("notice") and e["notice"] not in notice:
            probs.append("%s: no NOTICE line %r" % (rel, e["notice"]))
    cfg = m.get("config") if isinstance(m.get("config"), dict) else {}
    if ((cfg.get("settings") or {}).get("added") or {}).get("env"):
        probs.append(".claude/settings.json: Dryas entries set env (hooks get it from cloud_hook.py only)")
    for name, rel, key in (("settings", ".claude/settings.json", "added"), ("mcp", ".mcp.json", "entry")):
        blob = json.dumps((cfg.get(name) or {}).get(key) or {})
        if MAC_PATH.search(blob) or "~/" in blob:
            probs.append("%s: a Dryas entry names a home or Mac path" % rel)
    ignore = {line.strip() for line in (_read(os.path.join(repo, ".gitignore")) or "").splitlines()}
    if ".dryas/state/" not in ignore:
        probs.append(".gitignore: .dryas/state/ is not ignored")
    md = _read(os.path.join(repo, "CLAUDE.md")) or ""
    i, j = md.find(START), md.find(END)
    if not 0 <= i < j:
        probs.append("CLAUDE.md: the Dryas rules block is missing")
    else:
        probs += scan_text("CLAUDE.md", md[i:j])
    have = (m.get("dryas") or {}).get("version")
    if version and have != version:
        probs.append("copy is Dryas %s, this Dryas is %s: run dryas cloud update" % (have, version))
    return probs


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="dryas cloud check", description="Check this repo's Dryas copy.")
    ap.add_argument("--repo", default=".")
    a = ap.parse_args(argv)
    probs = check(os.path.abspath(a.repo), own_version())
    for p in probs:
        print(p)
    print("dryas cloud check: %d problem%s" % (len(probs), "" if len(probs) == 1 else "s"))
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Remove the one Mac path in the runtime.** In `claude/jev/handoff.py`, `encode_cwd`'s docstring, replace

```python
    Verified against <config dir>/projects: /Users/x/.claude -> -Users-x--claude."""
```

with

```python
    Verified against <config dir>/projects: /home/x/.claude -> -home-x--claude."""
```

The mapping is the same rule, and only the example changes. `test_shipped_runtime_is_cloud_clean` pins it.

- [ ] **Step 5: Run** everything in Done. Expected: 14 new tests pass. If `test_shipped_runtime_is_cloud_clean` names a D-added file with a Mac path or a non-stdlib import, stop and report it: that file belongs to D, and changing it is outside this Scope.
- [ ] **Step 6: Commit** `git add claude/jev/cloud_check.py claude/jev/handoff.py claude/jev/tests/test_cloud_check.py`, then `git commit -m "feat(cloud): cloud_check.py checks a repo copy against its manifest"`.

---

## Task 6: Text rewrites for copied files
Goal: `tools/cloud_text.py` turns Dryas markdown into what the repo copy ships (Claude blocks only, repo-relative paths, `.dryas/state` for `~/.dryas`, project names, `--prefix`), builds the `CLAUDE.md` rules block and rewrites design-skill paths.
Scope:
- tools/cloud_text.py
- install/tests/test_cloud_text.py
Done:
- `python3 -m pytest -q install/tests/test_cloud_text.py` passes
- `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: install/tests/test_cloud_text.py :: RewriteTest :: test_plugin_paths_become_repo_paths

**Interfaces:**
- Consumes: `render.gate_blocks(text, comps)`, `sync_codex_plugin.harness_blocks(text, harness)`.
- Produces:
  - `PLUGIN = "${CLAUDE_PLUGIN_ROOT}"`;
  - `Names(prefix, skills, commands, agents)` with `.prefix`, `.skills`, `.commands`, `.agents` and `.name(n) -> prefix + n`;
  - `rewrite(text, names, comps) -> str`;
  - `set_name(text, name) -> str` (front matter `name:`);
  - `claude_md_body(template, names, comps, version) -> str` (starts `Dryas <version> runs from this repo's \`.dryas/\` folder`);
  - `third_party(text, skills_rel, renames) -> str`.
- Rewrite order:
  1. drop Codex blocks, then gate the component blocks;
  2. `${CLAUDE_PLUGIN_ROOT}/{skills,agents,commands}/<n>` → `.claude/<kind>/<prefix><n>`;
  3. `${CLAUDE_PLUGIN_ROOT}` → `.dryas`;
  4. `~/.dryas/docs/` → `.dryas/docs/`, then `~/.dryas` → `.dryas/state`;
  5. `mcp__plugin_dryas_jev` → `mcp__jev`;
  6. `dryas:<known name>` → `<prefix><name>`. A `$` before it (Codex), a word or path character, or an unknown name stops the rewrite;
  7. with a prefix, `/<command>` → `/<prefix><command>`.

- [ ] **Step 1: Write the failing test** `install/tests/test_cloud_text.py`:

```python
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import cloud_text as ct

SKILLS = ("orchestrate", "brainstorm", "plan", "review-request", "review-receive", "tdd", "debug", "verify",
          "worktree", "interrogate")
COMMANDS = ("orchestrate", "wplan", "wreview", "commit", "tune", "handoff", "dryas-cloud")
COMPS = ("core", "jev", "memory", "pstack-picks")
NM = ct.Names("", SKILLS, COMMANDS, ("executor",))
PX = ct.Names("x-", SKILLS, COMMANDS, ("executor",))


class RewriteTest(unittest.TestCase):
    def test_plugin_paths_become_repo_paths(self):
        src = ('"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/tune.py" report; read '
               '`${CLAUDE_PLUGIN_ROOT}/skills/plan/reference.md` and `${CLAUDE_PLUGIN_ROOT}/pstack/cleanup.md`')
        self.assertEqual(ct.rewrite(src, NM, COMPS),
                         '".dryas/bin/dryas-py" ".dryas/jev/tune.py" report; read `.claude/skills/plan/reference.md` '
                         'and `.dryas/pstack/cleanup.md`')
        self.assertIn("`.claude/skills/x-plan/reference.md`", ct.rewrite(src, PX, COMPS))

    def test_home_state_moves_into_the_repo(self):
        src = "Read(~/.dryas/jev/thresholds.json) ~/.dryas/docs/dryas-workflow.md ~/.dryas ~/.dryas-old ~/project"
        self.assertEqual(ct.rewrite(src, NM, COMPS),
                         "Read(.dryas/state/jev/thresholds.json) .dryas/docs/dryas-workflow.md .dryas/state "
                         "~/.dryas-old ~/project")

    def test_plugin_names_become_project_names(self):
        src = ('Skill(dryas:plan), subagent_type: "dryas:executor", mcp__plugin_dryas_jev__log_dispatch, '
               'mcp__plugin_dryas_jev, `$dryas:plan`, dryas:unknown, dryas@dryas-workflow, <!-- dryas:start -->')
        self.assertEqual(ct.rewrite(src, NM, COMPS),
                         'Skill(plan), subagent_type: "executor", mcp__jev__log_dispatch, mcp__jev, `$dryas:plan`, '
                         'dryas:unknown, dryas@dryas-workflow, <!-- dryas:start -->')
        self.assertIn('Skill(x-plan), subagent_type: "x-executor"', ct.rewrite(src, PX, COMPS))

    def test_prefix_renames_commands_only_as_commands(self):
        src = ("Run /wreview, then /tune apply; see docs/plans/, https://example.com/commit/abc, "
               ".orchestrate/PLAN.md and /cost")
        self.assertEqual(ct.rewrite(src, PX, COMPS),
                         "Run /x-wreview, then /x-tune apply; see docs/plans/, https://example.com/commit/abc, "
                         ".orchestrate/PLAN.md and /cost")
        self.assertEqual(ct.rewrite(src, NM, COMPS), src)

    def test_harness_and_component_blocks(self):
        src = ("a\n<!-- claude -->\nc\n<!-- /claude -->\n<!-- codex -->\nx\n<!-- /codex -->\n"
               "<!-- pstack-picks -->\np\n<!-- /pstack-picks -->\nz\n")
        self.assertEqual(ct.rewrite(src, NM, COMPS), "a\nc\np\nz\n")
        self.assertEqual(ct.rewrite(src, NM, ("core",)), "a\nc\nz\n")

    def test_shipped_files_leave_no_plugin_trace(self):
        bad = re.compile(r"(?<![\w$/.@-])dryas:(%s)(?![\w-])" % "|".join(SKILLS + COMMANDS + ("executor",)))
        files = [p for s in SKILLS for p in sorted((ROOT / "claude/skills" / s).rglob("*.md"))]
        files += [p for p in (ROOT / "claude/commands" / (c + ".md") for c in COMMANDS) if p.is_file()]
        files += [ROOT / "claude/agents/executor.md", ROOT / "claude/CLAUDE.md.template", ROOT / "docs/workflow.md"]
        files += sorted((ROOT / "claude/pstack").rglob("*.md"))
        for names in (NM, PX):
            for f in files:
                text = ct.rewrite(f.read_text(encoding="utf-8"), names, COMPS)
                for token in ("${CLAUDE_PLUGIN_ROOT}", "~/.dryas", "mcp__plugin_dryas_jev", "<!-- codex -->"):
                    self.assertNotIn(token, text, (str(f), token))
                self.assertIsNone(bad.search(text), str(f))
                self.assertIsNone(re.search(r"(?<![\w.~-])/(?:Users|Volumes)/", text), str(f))


class HelpersTest(unittest.TestCase):
    def test_set_name(self):
        self.assertEqual(ct.set_name("---\nname: plan\ndescription: d\n---\nname: body\n", "x-plan"),
                         "---\nname: x-plan\ndescription: d\n---\nname: body\n")
        self.assertEqual(ct.set_name("no front matter\n", "x"), "no front matter\n")

    def test_claude_md_body(self):
        tpl = (ROOT / "claude/CLAUDE.md.template").read_text(encoding="utf-8")
        body = ct.claude_md_body(tpl, NM, COMPS, "9.9.9")
        self.assertTrue(body.startswith("Dryas 9.9.9 runs from this repo's `.dryas/` folder"), body[:80])
        self.assertIn("(`/dryas-cloud check` verifies it)", body)
        for token in ("${CLAUDE_PLUGIN_ROOT}", "~/.dryas", "dryas:brainstorm"):
            self.assertNotIn(token, body)
        self.assertIn("`/x-dryas-cloud check`", ct.claude_md_body(tpl, PX, COMPS, "9.9.9"))

    def test_third_party_paths(self):
        src = 'python "${CLAUDE_PLUGIN_ROOT}/.claude/skills/ui-ux-pro-max/scripts/search.py" and "${CLAUDE_SKILL_DIR}/x"'
        self.assertEqual(ct.third_party(src, "./.claude/skills/", {"ui-ux-pro-max": "x-ui-ux-pro-max"}),
                         'python ".claude/skills/x-ui-ux-pro-max/scripts/search.py" and "${CLAUDE_SKILL_DIR}/x"')
        self.assertEqual(ct.third_party("${CLAUDE_PLUGIN_ROOT}/src/data", "skills", {}), "${CLAUDE_PLUGIN_ROOT}/src/data")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python3 -m pytest -q install/tests/test_cloud_text.py`. Expected: FAIL (`ModuleNotFoundError: cloud_text`).

- [ ] **Step 3: Implement** `tools/cloud_text.py`:

```python
"""Text rewrites for the files `dryas cloud` copies into a repo (owned core E).

A repo copy has no plugin. Its runtime is in .dryas/, its skills, commands and agent under .claude/, its state in
.dryas/state/. So copied markdown gets:
- repo-relative paths (a cloud session, and every worktree of it, starts at the repo root);
- the project's names instead of the plugin's (`dryas:plan` -> `plan`, `mcp__plugin_dryas_jev__x` -> `mcp__jev__x`);
- the Claude harness blocks and the selected component blocks only.

--prefix renames the Dryas copies and the /commands that name them."""
import re
import sys
from pathlib import Path
from typing import Dict, Iterable

ROOT = Path(__file__).resolve().parents[1]
for _d in (ROOT / "tools", ROOT / "install"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
import render  # noqa: E402  (gate_blocks: <!-- pstack-picks --> blocks)
from sync_codex_plugin import harness_blocks  # noqa: E402

PLUGIN = "${CLAUDE_PLUGIN_ROOT}"
_SUB = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/(skills|agents|commands)/([A-Za-z0-9_-]+)")
_HOME_STATE = re.compile(r"~/\.dryas(?![\w-])")
LEAD = ("Dryas {version} runs from this repo's `.dryas/` folder, a pinned copy made by `dryas cloud` (`/{check}` "
        "verifies it). Its skills, commands and executor agent are project files under `.claude/`, its state is in "
        "`.dryas/state/` (git-ignored), and the judge is local unless this environment opted into Jev.")


class Names:
    """The copy's names for the Dryas skills, commands and agents, with --prefix applied."""

    def __init__(self, prefix: str, skills: Iterable[str], commands: Iterable[str], agents: Iterable[str]) -> None:
        self.prefix = prefix
        self.skills, self.commands, self.agents = tuple(skills), tuple(commands), tuple(agents)
        known = sorted(set(self.skills) | set(self.commands) | set(self.agents), key=len, reverse=True)
        self.plugin_names = (re.compile(r"(?<![\w$/.@-])dryas:(%s)(?![\w-])" % "|".join(map(re.escape, known)))
                             if known else None)
        cmds = sorted(self.commands, key=len, reverse=True)
        self.slash = (re.compile(r"(?<![\w$/.<-])/(%s)(?![/\w-]|\.\w)" % "|".join(map(re.escape, cmds)))
                      if cmds else None)

    def name(self, n: str) -> str:
        return self.prefix + n


def rewrite(text: str, names: Names, comps: Iterable[str]) -> str:
    """A Dryas markdown file as the repo copy ships it."""
    text = render.gate_blocks(harness_blocks(text, "claude"), list(comps))
    text = _SUB.sub(lambda m: ".claude/%s/%s" % (m.group(1), names.name(m.group(2))), text)
    text = text.replace(PLUGIN, ".dryas")
    text = text.replace("~/.dryas/docs/", ".dryas/docs/")
    text = _HOME_STATE.sub(".dryas/state", text)
    text = text.replace("mcp__plugin_dryas_jev", "mcp__jev")
    if names.plugin_names is not None:
        text = names.plugin_names.sub(lambda m: names.name(m.group(1)), text)
    if names.prefix and names.slash is not None:
        text = names.slash.sub(lambda m: "/" + names.name(m.group(1)), text)
    return text


def set_name(text: str, name: str) -> str:
    """Set the front matter `name:` of a SKILL.md or agent file; text without front matter is returned as it is."""
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---", 3)
    if end < 0:
        return text
    return re.sub(r"(?m)^name:[^\n]*$", "name: " + name, text[:end], count=1) + text[end:]


def claude_md_body(template: str, names: Names, comps: Iterable[str], version: str) -> str:
    """The rules block for the repo's CLAUDE.md: one paragraph on the copy, then the rules as the copy reads them."""
    lead = LEAD.format(version=version, check=names.name("dryas-cloud") + " check")
    return lead + "\n\n" + rewrite(template, names, comps).strip() + "\n"


def third_party(text: str, skills_rel: str, renames: Dict[str, str]) -> str:
    """A design skill's markdown: `${CLAUDE_PLUGIN_ROOT}/<skills folder>/<name>` becomes `.claude/skills/<new name>`.
    Other plugin-root paths stay, so the caller sees that the skill needs files outside its folder."""
    rel = (skills_rel[2:] if skills_rel.startswith("./") else skills_rel).strip("/")
    pat = re.compile(re.escape(PLUGIN + "/" + rel + "/") + r"([A-Za-z0-9_-]+)")
    return pat.sub(lambda m: ".claude/skills/" + renames.get(m.group(1), m.group(1)), text)
```

- [ ] **Step 4: Run** `python3 -m pytest -q install/tests/test_cloud_text.py`. Expected: 9 passed. If `test_shipped_files_leave_no_plugin_trace` reports a token in a file D rewrote, add a rewrite rule for that token form here; never edit D's file.
- [ ] **Step 5: Commit** `git add tools/cloud_text.py install/tests/test_cloud_text.py`, then `git commit -m "feat(cloud): text rewrites for files copied into a repo"`.

---

## Task 7: Repo config in and out
Goal: `tools/cloud_config.py` adds Dryas's entries to the repo's `.claude/settings.json`, `.mcp.json`, `CLAUDE.md` and `.gitignore` and takes them out again byte-exact, working on text in memory so the CLI can print a dry run, and stopping on text that is not valid JSON.
Scope:
- tools/cloud_config.py
- install/tests/test_cloud_config.py
Done:
- `python3 -m pytest -q install/tests/test_cloud_config.py install/tests/test_settings_merge.py install/tests/test_claude_md_block.py` passes
- `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: install/tests/test_cloud_config.py :: HooksTest :: test_every_plugin_hook_runs_from_the_copy

**Interfaces:**
- Consumes: `settings_merge.merge(settings, fragment) -> (new, added, conflicts)` and `settings_merge.unmerge(settings, added)`. Also `claude_md_block.insert_block(path, body, rec, key)` and `remove_block(path, rec, key)` with markers `<!-- dryas:start -->` / `<!-- dryas:end -->`, and `claude/hooks/hooks.json` as D leaves it.
- Produces: `CloudError`, `ENTRY`, `SKIP_SCRIPTS`, `ALLOW`, `GITIGNORE`, `PROJ` and these functions (`fragment` has `permissions` and `hooks` only, never `env`; `mcp_entry` carries the `env` block):
  - `hooks(plugin_hooks) -> dict`, `fragment(plugin_hooks) -> dict`, `mcp_entry() -> dict`;
  - `parse(name, text) -> dict` (`{}` for `None`; `CloudError` on bad JSON or a non-object), `dump(obj) -> str`, `restore(obj, original) -> Optional[str]`;
  - `add_settings(text, frag) -> (text, added, conflicts)` and `remove_settings(text, added, original) -> Optional[str]`;
  - `add_mcp(text, owned_entry) -> (text, entry)` and `remove_mcp(text, entry, original) -> Optional[str]`;
  - `claude_md(text, body, rec) -> Optional[str]` and `undo_claude_md(text, rec) -> Optional[str]`;
  - `add_gitignore(text) -> (text, rec)` and `remove_gitignore(text, rec) -> Optional[str]`.

  `None` text means the file does not exist; a `None` result means the file should not exist.
- The hook command a copy runs: `ENTRY + "<script>.py" + "<args>"`, for example `"${DRYAS_PY:-python3}" -X utf8 "$CLAUDE_PROJECT_DIR/.dryas/jev/cloud_hook.py" chain.py pretool`.

- [ ] **Step 1: Write the failing test** `install/tests/test_cloud_config.py`:

```python
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import cloud_config as cfg

PLUGIN_HOOKS = json.loads((ROOT / "claude/hooks/hooks.json").read_text(encoding="utf-8"))
USER = '{\n    "permissions": {"allow": ["Bash(make test)"]},\n    "env": {"FOO": "1"}\n}\n'


class HooksTest(unittest.TestCase):
    def test_every_plugin_hook_runs_from_the_copy(self):
        h = cfg.hooks(PLUGIN_HOOKS)
        cmds = [x["command"] for groups in h.values() for g in groups for x in g["hooks"]]
        for c in cmds:
            self.assertTrue(c.startswith(cfg.ENTRY), c)
            self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", c)
        self.assertIn(cfg.ENTRY + "chain.py pretool", cmds)
        self.assertFalse(any("rules_inject.py" in c for c in cmds))
        self.assertEqual(h["PreToolUse"][0]["matcher"], PLUGIN_HOOKS["hooks"]["PreToolUse"][0]["matcher"])
        plugin = [x["command"] for groups in PLUGIN_HOOKS["hooks"].values() for g in groups for x in g["hooks"]]
        self.assertEqual(len(cmds), len([c for c in plugin if "rules_inject.py" not in c]))

    def test_fragment_sets_no_env(self):
        f = cfg.fragment(PLUGIN_HOOKS)
        self.assertEqual(sorted(f), ["hooks", "permissions"])
        self.assertEqual(f["permissions"], {"allow": ["mcp__jev"]})
        self.assertEqual(cfg.mcp_entry()["env"], {"CLAUDE_PLUGIN_ROOT": "${CLAUDE_PROJECT_DIR:-.}/.dryas",
                                                  "DRYAS_DATA_ROOT": "${CLAUDE_PROJECT_DIR:-.}/.dryas/state"})


class SettingsTest(unittest.TestCase):
    def test_merge_keeps_the_users_entries_and_undo_restores_bytes(self):
        text, added, conflicts = cfg.add_settings(USER, cfg.fragment(PLUGIN_HOOKS))
        obj = json.loads(text)
        self.assertEqual(conflicts, [])
        self.assertEqual(obj["permissions"]["allow"], ["Bash(make test)", "mcp__jev"])
        self.assertEqual(obj["env"]["FOO"], "1")
        self.assertEqual(cfg.remove_settings(text, added, USER), USER)

    def test_created_file_is_removed_again(self):
        text, added, _ = cfg.add_settings(None, cfg.fragment(PLUGIN_HOOKS))
        self.assertIsNone(cfg.remove_settings(text, added, None))
        self.assertIsNone(cfg.remove_settings(None, added, None))

    def test_settings_env_is_never_touched(self):
        user = '{"env": {"DRYAS_DATA_ROOT": "elsewhere", "FOO": "1"}}'
        text, added, conflicts = cfg.add_settings(user, cfg.fragment(PLUGIN_HOOKS))
        self.assertEqual(json.loads(text)["env"], {"DRYAS_DATA_ROOT": "elsewhere", "FOO": "1"})
        self.assertEqual((conflicts, added["env"]), ([], {}))
        self.assertEqual(cfg.remove_settings(text, added, user), user)
        text, added, _ = cfg.add_settings(None, cfg.fragment(PLUGIN_HOOKS))
        self.assertNotIn("env", json.loads(text))

    def test_unparseable_settings_raise(self):
        for bad in ("{not json", "[1, 2]"):
            with self.assertRaises(cfg.CloudError):
                cfg.add_settings(bad, cfg.fragment(PLUGIN_HOOKS))

    def test_later_user_edits_survive_removal(self):
        text, added, _ = cfg.add_settings(USER, cfg.fragment(PLUGIN_HOOKS))
        obj = json.loads(text)
        obj["env"]["BAR"] = "2"
        out = json.loads(cfg.remove_settings(json.dumps(obj), added, USER))
        self.assertEqual(out["env"], {"FOO": "1", "BAR": "2"})
        self.assertNotIn("hooks", out)


class McpTest(unittest.TestCase):
    OTHER = '{"mcpServers": {"docs": {"command": "docs-server"}}}'  # no final newline, on purpose

    def test_add_keeps_other_servers_and_undo_restores_bytes(self):
        text, entry = cfg.add_mcp(self.OTHER, None)
        servers = json.loads(text)["mcpServers"]
        self.assertEqual(sorted(servers), ["docs", "jev"])
        self.assertEqual(servers["jev"]["args"], ["-X", "utf8", "${CLAUDE_PROJECT_DIR:-.}/.dryas/jev/jev_mcp.py"])
        self.assertEqual(cfg.remove_mcp(text, entry, self.OTHER), self.OTHER)

    def test_created_file_is_removed_again(self):
        text, entry = cfg.add_mcp(None, None)
        self.assertIsNone(cfg.remove_mcp(text, entry, None))

    def test_a_foreign_jev_server_stops_the_run(self):
        with self.assertRaises(cfg.CloudError):
            cfg.add_mcp(json.dumps({"mcpServers": {"jev": {"command": "my-jev"}}}), None)
        owned = {"command": "older-dryas"}
        text, _ = cfg.add_mcp(json.dumps({"mcpServers": {"jev": owned}}), owned)  # the one Dryas wrote is replaced
        self.assertEqual(json.loads(text)["mcpServers"]["jev"], cfg.mcp_entry())

    def test_malformed_mcp_raises(self):
        for bad in ("{", '{"mcpServers": []}', "[]"):
            with self.assertRaises(cfg.CloudError):
                cfg.add_mcp(bad, None)


class ClaudeMdTest(unittest.TestCase):
    def test_block_round_trip_keeps_the_repos_text(self):
        for orig in (None, "# Repo rules\n\nKeep tests green.\n", "# Repo\r\nCRLF lines\r\nno final newline"):
            rec = {}
            new = cfg.claude_md(orig, "Dryas rules here", rec)
            self.assertIn("<!-- dryas:start -->\nDryas rules here\n<!-- dryas:end -->\n", new)
            if orig:
                self.assertTrue(new.startswith(orig))
            self.assertEqual(cfg.undo_claude_md(new, rec), orig)

    def test_second_insert_replaces_the_block(self):
        rec = {}
        twice = cfg.claude_md(cfg.claude_md("# Repo\n", "v1", rec), "v2", rec)
        self.assertEqual(twice.count("<!-- dryas:start -->"), 1)
        self.assertIn("v2", twice)
        self.assertEqual(cfg.undo_claude_md(twice, rec), "# Repo\n")


class GitignoreTest(unittest.TestCase):
    def test_lines_added_once_and_removed_exactly(self):
        for orig in (None, "node_modules/\n", "node_modules/", ".orchestrate/\nbuild/\n"):
            text, rec = cfg.add_gitignore(orig)
            for line in cfg.GITIGNORE:
                self.assertEqual(text.splitlines().count(line), 1, (orig, line))
            self.assertEqual(cfg.remove_gitignore(text, rec), orig)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python3 -m pytest -q install/tests/test_cloud_config.py`. Expected: FAIL (`ModuleNotFoundError: cloud_config`).

- [ ] **Step 3: Implement** `tools/cloud_config.py`:

```python
"""Repo config that a Dryas copy adds and takes out again (owned core E):
- .claude/settings.json: hooks and one allow rule, never env (it would also reach the plugin's own hooks on a Mac);
- .mcp.json: the jev server;
- the CLAUDE.md rules block;
- the .gitignore lines.

Every function takes and returns text (None: the file does not exist, or should not), so `dryas cloud` can print a
dry run before it writes. A file that is not valid JSON, or not a JSON object, stops the run: Dryas never overwrites
what it cannot parse."""
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "install") not in sys.path:
    sys.path.insert(0, str(ROOT / "install"))
import claude_md_block as cmb  # noqa: E402
import settings_merge as sm  # noqa: E402

ENTRY = '"${DRYAS_PY:-python3}" -X utf8 "$CLAUDE_PROJECT_DIR/.dryas/jev/cloud_hook.py" '
_HOOK = re.compile(r'"\$\{CLAUDE_PLUGIN_ROOT\}/jev/([A-Za-z0-9_]+\.py)"(.*)$')
SKIP_SCRIPTS = ("rules_inject.py",)  # the CLAUDE.md block carries the rules in a repo copy
ALLOW = ("mcp__jev",)
GITIGNORE = (".dryas/state/", ".dryas/**/__pycache__/", ".orchestrate/")
PROJ = "${CLAUDE_PROJECT_DIR:-.}"


class CloudError(Exception):
    """Stops a dryas cloud run before anything is written."""


def hooks(plugin_hooks: Dict[str, Any]) -> Dict[str, Any]:
    """The plugin's hook groups (claude/hooks/hooks.json), each command re-pointed at the repo copy through
    cloud_hook.py; rules_inject.py is left out."""
    out: Dict[str, Any] = {}
    for ev, groups in (plugin_hooks.get("hooks") or {}).items():
        for g in groups:
            hs = []
            for h in g.get("hooks", []):
                m = _HOOK.search(str(h.get("command", "")))
                if m and m.group(1) not in SKIP_SCRIPTS:
                    hs.append(dict(type="command", command=ENTRY + m.group(1) + m.group(2), timeout=h.get("timeout", 10)))
            if hs:
                out.setdefault(ev, []).append(dict(matcher=g["matcher"], hooks=hs) if "matcher" in g else dict(hooks=hs))
    return out


def fragment(plugin_hooks: Dict[str, Any]) -> Dict[str, Any]:
    """Dryas's .claude/settings.json entries. No env: hooks get theirs from cloud_hook.py, the jev server from .mcp.json."""
    return dict(permissions=dict(allow=list(ALLOW)), hooks=hooks(plugin_hooks))


def mcp_entry() -> Dict[str, Any]:
    """The jev MCP server run from the copy: the argv shape claude_mcp.py registers, with repo-relative paths and its
    own env (Claude Code expands ${VAR:-default} here; paths._env_path copes when a client does not)."""
    return dict(command="${DRYAS_PY:-python3}", args=["-X", "utf8", PROJ + "/.dryas/jev/jev_mcp.py"],
                env=dict(CLAUDE_PLUGIN_ROOT=PROJ + "/.dryas", DRYAS_DATA_ROOT=PROJ + "/.dryas/state"))


def parse(name: str, text: Optional[str]) -> Dict[str, Any]:
    if text is None:
        return {}
    try:
        obj = json.loads(text)
    except ValueError as e:
        raise CloudError("%s is not valid JSON (%s); nothing changed" % (name, e))
    if not isinstance(obj, dict):
        raise CloudError("%s is not a JSON object; nothing changed" % name)
    return obj


def dump(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, indent=2) + "\n"


def restore(obj: Dict[str, Any], original: Optional[str]) -> Optional[str]:
    """Text for obj once Dryas's entries are out: the original bytes when nothing else changed, None when Dryas
    created the file and nothing is left."""
    if original is not None:
        try:
            if json.loads(original) == obj:
                return original
        except ValueError:
            pass
    elif not obj:
        return None
    return dump(obj)


def add_settings(text: Optional[str], frag: Dict[str, Any]) -> Tuple[str, Dict[str, Any], List[str]]:
    new, added, conflicts = sm.merge(parse(".claude/settings.json", text), frag)
    return dump(new), added, conflicts


def remove_settings(text: Optional[str], added: Dict[str, Any], original: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return restore(sm.unmerge(parse(".claude/settings.json", text), added), original)


def add_mcp(text: Optional[str], owned: Optional[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    obj = parse(".mcp.json", text)
    servers = obj.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise CloudError('.mcp.json: "mcpServers" is not an object; nothing changed')
    cur = servers.get("jev")
    if cur is not None and cur != mcp_entry() and cur != owned:
        raise CloudError(".mcp.json already has a jev server that Dryas did not write; nothing changed")
    servers["jev"] = mcp_entry()
    return dump(obj), mcp_entry()


def remove_mcp(text: Optional[str], entry: Optional[Dict[str, Any]], original: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    obj = parse(".mcp.json", text)
    servers = obj.get("mcpServers")
    if isinstance(servers, dict) and entry is not None and servers.get("jev") == entry:
        del servers["jev"]
        if not servers and "mcpServers" not in parse(".mcp.json", original):
            del obj["mcpServers"]
    return restore(obj, original)


def _via_file(text: Optional[str], edit: Callable[[Path], None]) -> Optional[str]:
    """Run a claude_md_block edit on a temp copy, so the repo is written only after the dry run."""
    d = tempfile.mkdtemp()
    try:
        p = Path(d) / "CLAUDE.md"
        if text is not None:
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        edit(p)
        if not p.exists():
            return None
        with open(p, encoding="utf-8", newline="") as f:
            return f.read()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def claude_md(text: Optional[str], body: str, rec: Dict[str, Any]) -> Optional[str]:
    return _via_file(text, lambda p: cmb.insert_block(p, body, rec, "claude_md"))


def undo_claude_md(text: Optional[str], rec: Dict[str, Any]) -> Optional[str]:
    return _via_file(text, lambda p: cmb.remove_block(p, rec, "claude_md"))


def add_gitignore(text: Optional[str]) -> Tuple[Optional[str], Dict[str, Any]]:
    have = {line.strip() for line in (text or "").splitlines()}
    lines = [line for line in GITIGNORE if line not in have]
    if not lines:
        return text, dict(added=[], sep="", created=False)
    base = text or ""
    sep = "\n" if base and not base.endswith("\n") else ""
    return base + sep + "".join(line + "\n" for line in lines), dict(added=lines, sep=sep, created=text is None)


def remove_gitignore(text: Optional[str], rec: Dict[str, Any]) -> Optional[str]:
    if text is None:
        return None
    added = list(rec.get("added") or [])
    block = rec.get("sep", "") + "".join(line + "\n" for line in added)
    if added and text.endswith(block):
        new = text[:len(text) - len(block)]
    else:
        out = []
        for line in text.splitlines(True):
            if line.strip() in added:
                added.remove(line.strip())
                continue
            out.append(line)
        new = "".join(out)
    if rec.get("created") and not new.strip():
        return None
    return new
```

- [ ] **Step 4: Run** everything in Done. Expected: 14 new tests pass, and the `settings_merge` and `claude_md_block` tests pass unchanged.
- [ ] **Step 5: Commit** `git add tools/cloud_config.py install/tests/test_cloud_config.py`, then `git commit -m "feat(cloud): add and remove the repo config of a Dryas copy"`.

---

## Task 8: The copy plan, with licences and the `/dryas-cloud` command
Goal: `tools/cloud_plan.py` computes every file of a repo copy (the Dryas core always, licence-confirmed design skills with `--with-design`, scanned own skills with `--with-own`) with its source, group, version, licence, NOTICE line and executable bit, adds `.dryas/NOTICE` and `.dryas/VERSION`, and ships the `/dryas-cloud` command it copies.
Scope:
- tools/cloud_plan.py
- claude/commands/dryas-cloud.md
- install/tests/cloud_fixtures.py
- install/tests/test_cloud_plan.py
Done:
- `python3 -m pytest -q install/tests/test_cloud_plan.py install/tests/test_cloud_text.py install/tests/test_invocation.py install/tests/test_shipped_files.py` passes
- `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: install/tests/test_cloud_plan.py :: CorePlanTest :: test_core_files

**Interfaces:**
- Consumes:
  - `cloud_text.Names`, `rewrite`, `set_name`, `third_party` and `PLUGIN` (Task 6);
  - `cloud_check.sha256`, `files_hash`, `MAC_PATH`, `HOME_STATE`, `nonstdlib_imports`, `siblings`, `NOTICE` and `VERSION` (Task 5);
  - `render.chain_bytes(f, comps, mapping, cd=None)`, `redact.redact` and `install/components.json` (`design.commands`);
  - a Claude config dir's `plugins/installed_plugins.json`: `{"plugins": {id: [{"installPath", "version"}]}}`;
  - a plugin's `.claude-plugin/plugin.json` `"skills"` (a string or list, default `./skills/`), and `plugins/marketplaces/<marketplace>/LICENSE|NOTICE|NOTICE.md`.
- Produces:
  - `CORE_SKILLS`, `CORE_COMMANDS`, `CORE_AGENTS`, `COMPS`, `DESIGN`, `NOT_COPIED`, `OWN_EXCLUDED`, `MAX_FILE`, `DRYAS_LICENCE`, `SP_LICENCE`, `PSTACK_LICENCE`;
  - `entry(data, source, group, version, licence, licence_file, notice, exe=False) -> dict` with keys `data`, `source`, `group`, `version`, `licence`, `licence_file`, `notice`, `exec`;
  - `version(repo) -> str`, `commit(repo) -> str`, `names(prefix) -> cloud_text.Names`, `dryas_notice(ver) -> str`, `design_plugins(repo) -> List[str]`;
  - `build(repo: Path, opts: dict, claude_dir: Path) -> {"files": {repo path: entry}, "skipped": [(what, why)], "names", "version", "commit"}`, where `opts` has the keys `prefix`, `design`, `own`, `confirm_own` and `persist_memory`;
  - `finish(plan) -> None`, which adds `.dryas/NOTICE` and `.dryas/VERSION` (`version: X\ncommit: SHA\nfiles: SHA256\n`).
- Produces `claude/commands/dryas-cloud.md` (user-invoked). In the plugin and in a copy alike, its `check` runs `"<root>/bin/dryas-py" "<root>/jev/cloud_check.py" --repo "$PWD"`. Its `init`, `update` and `remove` run `"<root>/bin/dryas" cloud ...`, which only a checkout has (Task 10).
- Produces the test helper `install/tests/cloud_fixtures.py`, used by Tasks 9–11:
  - `git(repo, *args)`, `git_repo(path, files=None)`, `commit_all(repo, msg="snapshot")`, `git_status(repo)`, `snapshot(repo)`, `run_cli(argv) -> (rc, output)`;
  - `design_config(base, impeccable_licence=True, pip_skill=None) -> Path` and `own_skill(claude_dir, name, text) -> Path`.

- [ ] **Step 1: Write the test helper** `install/tests/cloud_fixtures.py`:

```python
"""Shared helpers for the dryas cloud tests (owned core E): temp git repos, the CLI runner, and a Claude config dir
with the two design plugins laid out the way `claude plugin install` leaves them."""
import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
GIT = ["git", "-c", "user.email=dev@example.com", "-c", "user.name=Dev", "-c", "commit.gpgsign=false",
       "-c", "init.defaultBranch=main", "-c", "gc.auto=0"]  # no background gc while a test walks the repo
MIT = "MIT License\n\nCopyright (c) 2026 Example Author\n\nPermission is hereby granted, free of charge.\n"
APACHE = ("\n                                 Apache License\n                           Version 2.0, January 2004\n"
          "                        http://www.apache.org/licenses/\n\n   TERMS AND CONDITIONS\n")
UI_SKILLS = ("ui-ux-pro-max", "design", "design-system", "banner-design", "brand", "slides", "ui-styling")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(GIT + ["-C", str(repo)] + list(args), capture_output=True, text=True, check=True,
                          timeout=60).stdout


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return p


def commit_all(repo: Path, msg: str = "snapshot") -> None:
    git(repo, "add", "-A")
    if git(repo, "status", "--porcelain").strip():
        git(repo, "commit", "-qm", msg)


def git_repo(path: Path, files: Optional[Dict[str, str]] = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(GIT + ["init", "-q", str(path)], capture_output=True, check=True, timeout=60)
    for rel, text in (files or {"README.md": "# demo\n"}).items():
        _write(path / rel, text)
    commit_all(path, "init")
    return path


def git_status(repo: Path) -> str:
    return git(repo, "status", "--porcelain").strip()


def snapshot(repo: Path) -> Dict[str, bytes]:
    """Every file of the work tree (never walks into .git), by repo-relative path."""
    out: Dict[str, bytes] = {}
    for d, dirs, files in os.walk(str(repo)):
        dirs[:] = sorted(x for x in dirs if x != ".git")
        for f in files:
            p = Path(d) / f
            out[p.relative_to(repo).as_posix()] = p.read_bytes()
    return out


def run_cli(argv: List[str]) -> Tuple[int, str]:
    if str(ROOT / "tools") not in sys.path:
        sys.path.insert(0, str(ROOT / "tools"))
    import dryas_cloud
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        rc = dryas_cloud.main(argv)
    return rc, out.getvalue()


def design_config(base: Path, impeccable_licence: bool = True, pip_skill: Optional[str] = None) -> Path:
    cd = base / "claude-config"
    ui = cd / "plugins/cache/ui-ux-pro-max-skill/ui-ux-pro-max/9.9.9"
    imp = cd / "plugins/cache/impeccable/impeccable/9.9.9"
    _write(ui / ".claude-plugin/plugin.json", json.dumps({"name": "ui-ux-pro-max", "skills": "./.claude/skills/"}))
    _write(ui / "LICENSE", MIT)
    for s in UI_SKILLS:
        _write(ui / ".claude/skills" / s / "SKILL.md", "---\nname: %s\ndescription: d\n---\nRun `python "
               "\"${CLAUDE_PLUGIN_ROOT}/.claude/skills/%s/scripts/search.py\" <query>`.\n" % (s, s))
        _write(ui / ".claude/skills" / s / "scripts/search.py",
               "import json\nimport sys\n" + ("import numpy\n" if s == pip_skill else ""))
    _write(imp / ".claude-plugin/plugin.json", json.dumps({"name": "impeccable", "skills": "./skills/"}))
    _write(imp / "skills/impeccable/SKILL.md", "---\nname: impeccable\ndescription: d\nlicense: Apache 2.0\n---\n"
           "Run `\"${CLAUDE_SKILL_DIR}/scripts/impeccable\" context`.\n")
    launcher = _write(imp / "skills/impeccable/scripts/impeccable", "#!/usr/bin/env sh\necho ok\n")
    launcher.chmod(0o755)
    if impeccable_licence:
        _write(cd / "plugins/marketplaces/impeccable/LICENSE", APACHE)
        _write(cd / "plugins/marketplaces/impeccable/NOTICE.md", "Impeccable\nCopyright 2026 Example Author\n")
    _write(cd / "plugins/installed_plugins.json", json.dumps({"version": 2, "plugins": {
        "ui-ux-pro-max@ui-ux-pro-max-skill": [{"scope": "user", "installPath": str(ui), "version": "9.9.9"}],
        "impeccable@impeccable": [{"scope": "user", "installPath": str(imp), "version": "9.9.9"}]}}))
    return cd


def own_skill(claude_dir: Path, name: str, text: str) -> Path:
    return _write(claude_dir / "skills" / name / "SKILL.md", text)
```

`launcher.chmod` is `Path.chmod`, not `os.chmod`, and `test_portability.py` flags only `os.chmod(`. On Windows it is a harmless no-op.

- [ ] **Step 2: Write the failing test** `install/tests/test_cloud_plan.py`:

```python
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _d in (HERE, ROOT / "tools", ROOT / "claude" / "jev"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
import cloud_check as cc
import cloud_fixtures as fx
import cloud_plan as cp

OPTS = {"prefix": "", "design": False, "own": [], "confirm_own": [], "persist_memory": False}


class CorePlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.empty = Path(tempfile.mkdtemp())
        cls.plan = cp.build(ROOT, OPTS, cls.empty)
        cp.finish(cls.plan)
        cls.files = cls.plan["files"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(str(cls.empty), True)

    def test_core_files(self):
        for rel in (".dryas/jev/gate.py", ".dryas/jev/cloud_hook.py", ".dryas/jev/cloud_check.py", ".dryas/jev/memnotes.py",
                    ".dryas/jev/chain.json", ".dryas/bin/dryas-py", ".dryas/pstack/cleanup.md",
                    ".dryas/docs/dryas-workflow.md", ".dryas/licenses/LICENSE-dryas", ".dryas/licenses/LICENSE-superpowers",
                    ".dryas/NOTICE", ".dryas/VERSION", ".claude/skills/orchestrate/SKILL.md",
                    ".claude/skills/interrogate/SKILL.md", ".claude/commands/tune.md", ".claude/commands/dryas-cloud.md",
                    ".claude/agents/executor.md"):
            self.assertIn(rel, self.files)
        for rel in self.files:
            self.assertFalse("/tests/" in rel or "__pycache__" in rel or rel.startswith(".dryas/ruflo"), rel)
            self.assertFalse("benchmark-checklist/" in rel or rel.endswith("/retro.md"), rel)
        self.assertEqual(self.plan["skipped"], [])
        if os.name != "nt":
            self.assertTrue(self.files[".dryas/bin/dryas-py"]["exec"])

    def test_chain_json_keeps_placeholders_and_drops_extras(self):
        c = json.loads(self.files[".dryas/jev/chain.json"]["data"])
        by = {s["name"]: s for stages in c.values() for s in stages}
        self.assertEqual(by["scope-lock"]["cmd"][-1], "$CD/jev/scope_lock.py")
        self.assertIs(by["ruflo-pre-bash"].get("enabled"), False)
        self.assertIs(by["flowobserve"].get("enabled"), False)
        for name in ("jev-gate", "mem-session-end", "mem-notes"):
            self.assertNotEqual(by[name].get("enabled"), False, name)

    def test_every_planned_file_passes_the_scan(self):
        hits = []
        for rel, e in self.files.items():
            try:
                hits += cc.scan_text(rel, e["data"].decode("utf-8"))
            except UnicodeDecodeError:
                continue
        self.assertEqual(hits, [])

    def test_version_notice_and_records(self):
        v = self.files[".dryas/VERSION"]["data"].decode("utf-8")
        self.assertRegex(v, r"\Aversion: \d+\.\d+\.\d+\S*\ncommit: \S+\nfiles: [0-9a-f]{64}\n\Z")
        notice = self.files[".dryas/NOTICE"]["data"].decode("utf-8").splitlines()
        for rel, e in self.files.items():
            self.assertIn(e["notice"], notice, rel)
            self.assertEqual((e["group"], e["licence"]), ("dryas", "MIT"), rel)
        self.assertEqual(self.files[".claude/skills/plan/SKILL.md"]["source"], "claude/skills/plan/SKILL.md")

    def test_dryas_cloud_command(self):
        text = self.files[".claude/commands/dryas-cloud.md"]["data"].decode("utf-8")
        self.assertIn('Bash(".dryas/bin/dryas-py" ".dryas/jev/cloud_check.py":*)', text)
        self.assertIn('".dryas/bin/dryas-py" ".dryas/jev/cloud_check.py" --repo "$PWD"', text)
        self.assertIn("disable-model-invocation: true", text)

    def test_persist_memory_adds_the_notes_folder(self):
        plan = cp.build(ROOT, dict(OPTS, persist_memory=True), self.empty)
        self.assertEqual(plan["files"][".dryas/memory/notes/.gitkeep"]["data"], b"")
        self.assertNotIn(".dryas/memory/notes/.gitkeep", self.files)


class PrefixTest(unittest.TestCase):
    def test_prefix_renames_the_copies(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(d), True)
        f = cp.build(ROOT, dict(OPTS, prefix="x-"), d)["files"]
        self.assertIn("\nname: x-plan\n", f[".claude/skills/x-plan/SKILL.md"]["data"].decode("utf-8"))
        self.assertIn(".claude/commands/x-wreview.md", f)
        self.assertIn("\nname: x-executor\n", f[".claude/agents/x-executor.md"]["data"].decode("utf-8"))
        self.assertNotIn(".claude/skills/plan/SKILL.md", f)


class DesignTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.base), True)

    def test_design_plugins_come_from_components_json(self):
        self.assertEqual(sorted(cp.design_plugins(ROOT)), sorted(cp.DESIGN))

    def test_licensed_design_skills_are_copied_with_their_licence(self):
        plan = cp.build(ROOT, dict(OPTS, design=True), fx.design_config(self.base))
        cp.finish(plan)
        f = plan["files"]
        self.assertEqual(plan["skipped"], [])
        for s in fx.UI_SKILLS + ("impeccable",):
            self.assertEqual(f[".claude/skills/%s/SKILL.md" % s]["group"], "design", s)
        self.assertIn('".claude/skills/ui-ux-pro-max/scripts/search.py"',
                      f[".claude/skills/ui-ux-pro-max/SKILL.md"]["data"].decode("utf-8"))
        self.assertIn("MIT License", f[".dryas/licenses/ui-ux-pro-max-LICENSE"]["data"].decode("utf-8"))
        self.assertIn("Apache License", f[".dryas/licenses/impeccable-LICENSE"]["data"].decode("utf-8"))
        self.assertIn(".dryas/licenses/impeccable-NOTICE.md", f)
        notice = f[".dryas/NOTICE"]["data"].decode("utf-8")
        self.assertIn("- impeccable@impeccable 9.9.9 (Apache-2.0): .dryas/licenses/impeccable-LICENSE", notice)
        self.assertIn("- ui-ux-pro-max@ui-ux-pro-max-skill 9.9.9 (MIT): .dryas/licenses/ui-ux-pro-max-LICENSE", notice)
        if os.name != "nt":
            self.assertTrue(f[".claude/skills/impeccable/scripts/impeccable"]["exec"])

    def test_unconfirmed_licence_is_skipped(self):
        plan = cp.build(ROOT, dict(OPTS, design=True), fx.design_config(self.base, impeccable_licence=False))
        self.assertNotIn(".claude/skills/impeccable/SKILL.md", plan["files"])
        self.assertIn(("impeccable@impeccable", "licence not confirmed (Apache-2.0 text not found)"), plan["skipped"])
        self.assertIn(".claude/skills/design/SKILL.md", plan["files"])

    def test_skill_needing_pip_package_is_skipped(self):
        plan = cp.build(ROOT, dict(OPTS, design=True), fx.design_config(self.base, pip_skill="slides"))
        self.assertNotIn(".claude/skills/slides/SKILL.md", plan["files"])
        self.assertIn(("ui-ux-pro-max@ui-ux-pro-max-skill/slides", "scripts/search.py needs numpy (not stdlib)"),
                      plan["skipped"])
        self.assertIn(".claude/skills/brand/SKILL.md", plan["files"])

    def test_not_installed_is_reported(self):
        plan = cp.build(ROOT, dict(OPTS, design=True), self.base / "nowhere")
        self.assertEqual(sorted(w for w, _ in plan["skipped"]), sorted(cp.DESIGN))


class OwnTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.base), True)
        self.cd = self.base / "cfg"

    def test_own_skill_is_copied(self):
        fx.own_skill(self.cd, "release-notes", "---\nname: release-notes\ndescription: d\n---\nWrite the notes.\n")
        plan = cp.build(ROOT, dict(OPTS, own=["release-notes"]), self.cd)
        cp.finish(plan)
        e = plan["files"][".claude/skills/release-notes/SKILL.md"]
        self.assertEqual((e["group"], e["licence"], e["licence_file"]), ("own", "own", ""))
        self.assertIn("- own skill release-notes", plan["files"][".dryas/NOTICE"]["data"].decode("utf-8"))

    def test_secret_shaped_text_stops_the_copy_until_confirmed(self):
        fx.own_skill(self.cd, "deploy", "---\nname: deploy\n---\napi_key: example-value-123\n")
        plan = cp.build(ROOT, dict(OPTS, own=["deploy"]), self.cd)
        self.assertNotIn(".claude/skills/deploy/SKILL.md", plan["files"])
        (what, why), = plan["skipped"]
        self.assertEqual(what, "deploy")
        self.assertIn("SKILL.md:4", why)
        self.assertIn("--confirm-own deploy", why)
        self.assertNotIn("example-value-123", why)
        plan = cp.build(ROOT, dict(OPTS, own=["deploy"], confirm_own=["deploy"]), self.cd)
        self.assertIn(".claude/skills/deploy/SKILL.md", plan["files"])

    def test_excluded_and_bad_names_are_refused(self):
        fx.own_skill(self.cd, "update-my-vault", "---\nname: update-my-vault\n---\nx\n")
        plan = cp.build(ROOT, dict(OPTS, own=["update-my-vault", "../escape", "absent"]), self.cd)
        self.assertEqual([w for w, _ in plan["skipped"]], ["update-my-vault", "../escape", "absent"])
        self.assertFalse(any("update-my-vault" in r for r in plan["files"]))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run** `python3 -m pytest -q install/tests/test_cloud_plan.py`. Expected: FAIL (`ModuleNotFoundError: cloud_plan`).

- [ ] **Step 4: Write the command** `claude/commands/dryas-cloud.md`:

```markdown
---
description: Check, set up, update or remove the Dryas copy that makes this repo work in claude.ai/code cloud sessions
argument-hint: check | init | update | remove [options]
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/cloud_check.py":*), Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas" cloud:*), Bash(git status:*)
disable-model-invocation: true
---
Subcommand and options: $ARGUMENTS (none means `check`).

- `check`: from the repo root, run `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/cloud_check.py" --repo "$PWD"` and report each line it prints; exit 0 means the copy is intact. Fix nothing yourself: a drift line is a hand edit, which the user keeps or replaces with `update --force`.
- `init`, `update`, `remove`: these need a Dryas checkout, so they never run inside a cloud session. If `${CLAUDE_PLUGIN_ROOT}/bin/dryas` does not exist, say so, name the command for a machine with Dryas (`dryas cloud <subcommand> --repo <path>`, or `install/install.sh --repo <path>` for init) and stop. Otherwise run `"${CLAUDE_PLUGIN_ROOT}/bin/dryas" cloud <subcommand> --repo "$PWD"` with the user's options and without `--yes`, show the dry run, and ask before running it again with `--yes`. It never commits: show the `git add` and `git commit` lines it prints and leave the commit to the user.
```

- [ ] **Step 5: Implement** `tools/cloud_plan.py`:

```python
"""What `dryas cloud` copies into a repo (owned core E). build() returns bytes per repo path and writes nothing.

- Always: the Dryas core. Its runtime goes in .dryas/ (jev/ without tests, pstack/, bin/dryas-py,
  docs/dryas-workflow.md, licences), its skills, commands and executor agent under .claude/.
- --with-design: the design skills of the plugins install/components.json installs, each only with a confirmed
  licence (its text in .dryas/licenses/, a line in .dryas/NOTICE).
- --with-own NAME: that skill from the user's Claude config dir, after a redact.py scan; a hit stops it until
  --confirm-own NAME.

A skill is skipped and reported, never copied, when:
- its licence is not confirmed;
- a Python file needs a pip package;
- a file names a Mac path, ~/.dryas or a plugin file outside the skill;
- a file is over 5 MB."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
for _d in (ROOT / "tools", ROOT / "install", ROOT / "claude" / "jev"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
import cloud_check as cc  # noqa: E402
import cloud_text as ct  # noqa: E402
import redact  # noqa: E402
import render  # noqa: E402

CORE_SKILLS = ("orchestrate", "brainstorm", "plan", "review-request", "review-receive", "tdd", "debug", "verify",
               "worktree", "interrogate")
CORE_COMMANDS = ("orchestrate", "wplan", "wreview", "commit", "tune", "handoff", "dryas-cloud")
CORE_AGENTS = ("executor",)
COMPS = ("core", "jev", "memory", "pstack-picks")  # chain.json stages and rules blocks a repo copy keeps
DESIGN: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "ui-ux-pro-max@ui-ux-pro-max-skill": ("MIT", ("ui-ux-pro-max", "design", "design-system", "banner-design",
                                                   "brand", "slides", "ui-styling")),
    "impeccable@impeccable": ("Apache-2.0", ("impeccable",)),
}
NOT_COPIED = (
    ("update-my-vault", "its vault and sources are on the Mac"),
    ("fo-iterm", "it drives iTerm on the Mac"),
    ("claude-hud", "a local status line"),
    ("Ruflo", "needs Node and npm"),
    ("Superpowers", "the Dryas process skills replace it"),
    ("Playwright MCP", "needs npm and network"),
    ("Context7 MCP", "needs network"),
    ("GitHub MCP", "needs network"),
    ("Codex files", "cloud sessions run Claude Code"),
)
OWN_EXCLUDED = ("update-my-vault", "fo-iterm", "claude-hud")
SKIP_DIRS = frozenset(("tests", "logs", "compact", "__pycache__", ".pytest_cache"))
TEXT = (".md", ".template")
MAX_FILE = 5 * 1024 * 1024
DRYAS_LICENCE = ".dryas/licenses/LICENSE-dryas"
SP_LICENCE = ".dryas/licenses/LICENSE-superpowers"
PSTACK_LICENCE = ".dryas/pstack/LICENSE"
_OWN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_APACHE = re.compile(r"(?i)apache[- ]?(?:license[- ])?(?:version[- ])?2\.0")
Entry = Dict[str, Any]
Files = Dict[str, Tuple[bytes, bool]]


class _Same(dict):
    """A render.chain_bytes mapping that keeps every placeholder ($CD, $PY, $DRYAS_DATA_ROOT, $HOME): chain.py
    expands them at run time, so the copy names no absolute path."""

    def __contains__(self, key: object) -> bool:
        return True

    def __missing__(self, key: str) -> str:
        return "$" + key


def _walk(base: Path) -> Iterator[Tuple[str, Path]]:
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base)
        if p.is_file() and not set(rel.parts[:-1]) & SKIP_DIRS and p.suffix != ".pyc" and p.name != ".gitignore":
            yield rel.as_posix(), p


def _exec(p: Path) -> bool:
    return os.name != "nt" and os.access(str(p), os.X_OK)


def entry(data: bytes, source: str, group: str, version: str, licence: str, licence_file: str, notice: str,
          exe: bool = False) -> Entry:
    return dict(data=data, source=source, group=group, version=version, licence=licence, licence_file=licence_file,
                notice=notice, exec=exe)


def version(repo: Path) -> str:
    return str(json.loads((repo / "claude/.claude-plugin/plugin.json").read_text(encoding="utf-8")).get("version", ""))


def commit(repo: Path) -> str:
    try:
        p = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30)
        return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def names(prefix: str) -> ct.Names:
    return ct.Names(prefix, CORE_SKILLS, CORE_COMMANDS, CORE_AGENTS)


def dryas_notice(ver: str) -> str:
    return "- Dryas %s (MIT): %s" % (ver, DRYAS_LICENCE)


def core(repo: Path, nm: ct.Names, ver: str, persist_memory: bool) -> Dict[str, Entry]:
    out: Dict[str, Entry] = {}
    dn = dryas_notice(ver)

    def text(f: Path, name: Optional[str] = None) -> bytes:
        t = ct.rewrite(f.read_text(encoding="utf-8"), nm, COMPS)
        return (ct.set_name(t, name) if name else t).encode("utf-8")

    def put(rel: str, f: Path, data: Optional[bytes] = None, lic: str = DRYAS_LICENCE, notice: str = dn) -> None:
        if data is None:
            data = text(f) if f.suffix in TEXT else f.read_bytes()
        out[rel] = entry(data, f.relative_to(repo).as_posix(), "dryas", ver, "MIT", lic, notice, _exec(f))

    for rel, f in _walk(repo / "claude/jev"):
        put(".dryas/jev/" + rel, f, render.chain_bytes(f, list(COMPS), _Same()) if rel == "chain.json" else None)
    for rel, f in _walk(repo / "claude/pstack"):
        put(".dryas/pstack/" + rel, f, lic=PSTACK_LICENCE,
            notice="- pstack picks (MIT; see .dryas/pstack/NOTICE.md): " + PSTACK_LICENCE)
    put(".dryas/bin/dryas-py", repo / "claude/bin/dryas-py")
    put(".dryas/docs/dryas-workflow.md", repo / "docs/workflow.md")
    put(DRYAS_LICENCE, repo / "claude/LICENSE")
    put(SP_LICENCE, repo / "claude/skills/LICENSE-superpowers", lic=SP_LICENCE,
        notice="- Superpowers (MIT), adapted in the Dryas process skills: " + SP_LICENCE)
    for s in CORE_SKILLS:
        for rel, f in _walk(repo / "claude/skills" / s):
            name = nm.name(s) if rel == "SKILL.md" and nm.prefix else None
            put(".claude/skills/%s/%s" % (nm.name(s), rel), f, text(f, name) if f.suffix in TEXT else None)
    for c in CORE_COMMANDS:
        put(".claude/commands/%s.md" % nm.name(c), repo / "claude/commands" / (c + ".md"))
    for a in CORE_AGENTS:
        f = repo / "claude/agents" / (a + ".md")
        put(".claude/agents/%s.md" % nm.name(a), f, text(f, nm.name(a)))
    if persist_memory:
        out[".dryas/memory/notes/.gitkeep"] = entry(b"", "dryas cloud --persist-memory", "dryas", ver, "MIT",
                                                    DRYAS_LICENCE, dn)
    return out


def design_plugins(repo: Path) -> List[str]:
    """The design plugins install/components.json installs (its `claude plugin install <id>` commands)."""
    comp = json.loads((repo / "install/components.json").read_text(encoding="utf-8")).get("design", {})
    return [c[3] for c in comp.get("commands", []) if c[:3] == ["claude", "plugin", "install"] and len(c) > 3]


def _installed(claude_dir: Path, pid: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads((claude_dir / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        recs = data.get("plugins", {}).get(pid) or []
        rec = recs[0] if isinstance(recs, list) and recs else None
        return rec if isinstance(rec, dict) and rec.get("installPath") else None
    except (OSError, ValueError, AttributeError):
        return None


def _skills_rel(install: Path) -> str:
    try:
        v = json.loads((install / ".claude-plugin/plugin.json").read_text(encoding="utf-8")).get("skills", "./skills/")
    except (OSError, ValueError, AttributeError):
        v = "./skills/"
    v = v[0] if isinstance(v, list) and v else v
    v = v if isinstance(v, str) else "./skills/"
    return (v[2:] if v.startswith("./") else v).strip("/")


def _licence_text(dirs: Tuple[Path, ...], licence: str) -> Optional[bytes]:
    for d in dirs:
        try:
            data = (d / "LICENSE").read_bytes()
        except OSError:
            continue
        head = data[:600].decode("utf-8", "replace")
        if licence == "MIT" and "MIT License" in head:
            return data
        if licence == "Apache-2.0" and "Apache License" in head and "Version 2.0" in head:
            return data
    return None


def _front_licence(skill_md: Path) -> str:
    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    if not text.startswith("---") or text.count("---") < 2:
        return ""
    m = re.search(r"(?m)^license:\s*(.+)$", text.split("---", 2)[1])
    return m.group(1).strip() if m else ""


def _skill_files(src: Path, dst: str, fix_md: Callable[[str], str]) -> Tuple[Files, str]:
    """({repo path: (bytes, executable)}, "") or ({}, why the skill is skipped)."""
    out: Files = {}
    for rel, f in _walk(src):
        if f.stat().st_size > MAX_FILE:
            return {}, "%s is over 5 MB" % rel
        data = f.read_bytes()
        try:
            text: Optional[str] = data.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        if text is not None and f.suffix in TEXT:
            text = fix_md(text)
            data = text.encode("utf-8")
            if ct.PLUGIN in text:
                return {}, "%s names a plugin file outside the skill folder" % rel
        if text is not None:
            if cc.MAC_PATH.search(text):
                return {}, "%s names an absolute Mac path" % rel
            if cc.HOME_STATE.search(text):
                return {}, "%s names ~/.dryas" % rel
            if f.suffix == ".py":
                bad = cc.nonstdlib_imports(text, cc.siblings(str(f)))
                if bad:
                    return {}, "%s needs %s (not stdlib)" % (rel, ", ".join(bad))
        out["%s/%s" % (dst, rel)] = (data, _exec(f))
    return out, ""


def _named(files: Files, nm: ct.Names, skill: str) -> Files:
    """With --prefix, the copied SKILL.md carries the new name."""
    k = ".claude/skills/%s/SKILL.md" % nm.name(skill)
    if nm.prefix and k in files:
        data, exe = files[k]
        files[k] = (ct.set_name(data.decode("utf-8"), nm.name(skill)).encode("utf-8"), exe)
    return files


def design(repo: Path, claude_dir: Path, nm: ct.Names, skipped: List[Tuple[str, str]]) -> Dict[str, Entry]:
    out: Dict[str, Entry] = {}
    for pid in design_plugins(repo):
        if pid not in DESIGN:
            skipped.append((pid, "licence not confirmed (not in the cloud licence table)"))
            continue
        licence, skills = DESIGN[pid]
        rec = _installed(claude_dir, pid)
        if rec is None:
            skipped.append((pid, "not installed in this Claude config dir"))
            continue
        install, ver = Path(str(rec["installPath"])), str(rec.get("version") or "?")
        mkt = claude_dir / "plugins" / "marketplaces" / pid.split("@", 1)[1]
        rel_root = _skills_rel(install)
        text = _licence_text((install, mkt), licence)
        if licence == "Apache-2.0" and not _APACHE.search(_front_licence(install / rel_root / skills[0] / "SKILL.md")):
            text = None
        if text is None:
            skipped.append((pid, "licence not confirmed (%s text not found)" % licence))
            continue
        short = pid.split("@", 1)[0]
        lic = ".dryas/licenses/%s-LICENSE" % short
        notice = "- %s %s (%s): %s" % (pid, ver, licence, lic)

        def put(rel: str, data: bytes, src: str, exe: bool = False) -> None:
            out[rel] = entry(data, src, "design", ver, licence, lic, notice, exe)

        put(lic, text, "plugin:%s/LICENSE" % pid)
        for nf in ("NOTICE", "NOTICE.md"):  # Apache-2.0 asks redistributors to carry the NOTICE file
            found = next((d / nf for d in (install, mkt) if (d / nf).is_file()), None)
            if found is not None:
                put(".dryas/licenses/%s-%s" % (short, nf), found.read_bytes(), "plugin:%s/%s" % (pid, nf))
                break
        renames = {s: nm.name(s) for s in skills}
        for s in skills:
            src = install / rel_root / s
            if not (src / "SKILL.md").is_file():
                skipped.append(("%s/%s" % (pid, s), "not found in the installed plugin"))
                continue
            files, why = _skill_files(src, ".claude/skills/" + nm.name(s),
                                      lambda t, r=rel_root, n=renames: ct.third_party(t, r, n))
            if why:
                skipped.append(("%s/%s" % (pid, s), why))
                continue
            for rel, (data, exe) in _named(files, nm, s).items():
                put(rel, data, "plugin:%s/%s/%s" % (pid, rel_root, s), exe)
    return out


def _secret_lines(src: Path) -> List[str]:
    hits: List[str] = []
    for rel, f in _walk(src):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        hits += ["%s:%d" % (rel, n) for n, line in enumerate(text.splitlines(), 1) if redact.redact(line) != line]
    return hits


def own(claude_dir: Path, wanted: List[str], confirmed: List[str], nm: ct.Names,
        skipped: List[Tuple[str, str]]) -> Dict[str, Entry]:
    out: Dict[str, Entry] = {}
    reasons = dict(NOT_COPIED)
    for name in wanted:
        src = claude_dir / "skills" / name
        if not _OWN_NAME.match(name):
            skipped.append((name, "not a skill folder name"))
            continue
        if name in OWN_EXCLUDED:
            skipped.append((name, "excluded: " + reasons[name]))
            continue
        if not (src / "SKILL.md").is_file():
            skipped.append((name, "no skills/%s/SKILL.md in the Claude config dir" % name))
            continue
        if any(p.name.upper().startswith(("LICENSE", "LICENCE", "COPYING")) for p in src.iterdir()):
            skipped.append((name, "it has a licence file, so it is not an own skill"))
            continue
        hits = _secret_lines(src)
        if hits and name not in confirmed:
            skipped.append((name, "secret-shaped text at %s; review it, then pass --confirm-own %s"
                            % (", ".join(hits[:5]), name)))
            continue
        files, why = _skill_files(src, ".claude/skills/" + nm.name(name), lambda t: t)
        if why:
            skipped.append((name, why))
            continue
        notice = "- own skill %s (the repo owner's; not licensed by Dryas)" % name
        for rel, (data, exe) in _named(files, nm, name).items():
            out[rel] = entry(data, "own:" + name, "own", "", "own", "", notice, exe)
    return out


def build(repo: Path, opts: Dict[str, Any], claude_dir: Path) -> Dict[str, Any]:
    nm = names(str(opts.get("prefix") or ""))
    ver = version(repo)
    skipped: List[Tuple[str, str]] = []
    files = core(repo, nm, ver, bool(opts.get("persist_memory")))
    if opts.get("design"):
        files.update(design(repo, Path(claude_dir), nm, skipped))
    if opts.get("own"):
        files.update(own(Path(claude_dir), list(opts["own"]), list(opts.get("confirm_own") or []), nm, skipped))
    return dict(files=files, skipped=skipped, names=nm, version=ver, commit=commit(repo))


def finish(plan: Dict[str, Any]) -> None:
    """Add .dryas/NOTICE (every licence line) and .dryas/VERSION (version, commit, hash of every other file)."""
    files, ver = plan["files"], plan["version"]
    dn = dryas_notice(ver)
    lines = sorted({e["notice"] for e in files.values() if e["notice"]} | {dn})
    head = "Dryas %s, copied into this repo by `dryas cloud`. Licences of the copied material:\n" % ver
    files[cc.NOTICE] = entry((head + "\n".join(lines) + "\n").encode("utf-8"), "dryas cloud", "dryas", ver, "MIT",
                             DRYAS_LICENCE, dn)
    shas = {rel: cc.sha256(e["data"]) for rel, e in files.items() if rel != cc.VERSION}
    text = "version: %s\ncommit: %s\nfiles: %s\n" % (ver, plan["commit"], cc.files_hash(shas))
    files[cc.VERSION] = entry(text.encode("utf-8"), "dryas cloud", "dryas", ver, "MIT", DRYAS_LICENCE, dn)
```

- [ ] **Step 6: Run** everything in Done. Expected: 15 new tests pass. If `test_every_planned_file_passes_the_scan` names a file, extend `cloud_text.rewrite` only if Task 6's test also shows the token. Otherwise report it.
- [ ] **Step 7: Commit** `git add tools/cloud_plan.py claude/commands/dryas-cloud.md install/tests/cloud_fixtures.py install/tests/test_cloud_plan.py`, then `git commit -m "feat(cloud): the copy plan with licences, NOTICE and VERSION; /dryas-cloud"`.

---

## Task 9: `dryas cloud init | check | update | remove`
Goal: `tools/dryas_cloud.py` runs a preflight, prints a dry run of every file added, changed or removed with sizes, writes only with `--yes`, merges config, stops on clashes and unparseable JSON, keeps and reports hand edits, removes exactly what it added, and never commits.
Scope:
- tools/dryas_cloud.py
- install/tests/test_dryas_cloud.py
Done:
- `python3 -m pytest -q install/tests/test_dryas_cloud.py install/tests/test_cloud_plan.py install/tests/test_cloud_config.py` passes
- `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: install/tests/test_dryas_cloud.py :: CloudCliTest :: test_dry_run_changes_nothing

**Interfaces:**
- Consumes:
  - `cloud_plan.build(repo, opts, claude_dir)`, `finish(plan)`, `version(repo)`, `COMPS` and `NOT_COPIED` (Task 8);
  - all of `cloud_config` (Task 7) and `cloud_text.claude_md_body` (Task 6);
  - `cloud_check.check`, `load_manifest`, `file_sha`, `sha256`, `files_hash`, `MANIFEST` (Task 5);
  - `claude/hooks/hooks.json` and `claude/CLAUDE.md.template` as D leaves them.
- Produces:
  - the CLI `python3 tools/dryas_cloud.py {init,check,update,remove} [--repo PATH] [--yes] [--force] [--prefix P] [--with-design] [--with-own NAME]... [--confirm-own NAME]... [--persist-memory] [--claude-dir DIR]`;
  - `main(argv=None) -> int` (0 ok; 1 problems, refusal or stop; 2 usage);
  - `parse`, `options(a, old=None) -> dict`, `preflight(repo, rels, force) -> List[str]`, `roots(rels) -> List[str]`, `config_new`, `config_undo`, `manifest_bytes`.
- Output:
  - lines `  add     <rel> (<n> bytes)`, `  change  <rel> (<a> -> <b> bytes)` and `  remove  <rel> (<n> bytes)`;
  - notes (`skipped ...`, `not copied: ...`, `kept hand-edited ...`, and `kept the repo's own .claude/settings.json value for ...`, which with no Dryas `env` only a top-level key clash could print);
  - then `Dry run: nothing written. Re-run with --yes to write these N changes.`, or `Nothing to change.`, or `Nothing committed. To commit:` followed by `  git add -A -- <paths>`, `  git add --chmod=+x -- <exec files>` and `  git commit -m "<message>"`.
- Manifest written to `.dryas/manifest.json`: the shape in Task 5.

- [ ] **Step 1: Write the failing test** `install/tests/test_dryas_cloud.py`:

```python
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cloud_fixtures as fx

SETTINGS = '{\n    "permissions": {"allow": ["Bash(make test)"]},\n    "env": {"FOO": "1"}\n}\n'
MCP = '{"mcpServers": {"docs": {"command": "docs-server"}}}\n'
FILES = {"README.md": "# demo\n", "CLAUDE.md": "# Repo rules\n\nKeep tests green.\n", ".gitignore": "node_modules/\n",
         ".claude/settings.json": SETTINGS, ".mcp.json": MCP}


class CloudCliTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.base), True)
        self.repo = fx.git_repo(self.base / "repo", FILES)
        self.cfg = self.base / "no-config"  # no design plugins, no own skills

    def cli(self, *args):
        return fx.run_cli(list(args) + ["--repo", str(self.repo), "--claude-dir", str(self.cfg)])

    def init(self, *extra):
        rc, out = self.cli("init", "--yes", *extra)
        self.assertEqual(rc, 0, out)
        fx.commit_all(self.repo)
        return out

    def test_dry_run_changes_nothing(self):
        before = fx.snapshot(self.repo)
        rc, out = self.cli("init")
        self.assertEqual(rc, 0, out)
        self.assertIn("  add     .dryas/jev/gate.py (", out)
        self.assertIn("  change  .claude/settings.json (", out)
        self.assertIn("not copied: update-my-vault (its vault and sources are on the Mac)", out)
        self.assertIn("Dry run: nothing written.", out)
        self.assertEqual(fx.snapshot(self.repo), before)

    def test_init_then_check_passes(self):
        out = self.init()
        self.assertIn("Nothing committed. To commit:", out)
        self.assertRegex(out, r"  git add -A -- .*\.claude/settings\.json .*\.dryas .*CLAUDE\.md")
        self.assertIn('  git commit -m "chore: add Dryas ', out)
        rc, out = self.cli("check")
        self.assertEqual(rc, 0, out)
        self.assertIn("dryas cloud check: 0 problems", out)

    def test_merges_keep_existing_entries(self):
        self.init()
        s = json.loads((self.repo / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertIn("Bash(make test)", s["permissions"]["allow"])
        self.assertEqual(s["env"], {"FOO": "1"})  # no Dryas env in settings.json
        jev = json.loads((self.repo / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["jev"]
        self.assertEqual(jev["env"]["DRYAS_DATA_ROOT"], "${CLAUDE_PROJECT_DIR:-.}/.dryas/state")
        pre = [h["command"] for g in s["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertIn('"${DRYAS_PY:-python3}" -X utf8 "$CLAUDE_PROJECT_DIR/.dryas/jev/cloud_hook.py" chain.py pretool', pre)
        servers = json.loads((self.repo / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
        self.assertEqual(sorted(servers), ["docs", "jev"])
        md = (self.repo / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertTrue(md.startswith("# Repo rules\n\nKeep tests green.\n"))
        self.assertIn("<!-- dryas:start -->\nDryas ", md)
        ignore = (self.repo / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(ignore[0], "node_modules/")
        self.assertIn(".dryas/state/", ignore)

    def test_hand_edit_is_drift_and_update_keeps_it(self):
        self.init()
        skill = self.repo / ".claude/skills/plan/SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8") + "\nLocal note.\n", encoding="utf-8")
        fx.commit_all(self.repo)
        rc, out = self.cli("check")
        self.assertEqual(rc, 1)
        self.assertIn("drift (hand-edited): .claude/skills/plan/SKILL.md", out)
        rc, out = self.cli("update", "--yes")
        self.assertEqual(rc, 0, out)
        self.assertIn("kept hand-edited .claude/skills/plan/SKILL.md", out)
        self.assertIn("Local note.", skill.read_text(encoding="utf-8"))
        fx.commit_all(self.repo)
        rc, out = self.cli("update", "--yes", "--force")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Local note.", skill.read_text(encoding="utf-8"))
        fx.commit_all(self.repo)
        self.assertEqual(self.cli("check")[0], 0)

    def test_update_twice_changes_nothing(self):
        self.init()
        rc, out = self.cli("update", "--yes")
        self.assertEqual(rc, 0, out)
        self.assertIn("Nothing to change.", out)

    def test_remove_restores_the_repo(self):
        before = fx.snapshot(self.repo)
        self.init()
        rc, out = self.cli("remove", "--yes")
        self.assertEqual(rc, 0, out)
        self.assertEqual(fx.snapshot(self.repo), before)
        self.assertFalse((self.repo / ".dryas").exists())
        self.assertFalse((self.repo / ".claude/skills").exists())

    def test_clash_stops_with_prefix_hint(self):
        own = self.repo / ".claude/skills/plan/SKILL.md"
        own.parent.mkdir(parents=True)
        own.write_text("---\nname: plan\n---\nOur own planning notes.\n", encoding="utf-8")
        fx.commit_all(self.repo)
        before = fx.snapshot(self.repo)
        rc, out = self.cli("init", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn(".claude/skills/plan", out)
        self.assertIn("--prefix", out)
        self.assertEqual(fx.snapshot(self.repo), before)
        self.init("--prefix", "dryas-")
        self.assertIn("\nname: dryas-plan\n", (self.repo / ".claude/skills/dryas-plan/SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(own.read_text(encoding="utf-8"), "---\nname: plan\n---\nOur own planning notes.\n")
        self.assertEqual(self.cli("check")[0], 0)

    def test_malformed_config_stops_the_run(self):
        for rel, bad in ((".claude/settings.json", "{not json\n"), (".mcp.json", "[]\n")):
            (self.repo / rel).write_text(bad, encoding="utf-8")
            fx.commit_all(self.repo)
            before = fx.snapshot(self.repo)
            rc, out = self.cli("init", "--yes")
            self.assertEqual(rc, 1, rel)
            self.assertIn("nothing changed", out)
            self.assertEqual(fx.snapshot(self.repo), before)
            (self.repo / rel).write_text(FILES[rel], encoding="utf-8")
            fx.commit_all(self.repo)

    def test_foreign_jev_server_stops_the_run(self):
        (self.repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"jev": {"command": "my-jev"}}}), encoding="utf-8")
        fx.commit_all(self.repo)
        rc, out = self.cli("init", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("a jev server that Dryas did not write", out)
        self.assertFalse((self.repo / ".dryas").exists())

    def test_mac_path_in_a_copied_file_fails_check(self):
        self.init()
        f = self.repo / ".claude/commands/tune.md"
        f.write_text(f.read_text(encoding="utf-8") + "See /Users/someone/notes.\n", encoding="utf-8")
        rc, out = self.cli("check")
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"\.claude/commands/tune\.md:\d+: absolute Mac path")

    def test_design_copy_carries_licence_and_notice(self):
        self.cfg = fx.design_config(self.base)
        self.init("--with-design")
        self.assertIn("Apache License", (self.repo / ".dryas/licenses/impeccable-LICENSE").read_text(encoding="utf-8"))
        notice = (self.repo / ".dryas/NOTICE").read_text(encoding="utf-8")
        self.assertIn("- impeccable@impeccable 9.9.9 (Apache-2.0): .dryas/licenses/impeccable-LICENSE", notice)
        self.assertTrue((self.repo / ".claude/skills/impeccable/SKILL.md").is_file())
        self.assertEqual(self.cli("check")[0], 0)

    def test_second_init_refuses(self):
        self.init()
        before = fx.snapshot(self.repo)
        rc, out = self.cli("init", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("use update or remove", out)
        self.assertEqual(fx.snapshot(self.repo), before)

    def test_uncommitted_changes_need_force(self):
        (self.repo / "CLAUDE.md").write_text("# changed\n", encoding="utf-8")
        rc, out = self.cli("init")
        self.assertEqual(rc, 1)
        self.assertIn("uncommitted changes in CLAUDE.md", out)
        rc, out = self.cli("init", "--force")
        self.assertEqual(rc, 0, out)
        self.assertIn("Dry run: nothing written.", out)

    def test_init_writes_no_dryas_env_and_remove_keeps_env(self):
        own = '{\n  "env": {"DRYAS_DATA_ROOT": "elsewhere", "FOO": "1"},\n  "permissions": {"allow": ["Bash(make test)"]}\n}\n'
        (self.repo / ".claude/settings.json").write_text(own, encoding="utf-8")
        fx.commit_all(self.repo)
        self.init()
        settings = json.loads((self.repo / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["env"], {"DRYAS_DATA_ROOT": "elsewhere", "FOO": "1"})
        self.assertIn("hooks", settings)
        rc, out = self.cli("remove", "--yes")
        self.assertEqual(rc, 0, out)
        self.assertEqual((self.repo / ".claude/settings.json").read_text(encoding="utf-8"), own)

    def test_not_the_repo_root(self):
        sub = self.repo / "pkg"
        sub.mkdir()
        rc, out = fx.run_cli(["init", "--repo", str(sub)])
        self.assertEqual(rc, 1)
        self.assertIn("is not the repo root", out)
        rc, out = fx.run_cli(["init", "--repo", str(self.base)])
        self.assertEqual(rc, 1)
        self.assertIn("is not a git work tree", out)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python3 -m pytest -q install/tests/test_dryas_cloud.py`. Expected: FAIL (`ModuleNotFoundError: dryas_cloud`).

- [ ] **Step 3: Implement** `tools/dryas_cloud.py`:

```python
#!/usr/bin/env python3
"""dryas cloud: make a GitHub repo work in claude.ai/code cloud sessions with the Dryas workflow (owned core E).

  dryas_cloud.py init   [--repo PATH] [--yes] [--force] [--prefix P] [--with-design] [--with-own NAME]...
                        [--confirm-own NAME]... [--persist-memory] [--claude-dir DIR]
  dryas_cloud.py update [the same options; options left out keep what the manifest records]
  dryas_cloud.py check  [--repo PATH] [--claude-dir DIR]
  dryas_cloud.py remove [--repo PATH] [--yes] [--force]

Also reached as `install.sh --repo PATH` / `install.ps1 -Repo PATH` (init), `dryas cloud ...` and /dryas-cloud.
init, update and remove always print the dry run (every file added, changed or removed, with sizes) and write only
with --yes. Nothing is committed: a run ends with the `git add` line and a suggested message. Preflight: the root of
a git work tree, Python 3.9+, and no uncommitted changes in the paths the run writes (--force skips that check)."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
for _d in (ROOT / "tools", ROOT / "install", ROOT / "claude" / "jev"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
import cloud_check as cc  # noqa: E402
import cloud_config as cfg  # noqa: E402
import cloud_plan as cp  # noqa: E402
import cloud_text as ct  # noqa: E402

CONFIG = (".claude/settings.json", ".mcp.json", "CLAUDE.md", ".gitignore")
KEYS = ("source", "group", "version", "licence", "licence_file", "notice")
_PREFIX = re.compile(r"[a-z0-9-]{0,20}\Z")
Changes = Dict[str, Optional[bytes]]


def parse(argv: List[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="dryas cloud", description="Dryas in claude.ai/code cloud sessions.")
    ap.add_argument("cmd", choices=("init", "check", "update", "remove"))
    ap.add_argument("--repo", default=".")
    ap.add_argument("--yes", action="store_true", help="write; without it the run is a dry run")
    ap.add_argument("--force", action="store_true", help="write over uncommitted changes and hand edits")
    ap.add_argument("--prefix", default=None, help="rename the Dryas copies, for example dryas-")
    ap.add_argument("--with-design", action="store_true", default=None)
    ap.add_argument("--with-own", action="append", default=None, metavar="NAME")
    ap.add_argument("--confirm-own", action="append", default=None, metavar="NAME")
    ap.add_argument("--persist-memory", action="store_true", default=None)
    ap.add_argument("--claude-dir", default=None)
    a = ap.parse_args(argv)
    if a.prefix is not None and not _PREFIX.match(a.prefix):
        ap.error("--prefix takes up to 20 characters of a-z, 0-9 and -")
    return a


def claude_dir(a: argparse.Namespace) -> Path:
    return Path(a.claude_dir or os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude"))


def options(a: argparse.Namespace, old: Any = None) -> Dict[str, Any]:
    old = old if isinstance(old, dict) else {}
    own = [str(n) for n in old.get("own") or []]
    for n in a.with_own or []:
        if n not in own:
            own.append(n)
    return dict(prefix=a.prefix if a.prefix is not None else str(old.get("prefix") or ""),
                design=bool(a.with_design or old.get("design")), own=own, confirm_own=list(a.confirm_own or []),
                persist_memory=bool(a.persist_memory or old.get("persist_memory")))


def _git(repo: Path, *args: str) -> Tuple[int, str]:
    try:
        p = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def roots(rels: Iterable[str]) -> List[str]:
    """Top paths for git: .dryas, each copied skill folder, every other file itself."""
    out: List[str] = []
    for r in sorted(rels):
        parts = r.split("/")
        if parts[0] == ".dryas":
            top = ".dryas"
        elif parts[:2] == [".claude", "skills"] and len(parts) > 3:
            top = "/".join(parts[:3])
        else:
            top = r
        if top not in out:
            out.append(top)
    return out


def preflight(repo: Path, rels: Iterable[str], force: bool) -> List[str]:
    if sys.version_info < (3, 9):
        return ["dryas cloud needs Python 3.9 or newer"]
    rc, out = _git(repo, "rev-parse", "--show-toplevel")
    if rc != 0 or not out.strip():
        return ["%s is not a git work tree" % repo]
    top = Path(out.strip()).resolve()
    if top != repo.resolve():
        return ["%s is not the repo root; run it on %s (cloud sessions read .claude/ and CLAUDE.md there)"
                % (repo, top)]
    rels = list(rels)
    if force or not rels:
        return []
    rc, out = _git(repo, "status", "--porcelain", "--", *roots(rels))
    dirty = [line[3:] for line in out.splitlines() if line.strip()]
    if dirty:
        return ["uncommitted changes in %s; commit or stash them, or re-run with --force" % ", ".join(dirty)]
    return []


def _read(repo: Path, rel: str) -> Optional[str]:
    p = repo / rel
    if not p.is_file():
        return None
    try:
        with open(p, encoding="utf-8", newline="") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise cfg.CloudError("%s is not readable (%s); nothing changed" % (rel, e))


def _bytes(texts: Dict[str, Optional[str]]) -> Changes:
    return {r: (t.encode("utf-8") if t is not None else None) for r, t in texts.items()}


def config_new(repo: Path, plan: Dict[str, Any], old: Dict[str, Any]
               ) -> Tuple[Dict[str, Optional[str]], Dict[str, Any], List[str]]:
    """New text of the four config files, the records the manifest keeps, and notes. old: an earlier run's records."""
    cur = {r: _read(repo, r) for r in CONFIG}
    o_s, o_m, o_g = old.get("settings") or {}, old.get("mcp") or {}, old.get("gitignore") or {}
    s_orig = o_s["original"] if "original" in o_s else cur[".claude/settings.json"]
    m_orig = o_m["original"] if "original" in o_m else cur[".mcp.json"]
    s_text = cur[".claude/settings.json"]
    if o_s.get("added"):
        s_text = cfg.remove_settings(s_text, o_s["added"], s_orig)
    hooks_json = json.loads((ROOT / "claude/hooks/hooks.json").read_text(encoding="utf-8"))
    s_new, added, conflicts = cfg.add_settings(s_text, cfg.fragment(hooks_json))
    m_new, entry = cfg.add_mcp(cur[".mcp.json"], o_m.get("entry"))
    rec = dict(old.get("claude_md") or {})
    tpl = (ROOT / "claude/CLAUDE.md.template").read_text(encoding="utf-8")
    c_new = cfg.claude_md(cur["CLAUDE.md"], ct.claude_md_body(tpl, plan["names"], cp.COMPS, plan["version"]), rec)
    g_new, g_rec = cfg.add_gitignore(cur[".gitignore"])
    if o_g:
        g_rec = dict(added=list(o_g.get("added") or []) + g_rec["added"], sep=o_g.get("sep", ""),
                     created=bool(o_g.get("created")))
    texts = {".claude/settings.json": s_new, ".mcp.json": m_new, "CLAUDE.md": c_new, ".gitignore": g_new}
    records = dict(settings=dict(added=added, original=s_orig), mcp=dict(entry=entry, original=m_orig),
                   claude_md=rec, gitignore=g_rec)
    return texts, records, ["kept the repo's own .claude/settings.json value for %s" % k for k in conflicts]


def config_undo(repo: Path, old: Dict[str, Any]) -> Dict[str, Optional[str]]:
    cur = {r: _read(repo, r) for r in CONFIG}
    s, m = old.get("settings") or {}, old.get("mcp") or {}
    return {".claude/settings.json": cfg.remove_settings(cur[".claude/settings.json"], s.get("added") or {},
                                                         s.get("original")),
            ".mcp.json": cfg.remove_mcp(cur[".mcp.json"], m.get("entry"), m.get("original")),
            "CLAUDE.md": cfg.undo_claude_md(cur["CLAUDE.md"], dict(old.get("claude_md") or {})),
            ".gitignore": cfg.remove_gitignore(cur[".gitignore"], old.get("gitignore") or {})}


def manifest_bytes(plan: Dict[str, Any], records: Dict[str, Any], opts: Dict[str, Any],
                   kept: Dict[str, Any]) -> bytes:
    files = {rel: dict({k: e[k] for k in KEYS}, sha256=cc.sha256(e["data"])) for rel, e in plan["files"].items()}
    files.update(kept)  # a kept hand edit keeps its old record, so check goes on reporting the drift
    shas = {r: str((f or {}).get("sha256")) for r, f in files.items()}
    m = dict(format=1, dryas=dict(version=plan["version"], commit=plan["commit"], files_hash=cc.files_hash(shas)),
             options={k: opts[k] for k in ("prefix", "design", "own", "persist_memory")}, files=files, config=records)
    return (json.dumps(m, indent=1, sort_keys=True) + "\n").encode("utf-8")


def clash_message(rels: Iterable[str]) -> str:
    tops = sorted({"/".join(r.split("/")[:3]) if r.startswith(".claude/") else r for r in rels})
    return ("already in the repo and not written by Dryas: %s. Nothing changed. Re-run with --prefix <p> "
            "(for example --prefix dryas-) to rename the Dryas copies" % ", ".join(tops))


def _differs(repo: Path, rel: str, new: Optional[bytes]) -> bool:
    p = repo / rel
    return (p.read_bytes() if p.is_file() else None) != new


def show(repo: Path, changes: Changes, trash: List[Path]) -> None:
    for rel in sorted(changes):
        new, p = changes[rel], repo / rel
        old = p.stat().st_size if p.is_file() else None
        if new is None:
            print("  remove  %s (%d bytes)" % (rel, old or 0))
        elif old is None:
            print("  add     %s (%d bytes)" % (rel, len(new)))
        else:
            print("  change  %s (%d -> %d bytes)" % (rel, old, len(new)))
    for d in trash:
        print("  remove  %s/ (generated, git-ignored)" % d.relative_to(repo).as_posix())


def write(repo: Path, changes: Changes, execs: List[str]) -> None:
    for rel in sorted(changes):
        p, data = repo / rel, changes[rel]
        if data is None:
            if p.is_file():
                p.unlink()
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
    if os.name != "nt":
        for rel in execs:
            os.chmod(str(repo / rel), 0o755)


def prune(repo: Path, rels: Iterable[str]) -> None:
    """Remove the folders a removal left empty, up to the repo root."""
    for rel in rels:
        d = (repo / rel).parent
        while d != repo and repo in d.parents and d.is_dir() and not any(d.iterdir()):
            d.rmdir()
            d = d.parent


def run(a: argparse.Namespace, repo: Path, changes: Changes, plan: Optional[Dict[str, Any]], notes: List[str],
        message: str, trash: Optional[List[Path]] = None) -> int:
    trash = list(trash or [])
    changes = {r: v for r, v in changes.items() if _differs(repo, r, v)}
    probs = preflight(repo, list(changes), a.force)
    if probs:
        for p in probs:
            print("dryas cloud: " + p, file=sys.stderr)
        return 1
    print("dryas cloud %s: %s" % (a.cmd, repo))
    show(repo, changes, trash)
    for line in notes:
        print("  " + line)
    if not changes and not trash:
        print("Nothing to change.")
        return 0
    if not a.yes:
        print("Dry run: nothing written. Re-run with --yes to write these %d changes." % (len(changes) + len(trash)))
        return 0
    files = (plan or {}).get("files", {})
    execs = sorted(r for r, e in files.items() if e.get("exec") and changes.get(r) is not None)
    write(repo, changes, execs)
    for d in trash:
        shutil.rmtree(str(d), ignore_errors=True)
    prune(repo, [r for r, v in changes.items() if v is None] + [d.relative_to(repo).as_posix() for d in trash])
    print("Nothing committed. To commit:")
    print("  git add -A -- %s" % " ".join(roots(changes)))
    for r in execs:
        print("  git add --chmod=+x -- %s" % r)
    print('  git commit -m "%s"' % message)
    return 0


def _manifest(repo: Path) -> Dict[str, Any]:
    try:
        return cc.load_manifest(str(repo))
    except OSError:
        raise cfg.CloudError("no Dryas copy here (%s is missing); run dryas cloud init" % cc.MANIFEST)
    except ValueError as e:
        raise cfg.CloudError("%s is unreadable (%s); nothing changed" % (cc.MANIFEST, e))


def _plan(a: argparse.Namespace, opts: Dict[str, Any]) -> Dict[str, Any]:
    plan = cp.build(ROOT, opts, claude_dir(a))
    cp.finish(plan)
    return plan


def init(a: argparse.Namespace, repo: Path) -> int:
    if (repo / cc.MANIFEST).exists():
        raise cfg.CloudError("this repo already has a Dryas copy (%s); use update or remove" % cc.MANIFEST)
    opts = options(a)
    plan = _plan(a, opts)
    skill_dirs = sorted({"/".join(r.split("/")[:3]) for r in plan["files"] if r.startswith(".claude/skills/")})
    clashes = [r for r in plan["files"] if (repo / r).exists()] + [d for d in skill_dirs if (repo / d).exists()]
    if clashes:
        raise cfg.CloudError(clash_message(clashes))
    texts, records, notes = config_new(repo, plan, {})
    changes: Changes = {r: e["data"] for r, e in plan["files"].items()}
    changes.update(_bytes(texts))
    changes[cc.MANIFEST] = manifest_bytes(plan, records, opts, {})
    notes = (["skipped %s: %s" % s for s in plan["skipped"]] + ["not copied: %s (%s)" % n for n in cp.NOT_COPIED]
             + notes)
    return run(a, repo, changes, plan, notes, "chore: add Dryas %s for cloud sessions" % plan["version"])


def update(a: argparse.Namespace, repo: Path) -> int:
    man = _manifest(repo)
    opts = options(a, man.get("options"))
    plan = _plan(a, opts)
    old = man["files"]
    changes: Changes = {}
    kept: Dict[str, Any] = {}
    clashes: List[str] = []
    for rel, e in sorted(plan["files"].items()):
        cur = cc.file_sha(str(repo / rel))
        if rel in old:
            if cur is not None and cur != (old[rel] or {}).get("sha256") and not a.force:
                kept[rel] = old[rel]
            else:
                changes[rel] = e["data"]
        elif cur is not None and cur != cc.sha256(e["data"]):
            clashes.append(rel)
        else:
            changes[rel] = e["data"]
    if clashes:
        raise cfg.CloudError(clash_message(clashes))
    for rel, e in sorted(old.items()):
        cur = cc.file_sha(str(repo / rel))
        if rel in plan["files"] or cur is None:
            continue
        if cur == (e or {}).get("sha256") or a.force:
            changes[rel] = None
        else:
            kept[rel] = e
    texts, records, cnotes = config_new(repo, plan, man.get("config") or {})
    changes.update(_bytes(texts))
    changes[cc.MANIFEST] = manifest_bytes(plan, records, opts, kept)
    notes = ["kept hand-edited %s (drift; --force replaces it)" % r for r in sorted(kept)]
    notes += ["skipped %s: %s" % s for s in plan["skipped"]] + cnotes
    return run(a, repo, changes, plan, notes, "chore: update the Dryas cloud copy to %s" % plan["version"])


def remove(a: argparse.Namespace, repo: Path) -> int:
    man = _manifest(repo)
    changes: Changes = {}
    kept: List[str] = []
    for rel, e in sorted(man["files"].items()):
        cur = cc.file_sha(str(repo / rel))
        if cur is None:
            continue
        if cur == (e or {}).get("sha256") or a.force:
            changes[rel] = None
        else:
            kept.append(rel)
    changes.update(_bytes(config_undo(repo, man.get("config") or {})))
    changes[cc.MANIFEST] = None
    state = repo / ".dryas" / "state"
    trash = [state] if state.is_dir() else []
    bases = {".dryas"} | {"/".join(r.split("/")[:3]) for r in man["files"] if r.startswith(".claude/skills/")}
    for b in sorted(bases):
        if (repo / b).is_dir():
            trash += [p for p in sorted((repo / b).rglob("__pycache__")) if p.is_dir() and state not in p.parents]
    notes = ["kept hand-edited %s (--force removes it)" % r for r in kept]
    if any((repo / ".dryas" / "memory" / "notes").glob("*.md")):
        notes.append("kept .dryas/memory/notes/*.md (memory notes are the repo's own work)")
    return run(a, repo, changes, None, notes, "chore: remove the Dryas cloud copy", trash)


def check(a: argparse.Namespace, repo: Path) -> int:
    probs = cc.check(str(repo), cp.version(ROOT))
    try:
        man: Optional[Dict[str, Any]] = cc.load_manifest(str(repo))
    except (OSError, ValueError):
        man = None
    if man is not None:
        plan = cp.build(ROOT, options(a, man.get("options")), claude_dir(a))
        old = man["files"]
        stale = sorted(r for r, e in plan["files"].items()
                       if e["group"] == "dryas" and (old.get(r) or {}).get("sha256") != cc.sha256(e["data"]))
        if stale:
            probs.append("out of date: %d files differ from this Dryas checkout (first: %s); run dryas cloud update"
                         % (len(stale), stale[0]))
        d = man.get("dryas") or {}
        print("copy: Dryas %s (%s); this checkout: Dryas %s (%s)"
              % (d.get("version"), str(d.get("commit"))[:12], plan["version"], plan["commit"][:12]))
    for p in probs:
        print(p)
    print("dryas cloud check: %d problem%s" % (len(probs), "" if len(probs) == 1 else "s"))
    return 1 if probs else 0


def main(argv: Optional[List[str]] = None) -> int:
    a = parse(sys.argv[1:] if argv is None else list(argv))
    repo = Path(a.repo).resolve()
    try:
        if a.cmd == "check":
            return check(a, repo)
        probs = preflight(repo, [], True)
        if probs:
            for p in probs:
                print("dryas cloud: " + p, file=sys.stderr)
            return 1
        return {"init": init, "update": update, "remove": remove}[a.cmd](a, repo)
    except cfg.CloudError as e:
        print("dryas cloud: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run** everything in Done. Expected: 15 new tests pass. `test_remove_restores_the_repo` is the strictest: if it fails, compare the two snapshots key by key before changing code.
- [ ] **Step 5: Commit** `git add tools/dryas_cloud.py install/tests/test_dryas_cloud.py`, then `git commit -m "feat(cloud): dryas cloud init, check, update and remove"`.

---

## Task 10: Entry points — `install.sh --repo`, `install.ps1 -Repo`, `dryas cloud`
Goal: `install.sh --repo PATH` and `install.ps1 -Repo PATH` run `dryas_cloud.py init` (every other installer run is unchanged), and `dryas cloud ...` runs the CLI from a checkout or says that it needs one.
Scope:
- install/install.sh
- install/install.ps1
- claude/bin/dryas
- claude/bin/dryas.cmd
- install/tests/test_cloud_entry.py
Done:
- `python3 -m pytest -q install/tests/test_cloud_entry.py install/tests/test_dryas_wrapper.py install/tests/test_portability.py install/tests/test_hook_shell.py` passes
- `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: install/tests/test_cloud_entry.py :: EntryTest :: test_installers_route_repo_to_cloud_init

**Interfaces:**
- Consumes: `tools/dryas_cloud.py` (Task 9), D's `claude/bin/dryas` (a `case "$1"` with `memory)` and a `*)` usage line exiting 2) and D's `claude/bin/dryas.cmd` (`if /I "%~1"=="memory" goto memory`, a usage `echo`, `exit /b 2`, a `:memory` block).
- Produces:
  - `install.sh`: a user-supplied `--repo` (or `--repo=PATH`) means `exec "$c" "$REPO/tools/dryas_cloud.py" init "$@"`. Without one, it runs `dryas_install.py run --repo "$REPO" "$@"` as before.
  - `install.ps1`: `-Repo` or `--repo` means `tools\dryas_cloud.py init`, with `-Repo` passed on as `--repo`.
  - `dryas cloud <args>` means `dryas-py tools/dryas_cloud.py <args>` when `tools/dryas_cloud.py` exists two levels above `bin/`. Otherwise it exits 2 with `dryas cloud: needs a Dryas checkout`.
  - The usage line names both `dryas memory` and `dryas cloud`.

- [ ] **Step 1: Write the failing test** `install/tests/test_cloud_entry.py`:

```python
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import cloud_fixtures as fx


class EntryTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.base), True)
        self.repo = fx.git_repo(self.base / "repo")
        self.env = dict(os.environ, DRYAS_PYTHON=sys.executable, DRYAS_PY=sys.executable,
                        CLAUDE_CONFIG_DIR=str(self.base / "cfg"))

    def test_installers_route_repo_to_cloud_init(self):
        sh = (ROOT / "install/install.sh").read_text(encoding="utf-8")
        self.assertIn('exec "$c" "$REPO/tools/dryas_cloud.py" init "$@"', sh)
        self.assertIn('run --repo "$REPO" "$@"', sh)  # every other run is the plugin installer, as before
        self.assertLess(sh.index("tools/dryas_cloud.py"), sh.index('run --repo "$REPO"'))
        ps = (ROOT / "install/install.ps1").read_text(encoding="utf-8")
        self.assertIn("tools\\dryas_cloud.py", ps)
        self.assertIn("'-Repo'", ps)
        self.assertIn("run --repo $repo @args", ps)

    @unittest.skipIf(os.name == "nt", "POSIX installer")
    def test_install_sh_with_repo_runs_cloud_init(self):
        before = fx.snapshot(self.repo)
        p = subprocess.run(["sh", str(ROOT / "install/install.sh"), "--repo", str(self.repo)], capture_output=True,
                           text=True, env=self.env, timeout=300)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("dryas cloud init: ", p.stdout)
        self.assertIn("Dry run: nothing written.", p.stdout)
        self.assertEqual(fx.snapshot(self.repo), before)

    def test_wrappers_name_the_checkout_tool(self):
        sh = (ROOT / "claude/bin/dryas").read_text(encoding="utf-8")
        self.assertIn("cloud)", sh)
        self.assertIn("tools/dryas_cloud.py", sh)
        self.assertIn("memory)", sh)  # D's case stays
        cmd = (ROOT / "claude/bin/dryas.cmd").read_text(encoding="utf-8")
        self.assertIn('if /I "%~1"=="cloud" goto cloud', cmd)
        self.assertIn("tools\\dryas_cloud.py", cmd)

    @unittest.skipIf(os.name == "nt", "POSIX wrapper")
    def test_dryas_cloud_wrapper(self):
        p = subprocess.run(["sh", str(ROOT / "claude/bin/dryas"), "cloud", "check", "--repo", str(self.repo)],
                           capture_output=True, text=True, env=self.env, timeout=120)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn("no Dryas copy here", p.stdout)
        p = subprocess.run(["sh", str(ROOT / "claude/bin/dryas"), "nope"], capture_output=True, text=True,
                           env=self.env, timeout=60)
        self.assertEqual(p.returncode, 2)
        self.assertIn("usage:", p.stderr)
        self.assertIn("dryas cloud", p.stderr)

    @unittest.skipIf(os.name == "nt", "POSIX wrapper")
    def test_wrapper_without_a_checkout_says_so(self):
        b = self.base / "plugin" / "bin"
        b.mkdir(parents=True)
        for n in ("dryas", "dryas-py"):
            shutil.copy(str(ROOT / "claude/bin" / n), str(b / n))
        p = subprocess.run(["sh", str(b / "dryas"), "cloud", "check"], capture_output=True, text=True, env=self.env,
                           timeout=60)
        self.assertEqual(p.returncode, 2)
        self.assertIn("needs a Dryas checkout", p.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows wrapper")
    def test_dryas_cloud_wrapper_windows(self):
        p = subprocess.run(["cmd", "/c", str(ROOT / "claude/bin/dryas.cmd"), "cloud", "check", "--repo", str(self.repo)],
                           capture_output=True, text=True, env=self.env, timeout=120)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("no Dryas copy here", p.stdout)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python3 -m pytest -q install/tests/test_cloud_entry.py`. Expected: FAIL (no `tools/dryas_cloud.py` route in `install.sh`, and no `cloud)` case).

- [ ] **Step 3: `install/install.sh`.** Add one usage line to the header comment, after D's last usage line:

```sh
#        install.sh --repo PATH [--yes] [--force] [--prefix P] [--with-design] [--with-own NAME] [--persist-memory]
#                   sets the repo at PATH up for claude.ai/code cloud sessions (tools/dryas_cloud.py init; docs/cloud-sessions.md)
```

Right after the line `REPO=$(cd "$(dirname "$0")/.." && pwd)`, add:

```sh
CLOUD=0  # a --repo of your own: set that repo up for cloud sessions instead of installing the plugin
for arg in "$@"; do
  case "$arg" in --repo|--repo=*) CLOUD=1 ;; esac
done
```

Inside the interpreter loop, right before the line `exec "$c" "$REPO/install/dryas_install.py" run --repo "$REPO" "$@"`, add:

```sh
    if [ "$CLOUD" = 1 ]; then
      exec "$c" "$REPO/tools/dryas_cloud.py" init "$@"
    fi
```

- [ ] **Step 4: `install/install.ps1`.** Add to the header comment, after D's last usage line:

```powershell
#        .\install\install.ps1 -Repo PATH [--yes] [--force] [--prefix P] [--with-design] [--with-own NAME] [--persist-memory]
#                   sets the repo at PATH up for claude.ai/code cloud sessions (tools\dryas_cloud.py init; docs\cloud-sessions.md)
```

Right after `$script = Join-Path $repo 'install\dryas_install.py'`, add:

```powershell
$cloud = $false  # -Repo PATH (or --repo PATH): set that repo up for cloud sessions instead of installing the plugin
foreach ($arg in $args) { if ($arg -eq '-Repo' -or $arg -eq '--repo' -or "$arg".StartsWith('--repo=')) { $cloud = $true } }
```

Inside `if ($LASTEXITCODE -eq 0) {`, right after the `DRYAS_PYTHON_PATH` line and before `& $exe @pre $script run --repo $repo @args`, add:

```powershell
    if ($cloud) {
      $fwd = @($args | ForEach-Object { if ($_ -eq '-Repo') { '--repo' } else { $_ } })
      & $exe @pre (Join-Path $repo 'tools\dryas_cloud.py') init @fwd
      exit $LASTEXITCODE
    }
```

- [ ] **Step 5: `claude/bin/dryas`** (D's file). Add this case above D's `*)` line:

```sh
  cloud) shift; t="$here/../../tools/dryas_cloud.py"
         if [ ! -f "$t" ]; then echo "dryas cloud: needs a Dryas checkout (tools/dryas_cloud.py beside claude/)" >&2; exit 2; fi
         exec "$here/dryas-py" "$t" "$@" ;;
```

Change D's usage `echo` in the `*)` line so it names both commands:

```sh
  *) echo "usage: dryas memory {import-ruflo|consolidate|stats} [options] | dryas cloud {init|check|update|remove} [options]" >&2; exit 2 ;;
```

- [ ] **Step 6: `claude/bin/dryas.cmd`** (D's file).
  - Below D's `if /I "%~1"=="memory" goto memory`, add `if /I "%~1"=="cloud" goto cloud`.
  - Change D's usage `echo` to `echo usage: dryas memory {import-ruflo^|consolidate^|stats} [options] ^| dryas cloud {init^|check^|update^|remove} [options] 1>&2`.
  - D's memory path ends in the `:plain` label, the last in the file, whose `python ... memcli.py ...` line has no `exit /b`. Add `exit /b %ERRORLEVEL%` after that line, so that it never falls through into the new block.
  - Append:

```bat
:cloud
if not exist "%~dp0..\..\tools\dryas_cloud.py" (
  echo dryas cloud: needs a Dryas checkout ^(tools\dryas_cloud.py beside claude\^) 1>&2
  exit /b 2
)
if defined DRYAS_PY goto cloudenv
where py >nul 2>&1 && goto cloudpy
where python3 >nul 2>&1 && goto cloudpy3
python -X utf8 "%~dp0..\..\tools\dryas_cloud.py" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%
:cloudenv
"%DRYAS_PY%" -X utf8 "%~dp0..\..\tools\dryas_cloud.py" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%
:cloudpy
py -3 -X utf8 "%~dp0..\..\tools\dryas_cloud.py" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%
:cloudpy3
python3 -X utf8 "%~dp0..\..\tools\dryas_cloud.py" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%
```

  The block uses D's Python lookup order (`DRYAS_PY`, `py -3`, `python3`, `python`). It passes `%2`–`%9` and does not `shift`, because a plain `shift` also moves `%0`, and then `%~dp0` no longer names `bin\`. **Known D defect, outside this Scope:** D's `:memory` block (merged at e28218e) runs `shift` and then `%~dp0..\jev\memcli.py`. Do not fix it in this task. The orchestrator raises it with Promprit as a separate one-line fix (`shift /1`, or drop the `shift` and pass `%2`–`%9`).

- [ ] **Step 7: Run** everything in Done. Expected: the new tests pass (one is skipped by OS), and D's `test_dryas_wrapper.py` passes unchanged.
- [ ] **Step 8: Commit** `git add install/install.sh install/install.ps1 claude/bin/dryas claude/bin/dryas.cmd install/tests/test_cloud_entry.py`, then `git commit -m "feat(cloud): install.sh --repo, install.ps1 -Repo and dryas cloud reach dryas_cloud.py"`.

---

## Task 11: A simulated cloud session
Goal: prove the spec's cloud run end to end: in a repo set up by `dryas cloud init` (its path has a space), the committed hooks run with `CLAUDE_CODE_REMOTE=true`, an empty `HOME` and no Jev opt-in, with a local judge, state in `.dryas/state/`, Mac-equal gate and scope-lock decisions, quiet session hooks, memory notes that round-trip, and quiet hooks where Dryas is installed.
Scope:
- install/tests/test_cloud_session.py
Done:
- `python3 -m pytest -q install/tests/test_cloud_session.py` passes (skipped on Windows: cloud sessions run POSIX shells)
- `python3 tools/inventory.py --check` prints `0 problems`
Failing test first: install/tests/test_cloud_session.py :: CloudSessionTest :: test_judge_is_local_and_state_stays_in_the_repo

This task adds one test file and no code. Its tests are the integration gate for Tasks 2–9. If one fails, find the root cause (`dryas:debug`) and report the failing module and the fix it needs. Do not change code outside this Scope.

**Interfaces:**
- Consumes: `cloud_fixtures` (Task 8), `dryas_cloud` (Task 9), the hooks it writes (Task 7), `cloud_hook.py` (Task 3), `providers` and `paths` (Task 2), `memnotes` and the `mem-notes` stage (Task 4), D's chain observe kinds and memory stages, A2's local judge (`git checkout -- .` → `ask`, reason `destructive:git_checkout_discard`), and `projns.project_ns`.

- [ ] **Step 1: Write the test** `install/tests/test_cloud_session.py`:

```python
"""A simulated claude.ai/code session (owned core E): a repo set up by `dryas cloud init` runs its committed hooks
the way a cloud session does: CLAUDE_CODE_REMOTE=true, an empty HOME, no Jev opt-in. The repo path has a space."""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _d in (HERE, ROOT / "claude" / "jev"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
import cloud_fixtures as fx
import projns

PLAN = "## Task 1: a\nGoal: g\nScope:\n- src/feature/**\nDone:\n- d\n"
DISCARD = "git checkout -- ."


@unittest.skipIf(os.name == "nt", "a cloud session runs the hook commands with a POSIX shell")
class CloudSessionTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.base), True)
        self.repo = fx.git_repo(self.base / "my repo")
        self.home = self.base / "home"
        self.home.mkdir()

    def init(self, *extra):
        rc, out = fx.run_cli(["init", "--repo", str(self.repo), "--yes", "--claude-dir", str(self.base / "cfg")]
                             + list(extra))
        self.assertEqual(rc, 0, out)
        fx.commit_all(self.repo)

    def env(self, **kw):
        e = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.repo),
             "CLAUDE_CODE_REMOTE": "true", "DRYAS_PY": sys.executable, "LANG": "C.UTF-8"}
        e.update(kw)
        return e

    def event(self, **kw):
        return dict(dict(cwd=str(self.repo), session_id="s1"), **kw)

    def hook(self, event, payload, env=None):
        """Run every committed hook command of the event whose matcher fits, as Claude Code does; their stdouts."""
        settings = json.loads((self.repo / ".claude/settings.json").read_text(encoding="utf-8"))
        key = str(payload.get("tool_name") or payload.get("source") or "")
        outs = []
        for g in settings["hooks"].get(event, []):
            if g.get("matcher") and not re.fullmatch(g["matcher"], key):
                continue
            for h in g["hooks"]:
                p = subprocess.run(["sh", "-c", h["command"]], input=json.dumps(payload), capture_output=True,
                                   text=True, env=env or self.env(), cwd=str(self.repo), timeout=60)
                self.assertEqual(p.returncode, 0, p.stderr)
                outs.append(p.stdout)
        return outs

    @staticmethod
    def decision(outs):
        for o in outs:
            if o.strip():
                return json.loads(o)["hookSpecificOutput"]["permissionDecision"]
        return None

    def test_judge_is_local_and_state_stays_in_the_repo(self):
        self.init()
        env = self.env(OPENROUTER_API_KEY="not-a-real-key")  # a key is present; the cloud default ignores it
        outs = self.hook("PreToolUse", self.event(tool_name="Bash", tool_input={"command": DISCARD}), env)
        self.assertEqual(self.decision(outs), "ask")
        self.assertIn("destructive:git_checkout_discard", "".join(outs))
        log = self.repo / ".dryas/state/jev/logs/gate.jsonl"
        rec = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()][-1]
        self.assertEqual((rec["provider"], rec["decision"]), ("local", "ask"))
        for field in ("fallback", "error", "latency_ms"):
            self.assertNotIn(field, rec)  # Jev was never tried: no network
        self.assertFalse((self.home / ".dryas").exists())
        self.assertEqual(fx.git_status(self.repo), "")  # state and bytecode are git-ignored

    def test_scope_lock_and_gate_match_the_mac(self):
        self.init()
        orch = self.repo / ".orchestrate"
        orch.mkdir()
        (orch / "PLAN.md").write_text(PLAN, encoding="utf-8")
        (orch / "active.json").write_text(json.dumps({"active": ["1"]}), encoding="utf-8")
        local = self.base / "chain.local.json"
        local.write_text(json.dumps({"stages": {"pretool": {"ruflo-pre-bash": {"enabled": False}}}}), encoding="utf-8")
        mac = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.base / "mac-home"), "DRYAS_PY": sys.executable,
               "DRYAS_DATA_ROOT": str(self.base / "mac-data"), "CLAUDE_PLUGIN_ROOT": str(ROOT / "claude"),
               "JEV_CHAIN_LOCAL": str(local)}
        events = [self.event(tool_name="Write", tool_input={"file_path": str(self.repo / "src/other.py"), "content": "x"}),
                  self.event(tool_name="Write", tool_input={"file_path": str(self.repo / "src/feature/a.py"),
                                                            "content": "x"}),
                  self.event(tool_name="Bash", tool_input={"command": DISCARD})]
        cloud, plugin = [], []
        for ev in events:
            cloud.append(self.decision(self.hook("PreToolUse", ev)))
            p = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "claude/jev/chain.py"), "pretool"],
                               input=json.dumps(ev), capture_output=True, text=True, env=mac, timeout=60)
            plugin.append(self.decision([p.stdout]))
        self.assertEqual(cloud, ["deny", None, "ask"])
        self.assertEqual(cloud, plugin)

    def test_session_hooks_run_quietly(self):
        self.init()
        edit = {"tool_name": "Edit", "tool_input": {"file_path": str(self.repo / "README.md")}}
        for event, payload in (("SessionStart", {"source": "startup"}), ("PostToolUse", edit), ("SubagentStop", {}),
                               ("SessionEnd", {})):
            outs = self.hook(event, self.event(**payload))
            self.assertTrue(outs, event)
            self.assertEqual("".join(outs), "", event)
        self.assertTrue((self.repo / ".dryas/state/dryas.db").is_file())

    def test_memory_notes_round_trip_between_sessions(self):
        self.init("--persist-memory")
        notes = self.repo / ".dryas/memory/notes"
        self.hook("SessionStart", self.event(source="startup"))
        ns = projns.project_ns(str(self.repo))
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import memdb, memstore; "
                "memstore.store(memdb.connect(), sys.argv[2], 'Retry flaky calls', 'Use the retry helper.')")
        subprocess.run([sys.executable, "-c", code, str(self.repo / ".dryas/jev"), ns], check=True, timeout=60,
                       env=self.env(DRYAS_DATA_ROOT=str(self.repo / ".dryas/state")))
        self.hook("SessionEnd", self.event())
        written = sorted(notes.glob("*.md"))
        self.assertEqual(len(written), 1, written)
        self.assertIn("Retry flaky calls", written[0].read_text(encoding="utf-8"))
        shutil.rmtree(str(self.repo / ".dryas/state"))  # the next cloud session starts with no state
        self.hook("SessionStart", self.event(source="startup", session_id="s2"))
        db = sqlite3.connect(str(self.repo / ".dryas/state/dryas.db"))
        self.addCleanup(db.close)
        titles = [r[0] for r in db.execute("SELECT title FROM memory WHERE kind = 'note'")]
        self.assertTrue(any(t.startswith("Dryas session ") for t in titles), titles)

    def test_hooks_stay_quiet_on_a_mac_with_dryas_installed(self):
        self.init()
        (self.home / ".dryas").mkdir()
        (self.home / ".dryas" / "chain.local.json").write_text("{}", encoding="utf-8")
        env = self.env()
        del env["CLAUDE_CODE_REMOTE"]
        outs = self.hook("PreToolUse", self.event(tool_name="Bash", tool_input={"command": DISCARD}), env)
        self.assertEqual("".join(outs), "")
        self.assertFalse((self.repo / ".dryas/state").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python3 -m pytest -q install/tests/test_cloud_session.py`. Expected: 5 passed. A failure points at the module listed under Interfaces: report it with the assertion text.
- [ ] **Step 3: Commit** `git add install/tests/test_cloud_session.py`, then `git commit -m "test(cloud): a simulated cloud session runs the committed hooks"`.

---

## Task 12: Cloud binding table, docs, Codex sync and the full suite
Goal: `reference/cloud-bindings.json` lists every core component as copied, opt-in or excluded with a reason and `tools/inventory.py --check` enforces it, cloud sessions are documented, `codex/jev` is regenerated, and the full suite passes.
Scope:
- reference/cloud-bindings.json
- tools/inventory.py
- install/tests/test_cloud_bindings.py
- docs/cloud-sessions.md
- reference/README.md
- GLOSSARY.md
- codex/jev/**
Done:
- `python3 tools/sync_codex_plugin.py --check` exits 0
- `python3 tools/inventory.py --check` prints `0 problems`
- `python3 -m pytest -q -rs claude/jev/tests install/tests` passes: Task 1's count plus 115 new tests (38 in `claude/jev/tests`, 77 in `install/tests`; one Windows-only test is skipped on macOS and Linux)
Failing test first: install/tests/test_cloud_bindings.py :: CloudBindingsTest :: test_table_covers_every_core_component

**Interfaces:**
- Consumes: `inventory.collect(repo)`, `inventory._json`, `inventory.check`; `cloud_plan.CORE_SKILLS`, `CORE_COMMANDS`, `CORE_AGENTS` and `NOT_COPIED` (Task 8); `cloud_config.hooks` and `ENTRY` (Task 7).
- Produces:
  - `inventory.CLOUD = "reference/cloud-bindings.json"`, `inventory.CLOUD_KINDS`, `inventory.CLOUD_VALUES`, and `inventory.cloud_check(current, table) -> List[str]`, wired into `--check` when the table exists;
  - the table `{"about": str, "entries": {inventory entry: "copy: <where>" | "opt-in: <flag>" | "exclude: <reason>"}, "not_copied": {name: reason}}`. It covers the kinds `command:claude:`, `skill:claude:`, `agent:claude:`, `mcp_server:claude:`, `plugin_hook:claude:`, `chain_stage:` and `component:`.

- [ ] **Step 1: Write the failing test** `install/tests/test_cloud_bindings.py`:

```python
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import cloud_config as cfg
import cloud_plan as cp
import inventory as inv

TABLE = json.loads((ROOT / "reference/cloud-bindings.json").read_text(encoding="utf-8"))


def copied(kind):
    return sorted(k.split(":")[2] for k, v in TABLE["entries"].items() if k.startswith(kind) and v.startswith("copy:"))


class CloudBindingsTest(unittest.TestCase):
    def test_table_covers_every_core_component(self):
        self.assertEqual(inv.cloud_check(inv.collect(ROOT), TABLE), [])

    def test_copied_skills_commands_and_agents_match_the_plan(self):
        self.assertEqual(copied("skill:claude:"), sorted(cp.CORE_SKILLS))
        self.assertEqual(copied("command:claude:"), sorted(cp.CORE_COMMANDS))
        self.assertEqual(copied("agent:claude:"), sorted(cp.CORE_AGENTS))

    def test_copied_plugin_hooks_match_the_settings_hooks(self):
        made = cfg.hooks(json.loads((ROOT / "claude/hooks/hooks.json").read_text(encoding="utf-8")))
        got = {(ev, g.get("matcher") or "*", h["command"][len(cfg.ENTRY):])
               for ev, groups in made.items() for g in groups for h in g["hooks"]}
        want = set()
        for k, v in TABLE["entries"].items():
            if k.startswith("plugin_hook:claude:") and v.startswith("copy:"):
                ev, matcher, key = k[len("plugin_hook:claude:"):].split(":", 2)
                want.add((ev, matcher, key))
        self.assertEqual(got, want)

    def test_not_copied_names_match_the_plan(self):
        self.assertEqual(TABLE["not_copied"], dict(cp.NOT_COPIED))

    def test_cloud_check_reports_gaps(self):
        cur = ["command:claude:a", "command:claude:b", "install_flag:--x"]
        table = {"entries": {"command:claude:a": "copy: .claude/commands/a.md", "command:claude:gone": "exclude: retired",
                             "command:claude:b": "maybe"}}
        self.assertEqual(inv.cloud_check(cur, table), [
            "cloud table: command:claude:gone is not in the inventory",
            "cloud table: command:claude:b needs copy:, opt-in: or exclude: and a reason"])
        self.assertEqual(inv.cloud_check(cur, {"entries": {}})[0],
                         "cloud table: command:claude:a is neither copied nor excluded")
        self.assertEqual(inv.cloud_check(cur, []), ['cloud table: reference/cloud-bindings.json has no "entries" object'])

    def test_docs_name_the_opt_ins(self):
        doc = (ROOT / "docs/cloud-sessions.md").read_text(encoding="utf-8")
        for want in ("dryas cloud init", "--yes", "DRYAS_JUDGE=jev", "OPENROUTER_API_KEY", "openrouter.ai",
                     "--persist-memory", ".dryas/jev/cloud_check.py", "DRYAS_CLOUD_HOOKS"):
            self.assertIn(want, doc)
        self.assertIn("cloud-bindings.json", (ROOT / "reference/README.md").read_text(encoding="utf-8"))
        self.assertRegex((ROOT / "GLOSSARY.md").read_text(encoding="utf-8"), r"(?m)^- \*\*repo copy\*\*: \S")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python3 -m pytest -q install/tests/test_cloud_bindings.py`. Expected: FAIL (`FileNotFoundError: reference/cloud-bindings.json`).

- [ ] **Step 3: Write** `reference/cloud-bindings.json`:

```json
{
 "about": "Cloud binding table (owned core E): what `dryas cloud` puts into a repo for claude.ai/code cloud sessions. Every core component of the inventory kinds command, skill, agent, MCP server, plugin hook, chain stage and component is copied, opt-in or excluded with a reason. tools/inventory.py --check enforces it.",
 "entries": {
  "agent:claude:executor": "copy: .claude/agents/executor.md",
  "chain_stage:post:gate-outcome:core": "copy: .dryas/jev/chain.json",
  "chain_stage:post:mem-edit:memory": "copy: .dryas/jev/chain.json (Dryas memory in .dryas/state/)",
  "chain_stage:precompact:mem-session-end:memory": "copy: .dryas/jev/chain.json",
  "chain_stage:pretool:flowobserve:flowobserve": "exclude: FlowObserve is not in a cloud session; the stage ships disabled",
  "chain_stage:pretool:jev-gate:jev": "copy: .dryas/jev/chain.json (local judge unless the environment opts into Jev)",
  "chain_stage:pretool:ruflo-pre-bash:ruflo": "exclude: Ruflo needs Node and npm; the stage ships disabled",
  "chain_stage:pretool:scope-lock:core": "copy: .dryas/jev/chain.json",
  "chain_stage:prompt:context-watch:core": "copy: .dryas/jev/chain.json",
  "chain_stage:prompt:flowobserve:flowobserve": "exclude: FlowObserve is not in a cloud session; the stage ships disabled",
  "chain_stage:prompt:jev-route:jev": "copy: .dryas/jev/chain.json (local judge unless the environment opts into Jev)",
  "chain_stage:session-end:mem-notes:core": "copy: .dryas/jev/chain.json (writes notes only with --persist-memory)",
  "chain_stage:session-end:mem-session-end:memory": "copy: .dryas/jev/chain.json",
  "chain_stage:session-start:mem-session-start:memory": "copy: .dryas/jev/chain.json",
  "chain_stage:subagent-stop:mem-task:memory": "copy: .dryas/jev/chain.json",
  "command:claude:commit": "copy: .claude/commands/commit.md",
  "command:claude:dryas-cloud": "copy: .claude/commands/dryas-cloud.md (check only, inside a cloud session)",
  "command:claude:handoff": "copy: .claude/commands/handoff.md",
  "command:claude:orchestrate": "copy: .claude/commands/orchestrate.md",
  "command:claude:retro": "exclude: not in the cloud command set (spec E, section 1)",
  "command:claude:tune": "copy: .claude/commands/tune.md",
  "command:claude:wplan": "copy: .claude/commands/wplan.md",
  "command:claude:wreview": "copy: .claude/commands/wreview.md",
  "component:design": "opt-in: --with-design (each skill only with a confirmed licence and a NOTICE line)",
  "component:optional:design": "opt-in: --with-design",
  "component:optional:jev": "copy: the gate and route stages and the jev MCP server; local judge by default",
  "component:optional:memory": "copy: Dryas memory in .dryas/state/; notes in the repo with --persist-memory",
  "component:optional:pstack-picks": "copy: .dryas/pstack/ and the pstack-picks rule blocks",
  "component:optional:ruflo": "exclude: Ruflo needs Node and npm",
  "component:optional:superpowers": "exclude: the Dryas process skills replace it",
  "component:ruflo": "exclude: Ruflo needs Node and npm",
  "component:superpowers": "exclude: the Dryas process skills replace it",
  "mcp_server:claude:jev": "copy: .mcp.json server jev, run from .dryas/jev/jev_mcp.py",
  "plugin_hook:claude:PostToolUse:Bash|Write|Edit|MultiEdit|NotebookEdit:chain.py post": "copy: .claude/settings.json through cloud_hook.py",
  "plugin_hook:claude:PostToolUseFailure:Bash|Write|Edit|MultiEdit|NotebookEdit:chain.py post": "copy: .claude/settings.json through cloud_hook.py",
  "plugin_hook:claude:PreCompact:*:chain.py precompact": "copy: .claude/settings.json through cloud_hook.py",
  "plugin_hook:claude:PreCompact:*:compact_keep.py": "copy: .claude/settings.json through cloud_hook.py",
  "plugin_hook:claude:PreToolUse:Bash|Edit|Write|MultiEdit|NotebookEdit:chain.py pretool": "copy: .claude/settings.json through cloud_hook.py",
  "plugin_hook:claude:SessionEnd:*:chain.py session-end": "copy: .claude/settings.json through cloud_hook.py",
  "plugin_hook:claude:SessionStart:clear:handoff_restore.py": "copy: .claude/settings.json through cloud_hook.py",
  "plugin_hook:claude:SessionStart:compact:compact_restore.py": "copy: .claude/settings.json through cloud_hook.py",
  "plugin_hook:claude:SessionStart:startup|resume|clear|compact:chain.py session-start": "copy: .claude/settings.json through cloud_hook.py",
  "plugin_hook:claude:SessionStart:startup|resume|clear|compact:rules_inject.py": "exclude: the CLAUDE.md rules block carries the rules in a repo copy",
  "plugin_hook:claude:SubagentStop:*:chain.py subagent-stop": "copy: .claude/settings.json through cloud_hook.py",
  "plugin_hook:claude:UserPromptSubmit:*:chain.py prompt": "copy: .claude/settings.json through cloud_hook.py",
  "skill:claude:benchmark-checklist": "exclude: not in the cloud skill set (spec E, section 3); its checklist ships in .dryas/pstack/",
  "skill:claude:brainstorm": "copy: .claude/skills/brainstorm/",
  "skill:claude:debug": "copy: .claude/skills/debug/",
  "skill:claude:interrogate": "copy: .claude/skills/interrogate/",
  "skill:claude:orchestrate": "copy: .claude/skills/orchestrate/",
  "skill:claude:plan": "copy: .claude/skills/plan/",
  "skill:claude:review-receive": "copy: .claude/skills/review-receive/",
  "skill:claude:review-request": "copy: .claude/skills/review-request/",
  "skill:claude:tdd": "copy: .claude/skills/tdd/",
  "skill:claude:verify": "copy: .claude/skills/verify/",
  "skill:claude:worktree": "copy: .claude/skills/worktree/"
 },
 "not_copied": {
  "update-my-vault": "its vault and sources are on the Mac",
  "fo-iterm": "it drives iTerm on the Mac",
  "claude-hud": "a local status line",
  "Ruflo": "needs Node and npm",
  "Superpowers": "the Dryas process skills replace it",
  "Playwright MCP": "needs npm and network",
  "Context7 MCP": "needs network",
  "GitHub MCP": "needs network",
  "Codex files": "cloud sessions run Claude Code"
 }
}
```

The `plugin_hook` and `chain_stage` keys are those D's plan defines; Task 1 pinned them. If `python3 tools/inventory.py --check` (Step 5) names an entry this table lacks, D added a surface this plan does not classify. Stop and report it with the entry; do not guess a row.

- [ ] **Step 4: `tools/inventory.py`.** Add one line to the module docstring after the `--check` line: `reference/cloud-bindings.json (owned core E) must list every core component as copy:, opt-in: or exclude: with a reason; --check enforces it.` After `MAP = "reference/inventory-map.json"`, add:

```python
CLOUD = "reference/cloud-bindings.json"
CLOUD_KINDS = ("command:claude:", "skill:claude:", "agent:claude:", "mcp_server:claude:", "plugin_hook:claude:",
               "chain_stage:", "component:")
CLOUD_VALUES = ("copy:", "opt-in:", "exclude:")
```

After `check(...)`, add:

```python
def cloud_check(current: Iterable[str], table: Any) -> List[str]:
    """The cloud binding table (owned core E): every core component a repo copy could carry is copied, opt-in or
    excluded, each with where it goes or why not, and the table names nothing the inventory lacks."""
    entries = table.get("entries") if isinstance(table, dict) else None
    if not isinstance(entries, dict):
        return ['cloud table: %s has no "entries" object' % CLOUD]
    cur = {e for e in current if e.startswith(CLOUD_KINDS)}
    problems = ["cloud table: %s is neither copied nor excluded" % e for e in sorted(cur - set(entries))]
    problems += ["cloud table: %s is not in the inventory" % e for e in sorted(set(entries) - cur)]
    for k, v in sorted(entries.items()):
        if not (isinstance(v, str) and v.startswith(CLOUD_VALUES) and v.split(":", 1)[1].strip()):
            problems.append("cloud table: %s needs copy:, opt-in: or exclude: and a reason" % k)
    return problems
```

In `main`, directly after the line `problems = check(base, cur, mapping, _json(repo / "install/components.json").keys())` (inside the same `try`), add:

```python
        if (repo / CLOUD).exists():
            problems += cloud_check(cur, _json(repo / CLOUD))
```

- [ ] **Step 5: Run** `python3 tools/inventory.py --check`. Expected: `387 baseline entries, 0 problems`. Then run `python3 -m pytest -q install/tests/test_cloud_bindings.py install/tests/test_inventory.py`; `test_docs_name_the_opt_ins` still fails until Step 6.

- [ ] **Step 6: Docs.** Write `docs/cloud-sessions.md`:

```markdown
# Dryas in cloud sessions

claude.ai/code cloud sessions build from a GitHub repo and load only what the repo commits:
- `.claude/skills`, `.claude/agents` and `.claude/commands`;
- the hooks in `.claude/settings.json`;
- `.mcp.json` and `CLAUDE.md`.

They do not install plugins. `dryas cloud` therefore writes a pinned, version-stamped copy of the Dryas core into the repo. A cloud session on that repo then runs the Dryas workflow with no setup inside the cloud environment. The core is Python stdlib only, so it needs no Node, Ruflo or Superpowers.

## Set a repo up

From a Dryas checkout, on a machine where Dryas is installed:

    install/install.sh --repo ../my-repo               # macOS, Linux, WSL: same as dryas cloud init
    .\install\install.ps1 -Repo ..\my-repo             # Windows
    claude/bin/dryas cloud init --repo ../my-repo      # the dryas command (also: /dryas-cloud init)

Every run first prints a dry run: each file it would add, change or remove, with sizes. Add `--yes` to write. Nothing is committed. The run ends with the `git add` lines and a suggested commit message.

| Option | Effect |
|---|---|
| `--yes` | write; without it the run is a dry run |
| `--force` | write over uncommitted changes in the paths it writes, and over hand edits on update |
| `--prefix P` | rename the copied skills, commands and agent (`P` + name) when the repo has its own of the same name; a clash otherwise stops the run |
| `--with-design` | also copy the design skills, each only with a confirmed licence; the licence text goes to `.dryas/licenses/` and a line to `.dryas/NOTICE` |
| `--with-own NAME` | also copy that skill from your Claude config dir; a secret-shaped line stops it until `--confirm-own NAME` |
| `--persist-memory` | keep short, redacted session notes in `.dryas/memory/notes/`, committed with the work |

`dryas cloud update` refreshes the copy from this checkout. Files you edited by hand are reported as drift and kept unless you pass `--force`. `dryas cloud remove` takes out exactly what Dryas added. `dryas cloud check` reports drift, Mac paths, non-stdlib scripts, missing licences and a copy that is out of date with this checkout.

## What the repo gets

- `.dryas/`: the runtime (`jev/`, `pstack/`, `bin/dryas-py`), `docs/dryas-workflow.md`, `licenses/`, `NOTICE`, `VERSION` and `manifest.json`, which lists every copied file with its source, version, licence and hash.
- `.claude/skills/`, `.claude/commands/`, `.claude/agents/`: the Dryas core skills, the commands `/orchestrate`, `/wplan`, `/wreview`, `/commit`, `/tune`, `/handoff` and `/dryas-cloud`, and the executor agent.
- `.claude/settings.json`: Dryas's hooks (through `.dryas/jev/cloud_hook.py`) and one allow rule, merged with what is there. Dryas adds no `env` entries there; the hook entry sets the copy's paths itself, so nothing leaks into the plugin's hooks on a machine with Dryas installed.
- `.mcp.json`: the `jev` MCP server with its own `env` block, merged with what is there.
- `CLAUDE.md`: the Dryas rules between `<!-- dryas:start -->` and `<!-- dryas:end -->`; the rest of the file is untouched.
- `.gitignore`: `.dryas/state/`, `.dryas/**/__pycache__/` and `.orchestrate/`.

[reference/cloud-bindings.json](../reference/cloud-bindings.json) lists every core component as copied, opt-in or excluded, with the reason. It never copies Ruflo, Superpowers, Codex files, MCP servers that need npm or network, or skills that live only on one machine.

## In the cloud session

- **Judge:** local, so there is no network and no key. To use Jev in one environment, set `DRYAS_JUDGE=jev`, add the secret `OPENROUTER_API_KEY`, and allow `openrouter.ai` in that environment's network settings.
- **State:** `.dryas/state/` holds the logs, threshold overrides and scope-lock files. It is git-ignored and new in every session, and nothing depends on an earlier one.
- **Memory:** within a session, Dryas memory works as on a workstation. With `--persist-memory`, each session end writes a redacted note to `.dryas/memory/notes/`, and the next session start reads the notes back. The notes are plain markdown, reviewed in pull requests.
- **Hooks:** they run as on a workstation: scope lock, gate, memory, observer. A hook that fails internally exits 0, and the gate then asks.

## Check it in CI

    python3 .dryas/jev/cloud_check.py --repo .

It exits 1 on any problem: drift, a Mac path, a non-stdlib script, a missing licence or NOTICE line, the ignore line or the rules block. In a session, `/dryas-cloud check` runs the same check.

## On a machine where Dryas is installed

The plugin's own hooks already run there. The repo copy's hooks see `~/.dryas/chain.local.json` and do nothing outside a cloud session, so the chain does not run twice. Set `DRYAS_CLOUD_HOOKS=1` to run the copy's hooks anyway, or `DRYAS_CLOUD_HOOKS=0` to turn them off everywhere.
```

In `reference/README.md`, add this row at the end of the Bindings table, in the table's current column format:

```markdown
| Harness | Cloud sessions | `dryas cloud` (`tools/dryas_cloud.py`) copies the core into a repo (`.dryas/`, `.claude/`); [cloud-bindings.json](cloud-bindings.json) lists each component as copied, opt-in or excluded, with the reason |
```

In `GLOSSARY.md`, under `## Terms` and in D's line format, add:

```markdown
- **repo copy**: the pinned Dryas core that `dryas cloud` writes into a repo (`.dryas/`, `.claude/`) so claude.ai/code cloud sessions run the workflow without the plugin.
```

- [ ] **Step 7: Codex sync.** Run `python3 tools/sync_codex_plugin.py`, then `python3 tools/sync_codex_plugin.py --check` and expect exit 0. This writes `codex/jev/{cloud_hook,memnotes,cloud_check}.py` and refreshes `providers.py`, `paths.py`, `handoff.py` and `chain.json`. The `mem-notes` stage has no `harness` key, so it stays Claude Code only.

- [ ] **Step 8: Full verification.**
  - `python3 -m pytest -q -rs claude/jev/tests install/tests`: Task 1's count plus 115, every skip explained.
  - `python3 tools/inventory.py --check`: `0 problems`.
  - `python3 tools/sync_codex_plugin.py --check`: exit 0.
  - `git diff --stat <D merge commit>..HEAD -- install/tests claude/jev/tests`: only new files. No test that existed at the D merge changed.
  - Every new Python file is under 500 lines: `wc -l tools/dryas_cloud.py tools/cloud_plan.py tools/cloud_config.py tools/cloud_text.py tools/inventory.py claude/jev/cloud_check.py claude/jev/memnotes.py claude/jev/cloud_hook.py`.

- [ ] **Step 9: Commit** `git add reference/cloud-bindings.json tools/inventory.py install/tests/test_cloud_bindings.py docs/cloud-sessions.md reference/README.md GLOSSARY.md codex/jev`, then `git commit -m "feat(cloud): cloud binding table in the inventory check; docs; codex sync"`.

- [ ] **Step 10: Manual acceptance (Promprit, once; not an executor step).**
  1. On the Mac, run `install/install.sh --repo <small test repo>`, read the dry run, re-run with `--yes`, commit and push.
  2. Open a claude.ai/code session on it, with no environment opt-ins.
  3. Confirm that:
     - the Dryas rules load;
     - `/orchestrate` is offered;
     - `git checkout -- .` asks;
     - `/tune` runs;
     - `.dryas/state/jev/logs/gate.jsonl` shows `"provider":"local"`.
  4. In the cloud session, confirm that the `jev` MCP tools answer and that `.dryas/state/` gets a `dryas.db` after a `memory_store` call (the `.mcp.json` `env` block works).
  5. On the Mac, open Claude Code in the same repo with the plugin installed. Confirm that `.claude/settings.json` has no Dryas `env` entries, that the plugin's hooks run once (the copy's hooks stay quiet), and that the plugin's logs still land in `~/.dryas/jev/logs/`, not in the repo.

---

## Self-review (done while writing)

- **Spec coverage:**
  - Goal and success line: Tasks 9 and 11, and Step 10's manual check.
  - §1:
    - `.dryas/` contents: Task 8;
    - `.claude/` skills, commands and agent: Task 8;
    - settings merge (hooks and one allow rule, no `env`, as amended): Task 7, written by Task 9; the copy's env comes from `cloud_hook.py` (Task 3) and the `.mcp.json` `env` block (Task 7);
    - `.mcp.json`, `CLAUDE.md` block, `.gitignore`: Task 7;
    - relative paths: Tasks 2, 6, 7;
    - clash and `--prefix`: Tasks 8, 9;
    - not copied: Task 8 (`NOT_COPIED`), Task 12.
  - §2:
    - judge: Task 2;
    - state: Tasks 2, 3;
    - opt-in memory: Tasks 3, 4, 8, 11;
    - Python fallback (`bin/dryas-py` copied): Task 8;
    - hooks exit 0 and ask: Task 3;
    - network: Tasks 2, 11.
  - §3: manifest with source, version, licence and hash (Tasks 8, 9); the design, own and excluded groups (Task 8); unconfirmed licences and non-stdlib scripts skipped (Task 8).
  - §4: CLI and its four commands (Task 9); entry points (Task 10); `/dryas-cloud` (Task 8); reuse of `render.py`, `claude_md_block.py`, `settings_merge.py` and `components.json` (Tasks 6–8). `claude_mcp.py` is mirrored, not imported (Decisions).
  - Error handling: Tasks 7 and 9.
  - Testing: every bullet maps to Tasks 9, 11 and 12. The manual acceptance is Task 12 Step 10.
- **Placeholder scan:** every code step has complete code. The executor fits four edits into D's text by anchor:
  - the `install.sh`/`install.ps1` header lines;
  - the `dryas`/`dryas.cmd` cases;
  - the `chain.json` stage;
  - the README and GLOSSARY lines.

  Their exact lines are given; only the position depends on D's final text.
- **Type consistency:** these names agree across Tasks 3–12:
  - `cloud_check.MANIFEST`, `NOTICE`, `VERSION`, `sha256`, `file_sha`, `files_hash`, `check`, `load_manifest`;
  - `cloud_plan.build`, `finish`, `entry` (keys `data`, `source`, `group`, `version`, `licence`, `licence_file`, `notice`, `exec`);
  - `cloud_config.ENTRY`, `hooks`, `fragment`, `add_*`/`remove_*`, `claude_md`/`undo_claude_md`;
  - `cloud_text.Names.name`, `rewrite`, `claude_md_body`, `third_party`, `PLUGIN`;
  - `dryas_cloud.main`, `options`, `KEYS`.
- **Review Focus:** each of the five lines has its test in the owning task. Of what the spec implies, these stay outside automated tests:
  - real cloud behaviour (Task 12, Step 10);
  - Windows wrapper behaviour, tested only on Windows runners;
  - the Mac check that the plugin's state stays in `~/.dryas` (Step 10.5). The `env` question is resolved by the amendment.
