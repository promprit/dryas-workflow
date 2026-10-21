# REA integration: design

Date: 2026-10-21. Status: design approved in chat 2026-10-21 (approach A, sections 1 and 2); written spec awaiting review. Branch: `spec/rea-integration`.
Contested: yes (adds a numbered template rule and a new install component that `run_cmd.select`, the install record and `release_check` depend on).

## 1. Goal

When a request depends on how software we do not have the source for behaves (an app, a binary, an APK, an Electron app, a website), brainstorm recommends investigating it with [REA](https://github.com/morluto/rea) (`rea-agents` on npm, MIT, tested 6.7.0) and uses its evidence in the design. REA is an MCP server plus a bundled skill. Dryas installs it by default as an optional extra, like the design skills.

Success:

- A fresh `install.sh` on a Mac with Node 22.19+ registers the `rea` MCP server and skill for the Claude config dir being installed, after our dry-run and confirmation. `--no-rea` skips it.
- An upgrade of an account that has no `rea` recorded does not install it; `--with-rea` adds it.
- `install.sh --uninstall` removes REA from that config dir only; `--keep-extras` leaves it.
- In brainstorm, a reverse-engineering request gets "investigate with REA first" as a proposed approach, said out loud, declinable. Any other request is unchanged.
- No Node, or a Node that is too old: a warning, REA skipped, the rest of the install goes on.
- **Not worse than 2.3.2** (prompts per task, speed, cost; `tools/compare_release.py`): REA adds no hook, so the hot path is unchanged.

Out of scope: Hopper, Ghidra or IDA installation (REA's own separate opt-in); executors calling REA; cloud installs; OpenCode; tracking REA versions past 6.7.0 automatically.

## 2. Decisions

| # | Decision |
| --- | --- |
| D1 | Trigger: the request depends on behaviour of third-party or closed-source software. Brainstorm says when it recommends REA; the user can decline. |
| D2 | Rule in `claude/CLAUDE.md.template` plus a note in brainstorm `reference.md` § Exploring approaches. |
| D3 | Full install component `rea`, on for fresh installs (`FRESH`), recorded in `.dryas-plugin.json`, flags `--no-rea` / `--with-rea` (approach A). Its own module `install/rea_setup.py`, not `thirdparty`/`components.json`. |
| D4 | Pinned: `npx -y rea-agents@6.7.0`. Run once per config dir with `CLAUDE_CONFIG_DIR` (Claude) or `CODEX_HOME` (Codex) set. |
| D5 | No native engines installed. Static JS, .NET and web analysis need none. |
| D6 | Executors never call REA. Plan task sections that need a REA finding carry the copied evidence. |
| D7 | Uninstall is per config dir (`claude mcp remove --scope user rea` + the skill folder); never the global `rea uninstall`, which acts on every client. |
| D8 | Not in cloud installs (`dryas_cloud`, `cloud_plan`): REA needs local tools. |

## 3. Workflow behaviour

### 3.1 Template (`claude/CLAUDE.md.template`)

New line directly after the design line:

`- Reverse-engineering work (how software you don't have the source for does something): use REA; brainstorm says when it recommends it, the user can decline.`

Kept short: the Claude template is at its byte budget (`install/tests/test_template_budget.py`), which this change raises deliberately.

Added to `codex/AGENTS.md.template` too; the process-skill changes are rendered to `codex/` and `opencode/` by `tools/sync_codex_plugin.py`. `docs/template-coverage.md` is not changed: it maps the frozen pre-2.0 lines only.

### 3.2 Brainstorm (`claude/skills/brainstorm/reference.md` § Exploring approaches)

A short paragraph:

- When the request depends on behaviour of software we do not own, one proposed approach is "investigate with REA first". State why it fits.
- REA's findings (evidence and stated limitations) go into the design artifact: the written spec for architectural work, the in-chat design for bounded work, the findings for a spike.
- If the `rea` MCP tools are not available in the session, say so and give the install command (`install.sh --with-rea`) instead of failing; the other approaches stay on the table.

`SKILL.md` is unchanged (its process section already points to § Exploring approaches).

### 3.3 Plan (`claude/skills/plan`)

One line in the task-section guidance: a task that depends on a REA finding carries the finding's evidence in its section; executors do not call REA.

### 3.4 Docs (`docs/workflow.md`)

- §4 step 1: a "Reverse-engineering work" paragraph next to "Design work", stating D1, D6 and the declinable recommendation.
- The tools table (where `impeccable`, `ui-ux-pro-max` are listed): a row `MCP `rea` + skill | Reverse engineering of software without source (§4 step 1)`.

## 4. Installer

### 4.1 Module (`install/rea_setup.py`, new)

REA is not a Claude plugin, so it does not go through `run_cmd.thirdparty` or `install/components.json` (`thirdparty` reads `plugin`/`tested` for every component it gets and aborts the install on a non-zero exit). REA gets its own module, Python 3.9 stdlib only, under 500 lines:

- Constants: `VERSION = "6.7.0"`, `PKG = "rea-agents@6.7.0"`, `MIN_NODE = ((22, 19), (24, 11), (26, 0))`.
- `node_ok(run=...) -> Optional[str]`: runs `node --version`; returns `None` when Node meets `MIN_NODE` (major 22 needs >=22.19, 24 needs >=24.11, 26 or later passes; 23 and 25 fail), else the warning text. No `node` or no `npx` on PATH also returns the warning.
- `setup_argv(client)`, `dry_run_argv(client)`, `doctor_argv(client)`: `npx -y rea-agents@6.7.0 setup --client <client> --yes --format json`, the same with `--dry-run` in place of `--yes`, and `doctor --client <client> --skill --format json`.
- `install(client, env, yes, dry_run) -> Optional[dict]`: the flow in 4.3; returns the record entry (4.3) or `None` when skipped or failed. Never raises, never returns a failing exit code to the caller.
- `uninstall_cmds(entry, client, env) -> List[List[str]]` and `uninstall(...)`: 4.5.

Confirmed against `rea-agents@6.7.0` on 2026-10-21 (probe and a real install on this Mac's four accounts): the flags above; `setup --dry-run --format json` returns `{"status": "planned", "plannedActions": [...]}` where the action with `kind == "install_skill"` has `target` = the skill directory (`<config dir>/skills/reverse-engineer-anything`); `setup --yes` returns `status: "ready"`; `doctor` returns `identity.skill.state` (`aligned` when ready, `missing` otherwise) and `identity.registrations[]` with `client` and `state`, but no skill path. For the default account (`~/.claude`, config `~/.claude.json`) `CLAUDE_CONFIG_DIR` must be unset, not set to `~/.claude`. The Codex removal command is confirmed in the plan's Codex task.

Existing accounts on this Mac (`~/.claude`, `~/.claude-team`, `~/.claude-team2`, `~/.claude-team2-vipa`) got REA by hand on 2026-10-21. Their `.dryas-plugin.json` does not record it; the next `install.sh --with-rea` re-runs setup (idempotent: REA reports `aligned`) and records it.

### 4.2 Selection (`install/run_cmd.py`)

- `rea` joins `OPTIONAL` and `FRESH`.
- `--with-rea` is added: every hard-coded `("ruflo", "superpowers", "design")` tuple for `with_*` flags in `run_cmd.py` (the `parse` loop and contradiction check, `select`, the `no_flags` check that the Codex legacy-record path depends on) gains `"rea"`. The plan replaces them with one module constant `WITH = ("ruflo", "superpowers", "design", "rea")`.
- Upgrade: the recorded component list wins, so an account without `rea` recorded does not get it unless `--with-rea`.
- `plugin_setup.py` keeps passing only `ruflo`, `design`, `superpowers` to `thirdparty`; after it, when `rea` is selected, it calls `rea_setup.install("claude_code", env, yes, dry_run)` with the same `env` (which carries `CLAUDE_CONFIG_DIR`). For the default dir `~/.claude`, `rea_setup` removes `CLAUDE_CONFIG_DIR` from the env it passes to REA (REA then targets `~/.claude.json`).

### 4.3 Running it

1. Node check (`node_ok`). Failing: print `warning: REA needs Node.js 22.19+, 24.11+ or 26+; skipped (install Node, then re-run with --with-rea).`, return `None`.
2. `--dry-run` of our installer: print the `setup_argv` it would run, run nothing, return `None`.
3. Run `dry_run_argv` and print its output, then ask `Install REA? [y/N]` (`dryas_install.confirm`, the installer's usual prompt). This is REA's own prompt, separate from and after the batch "Run these?" of `thirdparty`, so REA's planned changes are always shown before they are approved. `--yes` skips the question (the dry run is still printed). Declined: `skipped REA`, return `None`.
4. Run `setup_argv`. Non-zero exit: `warning: REA setup failed (exit N); REA is optional, Dryas setup continues`, return `None`. REA's setup backs up the configuration it edits and pins its MCP registration to the exact version.
5. The skill path is the `target` of the `install_skill` action in step 3's dry-run JSON. Missing or unparsable: `skill_dir` is `null`. Then run `doctor_argv` and require `identity.skill.state == "aligned"`; otherwise warn (still record, so uninstall can clean up).
6. Return the record entry `{"version": "6.7.0", "client": "claude_code", "skill_dir": "<path>" | null}`.

Record (`.dryas-plugin.json`): on a returned entry, `rea` is added to `components` and the entry is stored under a new key `rec["rea"]`. Nothing about REA goes into `rec["thirdparty"]`, so the generic third-party uninstall never sees it. On `None`, `rea` is left out of `components`.

### 4.4 Codex and OpenCode

- `--harness codex|both|all`: for the Codex home, `rea_setup.install("codex", env_with_CODEX_HOME, ...)`; the entry goes under `rea` in the Codex record.
- OpenCode: skipped with the existing note pattern ("REA is not set up for OpenCode; skipped").

### 4.5 Uninstall

- Per config dir, when `rec["rea"]` exists: `claude mcp remove --scope user rea` with `CLAUDE_CONFIG_DIR` set, then remove `skill_dir` if recorded and it is a real directory (not a symlink) whose name contains `rea`. Codex: the Codex removal command confirmed in the plan's Codex task, with `CODEX_HOME` set, then its `skill_dir`.
- No `skill_dir` recorded: nothing is deleted by guess; the uninstall prints the manual step instead.
- Listed in the uninstall plan and confirmed like the other extras; `--keep-extras` leaves REA and prints the commands; `--yes` runs them.
- A failed removal is a warning; the uninstall goes on.
- Never run `rea uninstall` (D7).

### 4.6 Windows (`install/install.ps1`)

Same flags passed through to `run_cmd.py`; usage line updated.

### 4.7 Cloud

`tools/dryas_cloud.py` and `tools/cloud_plan.py` never select `rea` (D8). Their tests assert it.

### 4.8 Release check (`tools/release_check.py`)

When `rec["rea"]` exists in the config dir's `.dryas-plugin.json`: run `npx -y rea-agents@6.7.0 doctor --client claude_code --skill --format json` with `CLAUDE_CONFIG_DIR` set and report `identity.skill.state`. Not `aligned`, or the command failing: a warning, not a failure. Not recorded: skipped, not reported as missing.

### 4.9 Docs (`docs/install.md`)

The component row (REA, tested 6.7.0, skip with `--no-rea`), the flag rows (`--no-rea`, `--with-rea`), the Node prerequisite, the uninstall note (per config dir; `rea uninstall` never run), the `--keep-extras` list.

## 5. Testing

In the existing `install/tests` style, with REA's commands mocked (no network in tests):

- `select`: fresh includes `rea`; `--no-rea` removes it; upgrade without `rea` recorded excludes it; `--with-rea` adds it; `--with-rea --no-rea` errors.
- Node check: 22.18 / 23.x / 25.x skip with the warning; 22.19 / 24.11 / 26.0 pass; no `node` skips.
- Install run (`rea_setup`): env carries `CLAUDE_CONFIG_DIR`; dry-run output shown before the real setup; decline skips; `--yes` skips the question; setup failure is a warning, exit code of the whole install stays 0, nothing recorded; doctor without a skill path records `skill_dir: null`; `rec["thirdparty"]` never contains a REA argv.
- `thirdparty` is never called with `rea`; `components.json` is unchanged.
- Codex: `--client codex` and `CODEX_HOME`.
- Uninstall: the two removal commands with the right env, the recorded skill dir removed, `rea uninstall` never appears in any argv; `--keep-extras` runs nothing.
- Cloud: `rea` never selected.
- Release check: recorded and ready → ok; not ready → warning; not recorded → skipped.
- Template budget test passes with the raised Claude budget; `tools/sync_codex_plugin.py --check` passes.
- Existing tests whose expected component lists change (`test_providers_install.py`, `test_plugin_setup.py`, `test_launch_docs.py` flag list) are updated to include `rea` where fresh defaults apply.

## 6. Risks

- REA changes quickly; the pin means updates are deliberate (bump `tested` and the version in one change).
- REA's setup writes the account's MCP config. Mitigated by our dry-run and confirmation (workflow rule: ask before any change to an account's configuration) and REA's own backups.
- Runtime analysis (process capture, browser observation) runs targets with the user's permissions; REA's guides describe the effects. Brainstorm recommends, the user decides (D1).
