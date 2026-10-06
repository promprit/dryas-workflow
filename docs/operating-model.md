# Operating model

**Purpose:** show on one page how Dryas covers each dimension of an operating model, and where each part is defined.

**The Dryas Workflow Framework is a target operating model for AI-assisted software delivery.**

The scope is deliberate: software delivery, not every use of AI in an organisation.

## Dimension map

The role column names who answers for the dimension or layer as a whole. Each metric has its own owner, which may be a different role: see [roles.md](roles.md).

| Dimension | What Dryas defines | Where | Accountable role | Metrics |
| --- | --- | --- | --- | --- |
| Process | The loop, its stages and their exit conditions | [architecture.md](architecture.md), [execution-model.md](execution-model.md), [review-model.md](review-model.md) | Loop owner | ESC-M1, REV-M1 |
| Governance and decision rights | Who decides what: humans for design and outward actions, a cheap judge for narrow questions, a lock for file scope | [governance.md](governance.md), [roles.md](roles.md) | Design approver | GOV-M2 |
| Technology | Layers as roles, not products; any harness can fill them | [architecture.md](architecture.md), [reference/](../reference/README.md) | Release owner | none |
| Controls and risk | Scope lock, gates, secrets, redaction, logged overrides and escalations | [governance.md](governance.md), [spec](../spec/dryas-spec-v1.md) | Threshold owner | GOV-M1, GOV-M3, GOV-M4, ESC-M2 |
| Cost | Escalation ladder, judge and swarm spend | [escalation-model.md](escalation-model.md), [metrics.md](metrics.md) | Threshold owner | EXE-M1, EXE-M2, EXE-M3 |
| Scale within a team | One agent per worktree, parallel loops, shared memory per repo | [execution-model.md](execution-model.md), [memory-model.md](memory-model.md) | Loop owner | none |
| People and organisation | Roles as hats, separation rules, RACI across the loop | [roles.md](roles.md) | All roles | none |
| Metrics | KPIs with range, source, cadence and status | [metrics.md](metrics.md) | Threshold owner | All |
| Current → target transition | Maturity levels L0–L4 | [adoption-guide.md](adoption-guide.md) | Design approver | none |

Status of each dimension and the work still open: [roadmap.md](roadmap.md).

## Layer view

How the spec, the roles and the metrics join, layer by layer.

| Layer | Spec rules | Accountable role | Metrics |
| --- | --- | --- | --- |
| Memory | MEM | Loop owner | none yet |
| Governance | GOV | Design approver, threshold owner | GOV-M1 to GOV-M4 |
| Execution | EXE | Loop owner | EXE-M1 to EXE-M3 |
| Escalation | ESC | Loop owner | ESC-M1, ESC-M2 |
| Review | REV | Reviewer, release owner | REV-M1 |

Rules that span the whole loop carry the WF prefix.

## Out of scope

- AI use outside software delivery
- Organisation-wide AI policy
- Hiring and team structure beyond the roles above
- Vendor and contract management
