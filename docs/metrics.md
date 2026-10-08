# Metrics

**Purpose:** show whether the loop is healthy, using numbers the loop already produces, and say what to do when one drifts.

## How to read this

- **Status.** A **live** metric has a log today and is reported by `/tune` (or by `/cost` for Claude-side spend). A **partial** metric has part of its data logged and the rest planned or checked by hand. **Manual** means a person reads the number (for example from `/cost`); no tool computes it. A **planned** metric is defined here but needs a log record that does not exist yet. [Logging records](#logging-records) lists what writes each log.
- **Source.** Logs are JSON Lines in `~/.claude/jev/logs/<name>.jsonl` (override with `JEV_LOG_DIR`). The source column names the file.
- **Healthy range.** Starting values, calibrated by `/tune`. Where `/tune` already has a threshold, the range uses it.
- **Cadence.** Weekly means the `/tune` run. Per task means the orchestrator checks it before merging.
- **Out of range.** A metric outside its range is a prompt to look, not an automatic change. `/tune` proposes threshold changes; a human approves each one ([governance.md](governance.md)).
- **Owners.** Each KPI's owner is listed in [roles.md](roles.md).
- **IDs.** `<LAYER>-M<n>`, matching the layer prefixes of the spec rules so the operating-model map can join them.

## Governance

| ID | KPI | Definition | Healthy | Source | Cadence | Status | If out of range |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GOV-M1 | Judge latency | Median latency of judged tool calls (gate records with latency_ms). Judged share (judged ÷ all tool calls) is reported as a trend only. | < 500 ms | `gate` | Weekly | live | Check the judge provider. If judged share also rose, review the allowlist (`/tune` proposes additions above 30% judged share). If a compound-command skip looks wrong, set `gate.compound` to false and report the command. |
| GOV-M2 | Judge override rate | Orchestrator overrides ÷ judge answers, across questions with ≥20 calls (`/tune` also shows each question's rate) | 5–25% | `mcp`, `overrides` | Weekly | live | Above 25%: `/tune` proposes raising `dispatch.min_confidence`. Below 5% with most answers under threshold: proposes lowering it. |
| GOV-M3 | Gate ask + deny share | (`ask` + `deny`) ÷ all gate decisions | Trend only | `gate` | Weekly | live | A sudden jump: read the denied commands before changing anything. |
| GOV-M4 | Scope-lock denials per task | Edits denied by the scope lock ÷ tasks dispatched | 0–1 | `scope` | Per task | live | Repeated denials on one task mean its Scope globs in the plan are wrong. Fix the plan, not the lock. Read scope.jsonl to see which tasks were active at each denial; /tune reports the total. |

## Escalation

| ID | KPI | Definition | Healthy | Source | Cadence | Status | If out of range |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ESC-M1 | Strong-tier escalation rate | Cheap → strong climbs ÷ tasks dispatched. Codex dispatches count in the denominator but its climbs are not from Sonnet, so mixed use understates the rate. With Haiku on, the denominator leaves out tasks Haiku finished without reaching Sonnet, so the rate measures the cheap tier only. | Under 20% | `escalations`, `dispatch` | Weekly | live: only climbs from Sonnet count | Read the logged reasons. One recurring reason usually points to a plan or prompt defect ([escalation-model.md](escalation-model.md)). |
| ESC-M2 | Frontier dispatches without a strong-tier failure | Escalation records to the frontier tier whose from-tier is not the strong tier. An unlogged dispatch is invisible, so this also relies on every climb being logged | 0 | `escalations` | Weekly | live: `/tune` reports "Fable without a prior Opus step" | Any value above 0 breaks "stop at the first success". Treat it as a compliance finding. |
| ESC-M3 | Economy-tier climb rate | Haiku → Sonnet climbs ÷ tasks whose attempt-1 dispatch was on Haiku. Skip-ups (Jev `needs_sonnet` before any Haiku attempt) are excluded; each task counts once. | At or under 35% (`escalation.haiku_climb_max`) | `escalations`, `dispatch` | Weekly | live | Read the logged reasons. Above the max over ≥10 Haiku-started tasks, `/tune` proposes `dispatch.haiku_default: false`. The rate covers all logged history, so after switching Haiku back on, expect the proposal to repeat until new Haiku tasks outweigh the old climbs. |

## Execution and cost

| ID | KPI | Definition | Healthy | Source | Cadence | Status | If out of range |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EXE-M1 | Swarm vs plain token ratio | Mean swarm tokens ÷ plain tokens over ≥3 comparisons | ≤ 3.0× | `compare` | Weekly | live | Above: `/tune` proposes raising `route.swarm_min` so swarms run only when the judge is more sure. |
| EXE-M2 | Judge spend share | Judge spend ÷ Claude-side spend | Under 5% | `gate`, `route`, `mcp`, `compact` + `/cost` | Weekly | live (manual) | Above: the judge is asked too often. Check the judged share trend in /tune first. |
| EXE-M3 | Cost per merged task | Claude-side spend attributed to a task ÷ tasks merged | Baseline first, then trend | `merge` | Monthly | partial: cost_usd is entered by hand; /tune reports how many merges lack it | A rising trend with a flat ESC-M1 points to plans that are too coarse. |

## Review

| ID | KPI | Definition | Healthy | Source | Cadence | Status | If out of range |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REV-M1 | Review rounds per branch | Median review rounds per branch (1 = passed first review) | ≤ 2 (at most one fix round) | `review` | Per task, trended monthly | live | Above: findings are caught too late. Tighten the task's done criteria in the plan ([review-model.md](review-model.md)). |

## Memory

No KPI yet. Memory quality has no reliable signal in the logs today, and a made-up number would mislead more than it helps.

## Logging records

Each record is written once, at the point shown. Records written by the orchestrator or /wreview are only as complete as those calls; the scope record is written by the hook itself.

| Record | Fields | Written by | Feeds |
| --- | --- | --- | --- |
| `scope` | task, path, decision | scope-lock hook, on every deny | GOV-M4 |
| `dispatch` | task, tier, role, attempt | orchestrator via `log_dispatch`, every dispatch | GOV-M4, ESC-M1, ESC-M3 |
| `review` | task, round, critical, important, minor | `/wreview` via `log_review`, every round | REV-M1 |
| `merge` | task, branch, tasks_merged, cost_usd (optional) | orchestrator via `log_merge`, at merge | EXE-M3 |
