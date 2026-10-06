# Why Dryas exists

The Dryas Workflow Framework (Dryas for short) is a target operating model for AI-assisted software delivery. It defines the process, decision rights, roles, controls, cost rules and metrics: who decides, who builds, what each agent may touch, what is remembered, when to spend more on a stronger model, and what must be true before work merges.

The tools in this repo (Claude Code, Superpowers, Ruflo, Jev, the design skills) are one way to run it. They are replaceable. The model is the asset.

## The problems it solves

Teams that hand real delivery work to AI agents hit the same failures, whatever tool they use:

| Problem | What it looks like | Dryas answer |
| --- | --- | --- |
| **Building before deciding** | The agent starts coding from a one-line prompt and builds the wrong thing well. | Brainstorm first. Nothing is built before a human approves the design. |
| **Agents that wander** | A task to fix a form also "tidies" three other modules. Parallel agents overwrite each other. | Every task names its file scope. A lock denies edits outside it. One agent per worktree. |
| **Big model for everything** | Every call goes to the most expensive model, or every call goes to the cheapest and fails. | Cheap model by default, a logged ladder to stronger models only on failure. |
| **Big model for small questions** | The orchestrator burns context on "is this command safe?" and "which agent?". | A small judge answers narrow, typed questions. Below its confidence threshold the orchestrator decides. |
| **Amnesia** | Each session relearns what failed last week. | One memory layer, read before planning and written after each task. |
| **"Done" that is not done** | The agent says the tests pass. They were never run. | Executors report a fixed block (changed, tests run, criteria met, confidence). Review and verification gate the merge. |
| **Silent autonomy** | An agent installs, deletes, pushes or edits global settings on its own. | Named actions always need a human: install, overwrite, delete, push, settings changes. |
| **No learning loop** | Nobody knows if the guardrails are too tight or too loose. | Every escalation and every override of the judge is logged, and a weekly tune proposes threshold changes. KPIs with healthy ranges ([metrics.md](metrics.md)) set the maturity levels. |

## What Dryas is not

- **Not a plugin.** A plugin is one binding of the model to one harness. This repo ships two (Claude Code and Codex). Others can be written against the [specification](../spec/dryas-spec-v1.md).
- **Not a prompt pack.** The rules are enforced where they can be (hooks, scope lock, gates), not only asked for.
- **Not autonomous.** Dryas puts a human at the two points that matter most, design approval and the final say on anything outward-facing, and keeps agents fast everywhere else.
- **Not an organisation-wide AI policy.** The scope is software delivery.

## Where to go next

- [Operating model](operating-model.md): the whole model on one page.
- [Architecture](architecture.md): the five layers and the loop.
- [Adoption guide](adoption-guide.md): how to take Dryas into a team or another harness.
- [Specification v1 (draft)](../spec/dryas-spec-v1.md): the rules an implementation must follow.
