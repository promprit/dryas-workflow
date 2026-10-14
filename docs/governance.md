# Governance

**Purpose:** keep every decision with the right party. Humans decide design and anything outward-facing. A cheap judge answers narrow questions. A lock decides what files an agent may touch.

## Who decides what

| Decision | Decided by | Never by |
| --- | --- | --- |
| What to build (design, approach) | Human, after a brainstorm | An agent on its own |
| How to split it into tasks | Orchestrator | Executors or the judge |
| Narrow typed questions (is this risky? which executor? done?) | Judge, if confident | The judge below its threshold: then the orchestrator |
| Which files a task may edit | The plan's `Scope:`, enforced by a lock | The executor |
| Install, move, delete, overwrite, settings change | Human, after a dry-run or diff | Any agent |
| Push, publish, release | Human | Any agent |

## Rules

1. **Brainstorm first.** No task is planned or dispatched before a human approves the design. Architectural work also gets a written spec.
2. **Scope lock.** Every task names its file scope as globs. While tasks are active, edits outside the union of their scopes are denied by the harness, not just discouraged. An executor that needs another file stops and asks.
3. **One agent per worktree.** A worktree belongs to one orchestrator session. Parallel work uses parallel worktrees.
4. **The judge answers, never acts.** The judge is a small, cheap model that answers typed questions with a confidence. It never writes code or plans. Below threshold, or when it flags escalation, the orchestrator decides.
5. **Gates never auto-allow.** A safety gate on tool calls can deny or ask; it cannot allow. On any failure (timeout, no key, offline) it makes no decision and normal permissions apply. Allowlisted commands skip the judge; a compound command skips it only when every part is allowlisted and the parts are joined by `&&`, `||`, `;` or `|` (plus `2>&1`, `>/dev/null`, `2>/dev/null`). Parts may use only plain characters (letters, digits, space, tab, quotes and . _ / = : @ % + , -); a cd in a compound must stay inside the working directory. Setting `gate.compound` to false turns compound skipping off.
6. **Overrides are logged.** Whenever the orchestrator acts against a judge answer, it logs the question, the answer, its own decision and why.
7. **Calibration is proposed, not applied.** A periodic tune reads overrides and escalations and proposes threshold changes. A human approves each one.
8. **Secrets stay in the environment.** Credentials live in the shell environment only, never in files, configs, logs or tests. Only the minimum (redacted command, file path and size, never file contents) leaves the machine for judging.
9. **Hook order is fixed.** Per event: scope lock, then judge gate, then memory hooks, then observers (observe-only, last). A deny beats an ask; a crashing stage never blocks.

## Asking good judge questions

- One narrow judgment per question.
- Named fields in the state, not prose.
- Every multiple choice includes `none_of_these`.
- Independent questions are batched into one call.

## Judge providers

The gate, the route hint and the `jev_judge` tool ask a judge. Two providers answer the same questions:

- **local** (no network, no key): deterministic rules in `claude/jev/local_judge.py`. It denies a short list of catastrophic commands (recursive deletes of `/`, `~` or a home root, fork bombs, disk formatting, raw device writes, `chmod -R 777 /`), asks before history- or data-destroying ones (`git reset --hard`, `git clean -f`, `git push --force`, `git branch -D`, SQL drops, piping a download into a shell), and leaves everything else to the harness's own permissions. It gives no route hint, and `jev_judge` returns every question in `escalate`, so the orchestrator decides.
- **jev**: the Jev model through OpenRouter, as before.

`judge.provider` chooses who decides; `judge.shadow` names a second provider whose answer is only logged (`shadow_*` fields in `gate.jsonl`). Both default to `auto`: Jev decides when a key is set, with the local judge as its shadow; without a key the local judge decides. When Jev is unreachable the local judge decides that call (`fallback` in the log). `/tune` reports providers, fallbacks, shadow agreement and judged gate calls per task; change a setting with `/tune apply judge.provider '"local"'`.

Setting `judge.shadow` to `jev` while the local judge decides makes a Jev call on every judged gate call (latency up to Jev's 3 s deadline, and its spend), so leave it at `auto` unless you are collecting comparison data. The local judge does not judge interpreter code (`python -c`, heredoc bodies fed to non-shell programs) and does not cover deletes of system folders such as `/usr` or `/etc`.

## Reference binding

Jev (TypeSafe, via OpenRouter) is the judge and gate. The scope lock is `claude/jev/scope_lock.py`, armed by `.orchestrate/active.json`. Hook order comes from `claude/jev/chain.json` (local choices in `~/.dryas/chain.local.json`). Thresholds live in `~/.dryas/jev/thresholds.json`; `/tune` proposes changes. Details: [workflow.md §1, §5–6](workflow.md).
