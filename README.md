# Dryas Workflow Framework

![ci](https://github.com/promprit/dryas-workflow/actions/workflows/ci.yml/badge.svg)

**The Dryas Workflow Framework (Dryas for short) is a target operating model plugin for AI software delivery: a framework, a draft specification and a reference implementation that runs on its own core (a deterministic local judge, its own memory and process skills) on Claude Code and Codex. Superpowers, Ruflo and the Jev model are optional extras or upgrades.** It defines the process, decision rights, roles, controls, cost rules and metrics: who decides, who builds, what each agent may touch, what is remembered, when to pay for a stronger model, and what must be true before work merges.

The method is the asset; the tools are replaceable. This repo holds both:

- **The framework:** why it exists, five layers, one loop, and a draft specification any harness can implement.
- **A reference implementation**: a Claude Code plugin (`dryas@dryas-workflow`) and a Codex plugin, with the Dryas core (judge, memory, process skills) built in, a few design skills, and Ruflo, Superpowers and the Jev model as optional extras.

This repo is public but expect rough edges. See [CONTRIBUTING.md](CONTRIBUTING.md) for the portability rules and how to run the tests.

Built and run by [Dryas Studio](https://dryasstudio.com), which delivers every client project with it.

See it running: [FlowObserve](https://github.com/promprit/flowobserve) shows every live session's stage in the loop and tells you when one needs you. [Live demo](https://dryasstudio.com/demos/flowobserve/), nothing to install.

## Why not just install the skills?

You can install process skills, a memory server and a few design skills on their own. Side by side, their rules are prompts the agent may skip, they compete for the same jobs, their hooks fire in install order and nothing controls model spend. Dryas owns the core of that system, so it works as one: hooks enforce the rules, each job has one owner (the Dryas skills own process, Dryas memory owns memory, the judge owns judgement, the scope lock owns scope), the hook chain has a fixed order, a logged ladder picks the model, and a weekly tune checks that the guardrails fit. Ruflo, Superpowers and the Jev model plug into the same slots when you want them. The full comparison: [Why not just install the skills?](docs/why-dryas.md#why-not-just-install-the-skills)

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
- **Build**: `fast`-tier executors do each task inside a git worktree; harder tasks start on the `standard` or `strong` tier.
- **Escalate**: if the `fast` tier fails a task, the `standard` tier tries it; then `strong`. The `frontier` tier is used only if `strong` also fails.
- **Review**: the diff is reviewed and the tests are run before anything merges.
- **Ship**: merge and commit, after verification.

Commands you will use: `/orchestrate`, `/wreview`, `/interrogate`, `/commit`, `/handoff`, `/tune` and `/retro` (a session retrospective that proposes lessons and never applies them). Terms are in the [glossary](GLOSSARY.md).

## How the reference implementation works

- **Escalation ladder.** `fast`, then `standard`, then `strong`, then `frontier`. Each step is logged with a reason.
- **Scope lock.** An executor can only edit the files its task names. A hook blocks edits to other files made with the file-edit tools; writes from shell commands are not covered.
- **Parallel loops.** One project can run many loops at once. The rule is one agent per git worktree: each loop has its own worktree and branch, so loops never collide, and each merges only after its own review.
- **Judge.** A judge answers narrow, typed questions (is this command risky? which model?). By default `judge.provider` is `auto`: the Jev model when `OPENROUTER_API_KEY` is set, otherwise the deterministic local judge, which needs no key and no network. It never writes code or plans. If it is unsure, the main model decides.
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

Run it once per Claude config dir (`--claude-dir`). A fresh install needs Python 3.9+ and git only: it adds the marketplace, installs the plugin and the owned core, and merges model, env and permission rules into that dir's `settings.json`. All accounts share one state folder, `~/.dryas`.

Optional extras and choices, all flags on the same command:

```
install/install.sh --judge local|jev       # judge provider; without it the setting stays auto (Jev when a key is set, else local)
install/install.sh --with-ruflo            # Ruflo extra (needs Node and npm); --memory dryas|ruflo|none picks the memory provider
install/install.sh --with-superpowers      # Superpowers extra
install/install.sh --no-design             # skip Impeccable and UI UX Pro Max (installed by default)
```

`--openrouter-key KEY` implies `--judge jev`. Upgrading from 1.x keeps what you have; the cut-over steps are in [docs/install.md](docs/install.md#cut-over-from-1x).

Manual route, inside Claude Code:

```
/plugin marketplace add promprit/dryas-workflow
/plugin install dryas@dryas-workflow
```

(Shell form: `claude plugin install dryas --marketplace promprit/dryas-workflow`.) This gives you the plugin only: the rules, hooks, scope lock, judge chain, Dryas memory, agents, commands and skills. It does not give you what setup merges into that dir's `settings.json`: the `model` setting, the `env` the hooks need (`DRYAS_PY`, `DRYAS_DATA_ROOT`, the Ruflo paths), the `permissions.allow` rules that let `/tune`, `/handoff` and the Jev scripts run without a prompt, and, when you add Superpowers (`--with-superpowers`), the `permissions.deny` rules that keep its skills Dryas replaces out of the way. Without them the hooks run with your default Python, and the shared state in `~/.dryas` is not set up. Run `install/install.sh` for all of that.

`--uninstall` lists what it will remove and asks (`--yes` answers every question), removes Dryas from one config dir and keeps `~/.dryas`; adding `--purge` on the last account also deletes the logs, `/tune` thresholds and handoffs there, but keeps your notes in `~/.dryas/docs/dryas-local.md`. It also offers to remove the third-party plugins setup installed (`--keep-extras` leaves them).

After installing on a new machine, run the [release check](docs/release-check.md).

### Codex

```
install/install.sh --harness codex                            # ~/.codex (--harness both: Codex and Claude Code)
install/install.sh --harness codex --codex-dir ~/.codex-work  # once more for each other Codex home
```

Codex 0.162.1 or newer. Setup adds the plugin to that Codex home, then lists the Dryas hooks and asks before it trusts them (`--yes` answers yes); untrusted hooks do not run. Codex reaches Dryas memory through the MCP tools; the memory hooks run on Claude Code only. For the Jev judge, set `OPENROUTER_API_KEY` in the shell Codex runs in; without it the local judge decides. Codex runs a copy of the plugin, so re-run setup for each Codex home after `git pull`. `codex plugin marketplace add promprit/dryas-workflow` on its own is not enough: the hooks stay untrusted and setup does not run. Details: [docs/install.md](docs/install.md#codex-plugin-plus-setup).

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

## Local judge scorecard

The local judge decides with deterministic rules and no key. This scorecard is measured on the checked-in corpus (`reference/judge-corpus/`, original to this repo) by `python3 tools/judge_score.py`, and CI fails when it gets worse. The numbers are the rule set's, not a model's, and they are what a keyless install gets.

<!-- scorecard:start -->
| Measure | Value |
|---|---|
| Commands in corpus | 79 |
| Edits in corpus | 21 |
| Missed dangerous commands | 14 |
| Deny downgraded to ask | 4 |
| Needless asks on safe commands | 0 |
| Always-judged files not judged | 1 |
<!-- scorecard:end -->

## Reference stack

These are the reference implementation's bindings, not part of the method; each layer can be bound to something else. The Dryas core is always on; every other part is a choice.

| Part | What it does | Choose with |
| --- | --- | --- |
| [Claude Code](https://docs.claude.com/en/docs/claude-code) or [Codex](https://developers.openai.com/codex) | The host: agents, hooks, commands | required |
| Dryas core | The local judge, Dryas memory (`~/.dryas/dryas.db`) and the process skills (`dryas:brainstorm`, `dryas:worktree`, `dryas:tdd`, `dryas:verify` and more) | always installed |
| [Jev model (TypeSafe)](https://github.com/typesafe-ai/skills) | Upgrades the judge: decision support and gates through OpenRouter | `--judge jev` or `--openrouter-key` |
| [Ruflo](https://github.com/ruvnet/ruflo) | Optional memory and orchestration | `--with-ruflo` (`--memory ruflo`) |
| [Superpowers](https://github.com/obra/superpowers) | Optional alternative process skills | `--with-superpowers` |
| [Impeccable](https://github.com/pbakaus/impeccable) and [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | Design skills, installed by default | skip with `--no-design` |
| [pstack](https://github.com/michael-denyer/pstack-claude) picks | Interrogate review, cleanup, benchmark checklist, executor principles (vendored, adapted) | skip with `--no-pstack-picks` |

Optional, installed separately: [FlowObserve](https://github.com/promprit/flowobserve), an observe-only monitor for live Claude Code sessions. With Dryas it also shows escalations, one build lane per plan task, Jev spend against budget and per-stage timings. It never blocks or changes anything.

## Requirements

- A Claude subscription with Claude Code, or the Codex CLI (0.162.1 or newer).
- Optional: an OpenRouter API key for the Jev judge. It is bring-your-own-key: set `OPENROUTER_API_KEY` in your shell, or pass `--openrouter-key` to setup (stored in Claude Code's secure storage; Codex reads the key from the shell only). Without a key the local judge decides and the workflow runs the same.
- macOS, Linux, WSL or Windows.
- Python 3.9+ and git. Node and npm only with `--with-ruflo`. The hooks run `${DRYAS_PY:-python3}`; setup sets `DRYAS_PY` to the Python it ran with (in `settings.json` for Claude Code), and you can point it at another interpreter.

## Credits

- [Superpowers](https://github.com/obra/superpowers) by obra: the Dryas process skills are derived from it, and it remains an optional extra
- [Ruflo](https://github.com/ruvnet/ruflo) by ruvnet: an optional extra
- [Impeccable](https://github.com/pbakaus/impeccable) by pbakaus
- [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) by nextlevelbuilder
- [TypeSafe skills (Jev)](https://github.com/typesafe-ai/skills) by TypeSafe: the optional Jev judge
- [pstack](https://github.com/cursor/plugins/tree/main/pstack) by Lauren Tan, Claude Code port [pstack-claude](https://github.com/michael-denyer/pstack-claude) by Michael Denyer, and deslop from Cursor's cursor-team-kit (all MIT)

Third-party code is fetched from upstream by the installer, except the adapted pstack files in `claude/pstack/` and the process skills derived from Superpowers (see [NOTICE.md](NOTICE.md)).

## License

MIT. See [LICENSE](LICENSE).
