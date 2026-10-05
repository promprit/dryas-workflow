# Dryas Workflow

![ci](https://github.com/promprit/dryas-workflow/actions/workflows/ci.yml/badge.svg)

A Claude Code workflow: brainstorm first, plan, gate risky steps with a cheap judge, build with Sonnet executors under a file-scope lock, escalate only when needed, review, ship.

This repo is public but not promoted. Expect rough edges.

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

## How it works

- **Escalation ladder.** Sonnet, then Opus, then Fable. Each step is logged with a reason.
- **Scope lock.** An executor can only edit the files its task names. A hook blocks other edits.
- **Jev gating.** Jev is a small model that answers narrow, typed questions. It never writes code or plans. If it is unsure, the main model decides.
- **Design rule.** UI work goes through Impeccable and UI UX Pro Max.

## Install

```
git clone https://github.com/promprit/dryas-workflow
cd dryas-workflow
./install/install.sh      # macOS, Linux, WSL
.\install\install.ps1     # Windows (PowerShell)
```

Works on macOS, Linux, WSL and Windows, with Claude Code and Codex (`--harness codex|both`).

Details, flags and troubleshooting: [docs/install.md](docs/install.md). Other agent harnesses: [docs/harnesses.md](docs/harnesses.md).

## Recommended stack

All parts are on by default. Each can be skipped with a flag.

| Part | What it does | Skip with |
| --- | --- | --- |
| [Claude Code](https://docs.claude.com/en/docs/claude-code) | The host: agents, hooks, commands | required |
| [Jev (TypeSafe)](https://github.com/typesafe-ai/skills) | Decision support and gates | `--no-jev` |
| [Ruflo](https://github.com/ruvnet/ruflo) | Orchestration and memory | `--no-ruflo` |
| [Superpowers](https://github.com/obra/superpowers) | Process skills (brainstorming, worktrees, review) | `--no-superpowers` |
| [Impeccable](https://github.com/pbakaus/impeccable) and [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | Design skills | `--no-design` |

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

Third-party code is not vendored here. The installer fetches it from upstream.

## License

MIT. See [LICENSE](LICENSE).
