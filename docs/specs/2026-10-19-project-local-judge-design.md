# Project-local judge: design

Date: 2026-10-19. Status: design approved in chat 2026-10-19; written spec awaiting review. Branch: `spec/project-local-judge`.
Contested: yes (changes `providers.resolve`, the provider interface every judge caller uses, and adds a log field FlowObserve reads).

## 1. Goal

A project can force the local judge for every session at or below its folder, so no judge data from that project leaves the Mac. First user: `projects/VOID` (client data), which uses the local judge alone: no Jev, no Laya. Every other project keeps today's behaviour (Jev as the upgrade when a key is set).

Success:

- A session whose working directory is `VOID`, a child repo (`VOID/Pilot`, `VOID/void-data-platform`, `VOID/void-delivery-playbook`), a `.claude/worktrees/*` folder or a sibling worktree under `VOID/` makes **zero** OpenRouter calls: gate, route, MCP `jev_judge`, Jev shadow, `/handoff`, PreCompact compaction, and the OpenCode compact and handoff paths.
- A global `judge.provider: local` also stops `/handoff` and compaction from calling Jev (today they ignore it).
- **No new prompts**, no new allow rule, no change to any account's `settings.json`.
- **Not slower than 2.3.2** beyond run-to-run noise (`tools/compare_release.py`, section 7).
- Without a marker, behaviour and log lines are byte-for-byte what they are today.

Background: a spike on 2026-10-19 rejected stock Laya 0.4.12 as a Jev replacement (missed 50 of 50 dangerous commands on `reference/judge-corpus`; Jev missed 4). Jev's data path (OpenRouter, then TypeSafe) is not covered by an agreement the way Claude Team is, so client data must not reach it.

Out of scope: Laya or any other provider; a path list in `thresholds.json` (declined); other projects; per-session switching; FlowObserve changes (notified, section 6).

## 2. Decisions

| # | Decision |
| --- | --- |
| D1 | Opt-in by a committed marker file `.dryas-judge` at the project root. Found by walking up from the session's directory. |
| D2 | Any marker means local: content `local`, any other content, an empty file or an unreadable file. A broken marker never sends data out. |
| D3 | Policy in `providers.resolve` (approach A) plus a last-line guard in `jev_client.judge` (approach B). A decides and logs; B makes a forgotten `cwd` unable to leak. |
| D4 | A marked project overrides `judge.provider` and `judge.shadow` from `thresholds.json`, including `jev`, and any key in the environment. |
| D5 | Handoff and compaction respect the provider, both the marker and a global `judge.provider: local`, through one check in `handoff.build_handoff`. |
| D6 | One new log field, `"judge_policy": "project_local"`, only when the marker decided. `provider` stays `"local"`; `fallback` is not written for a policy decision. |
| D7 | Change `claude/jev`; sync to `codex/` and `opencode/` with the existing sync tools. |

## 3. Marker and lookup (`claude/jev/judge_policy.py`, new)

- `project_local(cwd: Optional[str]) -> bool`.
- Start directory: `cwd` when it is a non-empty string, else `os.getcwd()`; if that raises, return `False` (the B guard still runs with its own directory, section 4).
- Resolve with `os.path.realpath`, then `os.lstat("<dir>/.dryas-judge")` in that folder and every parent up to the filesystem root. Success is a hit. `FileNotFoundError` and `NotADirectoryError` mean no marker there; any other `OSError` (for example a parent folder without search permission) counts as a hit. Do not use `os.path.lexists`: it swallows `OSError` and would fail open. The first hit returns `True`. Content is never needed to decide (D2); the file is not read.
- Cache: a module-level dict from the resolved start directory to the result, for the life of the process. Hooks are short-lived processes; the MCP server is long-lived, so a marker added while it runs takes effect at the next session. That is acceptable: the marker is committed once, before client access (section 8).
- Python 3.9 stdlib only; no exceptions escape (any `OSError` during the walk counts as a hit, so an unreadable folder fails closed).
- Coverage: the VOID root, child repos and their subfolders, `VOID/**/.claude/worktrees/*` and sibling worktrees `VOID/<repo>-<slug>` are all below the marker. A worktree created outside `projects/VOID/` is not covered and is out of scope.

## 4. Callers

`providers.resolve(th, injected, cwd=None)` returns `(provider, shadow)` as today. When `judge_policy.project_local(cwd)` is true it returns `("local", "none")` before reading `th`, and `providers.policy(cwd)` returns `"project_local"` (else `None`) for callers that log. `providers.ask(..., cwd=None)` passes `cwd` through and, when the policy applied, adds `judge_policy` to its result dict.

| Caller | Change |
| --- | --- |
| `gate.py` (line 327 `providers.ask`) | Pass the event's `cwd`. Log `judge_policy` from the result. |
| `route.py` (`run`) | Pass the event's `cwd` to `resolve`; the existing local branch logs `{"provider": "local", "injected": false}` plus `judge_policy`. |
| `jev_mcp.py` (`jev_judge`) | The tool's `inputSchema` has only `state` and `questions`, and the orchestrator sends no `cwd`, so in practice the decision uses `state["cwd"]` when the state carries one, else the MCP server's process directory (its session's launch folder). Do not add a `cwd` argument to the schema. The existing `_local` branch answers; its `mcp.jsonl` line gets `judge_policy`. The server is long-lived and the lookup is cached, so the session must start in a folder under the marker (section 9). |
| `handoff.build_handoff` | Before `score()`: if `providers.resolve(thresholds.load(), judge_fn is not judge, cwd)[0] == "local"`, skip scoring and use the existing fallback (`kept = scored[-FALLBACK_NEWEST:]`). The note is `NOTE_LOCAL = "local judge (project policy) — kept newest 30"` when the policy applied, `"local judge — kept newest 30"` for a global `local`. `jev_ok` is `"local"`. Stats carry `judge_policy` when it applied; `handoff.run` and `compact_keep.run` log it. This covers `/handoff`, PreCompact and both `opencode_session` paths. |
| `jev_client.judge` (guard) | First statement: `cwd = state.get("cwd") if isinstance(state, dict) else None`; if `judge_policy.project_local(cwd)` raise `JevUnavailable("project_local")`. Nothing is built or sent. |

Test injection: callers that pass an explicit `judge_fn` keep today's meaning of `injected` for `resolve`, but the marker check runs first, so a test with a marker and a fake Jev must see zero calls to the fake. In `build_handoff`, `injected` is `judge_fn is not judge`; this is valid because `handoff.py` imports `judge` from `jev_client`, and `compact_keep.run` and `opencode_session` default to that same function.

Logging: `gate` builds its log line through `_provider_fields`; add `judge_policy` there (and in the other callers' existing log builders), so `tools/inventory.py --check`, which traces log fields, stays at 0 problems.

## 5. Behaviour in a marked project

- Gate: the local judge's decision stands, exactly as with no key. Danger-list denies and asks unchanged.
- Route: no route hint is injected (today's local behaviour).
- `jev_judge` (per-task triage, commit check, interrogate trigger): local answers; the orchestrator decides below threshold, as today without a key.
- `/handoff` and compaction: always-keep lines plus the newest 30 items, user-visible note says "local judge (project policy)". Cost 0.

## 6. Logs and FlowObserve

- New optional field `"judge_policy": "project_local"` on lines in `gate.jsonl`, `route.jsonl`, `handoff.jsonl`, `compact.jsonl` and `mcp.jsonl`, written only when the marker decided. No new log file. `provider` stays `"local"`.
- `handoff.jsonl` and `compact.jsonl` gain one new value: `jev_ok: "local"` (today `true`, `false` or `"partial"`) whenever the provider was local, by marker or global setting.
- `fallback` is not written for a policy decision. Fallbacks keep exactly `"fallback": "local"`.
- If the B guard fires, the caller logs its normal Jev-failure line (`fallback: "local"`, `error: "JevUnavailable"`) plus `judge_policy`. That combination means a caller bypassed policy A: a bug.
- FlowObserve (`server/src/dryasrec.ts`) was told the contract on 2026-10-19 (session `flowobserve-97`); after merge, send the commit hash. Workspace rule: log format changes stay in step with its reducer; this change is additive and needs no reducer change to keep working.

## 7. Tests and speed

Tests first, in `claude/jev/tests/`:

1. `test_judge_policy.py`: marker found from root, child repo, `.claude/worktrees/x/src`, sibling worktree folder; not found outside; empty, junk and unreadable (mode 000) marker count as local; a parent folder without search permission (mode 000) counts as local; missing `cwd` uses the process directory; cache returns the same answer without new `stat` calls.
2. `test_providers.py` (extend): with a marker, `resolve` returns `("local", "none")` for `provider` `jev`/`auto`, `shadow` `jev`, a key set, and `injected=True`.
3. One test per caller with a fake Jev that fails if called, all under a marked temp folder: gate, route, `jev_mcp` `jev_judge`, `handoff.run`, `compact_keep.run`, `opencode_session.compact` and `save_handoff`. Each asserts zero calls and `judge_policy` in the log line.
4. Global hole: `judge.provider: local`, key set, no marker: `build_handoff` never calls the judge; note is "local judge — kept newest 30".
5. Guard: `jev_client.judge` with `state["cwd"]` under a marker, and with the process directory under a marker, raises `JevUnavailable("project_local")` and the opener is never called.
6. No marker: the existing suite passes unchanged; `tools/inventory.py --check` 0 problems; `tools/sync_codex_plugin.py --check` and `tools/sync_opencode.py --check` exit 0 after sync. `tools/release_check.py` and `tools/release_check_opencode.py` check a real install and run in section 8, step 5.

Speed (release rule; read `pstack/benchmark-checklist.md` before reporting a number):

- `tools/compare_release.py --old <2.3.2>` PASS: 0 asks, 0 blocks, median per-event time within run-to-run noise. Run it twice: as is, and with the sandbox's working directory under a marked fixture.
- A micro-benchmark of `project_local` at depth `VOID/Pilot/.claude/worktrees/x/src`: target under 1 ms cold, under 10 µs cached, on this Mac.

## 8. Proof run (after merge, with Promprit)

1. Commit `.dryas-judge` (content `local`) at the VOID repo root, through the VOID session or Promprit. Update `VOID/CLAUDE.md`: Judge bullet says VOID uses the local judge alone; drop "(or Laya once it ships in Dryas)"; the `/handoff` restriction can go.
2. Start a session in `VOID/Pilot`; one prompt, one Bash command, one `/handoff`.
3. Check: `route.jsonl` and `gate.jsonl` lines for that session show `provider: local` and `judge_policy: project_local`; no `provider: jev` line for that session; `handoff.jsonl` shows `judge_policy` and no cost.
4. Repeat steps 2–3 in one VOID worktree.
5. Release per the usual process (version bump, both accounts upgraded with `claude plugin update`), then `tools/release_check.py` and `tools/release_check_opencode.py` pass on the install.

## 9. Risks

- A new judge caller added later that skips `resolve`: caught by the B guard as long as its state carries `cwd` or its process runs under the project.
- MCP `jev_judge` decides by the MCP server's launch folder when the state has no `cwd`: a session started outside VOID that later works in VOID gets Jev triage there. Same acceptance as the next point.
- A session started outside VOID that edits VOID files by absolute path: its `cwd` is not under the marker, so Jev judges those calls. Accepted: VOID work starts in VOID folders (workspace rule: one session per project folder).
- Marker deleted by a commit: visible in VOID's history; the proof check in section 8 is the guard against silent removal.
