# Dryas Workflow Framework Specification v1

- **Status:** Draft 0.1. Rules and manifest fields may still change before 1.0.
- **Scope:** what any implementation ("edition") of Dryas must do, on any agent harness.
- **Not in scope:** which tools, models or vendors an edition uses. Those are bindings, declared in the manifest.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are used as in RFC 2119.

## 1. Terms

| Term | Meaning |
| --- | --- |
| **Harness** | The agent runtime that hosts the session (Claude Code, Codex, OpenCode, …). |
| **Edition** | An implementation of this spec for one harness. |
| **Orchestrator** | The main session: brainstorms, plans, dispatches, integrates. |
| **Executor** | A sub-agent that does exactly one task. |
| **Judge** | A small model that answers narrow, typed questions with a confidence. |
| **Tier** | A rung on the escalation ladder (economy, cheap, strong, frontier). |
| **Loop** | One run of Brainstorm → Plan → Judge → Build → Escalate → Review → Ship, owning one worktree. |
| **Plan file** | The task list for one loop, stored in the loop's worktree. |
| **Scope** | The set of file globs a task may edit. |

## 2. Conformance

An edition is **Dryas Core** if it meets every Core rule. It is **Dryas Full** if it meets every rule. An edition MUST publish a conformance table listing each rule ID as `met`, `partial` or `not met`, with one line on how.

Rules marked *(Core)* below are Core. All others are Full.

## 3. Workflow (WF)

- **WF-1** *(Core)* Multi-step work MUST follow the stage order Brainstorm, Plan, Judge, Build, Escalate, Review, Ship. Judge and Escalate MAY be no-ops when not needed.
- **WF-2** *(Core)* A task MUST NOT be planned or dispatched before a human approves the design.
- **WF-3** Architectural work SHOULD produce a written spec before planning.
- **WF-4** A single-file change MAY skip Plan, Judge and Build. It MUST NOT skip Review.
- **WF-5** *(Core)* The always-loaded rules MUST come from one source in the edition's repository, so every machine's copy matches.

## 4. Memory (MEM)

- **MEM-1** An edition SHOULD have exactly one project-memory layer.
- **MEM-2** Project memory MUST be namespaced by the main repository, not the worktree.
- **MEM-3** The orchestrator SHOULD read memory before writing a plan, and SHOULD store each task's outcome after it returns.
- **MEM-4** *(Core)* Memory MUST NOT store secrets or file contents.
- **MEM-5** *(Core)* An unavailable memory layer MUST NOT block the loop.
- **MEM-6** An edition SHOULD provide a handoff that saves selected context before a session reset and restores it after.

## 5. Governance (GOV)

- **GOV-1** *(Core)* Every task MUST declare its scope as file globs.
- **GOV-2** *(Core)* While tasks are active, the harness MUST deny edits outside the union of their scopes. A prompt-only rule does not satisfy this. Edits the harness cannot see (for example a shell command that writes files) MUST be listed as a known limit.
- **GOV-3** *(Core)* A worktree MUST belong to exactly one orchestrator session.
- **GOV-4** *(Core)* Install, move, delete, overwrite and settings changes MUST be approved by a human after a dry-run or diff.
- **GOV-5** *(Core)* Push, publish and release MUST be done or approved by a human.
- **GOV-6** The judge MUST NOT write code or plans. Below its confidence threshold, or when it flags escalation, the orchestrator MUST decide.
- **GOV-7** *(Core)* A tool-call gate MUST NOT auto-allow. On failure it MUST make no decision, so normal permissions apply.
- **GOV-8** Every orchestrator decision against a judge answer MUST be logged with the question, the answer, the decision and the reason.
- **GOV-9** Threshold changes MUST be proposed and approved by a human, never applied automatically.
- **GOV-10** *(Core)* Credentials MUST live only in the environment, never in files, configs, logs or tests. Data sent to a judge MUST be redacted and MUST NOT include file contents.
- **GOV-11** Hooks for one event SHOULD run in a fixed order: scope lock, gate, memory, observers. A deny MUST beat an ask. A crashing stage MUST NOT block.

## 6. Execution (EXE)

- **EXE-1** *(Core)* Multi-step work MUST run in its own worktree (or an equivalent isolated checkout) and branch.
- **EXE-2** *(Core)* The plan MUST be a file with one section per task, each with Goal, Scope, Done and Failing test first. The plan file MUST NOT be committed.
- **EXE-3** Each executor SHOULD receive only its own task section and the worktree path.
- **EXE-4** *(Core)* If a task has no failing test, a test MUST be written and seen to fail before the fix.
- **EXE-5** The orchestrator MUST NOT edit project files itself on multi-step work.
- **EXE-6** Executors MUST NOT commit, push, merge, create worktrees or spawn agents.
- **EXE-7** *(Core)* Every executor MUST end with a report of changed files, tests run with results, each done criterion met or not, a confidence from 0 to 1, and anything unresolved.
- **EXE-8** Tasks with non-overlapping scopes MAY run in parallel.

## 7. Escalation (ESC)

- **ESC-1** Executors SHOULD start on the cheapest tier. The judge MAY start a task one tier up. A task MUST NOT start on the top tier.
- **ESC-2** A task MUST climb one tier after its configured failures or below its configured confidence.
- **ESC-3** A task MUST stop climbing at its first success.
- **ESC-4** Before each climb the orchestrator SHOULD root-cause the failure. A plan defect MUST be fixed in the plan and re-run on the same tier.
- **ESC-5** *(Core)* Every climb MUST be logged with task, reason, decider, from tier and to tier.
- **ESC-6** *(Core)* After the top tier fails, the task MUST go to a human with every tier's report.

## 8. Review (REV)

- **REV-1** *(Core)* Multi-step changes MUST be reviewed before merge.
- **REV-2** Review SHOULD run in two stages: spec compliance, then code quality.
- **REV-3** *(Core)* Tests in the done criteria MUST be run and seen to pass before work is reported done.
- **REV-4** Architectural or contested changes SHOULD get an adversarial review by two models below the top tier, with a lead verdict.
- **REV-5** *(Core)* Merge MUST come after review and verification.
- **REV-6** Measured performance claims SHOULD be vetted against a benchmark checklist before they are reported.

## 9. Manifest

An edition SHOULD describe its bindings in a `dryas.yaml` file at its repository root or in `reference/`. The manifest is descriptive in v1: it records what the edition uses so that people and tools can compare editions. A later version may make it the installer's input.

### 9.1 Top-level fields

| Field | Required | Meaning |
| --- | --- | --- |
| `dryas` | yes | Spec version the edition targets, e.g. `"1.0-draft"`. |
| `edition` | yes | Edition name. |
| `harness` | yes | Harness name(s). |
| `conformance` | yes | `core` or `full`, plus a link to the conformance table. |
| `workflow` | yes | Stages and which are required (WF). |
| `memory` | yes | Provider and policy (MEM). `provider: none` is allowed. |
| `governance` | yes | Scope lock, gate, judge, approvals (GOV). |
| `execution` | yes | Orchestrator, executor, isolation, TDD (EXE). |
| `escalation` | yes | Ladder and thresholds (ESC). |
| `review` | yes | Review stages and merge rule (REV). |

### 9.2 Example

```yaml
dryas: "1.0-draft"
edition: example
harness: [claude-code]
conformance: {level: core, table: CONFORMANCE.md}

workflow:
  stages: [brainstorm, plan, judge, build, escalate, review, ship]
  brainstorm: {required: true, approval: human}
  plan: {required: true, format: plan-file}
  judge: {required: false}

memory:
  provider: ruflo
  namespace: main-repo
  read: before-plan
  write: after-task

governance:
  scope_lock: {required: true, provider: dryas-scope-lock}
  gate: {provider: jev, auto_allow: false, on_failure: no-decision}
  judge: {provider: jev, min_confidence: 0.7, below_threshold: orchestrator}
  human_approval: [design, install, move, delete, overwrite, settings, push, release]

execution:
  orchestrator: opus
  executor: haiku
  review_executor: sonnet
  isolation: worktree
  one_agent_per_worktree: true
  tdd: required

escalation:
  ladder: [haiku, sonnet, opus, fable]
  climb_after_failures: {haiku: 1, sonnet: 2, opus: 1}
  climb_below_confidence: 0.5
  root_cause_before_climb: true
  log: required
  after_top: human

review:
  mandatory: true
  stages: [spec-compliance, code-quality]
  verification: required
  merge_after: [review, verification]
  push: human
```

The manifest for this repository's editions is [reference/dryas.yaml](../reference/dryas.yaml).

## 10. Changes

| Version | Date | Change |
| --- | --- | --- |
| 0.1 draft | 2026-10-06 | First draft, extracted from the reference implementation. |
