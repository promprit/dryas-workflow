# Why Dryas exists

**Brilliant agents. No discipline.** They build before anyone agreed what. They tidy files nobody asked about. They report tests they never ran. They spend big-model money on small-model questions.

Dryas fixes that with rules your agents can't ignore. It is a target operating model for AI software delivery (process, decision rights, roles, controls, cost rules and metrics) and a reference implementation that enforces it with hooks on Claude Code and Codex. The tools are replaceable. The model is the asset.

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

## Why not just install the skills?

Process skills, a memory server, a model router and design skills can each be installed on their own. Installed side by side, though, they are a pile of parts rather than a method. Each assumes it runs the show, none knows the others exist, and their rules are prompts the agent may follow or skip. Dryas owns the core of those jobs and makes them one system.

| Skills installed side by side | Dryas |
| --- | --- |
| **Rules are requests.** A skill tells the agent to stay in scope or run the tests; nothing stops it when it does not. | **Rules are enforced.** Hooks deny edits outside a task's Scope, gate risky commands and gate the commit. The prompt is backed by a check. |
| **Tools compete for the same job.** Third-party plan executors, agent swarms and your own subagents each want to run the plan; two memory systems each want to remember it. | **One owner per job.** The Dryas skills own process, Dryas memory owns memory, the judge (local, or Jev) owns judgement, the scope lock owns scope, `/orchestrate` runs the plan. |
| **Hooks run in install order.** Whichever plugin was installed last decides what fires first, and a noisy hook can mask a blocking one. | **One hook chain, in a fixed order.** Scope lock, then gate, then memory, then observer. The order is a file in the repo, tested like code. |
| **No cost policy.** Each tool picks its own model, so work runs on whatever is default: often too strong, sometimes too weak. | **A model ladder.** The cheapest model that can do the task goes first; a stronger one is used only after a failure, and every step up is logged with its reason. |
| **No feedback.** Nobody can say whether the guardrails are too tight or too loose. | **A learning loop.** Escalations and overrides of the judge are logged; `/tune` reads them weekly and proposes threshold changes. |
| **Every machine is set up by hand** and drifts from the others. | **One installer from one repo.** It merges into your settings without overwriting values you already set, and re-running it brings every machine back in line. |

The skills are still doing the work. Dryas decides which one does which part, in what order, under which checks, and at what cost.

Skills side by side also give you no view of the whole loop. [FlowObserve](https://github.com/promprit/flowobserve), an optional observe-only companion, shows it live: each session's stage, escalations up the ladder, one build lane per plan task and spend against budget.

## What Dryas is not

- **Not only a plugin.** The Claude Code edition ships as a plugin (`dryas@dryas-workflow`), but Dryas itself is a specification with one binding per harness. This repo ships three bindings (Claude Code, Codex and OpenCode); Pi, Roo and Cursor are planned. Others can be written against the [specification](../spec/dryas-spec-v1.md).
- **Not a prompt pack.** The rules are enforced where they can be (hooks, scope lock, gates), not only asked for.
- **Not autonomous.** Dryas puts a human at the two points that matter most, design approval and the final say on anything outward-facing, and keeps agents fast everywhere else.
- **Not an organisation-wide AI policy.** The scope is software delivery.

## Where to go next

- [Operating model](operating-model.md): the whole model on one page.
- [Architecture](architecture.md): the five layers and the loop.
- [Adoption guide](adoption-guide.md): how to take Dryas into a team or another harness.
- [Specification v1 (draft)](../spec/dryas-spec-v1.md): the rules an implementation must follow.
