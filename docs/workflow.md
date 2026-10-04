# Dryas Workflow

This is your development workflow on this Mac: what each layer does, the order things run in, where files live, and the rules. Claude reads it before doing multi-step work, and when asked "how does our workflow work".

- **Canonical copy:** `~/.claude/DryasWorkflow.md`, on the Mac, so it's available even when the SSD is unplugged.

Last updated: 2026-10-03.

---

## 1. Ground rules (non-negotiable)

- **Billing.** All Claude work runs on the Claude subscription.
  - Never set or use `ANTHROPIC_API_KEY`.
  - Executors spawn through Claude Code's own Agent/Task tool, never through Ruflo's provider layer.
- **The only API key is `OPENROUTER_API_KEY`, and only Jev uses it.**
  - It lives only in the shell environment (`~/.zshrc`). Never write it to any file, config, log or test.
  - Claude Code passes the environment on to hooks and MCP servers, so never use `claude mcp add -e` with the key.
- **User scope only.** Shared skills, agents, commands, hooks and MCP servers live in `~/.claude`. Nothing shared is copied into projects.
- **Ask you before any install, move, delete or overwrite.** That includes any change to `~/.claude/settings.json` or `~/.zshrc`. Show a dry-run or diff first.
  - Settings edits go through `Dev/_tools/settings_merge.py`: dry-run by default, `--apply` makes a backup first.
- Never use `--dangerously-skip-permissions`.
- **`CLAUDE.md` files:**
  - Merge into `Dev/CLAUDE.md`; never overwrite it.
  - `~/.claude/CLAUDE.md` only gets appended sections (model policy and the pointer to this file).
  - Never touch a project's `CLAUDE.md`.

## 2. The layers

| Layer | Role | Never does |
|---|---|---|
| **Orchestrator (main session)** — Claude Code on Opus by default; may be another harness (§14) | Orchestrator: brainstorms with you, plans, dispatches, judges, integrates | Edit project files itself on multi-step work |
| **Jev** (TypeSafe `typesafe/jev-1.13` via OpenRouter) | Decision support: tool-call gate, prompt routing, per-task triage, commit check, compaction keep/drop | Write code or plans |
| **Ruflo** (`ruflo@3.51.0`, pinned) | Orchestration plumbing (hierarchical swarm) and the **only** memory/learning layer | Plan (its goals/planning hooks are dropped); use `ANTHROPIC_API_KEY` |
| **Superpowers** (plugin) | Process: brainstorming, worktrees, TDD, two-stage review, verification, plan format | — |
| **FlowObserve** (separate observer app, optional) | Ambient monitor of live sessions: shows each session's stage in the loop (Brainstorm, Plan, Judge, Build, Escalate, Review, Ship) and what needs you (observe-only) | Block or change anything; write Jev logs or `.orchestrate/` |

## 3. Model policy and escalation ladder

- **The orchestrator is Opus, always.** `"model": "opus"` is set in `~/.claude/settings.json`.
- **Executors run on Sonnet by default.** This comes from `~/.claude/agents/executor.md` (`model: sonnet`).
- **The ladder is Sonnet → Opus → Fable.**
  1. A Sonnet executor that fails done-criteria twice, or reports confidence below 0.5, is re-run on **Opus**.
  2. If Opus solves it, stop. **No Fable.**
  3. Only if the Opus executor also fails is the task re-run once on **Fable**.
  4. If Fable fails too, the task goes to you with all three reports.
  - Jev's per-task `needs_opus` answer can start an executor on Opus directly. Nothing starts a task on Fable directly.
  - Every escalation step is logged with its reason via the `log_escalation` MCP tool.
- **Jev answers narrow typed questions only.** A Jev answer below 0.7 confidence, or flagged to escalate, means Opus decides.

## 4. How a task flows

1. **Brainstorm first, always.** The orchestrator runs `superpowers:brainstorming` with you:
   - it asks questions and proposes approaches
   - you approves the design
   - for architectural work, a written spec follows

   Nothing is dispatched to executors before you approves.

   **Design work.** Anything that needs design (UI, UX, layout, visual style, components, pages, design systems, copy on screen) uses both design skills: `ui-ux-pro-max` for design intelligence (style, palette, font pairing, UX guidelines, stack-specific patterns) and `impeccable` to shape, critique and polish the result. Use them while designing and again as a review pass before `/wreview`. Design executors get the same instruction in their task section.
2. **Route.** On every prompt, the Jev route hook may add one line such as `Jev route: swarm (0.82); opus: no (0.91)`. This is advisory, and it's silent below 0.7.
   - Single-file fix: plain Claude on Opus.
   - Multi-step: `/orchestrate <task>`.
3. **Memory first.** `/orchestrate` searches Ruflo memory (`memory_search`, with the main repo folder name as the namespace) and writes down the top 3 past outcomes (what worked, what failed).
4. **Plan as a file.**
   - Create a git worktree (`superpowers:using-git-worktrees`).
   - Write `.orchestrate/PLAN.md` in the worktree, one section per task, in this format:
     ```
     ## Task N: <title>
     Goal: ...
     Scope:
     - <glob>
     Done:
     - <criterion incl. test command>
     Failing test first: <file :: test>
     ```
   - `.orchestrate/` (including `.orchestrate/PLAN.md`) is globally git-ignored (`~/.config/git/ignore`) and never committed.
5. **Per-task Jev check.** One `jev_judge` call per task (one batched call when more than 5 tasks need triage). Its questions:
   - `executor` (coder / tester / reviewer / docs / none)
   - `specific` (is it specific enough?)
   - `failing_test_exists`
   - `needs_opus`
6. **TDD gate.** If no failing test exists, a **tester** executor goes first, and the coder runs only after that test fails for the right reason.
7. **Dispatch.**
   - Write `.orchestrate/active.json`, which arms the scope lock.
   - Each executor receives **only its own section** (`/usr/bin/python3 $HOME/.claude/jev/planfile.py section .orchestrate/PLAN.md N`, absolute path to match the allow rule) plus the worktree path, never the whole plan.
   - Independent tasks run in parallel through Ruflo's hierarchical swarm. Agents spawn via Claude Code's Agent tool, so they run on the subscription.
8. **On return.** Jev checks `done` (done-criteria met?) and `risk` (routine / worth a look / incident).
   - Only incidents, failures and escalations reach Opus in full; everything else becomes one summary line.
   - The outcome is stored in Ruflo memory.
9. **Finish.**
   - Delete `active.json`.
   - Run `/wreview` (two-stage: spec compliance, then code quality).
   - Run `superpowers:verification-before-completion`.
   - Run `/commit`: Jev asks "safe to commit?"; below 0.7, Opus decides. Commits only, never pushes.
   - Merge only after review and verification pass.
10. **Overrides.** Whenever Opus acts against a Jev answer, it calls `log_override`. That feeds `/tune`.

## 5. Hooks and their order

Claude Code runs all matching hooks in parallel, so the order of our stages comes from one **chain script per event**. The scripts are `~/.claude/hooks/pretool-chain.sh` and `prompt-chain.sh`, which symlink into `~/.claude/jev/hooks/`. They run the stages listed in `~/.claude/jev/chain.json` in sequence.

**PreToolUse** (matcher `*`, 20 s):
1. **Scope lock** (`scope_lock.py`). A pure path check with no model call.
   - It runs only while `.orchestrate/active.json` lists active tasks, and only for Edit/Write/MultiEdit/NotebookEdit.
   - It denies paths outside the union of the active tasks' `Scope:` globs.
   - When nothing is active, it runs and makes no decision.
2. **Jev gate** (`gate.py`), on Bash/Write/Edit.
   - **What it sends:** the redacted command, or the file path plus byte and line counts. Never file contents.
   - **Allowlist bypass:** plain commands such as `ls`, `cat`, `git status/diff/log/show` and `pnpm/npm test` skip Jev, but only when they contain no `; & | > < $( \``, newline or `--output`. The target is for Jev to judge about 20% of tool calls.
   - **Deny** when p(safe) < 0.2 at confidence ≥ 0.7.
   - **Ask** when the risk is "destructive" at confidence ≥ 0.7.
   - Otherwise no decision, so normal permissions apply. The gate **never auto-allows**.
   - Any failure (timeout 3 s, no key, offline, SSD missing) means no decision.
   - Gate state: `dev workspace on external SSD; prod credentials NOT present; parallel sessions possible in different project folders`.
3. **Ruflo PreToolUse stages** (pre-bash only), skipped when the SSD is missing.
4. *(optional)* **FlowObserve `fo-hook`** (observe-only, last; its output is ignored; shipped disabled; §12).

**UserPromptSubmit** (15 s): Jev route, then context watch, then FlowObserve if enabled (observe-only, §12). Ruflo's own route hook is dropped.

**Other events:**
- Ruflo learning and memory hooks: post-edit, session restore/end, memory import (no sync), PreCompact persist, SubagentStop post-task.
- Jev compaction: `PreCompact` runs `compact_keep.py`, `SessionStart(compact)` runs `compact_restore.py`, and `SessionStart(clear)` runs `handoff_restore.py` (for `/handoff`).
- *(optional)* FlowObserve's own hooks for other events, installed by FlowObserve itself (§12).

**Rules for the chain:**
- A deny beats an ask, and a stage's "allow" is ignored.
- A crashing stage never blocks: the chain always exits 0, and a decision already made is never lost.

**Outside the chain** (these run in parallel and can't be ordered):
- ECC (incl. GateGuard) and Orca hooks. GateGuard settings (env): `GATEGUARD_EXEMPT_GLOBS` skips the first-write fact check for scratch, tests, `.orchestrate/`, `Dev/docs/` and `Dev/.superpowers/`; `GATEGUARD_BASH_ROUTINE_DISABLED=1` skips the first-Bash-of-session check. Destructive-command checks stay on.
- The Ruflo plugins' own hooks. Their `{"permission":"allow"}` output is ignored by Claude Code; this was verified by test.

## 6. Jev details

- **Code** lives in `~/.claude/jev/` (a local git repo on the Mac). Python 3.9 stdlib only; tests run with `cd ~/.claude/jev && /usr/bin/python3 -m unittest discover -s tests`.
  - `jev_client.py`: `POST https://openrouter.ai/api/v1/systemone`, model `typesafe/jev-1.13`, timeout 3 s. It redacts the state first.
  - `redact.py`: removes keys and tokens, `NAME=secret`, bearer/authorization headers, PEM blocks, URL passwords and `--token` flags.
  - `gate.py`, `route.py`, `scope_lock.py`, `planfile.py`, `chain.py`, `jevlog.py`, `compact_keep.py`, `compact_restore.py`, `transcript_items.py`, `handoff.py`, `handoff_paths.py`, `handoff_restore.py`, `context_watch.py`, `tune.py`.
- **MCP server `jev`**, registered at user scope with `permissions.allow mcp__jev`:
  - `jev_judge(state, questions)` returns answers plus an `escalate` list.
  - `log_escalation(task, reason, decided_by, from_model, to_model)`.
  - `log_override(question, jev_answer, jev_confidence, opus_decision, reason)`.
- **Question rules** (from the typesafe skill):
  - one narrow judgment per question
  - named JSON fields in the state
  - every choice includes a `none_of_these` option
  - independent questions batched into one call
- Noul (yes/no) answers carry no confidence, so ours is computed as `max(p, 1-p)`.
- The Jev MCP server normalizes question shapes and returns safe error causes. The permission allow-list now includes the 3 Ruflo memory/swarm tools (`memory_search`, `memory_store`, `swarm_init`), `Read(~/.claude/jev/**)` and the planfile command.
- **Thresholds** live only in `~/.claude/jev/thresholds.json` (defaults in `thresholds.py`):

  | Area | Setting |
  |---|---|
  | gate | deny_safe_below 0.2, min_confidence 0.7, ask_risk destructive, allowlist |
  | route | 0.7 (swarm needs max(swarm_min 0.7, min_confidence); `/tune` proposes raising swarm_min when swarm costs >3x plain over ≥3 comparisons) |
  | dispatch | 0.7 |
  | escalation | executor_confidence_below 0.5, sonnet_failures_before_opus 2, opus_failures_before_fable 1 |
  | commit | 0.7 |
  | compact | keep_above 0.5 |
  | handoff | keep_min 0.5 |
  | context | warn_pct 0.65 |

- **Logs** go to `~/.claude/jev/logs/*.jsonl` (gate, route, mcp, calls, escalations, overrides, compact, compare). They hold decisions and confidences only, never payloads; a Bash call logs just the first word of the command.
- **Compaction.**
  - `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=75` starts auto-compaction at about 75%.
  - **Context warning** (`context_watch.py`, prompt chain stage): at 65% and again at 70% Claude tells you to run `/handoff` then `/clear`. Window = `JEV_CONTEXT_WINDOW`, else 1M if the model id contains `[1m]`, names a 1M-default model (Fable, Mythos, or Opus/Sonnet 4.6 and later, e.g. `claude-opus-5-5`; version read as 1-2 digits so dates never count), or usage went past 200k; else 200k (Haiku 4.5, Opus/Sonnet 4.5 and older, 3.x, unknown ids). Same rule as FlowObserve's `millionModel()`/`windowFor()` (`server/src/transcript.ts`); change both together. Tiers reset after a compaction.
  - **Manual (preferred, no lossy summary): `/handoff` then `/clear`.** `handoff.py` reads the whole transcript (deduped by uuid) into items: real user messages, Claude replies, subagent hand-backs, and one line per tool call with a trimmed result. Always kept without Jev: last 10 user messages, files touched, latest result per test command, commits. Jev scores the newest 200 other items keep/drop (40 per call, 60 s deadline). Saved redacted to `~/.claude/jev/handoff/<project>-<hash>.md` (0600, keyed by the main repo root so worktrees match, pruned after 24 h). `/clear` fires `SessionStart(clear)` -> `handoff_restore.py` injects it (only if under 30 min old and same project) and deletes it.
  - **Automatic (safety net):** at 75% Claude Code compacts and writes its own summary (kept short by the `~/.claude/CLAUDE.md` compact instructions). `PreCompact` runs the same handoff engine (`compact_keep.py`, 20 s deadline, hook timeout 30 s) and `SessionStart(compact)` re-injects the scored items word for word.
  - If Jev is down or the deadline passes, the newest 30 unscored items are kept instead, and the file says so.
  - This is our own code; **jev-use is not used** (it's unofficial).
- **`/tune`** (weekly) reports:
  - override rate per question
  - the share of tool calls Jev judged
  - sonnet→opus and opus→fable counts and reasons
  - the swarm-vs-plain token ratio
  - Jev spend

  It **proposes** threshold changes, and they're applied only after you approves each one.
- **Cost.** $0.042 per million input tokens, with free output. Each response carries `usage.cost`, which is summed in `/tune`.

## 7. Ruflo details

- **CLI:** `npm i -g ruflo@3.51.0`, pinned, on the Mac's nvm Node.
- **Plugins** (marketplace `ruvnet/ruflo`, user scope): ruflo-core 0.2.6, ruflo-swarm 0.3.0, ruflo-testgen 0.2.1, ruflo-jujutsu 0.2.1 (diff risk scoring). ruflo-cost-tracker 0.26.3 is installed but DISABLED (its Stop hook ran unpinned `npx @claude-flow/cli@latest`; disabled 2026-10-03). Not installed: ruflo-goals, or any other Ruflo plugin.
- **Settings env:** `RUFLO_HOOK_SKIP_NPX=1`, `RUFLO_MCP_SKIP_NPX=1` and `RUFLO_NO_AUTO_ENABLE=1`. Ruflo never runs `npx ruflo@latest`, and never writes `~/.ruflo/first-run-enabled.json`.
- **Topology:** hierarchical, passed in `swarm_init` arguments (the plugin MCP defaults to hierarchical-mesh, so the orchestrator always passes it).
- **MCP launch:** the Ruflo MCP runs through the `RUFLO_MCP_CLI_OVERRIDE` shim, with cwd `Dev/_caches/ruflo/<main repo name>`. `RUFLO_DAEMON_AUTOSTART=0`. The memory namespace is the main repo folder name.
- **Memory MCP tools** (from the ruflo-core plugin, named `mcp__plugin_ruflo-core_ruflo__<tool>`): `memory_search`, `memory_store` and `swarm_init`. The namespace is the main repo folder name.
- **Memory and data** go to `$DRYAS_DATA_ROOT/ruflo` (SSD), per project. Every lifted Ruflo hook is wrapped by `~/.claude/ruflo/run.sh`, so it's a silent no-op when the SSD or a helper is missing.
- **Hooks:**
  - **Lifted by us:** pre-bash (an observe-only chain stage), session-restore, auto-memory import (import only, no Stop sync), helper post-edit, helper session-end on SessionEnd and on PreCompact (manual and auto), and SubagentStop post-task.
  - **ruflo-core's own plugin hooks also run** (modify-bash, modify-file, post-command, post-edit, PreCompact guidance and Stop session-end), through the pinned CLI override. pre-edit and post-bash have no handler in Ruflo 3.51.0.
  - Two helper files (`intelligence.cjs` and `auto-memory-hook.mjs`) carry a 4-line local patch that honours `RUFLO_DATA_ROOT`, so they never write into project trees.
  - **Dropped:** route, compaction guidance, SubagentStart status, notify.
- Ruflo's `CLAUDE.md` planning sections ("Implementation Loop", "Concurrency and authority") are not used, because the orchestrator owns planning.

## 8. Superpowers details

- **Used:**
  - brainstorming (**always first**)
  - using-git-worktrees
  - test-driven-development
  - requesting-code-review and receiving-code-review
  - verification-before-completion
  - writing-plans (plan format)
  - systematic-debugging
- **Denied** in `permissions.deny`: subagent-driven-development, executing-plans, dispatching-parallel-agents, finishing-a-development-branch and diagnosing-superpowers. The orchestrate skill replaces the planning and orchestration ones. you can still type them by hand.
- **Allowed: writing-skills** (un-denied 2026-10-02 at your request). Use it to create new user-scope skills in `~/.claude/skills/`.

## 9. Commands, skills, agents (all in `~/.claude`)

| Name | What |
|---|---|
| `/orchestrate <task>` | The full flow in §4 (skill `~/.claude/skills/orchestrate/SKILL.md`) |
| `/wplan` | Write a plan in writing-plans format (`/plan` is a Claude Code built-in) |
| `/wreview` | Two-stage review (`/review` is a Claude Code built-in) |
| `/commit` | Conventional commit, gated by Jev "safe to commit?", never pushes |
| `/tune` | Weekly calibration (§6) |
| `/handoff` | Jev-scored context reset: saves kept items, then you type `/clear` (§6) |
| agent `executor` | Sonnet, tools Read/Edit/Write/Bash, one task section, locked scope. Ends with CHANGED / TESTS / DONE-CRITERIA / CONFIDENCE / UNRESOLVED |
| skills `stack-nextjs-ts`, `stack-supabase-postgres`, `stack-swift-ios`, `stack-python` | Conventions, test commands and pitfalls, scanned from the real projects |
| plugin `typesafe@typesafe-ai` | Official Jev/TypeSafe docs skill |
| skills `impeccable`, `ui-ux-pro-max` | Design pair, required for any task that involves design (§4 step 1) |
| `~/.claude/release/export.sh` (maintainer only) | One-way export of `~/.claude` to the public `dryas-workflow` repo: allowlist `public-manifest.txt`, path/name rewrites `rewrites.tsv`, deny-term and secret scans, Jev tests on the staged tree, FlowObserve stages shipped disabled. `--dry-run` first. Never edit `claude/` in the public repo; change `~/.claude` and re-export |

## 10. Where things live

| Mac (`~`) | SSD (`$DEV_ROOT`) |
|---|---|
| `~/.claude/` (settings, skills, agents, commands, hooks, jev code and logs, ruflo helpers, plugins, Claude memory per project) | `projects/<name>` |
| `~/.claude/DryasWorkflow.md` (this file) | `CLAUDE.md` (workspace rules, inherited by every project) |
| `ruflo` CLI (nvm Node), `~/.flowobserve/` (FlowObserve spool + SQLite) | `_caches/` (npm, pnpm, pip, Homebrew, Xcode, **Ruflo memory**) |
| `~/.zshrc` (`OPENROUTER_API_KEY`, guarded cache block, `dev` alias) | `_tools/` (settings_merge.py, relink_claude.py) |
| `~/.claude/release/` (private export pipeline, never published) | `projects/dryas-workflow` (public repo clone; installer `install/install.sh` generates Ruflo helpers with `ruflo init` + pinned patches) |
| | `projects/flowobserve` (the observer app) |
| | `docs/` (specs, plans, reports, backup copy of this file), `_archive/` |

**If the SSD is unplugged:**
- **Breaks:** projects, `Dev/CLAUDE.md`, Ruflo memory, caches and the FlowObserve server.
- **Keeps working:** Claude Code, everything in `~/.claude`, and Jev's code and logs.
- Ruflo hooks become silent no-ops, and the Jev gate makes no decision.

## 11. Orca

Everything is user scope, so Claude sessions launched by Orca get the same hooks, skills, agents and the `jev` MCP server. Orca's own hooks are kept.

If the gate logs `JevUnavailable` inside Orca, Orca's environment lacks `OPENROUTER_API_KEY`, because GUI apps don't read `~/.zshrc`. Launch Orca from a terminal, or set the variable in Orca's own environment settings. Never put the key in a file.

## 12. FlowObserve (observer)

An optional, separate observer app (closed source). The workflow runs fully without it, and it is not part of this repo.

- If installed, it adds an observe-only `flowobserve` stage at the end of `pretool` and `prompt` in `jev/chain.json` (shipped disabled here) and its own hooks for other events. Its output is ignored; it never blocks or changes anything.
- It reads the workflow's own signals (Jev logs, `.orchestrate/PLAN.md`) and never writes them.

## 13. Known trade-offs

- The OpenRouter key is never written by this workflow; it lives in `~/.zshrc` (pre-existing).
- Commands are redacted before leaving the Mac, and file contents are never sent.
- The gate fails open to normal permissions and never auto-allows.
- Ruflo is pinned, with the `@latest` fallback forbidden.
- Every settings change goes through dry-run, then approval, then backup.
- **Known exposures you accepted:**
  - the prompt route sends the first 4k characters of each prompt to OpenRouter
  - handoff/compaction sends up to 200 items (1k characters each, redacted)
  - ECC and Orca hooks run outside the chain

## 14. Harnesses (main agent)

The main agent (orchestrator) does not have to be Claude Code. Claude Code on Opus is the default, but another harness such as Codex (or any agent CLI that can follow these rules) may run the session.

- **Always applies, any harness:** the ground rules (§1), brainstorm first, worktree per multi-step task, plan-as-a-file format, TDD gate, design rule (§4 step 1), `/wreview`-style two-stage review, verification before completion, commit only after review, never push without asking.
- **Claude Code only today:** the hook chain (§5: scope lock, Jev gate, Jev route, context watch, compaction/handoff), Claude Code slash commands and skills, the `executor` agent and the Sonnet → Opus → Fable ladder. Another harness does not get these automatically.
- **Jev and Ruflo in another harness:** usable only if that harness supports MCP and is configured with the `jev` and Ruflo servers. Same billing rule: no `ANTHROPIC_API_KEY`; Jev still uses only `OPENROUTER_API_KEY` from the shell environment.
- **Instructions file:** another harness reads its own file (e.g. Codex reads `AGENTS.md`). Point it at this file rather than copying the rules.
- **Executors and escalation:** in another harness, use its own sub-agent mechanism if it has one and keep the same idea (cheaper model first, escalate on failure, log the reason). Note the harness used in commit messages or the plan when it is not Claude Code.
- **FlowObserve** only sees Claude Code sessions (it reads Claude Code hook events).
