# Roles

**Purpose:** give every decision the spec reserves for "a human" a named owner, so nothing an agent does goes unanswered for.

## Who you are

Working alone, you hold every role below. The roles still matter: they tell you which hat you are wearing when you approve something, and they are how the work splits when a second person joins. A role is a set of decision rights from the [spec](../spec/dryas-spec-v1.md), not a job title.

Solo, the agents supply the second pair of eyes: two-stage review (`/wreview`) and the two-model adversarial review (`/interrogate`). A human still signs every decision below.

## The roles

| Role | Decision rights | Owns metrics | Skills | Solo | Team |
| --- | --- | --- | --- | --- | --- |
| Design approver | Approves the design and, for architectural work, the written spec (WF-2, WF-3) | none | Judging scope and intent; reading a spec for gaps | You | Product or tech lead |
| Loop owner | Runs the orchestrated loop. Approves in-session install, move, delete, overwrite and settings changes after a dry-run or diff (GOV-4). Takes the task when the top tier fails (ESC-6) | GOV-M4, ESC-M1 | Writing tight plans; debugging from agent reports | You | The developer on the task |
| Reviewer | Decides a change is ready to merge after review and verification | REV-M1 | Reading a diff against its spec; judging test evidence | You | Another developer |
| Threshold owner | Runs the periodic tune and approves or rejects each proposal (GOV-9) | GOV-M1, GOV-M2, GOV-M3, ESC-M2, EXE-M1, EXE-M2 | Reading logs and trends; not retuning for one bad week | You | Platform or tooling lead |
| Release owner | Push, publish and release (GOV-5). Merges changes to the workflow repo and re-runs the installer, which is how shared settings change for everyone | EXE-M3 | Release hygiene; rollback | You | Tech lead or release manager |

Metric IDs are defined in [metrics.md](metrics.md).

## Separation

| Rule | Team | Solo |
| --- | --- | --- |
| **Must:** the reviewer of a change is not its loop owner. | Two people. | A `/wreview` runs between building and approving the merge; you approve its findings, not your memory of the work. |
| **Should:** the threshold owner is not the main loop owner. | Two people, so no one calibrates the gates that judge their own work. | Run `/tune` as its own sitting, never mid-task, and approve proposals one by one. |

## RACI across the loop

R = does the work, A = answers for it, C = consulted, I = informed. Stages are from [architecture.md](architecture.md). Agents are never A: wherever agents do the work, a named human answers for it.

| Stage | Agents | Design approver | Loop owner | Reviewer | Threshold owner | Release owner |
| --- | --- | --- | --- | --- | --- | --- |
| Brainstorm | R | A | R | C | | I |
| Plan | R | C | A | | | |
| Judge | R | | A | | | |
| Build | R | | A | | | |
| Escalate | R | | A | | I | |
| Review | R | | C | A | | |
| Ship | R (commit) | | I | C | | A, R (push, merge) |
| Calibrate (weekly) | | | C | | A, R | |

Solo, every human column is you.
