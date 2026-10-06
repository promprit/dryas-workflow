# Dryas

![ci](https://github.com/promprit/dryas-workflow/actions/workflows/ci.yml/badge.svg)

**Dryas is an opinionated operating model for delivering software with AI agents.** It says who decides, who builds, what each agent may touch, what is remembered, when to pay for a stronger model, and what must be true before work merges.

The method is the asset; the tools are replaceable. This repo holds both:

- **The framework:** why it exists, five layers, one loop, and a draft specification any harness can implement.
- **A reference implementation** for Claude Code and Codex, built on Superpowers, Ruflo, Jev and a few design skills.

This repo is public but not promoted. Expect rough edges. See [CONTRIBUTING.md](CONTRIBUTING.md) for the portability rules and how to run the tests.

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
| [Why Dryas](docs/why-dryas.md) | The problems it solves, and what it is not |
| [Architecture](docs/architecture.md) | The five layers, the loop, design principles |
| [Memory](docs/memory-model.md) · [Governance](docs/governance.md) · [Execution](docs/execution-model.md) · [Escalation](docs/escalation-model.md) · [Review](docs/review-model.md) | One model doc per layer |
| [Specification v1 (draft)](spec/dryas-spec-v1.md) | Numbered MUST / SHOULD rules and the `dryas.yaml` manifest |
| [Reference map](reference/README.md) | How this repo implements each rule, with a conformance table |
| [Examples](examples/README.md) | A feature walked through the loop, a plan file, manifests |
| [Adoption guide](docs/adoption-guide.md) | Use it, fork it, or write an edition for another harness |
| [Roadmap](docs/roadmap.md) | Framework, then spec and manifest, then editions |

## The loop

```
Brainstorm → Plan → Judge → Build → Escalate → Review → Ship
```

- **Brainstorm**: settle the design with you before any code is written.
- **Plan**: split the approved design into small tasks, each with a file scope and a done check.
- **Judge**: a small model answers narrow questions (is this step risky? which model?) so the big model is called less.
- **Build**: Sonnet executors do each task inside a git worktree.
- **Escalate**: if Sonnet cannot finish a task, Opus tries it. Fable is used only if Opus also fails.
- **Review**: the diff is reviewed and the tests are run before anything merges.
- **Ship**: merge and commit, after verification.

## How the reference implementation works

- **Escalation ladder.** Sonnet, then Opus, then Fable. Each step is logged with a reason.
- **Scope lock.** An executor can only edit the files its task names. A hook blocks other edits.
- **Parallel loops.** One project can run many loops at once. The rule is one agent per git worktree: each loop has its own worktree and branch, so loops never collide, and each merges only after its own review.
- **Jev gating.** Jev is a small model that answers narrow, typed questions. It never writes code or plans. If it is unsure, the main model decides.
- **Design rule.** UI work goes through Impeccable and UI UX Pro Max.
- **One source for the rules.** The always-loaded rules in `~/.claude/CLAUDE.md` come from `claude/CLAUDE.md.template`, and the full reference from `docs/workflow.md`. Change them here and re-run the installer; every machine's copy then matches the repo.

## Install

```
git clone https://github.com/promprit/dryas-workflow
cd dryas-workflow
./install/install.sh      # macOS, Linux, WSL
.\install\install.ps1     # Windows (PowerShell)
```

Works on macOS, Linux, WSL and Windows, with Claude Code and Codex (`--harness codex|both`).

Details, flags and troubleshooting: [docs/install.md](docs/install.md). Other agent harnesses: [docs/harnesses.md](docs/harnesses.md).

## Use it for yourself

Fork this repo and make the workflow yours:

1. Fork it and clone your fork.
2. Edit `claude/CLAUDE.md.template` (the rules every session loads) and `docs/workflow.md` (the full reference). If your method differs, change the layer docs and `reference/dryas.yaml` too ([adoption guide](docs/adoption-guide.md)).
3. Run `./install/install.sh` (or `.\install\install.ps1` on Windows). Every re-install brings your `~/.claude` back in step with your fork.

Keep notes that only fit your machine in `~/.claude/docs/dryas-local.md`. The installer never touches that file.

## Reference stack

These are the reference implementation's bindings, not part of the method; each layer can be bound to something else. All parts are on by default. Each can be skipped with a flag.

| Part | What it does | Skip with |
| --- | --- | --- |
| [Claude Code](https://docs.claude.com/en/docs/claude-code) | The host: agents, hooks, commands | required |
| [Jev (TypeSafe)](https://github.com/typesafe-ai/skills) | Decision support and gates | `--no-jev` |
| [Ruflo](https://github.com/ruvnet/ruflo) | Orchestration and memory | `--no-ruflo` |
| [Superpowers](https://github.com/obra/superpowers) | Process skills (brainstorming, worktrees, review) | `--no-superpowers` |
| [Impeccable](https://github.com/pbakaus/impeccable) and [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | Design skills | `--no-design` |
| [pstack](https://github.com/michael-denyer/pstack-claude) picks | Interrogate review, cleanup, benchmark checklist, executor principles (vendored, adapted) | `--no-pstack-picks` |

## Requirements

- A Claude subscription with Claude Code, or the Codex CLI.
- An OpenRouter API key for Jev. Without it Jev makes no decisions and everything else still works.
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
