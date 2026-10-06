# Adoption guide

There are three ways to adopt Dryas. Pick the lightest one that fits.

## 1. Use the reference implementation as is

For: one developer on Claude Code or Codex who wants the whole loop today.

1. Clone the repo and run the installer ([install.md](install.md)).
2. Read [workflow.md](workflow.md) once; Claude reads it before multi-step work.
3. Start every non-trivial task with a brainstorm, then `/orchestrate`.
4. Run `/tune` weekly and approve or reject its proposals.

## 2. Fork it and make it yours

For: a team that agrees with the model but has its own tools, models or rules.

1. Fork the repo.
2. Edit the method first, then the bindings:
   - [spec/dryas-spec-v1.md](../spec/dryas-spec-v1.md) and the layer docs in `docs/`, if your rules differ;
   - `reference/dryas.yaml`, to record your bindings (models, judge, memory);
   - `claude/CLAUDE.md.template` and `docs/workflow.md`, the always-loaded rules and the full reference.
3. Re-run the installer on every machine. Each re-install brings `~/.claude` back in step with your fork.
4. Keep machine-only notes in `~/.claude/docs/dryas-local.md`; the installer never touches it.

## 3. Write a new edition for another harness

For: running Dryas in a harness this repo does not support (OpenCode, Roo, Cursor, an in-house agent).

1. Read the [specification](../spec/dryas-spec-v1.md). Its rules are numbered so you can claim them one by one.
2. Write a `dryas.yaml` for your edition (start from [examples/manifests/](../examples/manifests/)).
3. Implement the **Core** rules first. They need only three harness features:
   - a way to load always-on rules (a rules file);
   - a pre-tool hook that can deny an edit (for the scope lock);
   - sub-agents or separate sessions (for executors).
4. Add the judge, memory and escalation logging next. Each degrades safely when missing.
5. Publish a conformance table: rule ID, met / partial / not met, and how.

The [reference map](../reference/README.md) shows how this repo implements each rule; reuse what you can. The scope lock (`claude/jev/scope_lock.py`) and plan-file tools are plain Python and harness-agnostic.

## Maturity levels

Turn layers on one at a time. Each one is useful alone, and a team that adopts all five on day one cannot tell which one caused a problem.

A level is earned by its metrics, not by the calendar. Move up only when the exit test has held for four weeks running. Metric IDs are defined in [metrics.md](metrics.md).

| Level | Turn on | Ready to move up when |
| --- | --- | --- |
| L0 Ad hoc | An AI assistant, no loop. | Starting point. |
| L1 Gated | Brainstorm-first, review-before-merge, only humans push. | Every merged change had an approved design (checked by hand) and a review (/tune: merges without a review = 0), and REV-M1 ≤ 2. |
| L2 Scoped | Plan files, worktrees and the scope lock. | GOV-M4 ≤ 1 denial per task. |
| L3 Laddered | Cheap executors and the escalation ladder, with every climb logged. | ESC-M1 under 20% and ESC-M2 = 0. |
| L4 Target | The judge, memory and a weekly tune. | Stay here: GOV-M1 < 500 ms, GOV-M2 5–25%, EXE-M1 ≤ 3×. |

Installing is not a level. The reference implementation turns on every L4 tool at once; the level is reached only when the metrics hold.

## Measuring it

KPIs, healthy ranges, sources and cadence: [metrics.md](metrics.md). Who owns each one: [roles.md](roles.md).
