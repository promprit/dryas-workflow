# Governance

**Purpose:** keep every decision with the right party. Humans decide design and anything outward-facing. A cheap judge answers narrow questions. A lock decides what files an agent may touch.

## Who decides what

| Decision | Decided by | Never by |
| --- | --- | --- |
| What to build (design, approach) | Human, after a brainstorm | An agent on its own |
| How to split it into tasks | Orchestrator | Executors or the judge |
| Narrow typed questions (is this risky? which executor? done?) | Judge, if confident | The judge below its threshold: then the orchestrator |
| Which files a task may edit | The plan's `Scope:`, enforced by a lock | The executor |
| Install, move, delete, overwrite, settings change | Human, after a dry-run or diff | Any agent |
| Push, publish, release | Human | Any agent |

## Rules

1. **Brainstorm first.** No task is planned or dispatched before a human approves the design. Architectural work also gets a written spec.
2. **Scope lock.** Every task names its file scope as globs. While tasks are active, edits outside the union of their scopes are denied by the harness, not just discouraged. An executor that needs another file stops and asks.
3. **One agent per worktree.** A worktree belongs to one orchestrator session. Parallel work uses parallel worktrees.
4. **The judge answers, never acts.** The judge is a small, cheap model that answers typed questions with a confidence. It never writes code or plans. Below threshold, or when it flags escalation, the orchestrator decides.
5. **Gates never auto-allow.** A safety gate on tool calls can deny or ask; it cannot allow. On any failure (timeout, no key, offline) it makes no decision and normal permissions apply.
6. **Overrides are logged.** Whenever the orchestrator acts against a judge answer, it logs the question, the answer, its own decision and why.
7. **Calibration is proposed, not applied.** A periodic tune reads overrides and escalations and proposes threshold changes. A human approves each one.
8. **Secrets stay in the environment.** Credentials live in the shell environment only, never in files, configs, logs or tests. Only the minimum (redacted command, file path and size, never file contents) leaves the machine for judging.
9. **Hook order is fixed.** Per event: scope lock, then judge gate, then memory hooks, then observers (observe-only, last). A deny beats an ask; a crashing stage never blocks.

## Asking good judge questions

- One narrow judgment per question.
- Named fields in the state, not prose.
- Every multiple choice includes `none_of_these`.
- Independent questions are batched into one call.

## Reference binding

Jev (TypeSafe, via OpenRouter) is the judge and gate. The scope lock is `claude/jev/scope_lock.py`, armed by `.orchestrate/active.json`. Hook order comes from `claude/jev/chain.json`. Thresholds live in `~/.claude/jev/thresholds.json`; `/tune` proposes changes. Details: [workflow.md §1, §5–6](workflow.md).
