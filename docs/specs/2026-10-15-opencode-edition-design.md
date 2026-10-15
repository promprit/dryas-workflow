# OpenCode edition: design

Date: 2026-10-15. Status: draft for review. Branch: `spec/opencode-edition`. Contested: yes.

## 1. Goal

People who use [OpenCode](https://opencode.ai) can run Dryas at full capacity: the spec's **Dryas Full** level (`spec/dryas-spec-v1.md` §2), with every rule `met` except where OpenCode itself lacks the capability. The maintainer does not use OpenCode, so automated tests against the real OpenCode binary stand in for day-to-day use.

Success means:

- `install/install.sh --harness opencode` gives an OpenCode user the rules, the process skills, the commands, the `jev` MCP server (judge, memory, logging), the scope lock, the Jev gate, where an `ask` blocks the call and the user allows it once with `dryas allow <code>`, the executor agents with the fast → standard → strong → frontier ladder, the memory stages, compaction keep/restore, context warnings and `/handoff`.
- The conformance table in `reference/README.md` has an **OC** column; every `partial` names a capability OpenCode lacks (section 8), none names a choice we made.
- A CI job runs a real OpenCode (pinned 1.18.x) end to end against a mock model, with no API key.
- No Python port, no Node install for the user, the user's `opencode.json` is not edited by default.

Delivered in two steps from this one spec, one plan each (section 9).

## 2. Decisions

| Topic | Decision |
|---|---|
| Who it is for | OpenCode users; the maintainer does not dogfood it |
| Target | Dryas Full; gaps only where OpenCode cannot carry a feature |
| Approach | A thin TS plugin that calls the existing Python chain per event (B, a Python daemon, and C, a TS port, were rejected: more moving parts, or two implementations of the core) |
| Ask | The plugin never reads or changes OpenCode's permission settings. A chain `ask` (judge or scope lock) blocks the call with the reason and a 4-hex code; the user allows that exact call once by typing `dryas allow <code>` in a root session. Codes in subagent prompts never approve |
| Tier models | `--tier-fast/standard/strong/frontier <provider/model>`; unset tiers default to the user's configured `model`, with a warning that the ladder is flat |
| Duplicate skills | Skills install as `dryas-<name>`; setup warns when Dryas skills are also visible from `~/.claude/skills` |
| Version floor | `>=1.18`; CI pins 1.18.x, a weekly job runs the latest release |
| Testing cuts | No separate unit tests for the TS shim (end-to-end tests cover it); OpenCode CI on Linux only; no real-model smoke run |
| FlowObserve | Out of scope (Mac observer, not part of the spec) |

## 3. Spike findings (OpenCode 1.18.32)

Run against a mock OpenAI-compatible model, isolated XDG dirs, throwaway code.

| Need | OpenCode carrier | Result |
|---|---|---|
| Rules into the system prompt | `experimental.chat.system.transform` | Verified |
| Skills | `.opencode/skill/<name>/SKILL.md`, native `skill` tool | Verified. OpenCode also loads `~/.claude/skills` and `~/.agents/skills` on its own |
| Commands | `command/*.md`; `command.execute.before` and `command.executed` fire | Verified |
| Block a tool call | throw in `tool.execute.before`; the message reaches the model | Verified |
| Ask the user | no native prompt from a plugin: the `permission.ask` hook never fires in 1.18, and the v2 create-permission API gives no prompt (see below). The shim blocks and takes `dryas allow <code>` from the user's next message | Verified |
| Agent identity | a subagent runs in a child session (`parentID`); `chat.params` and `message.updated` carry the agent name per session before its tools run | Verified |
| Per-agent model | `model:` in the agent file | Verified |
| PostToolUse | `tool.execute.after`; blocked and rejected calls get no after event | Verified |
| Stop, SubagentStop | `session.idle` (child session for a subagent) | Fires |
| SessionStart | `session.created`, plugin init | Fires |
| SessionEnd | no event on a TUI exit | Gap |
| PreCompact keep/restore | `experimental.session.compacting` `output.context` | Verified (reached the model) |

Probed while planning (same setup, second run):

| Need | Result |
|---|---|
| Add context to a prompt | a text part pushed onto `output.parts` in `chat.message` reaches the model. Verified |
| Block a prompt | throwing in `chat.message` gives "Unexpected server error"; instead the shim replaces the prompt's text parts with one telling the model to report the block reason and stop. No prompt stage blocks today, so this is a safety net |
| MCP server from the plugin | an `mcp.jev` entry added in the `config` hook connects (`opencode mcp list`: connected); its tools are named `jev_<tool>` (`jev_memory_search`, `jev_jev_judge`). Verified, so setup never edits `opencode.json` |
| Token counts | `message.updated` carries `tokens.input`, `tokens.cache.read/write` from the stream's usage. Verified; `chat.params` `model.limit.context` gives the window |
| Claude-style command frontmatter | unknown keys (`allowed-tools`, `argument-hint`) are ignored. Verified |

**Why asks block (spike and interrogate).** OpenCode 1.18's v2 create-permission API evaluated a plugin request to allow and emitted no `permission.asked` event, so a plugin cannot raise a native prompt. The first design rewrote `edit` and `bash` to `"ask"` and answered the requests. Two interrogate reviewers found that this let Plan mode edit files and turned the user's inherited `deny` rules into auto-allows, so the design was dropped. OpenCode applies the last matching permission pattern, so an example with a catch-all writes it first, such as `{"*": "allow", "echo *": "ask"}`.

## 4. Layout

A new `opencode/` folder beside `codex/`, laid out exactly as it is installed into an OpenCode config dir. Generated by the sync tool except the hand-written files marked below.

```
opencode/
  plugin/dryas.ts          the shim (hand-written)
  dryas/jev/  dryas/pstack/   synced copy of claude/jev and claude/pstack
  dryas/AGENTS.md.template    rules, rendered from codex/AGENTS.md.template
  skill/dryas-<name>/      process skills rendered from claude/skills; dryas-orchestrate, dryas-interrogate and
                           dryas-benchmark-checklist hand-written (as on Codex)
  command/*.md             orchestrate, interrogate (thin: load the skill); wplan, wreview, commit, tune, retro
                           (rendered from codex/skills); handoff in step 2
  agent/dryas-executor-{fast,standard,strong,frontier}.md   rendered from claude/agents/executor.md
```

Changes to shared code:

- A new `tools/sync_opencode.py` renders the `opencode/` target; `tools/sync_codex_plugin.py` runs it too, so one command (and one `--check`) covers both; the harness-block regex learns `opencode`; the shared-name skill drift check covers three editions.
- `chain.py` and `rules_inject.py` accept `--harness opencode`. `chain.py` runs OpenCode tool events through `pretool_codex`, which already splits `apply_patch` per file (an unreadable patch is denied) and runs any other event in one pass. `rules_inject.py` treats OpenCode like Codex: `{{CD}}` resolved and a "Dryas paths:" line, so skills name `<dryas-root>` and `<dryas-py>` and nothing is substituted at install.
- `chain.json`: every stage except `ruflo-pre-bash` and `flowobserve` runs on OpenCode. Stages with no `harness` key today (they default to `["claude"]`: `context-watch`, `gate-outcome`, the `mem-*` stages) get an explicit list `["claude", "opencode"]`; stages listing `codex` keep it. Codex coverage is unchanged by this spec: its memory stages stay off by the 2.0 choice pinned by a test. Step 1 adds `opencode` to the pretool and prompt stages, step 2 to the rest.
- `context_watch.py` reads `usage` and `context_limit` from the event when `transcript_path` is absent (step 2). Memory stages that read Claude's transcript get the same event-field input.

## 5. The shim (`opencode/plugin/dryas.ts`)

Each hook builds a Claude-shaped hook event and pipes it to `${DRYAS_PY} -X utf8 <root>/jev/chain.py <kind> --harness opencode` (`DRYAS_PY` from `install.json`, else `python3`; `python` on Windows). It maps the chain's JSON answer back.

**State** (in memory per OpenCode process): `session → {agent, parentID, contextLimit, lastUsage}`, filled from `session.created`, `chat.params` and `message.updated`. A child session's events carry `agent_id = <sessionID>` and `agent_type = <agent name>`, so the scope lock's `"agent_id" in event` check works unchanged. Every event carries `session_id` and `cwd`.

**Tool names and arguments:** `bash→Bash {command}`, `write→Write {file_path, content}`, `edit→Edit {file_path, old_string, new_string}`, `multiedit→MultiEdit {file_path, edits}`, `patch`/`apply_patch→apply_patch {command: <patch text>}` (split per file by the chain). Other tools are not sent to the chain.

| OpenCode hook | Chain call | Mapping | Step |
|---|---|---|---|
| `config` | none | adds the `jev` MCP server; does not touch `permission` | 1 |
| `tool.execute.before` | `pretool` | deny: throw `Error(reason)`; ask: throw `Error(reason + code)` and remember the call under its 4-hex code; allow: pass | 1 |
| `chat.message` (root session) | none | text `dryas allow <code>` for a remembered ask: allow that exact call once; subagent sessions never count | 1 |
| `chat.message` (user) | `prompt` | `additionalContext` added as a text part; block → the prompt's text parts replaced (section 3) | 1 |
| `experimental.chat.system.transform` | `rules_inject.py --harness opencode` | output cached per process; on the first request of a session started by `/handoff`, also `handoff_restore.py` output | 1 (handoff: 2) |
| `tool.execute.after` | `post` | as PostToolUse | 2 |
| event `message.updated`, tool part `state: "error"` | `post` | as PostToolUseFailure | 2 |
| event `session.idle` | `subagent-stop` if `parentID`, else `stop` | | 2 |
| event `session.created` (no `parentID`) | `session-start` | | 2 |
| event `session.deleted`, plugin `dispose` | `session-end` | best effort (section 8) | 2 |
| `experimental.session.compacting` | `compact_keep.py`, then `precompact` | keep output pushed to `output.context` | 2 |

Gating calls (`pretool`, `prompt`) are awaited with Claude Code's timeouts (20 s, 15 s). Observe-only calls are started and not awaited. A chain crash or timeout lets the call proceed, as a failing Claude Code hook does; the unreadable-patch deny is the one fail-closed case.

**Executors:** `/orchestrate` on OpenCode dispatches `dryas-executor-<tier>` subagents through the `task` tool, starting at `fast`, moving up per the ladder and logging each step with `log_escalation`. The rendered orchestrate skill's opencode block says so.

## 6. Install, uninstall, release check

`install/install.sh --harness opencode`, plus a new value `--harness all` (Claude Code, Codex and OpenCode); `both` keeps meaning Claude Code + Codex. `--opencode-dir DIR`, default `$XDG_CONFIG_HOME/opencode`, else `~/.config/opencode`. `install/opencode_setup.py` mirrors `install/codex_plugin_setup.py` (setup, uninstall, verify); `install.ps1` takes the same flags.

Setup writes a copy (re-run after `git pull`, as with Codex):

```
<dir>/plugin/dryas.ts
<dir>/dryas/{jev,pstack}/ and <dir>/dryas/AGENTS.md.template
<dir>/dryas/install.json           version, DRYAS_PY, tier map, installed files with hashes
<dir>/skill/dryas-*/
<dir>/command/*.md                 each with a dryas-managed marker
<dir>/agent/dryas-executor-*.md    model: from the tier map
```

- Checks `opencode --version >= 1.18` before writing anything.
- Refuses to overwrite a command, agent or skill file without the dryas-managed marker, and names it.
- Warns on Dryas skills visible from `~/.claude/skills`, and on a flat tier map.
- `~/.dryas/accounts.json` gains `opencode_dirs`; `--purge` clears `~/.dryas` only when no Claude, Codex or OpenCode install is left.
- `--uninstall` removes the files listed in `install.json` whose hashes still match; edited files are kept and named.
- `tools/release_check.py`: an OpenCode check for the version floor, file hashes against `install.json`, `opencode debug config` showing the plugin and the `jev` server, and a flat tier map (warning only).

## 7. Tests, CI, docs

**Tests** (pytest):

- Mock-event tests (`install/tests/test_opencode_*.py`): the chain with `--harness opencode` on Claude-shaped events from shim fixtures. Scope lock with and without `agent_id`, `apply_patch` split, ask/allow/deny; step 2 adds context watch from `usage` and each observe stage.
- Sync drift: `--check` covers `opencode/`; harness-name and skill-drift tests run on three targets.
- Install: setup into a temp `--opencode-dir`, marker refusal, hash-guarded uninstall, version floor, `--purge` accounting.
- End to end, real binary, no key: `install/tests/fixtures/mock_llm.py` (OpenAI-compatible, scripted tool calls) and a pytest driving `opencode serve` over HTTP with isolated XDG dirs. Step 1: an allowed write lands; an out-of-scope write is blocked and the reason reaches the model; an executor subagent is scope-locked; a judge `ask` blocks until the test sends `dryas allow <code>`; `memory_search` works through MCP. Step 2: compaction context reaches the model; `post`, `stop` and `subagent-stop` reach the chain. Skipped when no `opencode` binary is found.

**CI:** `ci.yml` gets an `opencode` job (ubuntu-latest, OpenCode 1.18.x) running the suite above. `latest-compat.yml` gets a weekly `latest-opencode` job. Mock-event and install tests also run in the existing three-OS matrix (they need no binary).

**Docs:** OC column in `reference/README.md`; OpenCode section in `docs/harnesses.md`; flags in `docs/install.md`; install snippet and harness table in `README.md`; roadmap items ticked and the "parked" note removed in `docs/roadmap.md`; an opencode binding in `reference/dryas.yaml`; a CHANGELOG entry per step.

## 8. Known gaps (recorded as `partial`)

- **SessionEnd:** OpenCode has no event when the TUI exits. `session.deleted` and plugin `dispose` cover the rest; `mem-session-end` also runs at `precompact` and `mem-notes` at `stop`, so a missed end loses at most the last turn's notes.
- **Ask in headless runs:** `opencode run` has no follow-up message, so nobody can send `dryas allow <code>` and an `ask` stays a block there (Claude Code's `-p` behaves the same way).
- **Experimental hooks:** `experimental.chat.system.transform` and `experimental.session.compacting` may change; the weekly latest job catches it. If `system.transform` disappears, rules fall back to `AGENTS.md.template` installed as an `instructions` entry.

## 9. Delivery

**Plan 1: core (about 3 days).** The unprobed items were settled while planning (section 3). Plan 1 covers: layout and sync, `--harness opencode` in chain and rules, the shim's step-1 rows, skills, commands, executor agents and the tier ladder, installer, uninstall, release check, step-1 tests, CI jobs, docs with the OC column. The OC rows for the step-2 features say `partial: step 2`; the rows touched by section 8 (session end, headless ask) say `partial` with the reason. `accounts.json` readers are checked to tolerate the new `opencode_dirs` key. Release 2.2.0.

**Plan 2: full (about 1.5 days).** The shim's step-2 rows, `chain.json` lists, `context_watch.py` and memory-stage event input, `/handoff` on OpenCode, step-2 tests, the OC column updated to Full. Release: a later version (after 2.2.0).

## 10. Out of scope

FlowObserve on OpenCode; a TS or other port of the chain; Pi, Roo and Cursor editions; reading OpenCode's session database directly; a project-level install (`.opencode/` in a repo), which can follow if asked.
