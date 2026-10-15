# Dryas in cloud sessions

claude.ai/code cloud sessions build from a GitHub repo and load only what the repo commits:
- `.claude/skills`, `.claude/agents` and `.claude/commands`;
- the hooks in `.claude/settings.json`;
- `.mcp.json` and `CLAUDE.md`.

They do not install plugins. `dryas cloud` therefore writes a pinned, version-stamped copy of the Dryas core into the repo. A cloud session on that repo then runs the Dryas workflow with no setup inside the cloud environment. The core is Python stdlib only, so it needs no Node, Ruflo or Superpowers.

## Set a repo up

From a Dryas checkout:

    install/install.sh --repo ../my-repo               # macOS, Linux, WSL: same as dryas cloud init
    .\install\install.ps1 -Repo ..\my-repo             # Windows
    claude/bin/dryas cloud init --repo ../my-repo      # the dryas command

Every run first prints a dry run: each file it would add, change or remove, with sizes. Add `--yes` to write. Nothing is committed. The run ends with the `git add` lines and a suggested commit message.

| Option | Effect |
|---|---|
| `--yes` | write; without it the run is a dry run |
| `--force` | write over uncommitted changes in the paths it writes, and over hand edits on update |
| `--prefix P` | rename the copied skills, commands and agent (`P` + name) when the repo has its own of the same name; a clash otherwise stops the run |
| `--with-design` | also copy the design skills, each only with a confirmed licence; the licence text goes to `.dryas/licenses/` and a line to `.dryas/NOTICE` |
| `--with-own NAME` | also copy that skill from your Claude config dir; a secret-shaped line stops it until `--confirm-own NAME` |
| `--persist-memory` | keep short, redacted session notes in `.dryas/memory/notes/`, committed with the work |
| `--confirm-own NAME` | confirm a `--with-own NAME` skill whose secret-shaped line stopped the run |
| `--no-design` | `update` only: drop the design skills an earlier run copied |
| `--without-own NAME` | `update` only: drop that own skill |
| `--no-persist-memory` | `update` only: stop keeping session notes (the notes already written stay, as the repo's own work) |

`dryas cloud update` refreshes the copy from this checkout. Options you leave out keep what the manifest records. Files you edited by hand are reported as drift and kept unless you pass `--force`. Update keeps what it cannot rebuild this run (a skill it had to skip); only dropping its option removes it, even with `--force`. `dryas cloud remove` takes out exactly what Dryas added. `dryas cloud check` runs the copy's check and also compares the copy with this checkout. `init`, `update` and `remove` need a Dryas checkout, so they do not run inside a cloud session; `/dryas-cloud check` does.

## What the repo gets

- `.dryas/`: the runtime (`jev/`, `pstack/`, `bin/dryas-py`), `docs/dryas-workflow.md`, `licenses/`, `NOTICE`, `VERSION` and `manifest.json`, which lists every copied file with its source, version, licence and hash.
- `.claude/skills/`, `.claude/commands/`, `.claude/agents/`: the Dryas core skills, the commands `/orchestrate`, `/wplan`, `/wreview`, `/commit`, `/tune`, `/handoff` and `/dryas-cloud`, and the executor agent.
- `.claude/settings.json`: Dryas's hooks (through `.dryas/jev/cloud_hook.py`) and one allow rule, merged with what is there. Dryas adds no `env` entries there; the hook entry sets the copy's paths itself, so nothing leaks into the plugin's hooks on a machine with Dryas installed.
- `.mcp.json`: the `jev` MCP server with its own `env` block, merged with what is there.
- `CLAUDE.md`: the Dryas rules between `<!-- dryas:start -->` and `<!-- dryas:end -->`; the rest of the file is untouched.
- `.gitignore`: `.dryas/state/`, `.dryas/**/__pycache__/`, `.claude/skills/**/__pycache__/` and `.orchestrate/`.

[reference/cloud-bindings.json](../reference/cloud-bindings.json) lists every core component as copied, opt-in or excluded, with the reason. The copy ships `codex_event.py` and `ruflo_import.py` too, because `chain.py` and `memcli.py` import them; the copy never calls Ruflo. It never copies Ruflo, Superpowers, Codex files, MCP servers that need npm or network, or skills that live only on one machine.

## In the cloud session

- **Judge:** local, so there is no network and no key. To use Jev in one environment, set `DRYAS_JUDGE=jev`, add the secret `OPENROUTER_API_KEY`, and allow `openrouter.ai` in that environment's network settings.
- **State:** `.dryas/state/` holds the logs, threshold overrides and scope-lock files. It is git-ignored and new in every session, and nothing depends on an earlier one.
- **Memory:** within a session, Dryas memory works as on a workstation. With `--persist-memory`, a redacted note is written to `.dryas/memory/notes/` at Stop, PreCompact and SessionEnd (the same session overwrites its own note), and the next session start reads the notes back. A session can end without a clean SessionEnd, so run `python3 .dryas/jev/memnotes.py export` before the final commit to put the latest note in it. The notes are plain markdown, reviewed in pull requests. The plugin's own Stop route is a no-op without a notes folder, so a machine with the plugin installed never writes one.
- **Hooks:** they run as on a workstation: scope lock, gate, memory, observer. A hook that fails internally exits 0 and drops its output; for the pre-tool gate it answers "ask" instead.

## Check it in CI

    python3 .dryas/jev/cloud_check.py --repo .

It exits 1 on any problem: drift, a Mac path, a non-stdlib script, a missing licence or NOTICE line, the ignore line or the rules block. It also reads the live `.claude/settings.json` and `.mcp.json`: a Dryas hook entry gone, a `DRYAS_*` env entry in settings, or the `jev` server changed is a problem. Each memory note is scanned for a Mac path or secret-shaped text. In a session, `/dryas-cloud check` runs the same check.

## On a machine where Dryas is installed

The plugin's own hooks already run there. Outside a cloud session the repo copy's hooks stay quiet when `chain.local.json` exists (in `~/.dryas`, in `$DRYAS_DATA_ROOT` for a custom data root, or at `JEV_CHAIN_LOCAL`) or the Claude plugin registry (`installed_plugins.json`) lists `dryas@...`, so the chain does not run twice. For a plugin that is disabled but still installed the registry still lists it, so set `DRYAS_CLOUD_HOOKS=1` to run the copy's hooks anyway, or `DRYAS_CLOUD_HOOKS=0` to turn them off everywhere.

## Manual acceptance (once, by the maintainer)

- [ ] On the Mac, run `install/install.sh --repo <small test repo>`, read the dry run, re-run with `--yes`, commit and push.
- [ ] Open a claude.ai/code session on that repo with no environment opt-ins.
- [ ] The Dryas rules load, `/orchestrate` is offered, `git checkout -- .` asks, and `/tune` runs.
- [ ] `.dryas/state/jev/logs/gate.jsonl` shows `"provider":"local"`.
- [ ] The `jev` MCP tools answer, and `.dryas/state/` gets a `dryas.db` after a `memory_store` call (the `.mcp.json` `env` block works).
- [ ] On the Mac, open Claude Code in the same repo with the plugin installed: `.claude/settings.json` has no Dryas `env` entries, the plugin's hooks run once (the copy's hooks stay quiet), and the plugin's logs still land in `~/.dryas/jev/logs/`, not in the repo.
