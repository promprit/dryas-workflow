# Contributing

## Portability (macOS, Linux, WSL, Windows)

- All scripts are Python 3.9+ standard library. The core needs no Node, npm or compiled component. Node is needed only to test the optional Ruflo component (`claude/ruflo/tests`). There are no shell scripts except the two thin installer wrappers and the plugin's `claude/bin/dryas-py` launcher.
- Plugin hook commands (`claude/hooks/hooks.json`) use the form `"${DRYAS_PY:-python3}" -X utf8 "${CLAUDE_PLUGIN_ROOT}/..."`. Never hardcode an interpreter, a plugin path or `$HOME`.
- Plugin Markdown (agents, commands, skills) names files as `${CLAUDE_PLUGIN_ROOT}/...` and runs Python through `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py"`.
- The `{{CD}}` / `$CD` and `$PY` placeholders stay only for the settings fragment (`claude/settings.fragment.json`), the stage commands in `claude/jev/chain.json` (resolved by `chain.py` at run time) and the Codex edition.
- State paths (logs, thresholds, handoffs, `chain.local.json`, accounts) go only through `claude/jev/paths.py`, which honors `DRYAS_DATA_ROOT` (default `~/.dryas`) and the `JEV_*` overrides.
- Paths go through `install/platform_util.py` (`fwd`, `make_dir_link`, `remove_path`, `resolve_argv`).
- Read and write text files with `encoding="utf-8"`.
- `codex/jev` and `codex/pstack` are generated: edit `claude/`, run `python tools/sync_codex_plugin.py`, commit both. The command lines in `codex/hooks/hooks.json` are frozen (Codex trusts each hook by a hash of its entry); change one only with a version bump and a release note that setup will ask to re-trust.
- `install/tests/test_portability.py` enforces the banned patterns. Mark a deliberate exception with `portable-ok: <reason>` on the same line.
- CI must be green on macOS, Ubuntu and Windows before merging to main. Branch protection enforces this.
- Nothing is removed without a replacement: if `python tools/inventory.py --check` reports `lost:`, add the equivalent or map the entry in `reference/inventory-map.json` (see [reference/README.md](reference/README.md#no-loss-inventory)). Never rebuild `reference/inventory-1.x.json` to make the check pass.

## Plugin version

- The plugin runs in place from the clone, so a `git pull` is enough for directory installs. Still bump `version` in `claude/.claude-plugin/plugin.json` (and the plugin entry in `.claude-plugin/marketplace.json`) when shipped plugin content changes between releases: cache entries and non-directory installs only update on a new version.
- Codex runs a copy of `codex/` from `$CODEX_HOME/plugins/cache/dryas-workflow/dryas/<version>/`; users get changes by re-running setup (`codex plugin add` refreshes the copy). Bump `version` in `codex/.codex-plugin/plugin.json` when shipped Codex plugin content changes between releases.

## Running the tests

```
python -m pytest -q claude/jev/tests install/tests claude/ruflo/tests
node claude/ruflo/tests/test_ns.cjs
python tools/sync_codex_plugin.py --check
```

## Writing skills

- Start a skill's description, and every pointer to another file, with its trigger: the words that decide when the agent reaches for it (`Use when …`, `Before …`, `On …`).
- Always-loaded text spends context on every turn, and every choice put to the user spends their attention. Keep `SKILL.md` to the process (aim for 50–150 lines) and move reference material into companion files in the same folder, each behind a pointer that says when to read it.
- End every step on something checkable: a command and the result it should give, a count, a named artifact. A vague end point invites stopping early.
- Write what to do. Reserve "never" for hard guardrails, and pair each one with what to do instead.
- Give each meaning one home: state a rule once (template, skill or companion) and point to it from elsewhere; delete lines that change nothing.
- A rewrite of an upstream skill keeps every one of its rules; the coverage table in `<skill>/UPSTREAM.md` maps each rule to where it now lives.
- User-invoked skills and commands (`/orchestrate`, `/wplan`, `/wreview`, `/commit`, `/tune`, `/handoff`, `/interrogate`) orchestrate; model-invoked skills (the eight process skills) hold reusable discipline. A user-invoked skill may call model-invoked skills, never another user-invoked one.
