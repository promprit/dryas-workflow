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

## Rolling it out to a team

| Week | Do | Watch |
| --- | --- | --- |
| 1 | Brainstorm-first and review-before-merge only. | How often design changes after approval. |
| 2 | Plan files, worktrees and the scope lock. | Scope-lock denials: are scopes too tight, or tasks too big? |
| 3 | Cheap executors and the escalation ladder. | Climb rate and reasons in the escalation log. |
| 4 | Judge and memory. | Judge override rate per question. |

Turn layers on one at a time. Each one is useful alone, and a team that adopts all five on day one cannot tell which one caused a problem.

## Measuring it

- **Escalation rate** per tier, and the top reasons.
- **Judge override rate** per question. High means the threshold or the question is wrong.
- **Scope-lock denials** per task. High means tasks are badly scoped.
- **Rework after review.** High means brainstorm or planning is too thin.
- **Cost per merged task**, split by tier.
