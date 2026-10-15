# Template coverage

Every non-heading line of the pre-2.0 templates (frozen in `install/tests/fixtures/template-pre-2.0/`) and where its rule lives now. `template` = the line, possibly reworded, in the rewritten template; `pointer: <path>#<heading>` = detail moved to a shipped file. Pinned by `install/tests/test_template_budget.py`.

## claude/CLAUDE.md.template

| Rule (pre-2.0 line) | Where now |
|---|---|
| The user's dev workflow, called the Dryas Workflow, is documented in `~/.dryas/docs/dryas-workflow.md` (written by setup from the dryas-workflow repo). Machine-specific notes, if present: `~/.dryas/docs/dryas-local.md`. Read them before multi-step work or when asked about the workflow. | template |
| The repo is the source of truth for these rules and that doc. Edit the repo (`claude/CLAUDE.md.template`, `docs/workflow.md`), merge, then re-run setup (`install/install.sh`, once per Claude config dir). Never hand-edit the plugin files, the copy in `~/.dryas/docs`, or these injected rules. | template |
| Brainstorm first, always (dryas:brainstorm). Nothing is built or dispatched before the user approves the design. | template |
| Design work (UI/UX, layout, visual style, components, on-screen copy) uses both `ui-ux-pro-max` and `impeccable`. | template |
| Single-file fix: plain Claude on the strong tier. Anything multi-step: `/orchestrate <task>` on the approved design. | template |
| Every multi-step task runs in its own git worktree. One agent per worktree: never two sessions in one worktree; parallel loops each get their own worktree and branch. Merge only after `/wreview` and dryas:verify. | template |
| Layers: Jev = decision support (gates, routing; the local judge or the Jev model; never writes code or plans), Dryas memory = the memory/learning layer (Ruflo memory when that extra is selected), Dryas skills = process; Superpowers and Ruflo are optional extras, and the rules point at the Dryas skills even when they are installed. | template |
| Hook order per event: scope lock -> gate -> memory -> observer (observe-only, last). Stages: `jev/chain.json` in the Dryas plugin folder. | template |
| `.orchestrate/` (incl. `.orchestrate/PLAN.md`) in a worktree is orchestration scratch: globally git-ignored, never committed. | template |
| Ask before any install, move, delete or overwrite, including any change to the account's settings.json (`$CLAUDE_CONFIG_DIR/settings.json`, default `~/.claude/settings.json`). Show a dry-run or diff first. | template |
| Commands: `/orchestrate`, `/wplan`, `/wreview`, `/commit` (Jev-gated, never pushes), `/tune` (weekly calibration), `/handoff` (Jev-scored context reset: run it, then `/clear`). | template |
| pstack picks: before reporting a performance number you measured, read `pstack/benchmark-checklist.md` in the Dryas plugin folder and answer its questions. `/interrogate` (two-model adversarial review) runs only from `/orchestrate`'s gated step or when the user asks. | template |
| Orchestrator: strong tier, always (`"model": "opus"`, set by setup in the account's settings.json (`$CLAUDE_CONFIG_DIR/settings.json`, default `~/.claude/settings.json`)). | template |
| Executors: fast tier first. `/orchestrate` passes `model: haiku` unless Jev's `needs_sonnet` or `needs_opus` (or strong-tier judgment) starts the task higher; the plugin's `dryas:executor` agent stays on the standard tier so review dispatches never run on the fast tier. Kill switch: `dispatch.haiku_default` in `~/.dryas/jev/thresholds.json`. | template |
| Escalation ladder: fast → standard → strong → frontier (tier-to-model table in `~/.dryas/docs/dryas-workflow.md`). A task the fast tier fails `escalation.haiku_failures_before_sonnet` times (default 1) goes to the standard tier; a task the standard tier can't finish goes to a strong executor; the frontier tier is used only if the strong executor also fails that task. Stop at the first success. Every step is logged with its reason via `mcp__plugin_dryas_jev__log_escalation`. | template |
| Jev (via the `jev` MCP server and hooks) answers narrow typed questions only; it never writes code or plans. Below threshold or escalate → the strong tier decides. | template |
| When compacting, keep the summary SHORT (aim under 300 words): current goal, open decisions, next step. A Jev-scored handoff of verbatim excerpts (user messages, files touched, test results, commits, key tool lines) is re-injected right after compaction, so do not repeat file lists, test output or tool logs in the summary. | template |

## codex/AGENTS.md.template

| Rule (pre-2.0 line) | Where now |
|---|---|
| Process rules for coding sessions on this machine. Full reference: `~/.dryas/docs/dryas-workflow.md` (local notes, if present: `~/.dryas/docs/dryas-local.md`). | template |
| Brainstorm first: before new work, clarify intent and get the user's approval of a design (the `$dryas:brainstorm` skill). | template |
| Multi-step work runs in its own git worktree (`$dryas:worktree`); merge only after review and verification (`$dryas:verify`). | template |
| One agent per worktree: never run two sessions in the same worktree. Parallel loops on one project each get their own worktree and branch. | template |
| Plans are files: `.orchestrate/PLAN.md` in the worktree, sections `## Task N:` with Goal, Scope (globs), Done and Failing test first. Never commit `.orchestrate/`. | template |
| Test first. Never claim a pass you did not see. | template |
| Review before merge: spec compliance first, then code quality (`$dryas:wreview`). | template |
| Commit only after review, as Conventional Commits; never push without asking. | template |
| Do what was asked, nothing more. Read a file before editing it. Never commit secrets or `.env` files. | template |
| `$dryas:orchestrate` (multi-step tasks), `$dryas:wplan` (write a plan), `$dryas:wreview` (two-stage review), `$dryas:commit` (Jev-gated commit), `$dryas:tune` (weekly Jev calibration). | template |
| `$dryas:interrogate` (gated two-model review), `$dryas:benchmark-checklist` (vet a measured performance number). Shared references: `{{CD}}/pstack/`. | template |
| Jev answers narrow typed questions only (`jev_judge`); it never writes code or plans. When it is below threshold, escalates or is unavailable, you decide; log any disagreement with `log_override`. | template |
| Models: start a task on a cheaper model and move to a stronger one when it fails. Log every step with `log_escalation` (task, reason, decided_by, from_model, to_model). | template |
| Dryas memory: `memory_search` before a task, `memory_store` after success; namespace = the main repo's folder name. | template |
| Hooks enforce the scope lock (while `.orchestrate/active.json` exists, edits outside the active tasks' Scope are denied), the Jev gate on risky commands, and a Jev route hint on each prompt. | template |
| On Windows PowerShell, put `& ` before a command that starts with a quoted path. | template |
| Context-window warnings, compaction handoff, `$handoff` and the memory hooks other than session start run only in Claude Code. | template |
