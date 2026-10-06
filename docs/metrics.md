# Metrics

**Purpose:** show whether the loop is healthy, using numbers the loop already produces, and say what to do when one drifts.

## How to read this

- **Status.** A **live** metric has a log today and is reported by `/tune` (or by `/cost` for Claude-side spend). A **planned** metric is defined here but needs a log record that does not exist yet; [Planned logging](#planned-logging) lists each one.
- **Source.** Logs are JSON Lines in `~/.claude/jev/logs/<name>.jsonl` (override with `JEV_LOG_DIR`). The source column names the file.
- **Healthy range.** Starting values, calibrated by `/tune`. Where `/tune` already has a threshold, the range uses it.
- **Cadence.** Weekly means the `/tune` run. Per task means the orchestrator checks it before merging.
- **Out of range.** A metric outside its range is a prompt to look, not an automatic change. `/tune` proposes threshold changes; a human approves each one ([governance.md](governance.md)).
- **Owners.** Each KPI's owner is listed in [roles.md](roles.md).
- **IDs.** `<LAYER>-M<n>`, matching the layer prefixes of the spec rules so the operating-model map can join them.

## Governance

| ID | KPI | Definition | Healthy | Source | Cadence | Status | If out of range |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GOV-M1 | Judged share | Tool calls the judge reviewed ÷ all tool calls | 10–30% (target ~20%) | `gate`, `calls` | Weekly | live | Above: `/tune` proposes allowlisting heads that were judged often and never denied. Below: check the allowlist has not grown too broad. |
| GOV-M2 | Judge override rate | Per question with ≥20 calls: orchestrator overrides ÷ judge answers | 5–25% | `mcp`, `overrides` | Weekly | live | Above 25%: `/tune` proposes raising `dispatch.min_confidence`. Below 5% with most answers under threshold: proposes lowering it. |
| GOV-M3 | Gate ask + deny share | (`ask` + `deny`) ÷ all gate decisions | Trend only | `gate` | Weekly | live | A sudden jump: read the denied commands before changing anything. |
| GOV-M4 | Scope-lock denials per task | Edits denied by the scope lock ÷ tasks dispatched | 0–1 | `scope` (planned) | Per task | planned | Repeated denials on one task mean its Scope globs in the plan are wrong. Fix the plan, not the lock. |

## Escalation

| ID | KPI | Definition | Healthy | Source | Cadence | Status | If out of range |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ESC-M1 | Strong-tier escalation rate | Cheap → strong climbs ÷ tasks dispatched | Under 20% | `escalations` + task count (planned) | Weekly | partial: count live, denominator planned | Read the logged reasons. One recurring reason usually points to a plan or prompt defect ([escalation-model.md](escalation-model.md)). |
| ESC-M2 | Frontier dispatches without a strong-tier failure | Frontier-tier dispatches with no prior strong-tier failure on the same task | 0 | `escalations` | Weekly | live | Any value above 0 breaks "stop at the first success". Treat it as a compliance finding. |

## Execution and cost

| ID | KPI | Definition | Healthy | Source | Cadence | Status | If out of range |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EXE-M1 | Swarm vs plain token ratio | Mean swarm tokens ÷ plain tokens over ≥3 comparisons | ≤ 3.0× | `compare` | Weekly | live | Above: `/tune` proposes raising `route.swarm_min` so swarms run only when the judge is more sure. |
| EXE-M2 | Judge spend share | Judge spend ÷ Claude-side spend | Under 5% | `gate`, `route`, `mcp`, `compact` + `/cost` | Weekly | live (manual) | Above: the judge is asked too often. Check GOV-M1 first. |
| EXE-M3 | Cost per merged task | Claude-side spend attributed to a task ÷ tasks merged | Baseline first, then trend | `merge` (planned) | Monthly | planned | A rising trend with a flat ESC-M1 points to plans that are too coarse. |

## Review

| ID | KPI | Definition | Healthy | Source | Cadence | Status | If out of range |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REV-M1 | Fix rounds after review | Median rounds of `/wreview` findings fixed before a task merges | ≤ 1 | `review` (planned) | Per task, trended monthly | planned | Above: findings are caught too late. Tighten the task's done criteria in the plan ([review-model.md](review-model.md)). |

## Memory

No KPI yet. Memory quality has no reliable signal in the logs today, and a made-up number would mislead more than it helps.

## Planned logging

Each planned metric needs one new record. Adding them is a roadmap item ([roadmap.md](roadmap.md)).

| Record | Fields | Written by | Feeds |
| --- | --- | --- | --- |
| `scope` | task, path, decision | Scope lock, on every deny | GOV-M4 |
| `dispatch` | task, tier | Orchestrator, once per task dispatched | GOV-M4, ESC-M1 |
| `review` | task, findings, rounds | `/wreview`, once per task | REV-M1 |
| `merge` | task, branch, cost | Orchestrator, at merge | EXE-M3 |
