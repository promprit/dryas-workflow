# Install

```
git clone https://github.com/promprit/dryas-workflow
cd dryas-workflow
./install/install.sh
```

On Windows, use `.\install\install.ps1` (see [Windows](#windows-native)).

The installer asks before it changes anything (`--yes` answers every question). Use `--dry-run` first to see what it would do.

## Claude Code: plugin plus setup

For Claude Code, Dryas is a plugin, `dryas@dryas-workflow`, served from your clone (the repo is its own marketplace). The installer runs setup for one Claude config dir:

1. `claude plugin marketplace add <clone>` and `claude plugin install dryas@dryas-workflow`, run against that dir. `CLAUDE_CONFIG_DIR` is set only for a non-default dir. For `~/.claude`, leave it unset: setting it makes Claude Code read `~/.claude/.claude.json` instead of `~/.claude.json`, which hides your user-scope MCP servers. The plugin brings the rules (injected at session start), the hooks, the scope lock, the Jev chain, the Jev MCP server, the agents, commands and skills. The hooks run `"${DRYAS_PY:-python3}"`: setup records the Python it ran with as `DRYAS_PY` in that dir's `settings.json` env; change that value there to pick another interpreter.
2. The components you selected: the owned core (Dryas memory, Dryas skills, the local judge) needs nothing third-party; the optional extras (Ruflo, Superpowers) and the design skills are third-party installs.
3. A merge into that dir's `settings.json`: model, env and permission rules only (plus the Ruflo hooks when the Ruflo extra is on). It asks first.
4. Shared state in `~/.dryas`: the workflow reference (`docs/dryas-workflow.md`), `chain.local.json` (which optional stages are on) and `accounts.json` (the config dirs set up so far).

If the plugin install or its check fails, setup stops before it touches `settings.json`.

### Several accounts

Run setup once per config dir. The default dir is `$CLAUDE_CONFIG_DIR`, else `~/.claude`:

```
./install/install.sh                                # ~/.claude
./install/install.sh --claude-dir ~/.claude-team    # a second account
```

Both accounts share one `~/.dryas` (logs, thresholds, handoffs). See [harnesses.md](harnesses.md#several-accounts-t3-code-personal-and-team).

Claude Code runs the plugin in place from your clone (`<clone>/claude`), so `git pull` updates it for every account; the change takes effect at the next session start or after `/reload-plugins`. Switching branches in the clone changes the live plugin for every account at its next session. Re-run setup for each dir after you move the clone (the permission rules name the clone's path) or when you change components or the settings setup merges.

Component choices are shared: the `--no-` flags write `~/.dryas/chain.local.json`, which every account and every Codex home read. Setup warns when a run changes them while another account or a Codex home uses them.

### FlowObserve

`--flowobserve` turns on the FlowObserve stage of the Jev chain (it runs `~/.flowobserve/bin/fo_hook.py`, observe-only). `--no-flowobserve` turns both FlowObserve stages off (the two flags exclude each other). With neither flag, a setting you already have is kept; new installs leave it off. Codex does not read this setting.

### The OpenRouter key

Jev calls OpenRouter. The recommended way to give it the key is your shell profile (`export OPENROUTER_API_KEY=...`): the hooks and the Jev MCP server read `OPENROUTER_API_KEY` first, and setup does nothing with it.

Only if you pass `--openrouter-key KEY` does setup also store the key as the plugin option `openrouter_key`, which Claude Code keeps in its secure storage and hands to the hooks and the Jev MCP server. That helps when Claude Code is started from the GUI, which does not read your shell profile. The flag puts the key on the `claude plugin install` command line, so other processes on this machine can see it briefly while that command runs.

### Migration from a copy install

Earlier versions copied files into `~/.claude`. When setup finds such an install in the target dir, it migrates it first:

1. State moves to `~/.dryas`: `jev/logs`, `jev/handoff` and `jev/compact` are merged in, your `/tune` values in `thresholds.json` (only those that differ from the shipped defaults) move to `~/.dryas/jev/thresholds.json`, and `docs/dryas-local.md` is copied to `~/.dryas/docs/dryas-local.md`. Stages you turned on or off in `jev/chain.json` carry over to `chain.local.json`.
2. Only then is the copy install removed, exactly as `--uninstall` used to remove it.
3. Setup installs the plugin as above.

Data always moves before anything is removed. If removal fails, re-run the installer: state is not merged twice (the data root records which dirs were merged in `jev/.migrated.json`). A second run on a migrated dir is a no-op for the migration.

If an old Codex copy install still runs from that dir's runtime files, a `--harness claude` run stops and changes nothing: run with `--harness both` to move Claude Code and Codex to their plugins together (or remove the Codex copy install first with `--uninstall --harness codex`).

### Uninstall and purge

```
./install/install.sh --uninstall                              # ~/.claude only
./install/install.sh --uninstall --claude-dir ~/.claude-team  # one other dir
./install/install.sh --uninstall --purge                      # last account: also remove ~/.dryas
```

`--uninstall` works on one config dir: it runs `claude plugin uninstall dryas@dryas-workflow` there, removes only the settings entries setup added, and drops that dir from `~/.dryas/accounts.json`. It first lists exactly what it will remove (the command, the settings file or the entries in it, the record, the `accounts.json` entry and, with `--purge`, each path under `~/.dryas`) and asks `Proceed?`; `--yes` answers yes. It leaves the shared `~/.dryas` state (logs, thresholds, handoffs, `dryas.db`, the Ruflo runtime) in place by design, since other accounts or Codex may use it. The `dryas-workflow` marketplace stays registered in that dir; that is harmless, and `claude plugin marketplace remove dryas-workflow` (same config dir) removes it.

The third-party plugins setup installed for that dir (the Ruflo plugins `ruflo-core`, `ruflo-swarm`, `ruflo-testgen` and `ruflo-jujutsu`, Impeccable and UI UX Pro Max) are recorded in the dir's `.dryas-plugin.json` as setup ran them. `--uninstall` lists the `claude plugin uninstall <id>` commands that undo them and asks `Remove them too?`; `--yes` runs them, `--keep-extras` leaves them without asking (the commands are printed for later). The global `npm uninstall -g ruflo` is offered only on the last account, when no other Claude config dir or Codex home is listed in `accounts.json` (every account and Codex share the npm package). Their marketplaces (`ruflo`, `impeccable`, `ui-ux-pro-max-skill`) are never removed, since you may have installed other plugins from them; the `claude plugin marketplace remove` commands are printed. A failed removal is a warning; the uninstall goes on.

**Legacy cleanup.** For an account Dryas set up (its record exists in that dir), uninstall also offers the pre-2.0 Ruflo pieces still on the machine, offered by default and skipped with `--keep-extras`, each asked separately (under `--uninstall --yes` only the extras Dryas installed, listed above, are removed; every other legacy item is printed with its command and left for you to run): the Ruflo plugins, the global `npm uninstall -g ruflo` (last account only) and the `ruflo` folder under the data root. The folder is offered only on the last account and when no other account's install record lists Ruflo; the Ruflo folder is never removed by `--yes` (the exact `rm -rf` command is printed), and if `dryas.db` has no rows imported from Ruflo the prompt says the memory was never imported and names `dryas memory import-ruflo`. A dir Dryas never set up is not offered any of it.

`--purge` also removes the entries Dryas owns in `~/.dryas` (`accounts.json`, `chain.local.json`, `docs`, `jev`, `ruflo`), and only when `accounts.json` lists no other Claude config dir and no Codex home (`claude_dirs` and `codex_dirs`) and no old Codex copy install uses it (uninstall each Codex home first, or in the same run with `--harness both`). That deletes your Jev logs, your `/tune` thresholds, saved handoffs and Ruflo memory. It keeps your Dryas memory (`dryas.db` is not among the entries Dryas removes) and your notes in `~/.dryas/docs/dryas-local.md`. It refuses when `accounts.json` is missing or unreadable or the dir's record cannot be read (that dir then stays listed), and it never removes files Dryas did not create.

With `--harness codex` or `both`, `--uninstall` also removes the Codex plugin from one Codex home; see [Codex uninstall and purge](#codex-uninstall-and-purge).

### Hooks blocked by policy

Plugin hooks run as soon as the plugin is installed; there is no per-hook approval. An organization policy with `allowManagedHooksOnly` in managed settings blocks them. Then the rules, the scope lock and the Jev chain do not run, even though `/plugin` shows dryas as enabled. Ask your admin to allow the plugin's hooks.

### Manual plugin route

Manual route, inside Claude Code:

```
/plugin marketplace add promprit/dryas-workflow
/plugin install dryas@dryas-workflow
```

(Shell form: `claude plugin install dryas --marketplace promprit/dryas-workflow`.) This gives you the plugin only: the rules, hooks, scope lock, judge chain, Dryas memory, agents, commands and skills. It does not give you what setup merges into that dir's `settings.json`: the `model` setting, the `env` the hooks need (`DRYAS_PY`, `DRYAS_DATA_ROOT`, the Ruflo paths), the `permissions.allow` rules that let `/tune`, `/handoff` and the Jev scripts run without a prompt, and, when you add Superpowers (`--with-superpowers`), the `permissions.deny` rules that keep its skills Dryas replaces out of the way. Without them the hooks run with your default Python, and the shared state in `~/.dryas` is not set up. Run `install/install.sh` for all of that.

## Components

| Component | What it adds | Upstream |
| --- | --- | --- |
| Workflow core | The `dryas` plugin: rules, agents, commands, hooks, the scope lock and the Dryas process skills | this repo |
| Jev (judge) | The gate and routing hooks and the `jev` MCP server, with the [TypeSafe skills](https://github.com/typesafe-ai/skills). The judge is `local` (deterministic rules, no key) or `jev` (OpenRouter) | on by default; `--no-jev` = `--judge local` |
| Memory | Dryas memory: the memory stages and the memory tools in `~/.dryas/dryas.db` | on by default; `--no-memory` skips |
| Ruflo (optional extra) | Alternative memory provider and its hooks and plugins ([ruvnet/ruflo](https://github.com/ruvnet/ruflo), latest; tested 3.53.0). Needs Node and npm | off by default; `--with-ruflo` adds, `--no-ruflo` skips |
| Superpowers (optional extra) | The upstream process skills ([obra/superpowers](https://github.com/obra/superpowers), from the `claude-plugins-official` marketplace; plugin tested 6.4.1) | off by default; `--with-superpowers` adds, `--no-superpowers` skips |
| Design skills | [Impeccable](https://github.com/pbakaus/impeccable) (latest; tested 4.5.0) and [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | `--no-design` skips |
| pstack picks | Interrogate review, cleanup, benchmark checklist and principles, adapted from [pstack-claude](https://github.com/michael-denyer/pstack-claude) (see NOTICE.md) | `--no-pstack-picks` skips |

> Deprecated: removed in a future release. Dryas memory and the Dryas skills replace them. Bring 1.x Ruflo memory across with `dryas memory import-ruflo`. (Applies to the Ruflo and Superpowers rows above.)

Dryas installs the latest version of each component. If Dryas's Ruflo patches do not apply to the latest Ruflo, the installer falls back to the tested version. A weekly CI job checks the latest Ruflo.

You need [Claude Code](https://docs.claude.com/en/docs/claude-code), the Codex CLI, or both, installed first.

### Fresh install and upgrade

- **Fresh install:** the owned core: Jev (the gate, the route hint and the `jev` MCP server), Dryas memory, the design skills and the pstack picks. No key, no Node and no third-party process plugin is needed. Ruflo and Superpowers are off until you pass `--with-ruflo` or `--with-superpowers`.
- **Upgrade** (setup finds the components a previous run recorded): you keep what you have. An install that has Ruflo keeps Ruflo memory, with the Dryas memory stages off; one that has Superpowers keeps it; a recorded judge setting is left alone. Nothing is uninstalled unless you pass a `--no-` flag. A flag-less rerun of a 1.x `--no-jev` install keeps its gates off; passing `--no-jev` or `--judge` turns the local or Jev gates on. Without Ruflo recorded, an upgrade adds Dryas memory.

### Preflight

Setup needs Python 3.9+, git and the CLI of each harness you chose. Node, npm and the check for a space in your home or Python path apply only with Ruflo (`--with-ruflo`, or `--memory ruflo`); on a machine without Node, setup says that only Ruflo needs it and names `--with-ruflo` as the cause. `--preflight-only` runs the checks and stops.

### `dryas memory`

Setup installs a `dryas` command with the plugin (`claude/bin/dryas`; `claude/bin/dryas.cmd` on Windows): `dryas memory import-ruflo [--from PATH]`, `dryas memory consolidate [--ns NS]` and `dryas memory stats [--ns NS]`. `--db PATH` or `DRYAS_DB` picks another store.

### Cut-over from 1.x

To move a 1.x install (Ruflo, Superpowers and a Jev key) to the owned core:

1. Run `install.sh --judge jev --memory dryas`. This switches memory to Dryas; Ruflo stays installed as an extra unless you pass `--no-ruflo`. The local judge stays as shadow (`judge.shadow` is `auto`), so `/tune` can compare the two.
2. Run `dryas memory import-ruflo`. It copies your Ruflo memory into `dryas.db` read-only, is safe to repeat, and leaves `~/.dryas/ruflo` in place.
3. The legacy cleanup is offered by `--uninstall`, not by setup (see [Uninstall and purge](#uninstall-and-purge)); to remove the Ruflo extra earlier, run setup with `--no-ruflo` and then uninstall.
4. Keep working. Ruflo and Superpowers keep running as extras until you drop them.
5. Flip to `--judge local` when `/tune` proposes it, once the local judge has agreed with Jev for long enough.

## Reference stack

These are the reference implementation's bindings, not part of the method; each layer can be bound to something else. The Dryas core is always on; every other part is a choice.

| Part | What it does | Choose with |
| --- | --- | --- |
| [Claude Code](https://docs.claude.com/en/docs/claude-code), [Codex](https://developers.openai.com/codex) or [OpenCode](https://opencode.ai) | The host: agents, hooks, commands | required |
| Dryas core | The local judge, Dryas memory (`~/.dryas/dryas.db`) and the process skills (`dryas:brainstorm`, `dryas:worktree`, `dryas:tdd`, `dryas:verify` and more) | always installed |
| [Jev model (TypeSafe)](https://github.com/typesafe-ai/skills) | Upgrades the judge: decision support and gates through OpenRouter | `--judge jev` or `--openrouter-key` |
| [Ruflo](https://github.com/ruvnet/ruflo) | Optional memory and orchestration | `--with-ruflo` (`--memory ruflo`) |
| [Superpowers](https://github.com/obra/superpowers) | Optional alternative process skills | `--with-superpowers` |
| [Impeccable](https://github.com/pbakaus/impeccable) and [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | Design skills, installed by default | skip with `--no-design` |
| [pstack](https://github.com/michael-denyer/pstack-claude) picks | Interrogate review, cleanup, benchmark checklist, executor principles (vendored, adapted) | skip with `--no-pstack-picks` |

> Deprecated: removed in a future release. Dryas memory and the Dryas skills replace them. Bring 1.x Ruflo memory across with `dryas memory import-ruflo`. (Applies to the Ruflo and Superpowers rows above.)

Optional, installed separately: [FlowObserve](https://github.com/promprit/flowobserve), an observe-only monitor for live Claude Code sessions. With Dryas it also shows escalations, one build lane per plan task, Jev spend against budget and per-stage timings. It never blocks or changes anything.

## Flags

| Flag | Effect |
| --- | --- |
| `--judge local\|jev` | The judge provider. `local` decides with deterministic rules, no key and no network; `jev` asks Jev through OpenRouter and needs `OPENROUTER_API_KEY`. Writes `judge.provider`; without the flag the setting is left alone (default `auto`: Jev when a key is set, else local) |
| `--memory dryas\|ruflo\|none` | The memory provider. `dryas` is the default on a fresh install; `ruflo` installs the Ruflo extra and turns the Dryas memory stages off; `none` removes both |
| `--with-ruflo` | Add the Ruflo extra (needs Node and npm) |
| `--with-superpowers` | Add the Superpowers extra |
| `--with-design` | Add the design skills (they are on by default; this keeps them on an upgrade that dropped them) |
| `--no-memory` | Do not use Dryas memory |
| `--no-jev` | Alias for `--judge local`: the gate stays on with the local judge. On a flag-less upgrade of an install that had no Jev, the gates stay off; passing `--no-jev` or `--judge` turns them on |
| `--no-ruflo` | Do not install Ruflo, or drop it on an upgrade |
| `--no-superpowers` | Do not install Superpowers, or drop it on an upgrade. Codex never installs it |
| `--no-design` | Do not install Impeccable or UI UX Pro Max |
| `--no-pstack-picks` | Do not install the pstack picks |
| `--yes` | Answer yes to every question: the third-party installs, the settings merge, the uninstall and purge confirmation, the removal of the third-party plugins and, for Codex, the hook trust |
| `--force` | No effect: Claude Code and Codex both install a plugin, so there are no copied files to replace (kept so older scripts still run) |
| `--dry-run` | Print the plan and the settings diff, change nothing (skips third-party installs and verify) |
| `--uninstall` | Remove Dryas from one Claude config dir, or with `--harness codex\|both` from one Codex home (`--codex-dir`) |
| `--purge` | With `--uninstall`: also remove Dryas's entries in `~/.dryas` (logs, `/tune` thresholds, handoffs; keeps `dryas-local.md`) when no other Claude config dir or Codex home uses it. The paths are listed and confirmed first |
| `--keep-extras` | With `--uninstall`: leave the third-party plugins setup installed (Ruflo plugins, Impeccable, UI UX Pro Max, the global `ruflo` npm package) in place without asking |
| `--preflight-only` | Run the prerequisite checks and stop |
| `--harness claude\|codex\|both\|opencode\|all` | Choose what to install for. Claude Code is the default. `both` is Claude Code and Codex; `all` adds OpenCode |
| `--claude-dir DIR` | The Claude config dir to set up (default `$CLAUDE_CONFIG_DIR`, else `~/.claude`) |
| `--codex-dir DIR` | The Codex home to set up, one per run (default `$CODEX_HOME`, else `~/.codex`) |
| `--opencode-dir DIR` | The OpenCode config dir to set up, one per run (default `$XDG_CONFIG_HOME/opencode`, else `~/.config/opencode`) |
| `--tier-fast P/M`, `--tier-standard P/M`, `--tier-strong P/M`, `--tier-frontier P/M` | OpenCode only: the `provider/model` each executor tier uses |
| `--flowobserve` | Turn on the FlowObserve stage |
| `--no-flowobserve` | Turn the FlowObserve stage off (not with `--flowobserve`) |
| `--openrouter-key KEY` | Implies `--judge jev`. Claude Code only: also store the key as the plugin option (explicit only; see [the key](#the-openrouter-key)). Codex ignores it |

`--yes` skips every confirmation: the third-party installs, the settings merge (the diff is still printed), the uninstall and purge confirmation, the removal of the third-party plugins on uninstall and, for Codex, the hook trust question (see [Hook trust](#hook-trust)). Without it the installer asks before each of these.

## Windows (native)

Prerequisites: Python 3.9 or newer (python.org installer or `winget install Python.Python.3.12`), Git for Windows, Node.js 20+ (only for the Ruflo extra), and the Claude Code and/or Codex CLI.

Claude Code runs plugin hooks with Git Bash, so Git for Windows must be installed. The Jev MCP server starts with `python3`: make sure `python3` resolves on your PATH (enable the `python3` app alias or add Python to PATH). Setup warns when it does not (when Jev is selected).

Codex on Windows runs the plugin hooks' `commandWindows` lines, which start `python`; setup warns when `python` is not on PATH. This path is not yet verified on a real Windows machine: after setup, run the [release check](release-check.md) and its manual Codex steps (3 and 7) before you rely on the scope lock.

```powershell
git clone https://github.com/promprit/dryas-workflow.git
cd dryas-workflow
.\install\install.ps1
```

If PowerShell refuses to run scripts: `powershell -ExecutionPolicy Bypass -File .\install\install.ps1`.
If your user folder or Python path contains a space and Windows has no short (8.3) name for it, Ruflo cannot be installed (the check applies only with `--with-ruflo`). The installer says so and suggests leaving Ruflo out; the owned core installs.

## WSL

Inside WSL, follow the Linux steps (`./install/install.sh`). WSL and native Windows installs are separate: each has its own home folder.

## Codex: plugin plus setup

For Codex, Dryas is a Codex plugin with the same id, `dryas@dryas-workflow`, served from your clone (Codex reads `.agents/plugins/marketplace.json`; the plugin is `codex/`). Codex 0.162.1 or newer is required. `--harness codex` sets up Codex only, `--harness both` Codex and then Claude Code. For one Codex home (`CODEX_HOME`) setup runs:

1. `codex plugin marketplace add <clone>` and `codex plugin add dryas@dryas-workflow`, both with `CODEX_HOME` set to that home. Codex copies the plugin to `$CODEX_HOME/plugins/cache/dryas-workflow/dryas/<version>/`. The plugin brings the rules (injected by a SessionStart hook), the skills, the scope lock, the Jev gate and route hint, and the Jev MCP server.
2. If an old Codex copy install is found there, the [migration](#migration-from-the-codex-copy-install).
3. One marked block in that home's `config.toml`, between `# >>> dryas plugin >>>` and `# <<< dryas plugin <<<`: the Ruflo MCP server only when the Ruflo extra is on, and a Jev MCP fallback when `python3` 3.9+ is not found ([Python](#python)). Setup never writes a key into `config.toml`.
4. Hook trust, after you agree (see [Hook trust](#hook-trust)).
5. Shared state in `~/.dryas`, the same as for Claude Code: the workflow reference, `chain.local.json` and `accounts.json` (Codex homes are listed under `codex_dirs`).

If the marketplace add, the plugin add or the plugin listing fails, setup stops before it writes the config block, trust, `chain.local.json` or `accounts.json`.

The Dryas skills ship in the Codex plugin. Superpowers and the design skills are Claude Code plugins; setup skips them for Codex.

### Several Codex homes

Run setup once per Codex home. `--codex-dir` takes one home per run; the default is `$CODEX_HOME`, else `~/.codex`:

```
./install/install.sh --harness codex                            # ~/.codex
./install/install.sh --harness codex --codex-dir ~/.codex-work  # a second Codex account
```

All Codex homes and Claude config dirs share one `~/.dryas`.

### Hook trust

Codex runs a plugin hook only after you trust it. Trust is stored per Codex home and covers the hook's exact entry (event, matcher, command line, timeout), not the script it runs. Until the Dryas hooks are trusted, Codex skips them silently: no rules at session start, no scope lock, no Jev gate.

Setup lists the Dryas hooks that are not trusted yet and asks `Trust these Dryas hooks?`. If you agree (or pass `--yes`), it trusts exactly those hooks, the same way Codex's `/hooks` screen does, and no others. If you decline, nothing is trusted: open Codex, run `/hooks` and trust the Dryas hooks there. A release that changes a hook's command line needs trust again; setup asks when you re-run it.

### Python

The Codex hooks run `python3` (3.9 or newer) from your PATH, unless `DRYAS_PY` names another interpreter; the plugin's Jev MCP server starts `python3` too. On macOS and Linux the installer stops when `python3` is missing or older than 3.9. On Windows it only warns (see [Windows](#windows-native)); when `python3` 3.9+ is not found there, setup starts the Jev MCP server with the installer's own Python instead (the fallback in the config block; re-run setup after each update).

### The OpenRouter key in Codex

Codex hooks and the Jev MCP server read `OPENROUTER_API_KEY` from the shell Codex runs in (the MCP server gets it through `env_vars`). Set it in your shell profile. `--openrouter-key` is Claude Code only; Codex ignores it and the installer says so.

### Update

`git pull` in the clone, then re-run setup for each Codex home. Unlike Claude Code, Codex runs a copy of the plugin (in `$CODEX_HOME/plugins/cache`), so a pull alone does not change what Codex runs; re-running `codex plugin add` (which setup does) refreshes the copy.

### Migration from the Codex copy install

Earlier versions copied the Codex edition into four places: a block in `~/.codex/AGENTS.md`, skills in `~/.agents/skills`, entries in `~/.codex/hooks.json` and MCP servers, all running Python from a runtime copy in `~/.claude`. Setup for that Codex home removes them after the plugin is added: the `AGENTS.md` block, the skills, the hook entries and the MCP servers the copy install added, and then the runtime copy in `~/.claude` (its state moves to `~/.dryas` first, as in the [Claude Code migration](#migration-from-a-copy-install)). The runtime copy stays while another Codex home still has a copy install; setup says so. Your data is already in `~/.dryas` and stays. If a step fails, re-run the installer: it resumes.

A `--harness claude` run on a `~/.claude` that an old Codex copy install still uses stops and asks for `--harness both`.

### Codex uninstall and purge

```
./install/install.sh --uninstall --harness codex                            # ~/.codex only
./install/install.sh --uninstall --harness codex --codex-dir ~/.codex-work  # one other Codex home
./install/install.sh --uninstall --harness both --purge                     # last Claude dir and Codex home
```

`--uninstall --harness codex` works on one Codex home: it runs `codex plugin remove dryas@dryas-workflow`, removes the marketplace (when setup added it), the hook trust setup recorded, the config block, and drops that home from `~/.dryas/accounts.json`. An old copy install there is removed as in the migration. Other Codex homes, Claude Code and `~/.dryas` are not touched. `--purge` removes `~/.dryas` only when no Claude config dir and no Codex home is left in `accounts.json` (see [Uninstall and purge](#uninstall-and-purge)); with `--harness both`, Codex is removed first, so one run can remove the last of both.

## OpenCode: config-dir install

```
install/install.sh --harness opencode [--opencode-dir DIR] \
  [--tier-fast P/M --tier-standard P/M --tier-strong P/M --tier-frontier P/M]
```

OpenCode 1.18 or newer is required; setup checks `opencode --version` before it writes anything. `--harness all` sets up Claude Code, Codex and OpenCode in one run. Setup writes a copy into the config dir:

```
<dir>/plugin/dryas.ts
<dir>/dryas/{jev,pstack}/ and <dir>/dryas/AGENTS.md.template
<dir>/dryas/install.json           version, tier map, installed files with hashes
<dir>/skill/dryas-*/
<dir>/command/*.md
<dir>/agent/dryas-executor-*.md    model: from the tier map
```

Setup never edits `opencode.json`. The plugin adds the `jev` MCP server when OpenCode loads it. Dryas never changes OpenCode's permission settings; a gate `ask` blocks the call and you allow it once with `dryas allow <code>` (see [harnesses.md](harnesses.md#opencode)). Setup refuses to overwrite a file it did not write and names it. Without `--tier-*` flags every executor tier uses the same model; give each tier its own model to get the ladder.

OpenCode runs a copy, so re-run setup after `git pull`. A file you edited is kept as `<name>.dryas-old` on a re-run; an earlier `.dryas-old` copy is not overwritten (the next one is `.dryas-old.<n>`). Setup keeps other installs' component choices, and an interrupted setup can be re-run. Remove Dryas with `install/install.sh --uninstall --harness opencode`: it removes the files whose hashes still match `install.json` and keeps and names the ones you edited, and keeps `accounts.json` when it cannot read it. Check the install with `python3 tools/release_check.py --opencode-dir DIR`.

## The API key

Jev calls OpenRouter. Put the key in your shell profile:

```
export OPENROUTER_API_KEY=...
```

The installer never asks for the key and never writes it to a file. For Claude Code it can also be stored as a plugin option; see [The OpenRouter key](#the-openrouter-key). Codex reads it only from the shell ([The OpenRouter key in Codex](#the-openrouter-key-in-codex)).

## Data root

Workflow data lives under `~/.dryas`, shared by every account: Jev logs, thresholds, handoffs, compaction notes, `chain.local.json`, `accounts.json`, the workflow reference, the Dryas memory store `dryas.db`, and, with the Ruflo extra, Ruflo (its memory, helpers and MCP shim). Set `DRYAS_DATA_ROOT` to move it:

```
export DRYAS_DATA_ROOT=/path/to/data
```

Dryas memory is `$DRYAS_DATA_ROOT/dryas.db`. Ruflo data (extra) goes to `$DRYAS_DATA_ROOT/ruflo/<namespace>`. For Codex, set it in the shell Codex runs in: the hooks read it from there, and the Jev MCP server gets it through `env_vars`.

With the Ruflo extra, the helpers are generated locally by `ruflo init` and patched (data root, no background npx), not shipped in the repo. They and the Ruflo MCP shim live in `$DRYAS_DATA_ROOT/ruflo` (`helpers/`, `mcp-shim/`).

## Verify

The installer ends with a verify step for the config dir. Each check prints `PASS`, `FAIL` or `SKIP`:

- **dryas@dryas-workflow listed**: `claude plugin list --json` for that dir lists the plugin; the path shown is the folder it runs from (your clone's `claude/`).
- **dryas loads without errors**: the plugin is enabled and Claude Code reports no load errors.
- **rules hook prints SessionStart JSON**: the plugin's rules hook runs and injects the rules.
- **scope lock blocks an out-of-scope write**: a write outside an active task's scope is denied in a temporary folder.
- **Jev tests**: runs the tests in the installed plugin's `jev/tests` with the Python the installer was started with. They need `pytest`. If `pytest` is missing the check prints `SKIP (install pytest to run the Jev tests)`; install it (`python3 -m pip install pytest`) and re-run the installer.

With Codex, the checks for that Codex home follow: the plugin installed and enabled at the version setup recorded, the Jev MCP server listed, every Dryas hook trusted (a FAIL names the `/hooks` step), the skills listed, the rules hook output, the scope lock on an out-of-scope `apply_patch`, and no old copy install left. For a fuller check on a real machine, including several config dirs, see [release-check.md](release-check.md).

It ends with `verify: N failed`. The installer exits non-zero if any check failed.

## Upgrade

`git pull` in the clone updates the Claude Code plugin itself: Claude Code runs it from the clone. Run `./install/install.sh` again, once per config dir, to refresh the settings it merged (needed when a release changes them, when you change components, or after moving the clone). For Codex, re-run setup for each Codex home after a pull: Codex runs a copy of the plugin ([Update](#update)). You can add a component you skipped earlier (for example, re-run with `--with-ruflo`). A `--no-` flag on a re-run turns that component's stages off in `chain.local.json` (shared by every account and Codex home) and, for Claude Code, drops its settings entries. It does not remove that component's files: the plugin ships all of them (with `--no-pstack-picks` the pstack picks stay in the plugin, switched off); use `--uninstall` to remove Dryas.

`~/.dryas/jev/thresholds.json` is yours (`/tune` changes it); setup never overwrites it. The shipped `jev/chain.json` in the plugin is read-only; your stage choices live in `~/.dryas/chain.local.json` and keep their settings across re-runs.

## Uninstall

```
./install/install.sh --uninstall
```

For Claude Code this lists what it will remove, asks, then removes the plugin and the settings entries setup added in one config dir, and offers to remove the third-party plugins setup installed (`--keep-extras` keeps them); see [Uninstall and purge](#uninstall-and-purge). For Codex (`--harness codex|both`) it removes the plugin, the recorded hook trust and the config block from one Codex home; see [Codex uninstall and purge](#codex-uninstall-and-purge). A backup of your settings from before the merge (`<config dir>/settings.json.dryas-bak-<timestamp>`) is kept, and its path is printed. Use it as a manual fallback if something looks wrong.

Uninstall removes only settings values that still match what the installer wrote. A value changed afterwards, by you or by Claude Code itself (for example it may rewrite `"model": "opus"` to `"opus[1m]"`), counts as your edit and is kept.

## Troubleshooting

- **dryas fails to load (`/plugin` shows an error).** Run `claude plugin validate` on the clone's `claude/` folder and read the error; re-run setup for that config dir.
- **Jev shows `JevUnavailable`.** (Only with `--judge jev`; the local judge needs no key.) Apps launched from the GUI do not read your shell profile, so they do not see `OPENROUTER_API_KEY`. Launch Claude Code from a terminal, set the variable in the app's environment, or store the key as the plugin option (`--openrouter-key`).
- **Hooks do not fire.** Run `/plugin` and check that dryas is enabled. If it is, look for `allowManagedHooksOnly` in managed settings ([Hooks blocked by policy](#hooks-blocked-by-policy)). On Windows, check that Git for Windows is installed.
- **Permission prompts for `/tune` or `/handoff`.** The allow rules name the folder the plugin runs from (your clone's `claude/`). Re-run setup for that config dir after moving the clone.
- **`HOME` contains a space.** Only Ruflo cannot handle this. Install without `--with-ruflo`.
- **Codex: the scope lock or the rules do not run.** The Dryas hooks are not trusted in that Codex home. Open Codex, run `/hooks` and trust them, or re-run setup and answer yes. The release check shows `FAIL  Codex hooks trusted` until then.
- **Codex: hooks fail with `python3: not found`.** Install Python 3.9+ so `python3` is on the PATH Codex runs with, or set `DRYAS_PY` to an interpreter.
