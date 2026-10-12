# Dryas Workflow Framework

![ci](https://github.com/promprit/dryas-workflow/actions/workflows/ci.yml/badge.svg)

**The Dryas Workflow Framework (Dryas for short) is a target operating model for AI-assisted software delivery.** It defines the process, decision rights, roles, controls, cost rules and metrics: who decides, who builds, what each agent may touch, what is remembered, when to pay for a stronger model, and what must be true before work merges.

The method is the asset; the tools are replaceable. This repo holds both:

- **The framework:** why it exists, five layers, one loop, and a draft specification any harness can implement.
- **A reference implementation**: a Claude Code plugin (`dryas@dryas-workflow`) and a Codex plugin, built on Superpowers, Ruflo, Jev and a few design skills.

This repo is public but expect rough edges. See [CONTRIBUTING.md](CONTRIBUTING.md) for the portability rules and how to run the tests.

Built and run by [Dryas Studio](https://dryasstudio.com), which delivers every client project with it.

See it running: [FlowObserve](https://github.com/promprit/flowobserve) shows every live session's stage in the loop and tells you when one needs you. [Live demo](https://dryasstudio.com/demos/flowobserve/), nothing to install.

## Why not just install the skills?

You can install Superpowers, Ruflo and a few design skills on their own. Side by side, their rules are prompts the agent may skip, they compete for the same jobs, their hooks fire in install order and nothing controls model spend. Dryas makes them one system: hooks enforce the rules, each job has one owner, the hook chain has a fixed order, a logged ladder picks the model, and a weekly tune checks that the guardrails fit. The full comparison: [Why not just install the skills?](docs/why-dryas.md#why-not-just-install-the-skills)

## The framework

```
Memory       what was tried, what worked, what failed
Governance   who may decide, what may be touched, by whom
Execution    small tasks, cheap executors, isolated worktrees
Escalation   spend more only when cheaper failed, and log why
Review       nothing merges unverified; a human ships
```

| Read | For |
| --- | --- |
| [Operating model](docs/operating-model.md) | The whole model on one page: dimensions, layers, roles, metrics |
| [Why Dryas](docs/why-dryas.md) | The problems it solves, and what it is not |
| [Architecture](docs/architecture.md) | The five layers, the loop, design principles |
| [Memory](docs/memory-model.md) · [Governance](docs/governance.md) · [Execution](docs/execution-model.md) · [Escalation](docs/escalation-model.md) · [Review](docs/review-model.md) | One model doc per layer |
| [Roles](docs/roles.md) | Who holds each human decision, solo and in a team, with a RACI |
| [Metrics](docs/metrics.md) | KPIs per layer with healthy ranges, sources and cadence |
| [Dryas Workflow Framework Specification v1 (draft)](spec/dryas-spec-v1.md) | Numbered MUST / SHOULD rules and the `dryas.yaml` manifest |
| [Reference map](reference/README.md) | How this repo implements each rule, with a conformance table |
| [Examples](examples/README.md) | A feature walked through the loop, a plan file, manifests |
| [Adoption guide](docs/adoption-guide.md) | Use it, fork it, or write an edition for another harness |
| [Roadmap](docs/roadmap.md) | Framework, then spec and manifest, then editions |
| [Plans](docs/plans/) · [Specs](docs/specs/) · [Superpowers specs and plans](docs/superpowers/) | Design history: the dated specs and plans each change was built from. Kept as a record, not as current docs |

## The loop

```
Brainstorm → Plan → Judge → Build → Escalate → Review → Ship
```

- **Brainstorm**: settle the design with you before any code is written.
- **Plan**: split the approved design into small tasks, each with a file scope and a done check.
- **Judge**: a small model answers narrow questions (is this step risky? which model?) so the big model is called less.
- **Build**: Haiku executors do each task inside a git worktree; harder tasks start on Sonnet or Opus.
- **Escalate**: if Haiku fails a task, Sonnet tries it; then Opus. Fable is used only if Opus also fails.
- **Review**: the diff is reviewed and the tests are run before anything merges.
- **Ship**: merge and commit, after verification.

## How the reference implementation works

- **Escalation ladder.** Haiku, then Sonnet, then Opus, then Fable. Each step is logged with a reason.
- **Scope lock.** An executor can only edit the files its task names. A hook blocks other edits.
- **Parallel loops.** One project can run many loops at once. The rule is one agent per git worktree: each loop has its own worktree and branch, so loops never collide, and each merges only after its own review.
- **Jev gating.** Jev is a small model that answers narrow, typed questions. It never writes code or plans. If it is unsure, the main model decides.
- **Design rule.** UI work goes through Impeccable and UI UX Pro Max.
- **One source for the rules.** The always-loaded rules come from `claude/CLAUDE.md.template`; the Dryas plugin injects them at session start. The full reference comes from `docs/workflow.md`. Change them here and re-run the installer; every machine and account then matches the repo.

## Install

Dryas is a Claude Code plugin, `dryas@dryas-workflow`, served from its own marketplace: this repo. It is a community plugin, not an Anthropic-official one and not in `claude-plugins-official`.

```
git clone https://github.com/promprit/dryas-workflow
cd dryas-workflow
install/install.sh                              # macOS, Linux, WSL
install\install.ps1                             # Windows (PowerShell)
install/install.sh --claude-dir ~/.claude-team  # once more for each other Claude account
```

Run it once per Claude config dir (`--claude-dir`). It adds the marketplace, installs the plugin and its Superpowers dependency, and merges model, env and permission rules into that dir's `settings.json`. All accounts share one state folder, `~/.dryas`.

Manual route, inside Claude Code:

```
/plugin marketplace add promprit/dryas-workflow
/plugin install dryas@dryas-workflow
```

(Shell form: `claude plugin install dryas --marketplace promprit/dryas-workflow`.) This gives you the plugin only. Superpowers must also be installed from `claude-plugins-official`, and you still need setup for the settings, permissions and shared state in `~/.dryas`.

`--uninstall` removes Dryas from one config dir and keeps `~/.dryas`; adding `--purge` on the last account also deletes the logs, `/tune` thresholds and handoffs there, but keeps your notes in `~/.dryas/docs/dryas-local.md`.

Details, flags and troubleshooting: [docs/install.md](docs/install.md).

## Works with

| Harness | Status |
| --- | --- |
| Claude Code | Plugin `dryas@dryas-workflow` |
| Codex | Plugin `dryas@dryas-workflow` (`install/install.sh --harness codex`) |
| Pi, OpenCode, Roo, Cursor | Later |

Several accounts side by side (for example in T3 Code) share one `~/.dryas`. Details: [docs/harnesses.md](docs/harnesses.md).

Platforms: macOS, Linux, WSL and Windows.

## Use it for yourself

Fork this repo and make the workflow yours:

1. Fork it and clone your fork.
2. Edit `claude/CLAUDE.md.template` (the rules every session loads) and `docs/workflow.md` (the full reference). If your method differs, change the layer docs and `reference/dryas.yaml` too ([adoption guide](docs/adoption-guide.md)).
3. Run `./install/install.sh` (or `.\install\install.ps1` on Windows). Every re-install brings each account back in step with your fork.

Keep notes that only fit your machine in `~/.dryas/docs/dryas-local.md`. The installer never touches that file.

## Reference stack

These are the reference implementation's bindings, not part of the method; each layer can be bound to something else. All parts are on by default. Each can be skipped with a flag.

| Part | What it does | Skip with |
| --- | --- | --- |
| [Claude Code](https://docs.claude.com/en/docs/claude-code) | The host: agents, hooks, commands | required |
| [Jev (TypeSafe)](https://github.com/typesafe-ai/skills) | Decision support and gates | `--no-jev` |
| [Ruflo](https://github.com/ruvnet/ruflo) | Orchestration and memory | `--no-ruflo` |
| [Superpowers](https://github.com/obra/superpowers) | Process skills (brainstorming, worktrees, review) | required by the plugin (`--no-superpowers` drops only its deny rules) |
| [Impeccable](https://github.com/pbakaus/impeccable) and [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | Design skills | `--no-design` |
| [pstack](https://github.com/michael-denyer/pstack-claude) picks | Interrogate review, cleanup, benchmark checklist, executor principles (vendored, adapted) | `--no-pstack-picks` |

Optional, installed separately: [FlowObserve](https://github.com/promprit/flowobserve), an observe-only monitor for live Claude Code sessions. With Dryas it also shows escalations, one build lane per plan task, Jev spend against budget and per-stage timings. It never blocks or changes anything.

## Requirements

- A Claude subscription with Claude Code, or the Codex CLI (0.162.1 or newer).
- An OpenRouter API key for Jev. Jev is bring-your-own-key: set `OPENROUTER_API_KEY` in your shell, or pass `--openrouter-key` to setup (stored in Claude Code's secure storage; Codex reads the key from the shell only). Without a key, Jev checks are skipped and the workflow still runs.
- macOS, Linux, WSL or Windows.
- Python 3.9+, Node and npm (for Ruflo), git.

## Credits

- [Superpowers](https://github.com/obra/superpowers) by obra
- [Ruflo](https://github.com/ruvnet/ruflo) by ruvnet
- [Impeccable](https://github.com/pbakaus/impeccable) by pbakaus
- [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) by nextlevelbuilder
- [TypeSafe skills (Jev)](https://github.com/typesafe-ai/skills) by TypeSafe
- [pstack](https://github.com/cursor/plugins/tree/main/pstack) by Lauren Tan, Claude Code port [pstack-claude](https://github.com/michael-denyer/pstack-claude) by Michael Denyer, and deslop from Cursor's cursor-team-kit (all MIT)

Third-party code is fetched from upstream by the installer, except a few adapted pstack files in `claude/pstack/` (see [NOTICE.md](NOTICE.md)).

## License

MIT. See [LICENSE](LICENSE).

After installing on a new machine, run the [release check](docs/release-check.md).
