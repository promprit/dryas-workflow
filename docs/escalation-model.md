# Escalation model

**Purpose:** spend more only when something cheaper has failed, and keep the reason on record.

## The ladder

```
cheap tier ──fail──► strong tier ──fail──► frontier tier ──fail──► human
 (Sonnet)             (Opus)                (Fable)                (all reports)
```

Tiers are abstract; the reference implementation binds them to Sonnet, Opus and Fable.

## Rules

1. **Start at the bottom.** Every task starts on the cheap tier, unless the judge says the task needs the strong tier. Nothing starts on the frontier tier.
2. **Climb on evidence.** A task climbs when it fails its done criteria a set number of times, or reports confidence below a threshold.
3. **Stop at the first success.** If the strong tier solves it, the frontier tier is not used.
4. **Root cause before each climb.** Before climbing, the orchestrator debugs the failing reports:
   - a defect in the plan is fixed in the plan and re-run on the **same** tier;
   - otherwise the climb carries the root cause in its prompt.
5. **Log every step.** Each climb records the task, the reason, who decided, and the from and to tiers.
6. **The top of the ladder is a human.** If the frontier tier fails, the task goes to a human with every tier's report.
7. **Review uses the ladder too, capped.** Adversarial review panels may use the cheap and strong tiers, never the frontier tier.

## Reference thresholds

| Setting | Value |
| --- | --- |
| Cheap-tier failures before climbing | 2 |
| Executor confidence that triggers a climb | below 0.5 |
| Strong-tier failures before the frontier tier | 1 |
| Judge confidence to trust a `needs_opus` answer | 0.7 |

## Why a ladder

- Most tasks in a well-split plan are small. The cheap tier finishes them.
- A failed cheap attempt is not wasted: its report is the evidence the strong tier starts from.
- The log turns cost into data. A weekly tune shows how often each climb happens and why, which tells you whether tasks are split too coarsely or thresholds are wrong.

## Reference binding

Executors default to Sonnet (`claude/agents/executor.md`); the orchestrate skill re-runs on Opus and then Fable; `mcp__jev__log_escalation` records each step; thresholds are in `thresholds.json` (`escalation` key). In Codex, the same ladder runs on Codex's own cheaper and stronger models. Details: [workflow.md §3](workflow.md), [harnesses.md](harnesses.md).
