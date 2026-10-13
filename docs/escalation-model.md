# Escalation model

**Purpose:** spend more only when something cheaper has failed, and keep the reason on record.

## The ladder

```
fast ──fail──► standard ──fail──► strong ──fail──► frontier ──fail──► human
```

Tiers are abstract and the same in every harness: `fast`, `standard`, `strong`, `frontier`. The tier-to-model table is in [workflow.md §3](workflow.md).

## Rules

1. **Start at the bottom.** Every task starts on the `fast` tier, unless the judge says it needs the `standard` or `strong` tier. Nothing starts on the `frontier` tier. If the `fast` tier is switched off, tasks start on the `standard` tier.
2. **Climb on evidence.** A task climbs when it fails its done criteria a set number of times, or reports confidence below a threshold.
3. **Stop at the first success.** If the strong tier solves it, the frontier tier is not used.
4. **Root cause before each climb.** Before climbing, the orchestrator debugs the failing reports:
   - a defect in the plan is fixed in the plan and re-run on the **same** tier;
   - otherwise the climb carries the root cause in its prompt.
5. **Log every step.** Each climb records the task, the reason, who decided, and the from and to tiers.
6. **The top of the ladder is a human.** If the frontier tier fails, the task goes to a human with every tier's report.
7. **Review uses the ladder too, capped.** Adversarial review panels may use the `standard` and `strong` tiers, never the `fast` or `frontier` tier.

## Reference thresholds

| Setting | Value |
| --- | --- |
| `fast`-tier failures before the `standard` tier | 1 |
| `standard`-tier failures before climbing | 2 |
| Executor confidence that triggers a climb | below 0.5 |
| Strong-tier failures before the frontier tier | 1 |
| Judge confidence to trust a `needs_sonnet` or `needs_opus` answer | 0.7 |
| `fast`-tier climb rate above which the tune proposes switching it off | 0.35 over ≥10 tasks |

## Why a ladder

- Most tasks in a well-split plan are small. The `fast` tier finishes them.
- A failed `fast` attempt is not wasted: its report is the evidence the strong tier starts from.
- The log turns cost into data. A weekly tune shows how often each climb happens and why, which tells you whether tasks are split too coarsely or thresholds are wrong.

## Reference binding

Executors start on the `fast` tier (the orchestrate skill passes `model: haiku`; claude/agents/executor.md (`dryas:executor`) stays on the `standard` tier for review dispatches); the orchestrate skill re-runs on the `standard`, `strong` and then `frontier` tier; the Jev MCP tool `log_escalation` (`mcp__plugin_dryas_jev__log_escalation` in Claude Code) records each step; thresholds are in `thresholds.json` (`escalation` key). In Codex, the same ladder runs on the models configured in Codex. Details: [workflow.md §3](workflow.md), [harnesses.md](harnesses.md).
