# Architecture

Dryas has five layers and one loop. The layers say *what must exist*; the loop says *in what order work moves through them*. Neither names a tool. The [reference implementation](../reference/README.md) binds each layer to concrete tools for Claude Code and Codex.

## The five layers

```
┌──────────────────────────────────────────────────────────────┐
│ Memory        what was tried, what worked, what failed       │  read before planning, written after each task
├──────────────────────────────────────────────────────────────┤
│ Governance    who may decide, what may be touched, by whom   │  human approvals, scope lock, judge, gates
├──────────────────────────────────────────────────────────────┤
│ Execution     small tasks, cheap executors, isolated trees   │  plan file, worktree, test first
├──────────────────────────────────────────────────────────────┤
│ Escalation    spend more only when cheaper failed            │  logged ladder, root cause before each climb
├──────────────────────────────────────────────────────────────┤
│ Review        nothing merges unverified                      │  two-stage review, verification, human ships
└──────────────────────────────────────────────────────────────┘
```

| Layer | Purpose | Model doc | Reference binding |
| --- | --- | --- | --- |
| **Memory** | Carry outcomes across sessions so the same mistake is not paid for twice. | [memory-model.md](memory-model.md) | Ruflo memory, namespaced per repo |
| **Governance** | Keep decisions with the right party: humans for design and outward actions, a cheap judge for narrow questions, a lock for file scope. | [governance.md](governance.md) | Jev gate and judge, scope lock hook, approval rules |
| **Execution** | Turn an approved design into small, verifiable tasks done by cheap agents that cannot collide. | [execution-model.md](execution-model.md) | `/orchestrate`, `executor` agent (Haiku first; Sonnet default for reviews), git worktrees |
| **Escalation** | Climb to a stronger model only on evidence of failure, with the reason on record. | [escalation-model.md](escalation-model.md) | Haiku → Sonnet → Opus → Fable, `log_escalation` |
| **Review** | Prove the work before it merges, and keep shipping a human act. | [review-model.md](review-model.md) | `/wreview`, verification skill, `/interrogate`, `/commit` |

## The loop

```
Brainstorm → Plan → Judge → Build → Escalate → Review → Ship
     ▲                                                    │
     └──────────────── Memory (read / write) ◄────────────┘
```

| Stage | Layer | Exit condition |
| --- | --- | --- |
| Brainstorm | Governance | A human approved the design (and a written spec, for architectural work). |
| Plan | Execution, Memory | A plan file exists; every task has a goal, a file scope, done criteria and a failing test. Past outcomes for this repo were read. |
| Judge | Governance | Each task is triaged: which executor, specific enough, test exists, needs a stronger model. |
| Build | Execution | Each executor returned its report block inside its scope. |
| Escalate | Escalation | Failing tasks climbed the ladder with a logged reason, or reached a human. |
| Review | Review | Spec compliance and code quality reviewed; tests run and seen to pass. |
| Ship | Review, Memory | A human-approved commit or merge; the outcome is stored in memory. |

A single-file fix may skip Plan, Judge and Build and run as one session. It never skips Brainstorm approval for design changes, or Review.

## Design principles

1. **Method over tooling.** Every rule is stated without a tool name first. A tool is a binding.
2. **Enforce, don't request.** A rule that can be a hook is a hook. Prompts are the fallback, not the mechanism.
3. **Cheapest capable model.** Start cheap, climb on evidence, log the climb.
4. **Narrow questions to small models.** The judge answers typed questions with a confidence. It never writes code or plans.
5. **Fail open to humans, never to autonomy.** When a gate or judge is unavailable, the decision falls back to normal permissions or the orchestrator. Nothing is ever auto-allowed.
6. **Isolation by default.** One agent per worktree; executors inside a loop are kept apart by non-overlapping scopes.
7. **Evidence, not claims.** "Done" is a report of commands run and criteria met, checked by someone else.
8. **Learn from overrides.** Every time the orchestrator overrules the judge, it is logged and fed back into thresholds.

## How the layers fit the harness

```
             ┌─────────────── Dryas specification ───────────────┐
             │  layers, loop, rules (MUST / SHOULD), manifest     │
             └───────────────────────┬───────────────────────────┘
                                     │ implemented by
          ┌──────────────────────────┼──────────────────────────┐
   Claude Code edition         Codex edition           your edition
   (claude/, install/)         (codex/, install/)      (any harness)
```

The specification is in [spec/dryas-spec-v1.md](../spec/dryas-spec-v1.md). Each edition declares its bindings in a `dryas.yaml` manifest; the one for this repo is [reference/dryas.yaml](../reference/dryas.yaml).

The operational detail of the reference implementation (hooks, thresholds, file locations) is in [workflow.md](workflow.md).
