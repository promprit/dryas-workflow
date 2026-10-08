# Haiku as the economy executor tier

Date: 2026-10-08. Status: approved in conversation, pending written-spec review. **Contested: no** (model policy and metrics; no security gate changes).

## Goal

Add Haiku as a new bottom rung of the executor ladder so mechanical plan tasks (renames, docs, config, small single-file edits) run on the cheapest model, while anything harder starts on Sonnet or Opus as today. Success: a measurable share of first dispatches lands on Haiku, and the Haiku→Sonnet climb rate stays at or under 35%. If it does not, one config key restores the old behavior.

## Decisions (from the brainstorm)

- Ladder becomes **Haiku → Sonnet → Opus → Fable → human**.
- Haiku is the default **executor** tier only. Non-executor roles (interrogate reviewers, `/wreview`) are unchanged. Haiku never reviews; Fable never starts a task.
- The default lives in the orchestrator's dispatch, not in the agent file: `claude/agents/executor.md` stays `model: sonnet`, and `/orchestrate` passes `model: haiku`. Reason: interrogate reviewers reuse the `executor` agent; a forgotten override then costs money (visible in `/tune`), not review quality.
- Jev can skip Haiku per task with a new `needs_sonnet` question, mirroring `needs_opus`.
- Haiku gets **1** failure before climbing (Sonnet keeps 2, Opus keeps 1).
- Codex harness is untouched; it keeps its own cheaper and stronger models.

## Unchanged rules

- Sonnet → Opus → Fable climb rules, thresholds and logging.
- Root cause before every climb (now also before Haiku → Sonnet). A plan defect is fixed in PLAN.md and re-run on the **same** tier.
- Nothing starts on Fable. `/tune` "Fable without a prior Opus step" check unchanged.
- ESC-M1 (Sonnet → Opus climb rate) unchanged.
- `claude/jev/route.py` (prompt-level "needs more than Sonnet" for the main session) unchanged: it routes the orchestrator session, not executors.
- `log_escalation` and `log_dispatch` schemas unchanged (model and tier are free strings).

## Dispatch rule (`claude/skills/orchestrate/SKILL.md`)

Per task, the existing Jev batch gains:

- `needs_sonnet` noul: "Does the task in `task_section` need a model stronger than Haiku (touches more than one file, non-mechanical logic, or test design beyond a single assertion)?"

Start tier, in order:

1. `needs_opus` true at confidence ≥ `dispatch.min_confidence`, or orchestrator judgment → Opus (existing; logged as today).
2. Else, if `dispatch.haiku_default` is false → Sonnet (pre-change behavior); `needs_sonnet` is not asked and nothing extra is logged.
3. Else `needs_sonnet` true at confidence ≥ `dispatch.min_confidence`, or orchestrator judgment → Sonnet. Logged with `mcp__jev__log_escalation` (from_model haiku, to_model sonnet, decided_by jev or orchestrator, reason "skip-up: <why>").
4. Else → Haiku (`model: haiku` on the Agent call).

Answers below threshold go to the orchestrator, as today. Every dispatch still calls `mcp__jev__log_dispatch` with its `tier`.

Climb from Haiku: a Haiku executor that fails done-criteria `escalation.haiku_failures_before_sonnet` times (1), or reports CONFIDENCE below `escalation.executor_confidence_below`, gets the root-cause pass and is re-dispatched on Sonnet after `log_escalation` (from haiku, to sonnet). From there the existing Sonnet rules apply.

## Config (`claude/jev/thresholds.py`)

New defaults:

| Key | Default | Validation |
| --- | --- | --- |
| `escalation.haiku_failures_before_sonnet` | 1 | int in [1, 5] |
| `escalation.haiku_climb_max` | 0.35 | float in [0.0, 1.0] |
| `dispatch.haiku_default` | true | bool |

The failures-key check becomes one regex, `_failures_before_(sonnet|opus|fable)$`. This replaces the current `endswith("_failures_before_")` clause, which can never match a real key. The ladder comment is updated to `haiku -> sonnet -> opus -> fable`.

## Jev

- `needs_sonnet` added to `tune.CANONICAL`, so `needs_sonnet.<task>` folds onto it for override-rate stats.
- `log_escalation` description text: ladder `haiku -> sonnet -> opus -> fable`.

## `/tune` (`claude/jev/tune.py`)

- **ESC-M3 economy climb rate** = Haiku → Sonnet escalation records for tasks whose attempt-1 dispatch had `tier: haiku` ÷ tasks whose attempt-1 dispatch had `tier: haiku`. Skip-ups are excluded because those tasks have no Haiku attempt-1 dispatch. Reported as n/a with zero Haiku-started tasks.
- **Haiku share** = Haiku-started tasks ÷ tasks dispatched.
- **Proposal**: ESC-M3 > `escalation.haiku_climb_max` with at least 10 Haiku-started tasks → propose `dispatch.haiku_default: false`, with the logged climb reasons. Proposal only; the user approves, like other `/tune` changes.

## Docs

Updated to the four-tier ladder, keeping cheap / strong / frontier meanings and adding an **economy** tier below cheap:

- `claude/CLAUDE.md.template` (model policy block)
- `claude/skills/orchestrate/SKILL.md`, `claude/commands/orchestrate.md` (description)
- `docs/workflow.md` §3 and the thresholds table
- `docs/escalation-model.md` (diagram, rule 1, reference thresholds, reference binding)
- `docs/metrics.md` (new ESC-M3 row)
- `docs/architecture.md`, `README.md`
- `spec/dryas-spec-v1.md` (`ladder: [haiku, sonnet, opus, fable]`, `climb_after_failures: {haiku: 1, sonnet: 2, opus: 1}`)

`claude/agents/executor.md` is not changed. After merge, running `install/install.sh` rewrites the installed `~/.claude/CLAUDE.md` block; that run is asked for first.

## Coupling

- FlowObserve (`projects/flowobserve`): check its reducer for a hardcoded tier list. If one exists, the fix is a separate change in that repo, raised with the user, not made here.
- `claude/jev/context_watch.py` already treats Haiku as a 200k window. No change.

## Testing

pytest in `claude/jev/tests`, test-first:

- `test_thresholds.py`: new defaults present; `haiku_failures_before_sonnet` accepts 1 and 5, rejects 0, 6 and non-int; `haiku_climb_max` range; `haiku_default` must be bool.
- `test_tune.py`: ESC-M3 numerator and denominator; skip-up record does not count; n/a with no Haiku tasks; Haiku share; proposal fires at 0.36 with 10 tasks, not with 9 tasks, not at 0.35; `needs_sonnet.3` canonicalizes to `needs_sonnet`.
- Docs consistency: a grep finds no remaining three-tier ladder string ("Sonnet → Opus → Fable", "sonnet -> opus -> fable") outside dated history.

## Rollout

Worktree `worktree-haiku-tier` (off `main`). Multi-step, so `/orchestrate` runs the approved plan; then `/wreview` and verification-before-completion before merge.

## Out of scope

- Haiku for non-executor chores (summaries, commit messages, scouting).
- Changing the Codex binding.
- Auto-flipping `haiku_default` without user approval.
