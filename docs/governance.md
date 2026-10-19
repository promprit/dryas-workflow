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

- **local** (no network, no key): deterministic rules in `claude/jev/local_judge.py`. It denies a short list of catastrophic commands (recursive deletes of `/`, `~` or a home root, fork bombs, disk formatting, raw device writes, `chmod -R 777 /`), asks before history- or data-destroying ones (`git reset --hard`, `git clean -f`, `git push --force`, `git branch -D`, SQL drops, piping a download into a shell) and before discarding uncommitted work or stashes (`git checkout -f`/`--force`, `git checkout -- <path>`, `git checkout <tree-ish> <path>`, `git checkout .` and other directory pathspecs, `git switch -f`/`--force`/`--discard-changes`, `git restore <path>` without `--staged`, `git stash clear` and `git stash drop`), and leaves everything else to the harness's own permissions. It gives no route hint, and `jev_judge` returns every question in `escalate`, so the orchestrator decides.
- **jev**: the Jev model through OpenRouter, as before.

Without a key the safety checks are the **deterministic rules** of the local judge, and the planning questions the judge used to answer go to the user's own `strong` tier on their subscription. Jev is the upgrade for unclear cases, not a requirement. The local judge only knows the shapes its rules name, so it can miss a dangerous command a model would catch.

`judge.provider` chooses who decides; `judge.shadow` names a second provider whose answer is only logged (`shadow_*` fields in `gate.jsonl`). Both default to `auto`: Jev decides when a key is set, with the local judge as its shadow; without a key the local judge decides. When Jev is unreachable the local judge decides that call (`fallback` in the log). `/tune` reports providers, fallbacks, shadow agreement and judged gate calls per task; change a setting with `/tune apply judge.provider '"local"'`.

A project can opt out of every remote judge: commit an empty file named `.dryas-judge` (content `local`) at its root. Every session whose folder is at or below it, child repos and worktrees included, uses the local judge alone, whatever `judge.provider`, `judge.shadow` or a key say: the gate, prompt routing, `jev_judge`, `/handoff` and compaction send nothing to OpenRouter. Any marker means local, even an unreadable one. Log lines decided this way carry `"judge_policy": "project_local"`. `/handoff` and compaction also honour a global `judge.provider: local` and log `jev_ok: "local"`.

The local judge is scored, not assumed. `reference/judge-corpus/` holds labelled commands and edits, `tools/judge_score.py` scores the rules against them, a test that CI runs fails when a measure rises above `baseline.json`, and the current numbers (including the dangerous cases it still misses) are in `reference/judge-corpus/SCORECARD.md`.

The loop that improves it runs in `/tune`. Where the local judge decided and Jev, as shadow, disagreed, the call is listed as a candidate to add to the corpus (`CORPUS_CANDIDATES_JSON`). Allowlist proposals come from asks you approved: a command prefix is proposed only if the local judge's danger and destructive checks accept it, so a dangerous prefix is never proposed. `/tune apply gate.allowlist` applies one and refuses a dangerous entry even if typed by hand; on load, a refused entry is dropped alone and the rest of your allowlist stays. Nothing is applied without `/tune apply`.

Setting `judge.shadow` to `jev` while the local judge decides makes a Jev call on every judged gate call (latency up to Jev's 3 s deadline, and its spend), so leave it at `auto` unless you are collecting comparison data. The local judge does not judge interpreter code (`python -c`, heredoc bodies fed to non-shell programs) and does not cover deletes of system folders such as `/usr` or `/etc`.

## Task-level judgement

At dispatch the orchestrator runs `jev/task_review.py answer` for each task. The answer is local and deterministic: a **review set** (scope entries that name one file and are not always judged may skip per-edit judgement; wildcard entries stay reviewed), a **score** from 0 to 100 (size: files and lines in scope; risk: path classes; tests: whether a Done line runs a test; history: the escalation rate of this task type, counted only once `history.min_tasks` scored tasks of the type exist) and the start tier the score would pick. The orchestrator writes the review set into `.orchestrate/active.json` (`review_version` 1); executors cannot, because the scope lock denies them `.orchestrate/` for file tools and for shell writes. The score goes into the dispatch record, logged right after dispatch; the executor's tokens, duration and agent id follow in a second record with `phase: "return"` when it returns, so the dispatch metrics do not change. Codex workers carry no worker identity, so the scope lock cannot tell them from the main session and `review.task_skip` is never enforced for them. Content signals are best-effort: a miss is possible, so they back the review set up and do not replace it.

Both run in shadow first. The gate logs the task verdict (`task_review`, `task_review_why`) on every file edit in an orchestrated task, including edits that `local_file` skips, and logs `false_skip` when the deciding or shadow answer said deny or ask on a file the task verdict would have skipped. Two switches in thresholds, both off by default, act on the evidence:

- `review.task_skip`: the gate skips per-edit judgement on a file the task verdict skips. The false-skip rate is false skips divided by would-skip edits that Jev judged (as decider or in shadow); skipped edits (enforced skips and `local_file` skips) had no judge and are never evidence. With fewer than `review.min_tasks` (50) tasks that have such an edit there is "no evidence" and no proposal. `/tune` proposes ON when the rate is at most `review.max_false_skip_rate` (0.01). Before any skip is enforced it proposes OFF when the rate rises above that maximum. Once enforcement starts the evidence freezes, and any later false skip in a judged edit proposes OFF.
- `dispatch.scored_tier`: the orchestrator starts a task on the score's tier instead of the tier questions. In shadow, a scored task whose score tier differs from its start tier helps if the score starts lower on a task that did not escalate or higher on one that did, and hurts otherwise. `/tune` proposes ON when, over at least `dispatch.min_tasks` (50) scored tasks, helps are at least 2 x hurts and at least one. It proposes OFF when, with `dispatch.min_tasks` tasks in each group, tasks started from the score escalate more often than tasks started from the tier questions.

Whatever any provider or task verdict says, these stay judged per edit: paths with a dot component (`.git`, `.github`, `.env`, `.claude`, `.orchestrate`), CI files, key and certificate files, secret-looking names, build files and scripts (the gate's `SENSITIVE_*` lists: `package.json`, `Makefile`, `Dockerfile`, `requirements*.txt`, `*.sh` and the like) and anything outside the worktree. Plain files inside the session's working folder are not judged at all (as before), so a task verdict can only skip plain files that sit in the worktree but outside that folder. An edit whose new text carries a content signal (processes, `eval`/`exec`, deletes, environment reads, network calls, install hooks) is judged even inside a trusted scope. A missing, unreadable, malformed or older `active.json` review set means every edit is judged.

`/tune` reports per task the executor tokens and time, lines changed (overall and by start tier), Jev calls, judge spend and gate wait (medians, and per start tier medians and p90), tokens of failed attempts, deny and ask rate per edit, escalation rate, review findings, score buckets against escalations and false skips. Its Done-when lines compare a baseline window with the current one (`baseline.until`, a date; empty splits the logged tasks in halves) and print PASS or FAIL: Jev calls per task at most half, gate wait per task lower, executor tokens per task no higher, escalation rate no higher, review findings per reviewed branch no higher (critical + important findings, every review round summed; n/a below 3 reviewed branches in a window), and no enforced false skip on an always-judged file (an enforced skip outside the worktree counts as one).

## Reference binding

Jev (TypeSafe, via OpenRouter) is the judge and gate. The scope lock is `claude/jev/scope_lock.py`, armed by `.orchestrate/active.json`. Hook order comes from `claude/jev/chain.json` (local choices in `~/.dryas/chain.local.json`). Thresholds live in `~/.dryas/jev/thresholds.json`; `/tune` proposes changes. Details: [workflow.md §1, §5–6](workflow.md).
