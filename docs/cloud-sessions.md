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

`dryas cloud update` refreshes the copy from this checkout. Files you edited by hand are reported as drift and kept unless you pass `--force`. `dryas cloud remove` takes out exactly what Dryas added. `dryas cloud check` runs the copy's check and also compares the copy with this checkout. `init`, `update` and `remove` need a Dryas checkout, so they do not run inside a cloud session; `/dryas-cloud check` does.

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
- **Hooks:** they run as on a workstation: scope lock, gate, memory, observer. A hook that fails internally exits 0 and drops its output; for the pre-tool gate it answers "ask" instead.

## Check it in CI

    python3 .dryas/jev/cloud_check.py --repo .

It exits 1 on any problem: drift, a Mac path, a non-stdlib script, a missing licence or NOTICE line, the ignore line or the rules block. In a session, `/dryas-cloud check` runs the same check.

## On a machine where Dryas is installed

The plugin's own hooks already run there. The repo copy's hooks see `~/.dryas/chain.local.json` and do nothing outside a cloud session, so the chain does not run twice. Set `DRYAS_CLOUD_HOOKS=1` to run the copy's hooks anyway, or `DRYAS_CLOUD_HOOKS=0` to turn them off everywhere.

## Manual acceptance (once, by the maintainer)

- [ ] On the Mac, run `install/install.sh --repo <small test repo>`, read the dry run, re-run with `--yes`, commit and push.
- [ ] Open a claude.ai/code session on that repo with no environment opt-ins.
- [ ] The Dryas rules load, `/orchestrate` is offered, `git checkout -- .` asks, and `/tune` runs.
- [ ] `.dryas/state/jev/logs/gate.jsonl` shows `"provider":"local"`.
- [ ] The `jev` MCP tools answer, and `.dryas/state/` gets a `dryas.db` after a `memory_store` call (the `.mcp.json` `env` block works).
- [ ] On the Mac, open Claude Code in the same repo with the plugin installed: `.claude/settings.json` has no Dryas `env` entries, the plugin's hooks run once (the copy's hooks stay quiet), and the plugin's logs still land in `~/.dryas/jev/logs/`, not in the repo.
