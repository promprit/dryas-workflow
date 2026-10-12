# Contributing

## Portability (macOS, Linux, WSL, Windows)

- All scripts are Python 3.9+ standard library. Node is used only for the Ruflo MCP shim. There are no shell scripts except the two thin installer wrappers and the plugin's `claude/bin/dryas-py` launcher.
- Plugin hook commands (`claude/hooks/hooks.json`) use the form `"${DRYAS_PY:-python3}" -X utf8 "${CLAUDE_PLUGIN_ROOT}/..."`. Never hardcode an interpreter, a plugin path or `$HOME`.
- Plugin Markdown (agents, commands, skills) names files as `${CLAUDE_PLUGIN_ROOT}/...` and runs Python through `"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py"`.
- The `{{CD}}` / `$CD` and `$PY` placeholders stay only for the settings fragment (`claude/settings.fragment.json`), the stage commands in `claude/jev/chain.json` (resolved by `chain.py` at run time) and the Codex edition.
- State paths (logs, thresholds, handoffs, `chain.local.json`, accounts) go only through `claude/jev/paths.py`, which honors `DRYAS_DATA_ROOT` (default `~/.dryas`) and the `JEV_*` overrides.
- Paths go through `install/platform_util.py` (`fwd`, `make_dir_link`, `remove_path`, `resolve_argv`).
- Read and write text files with `encoding="utf-8"`.
- `codex/jev` and `codex/pstack` are generated: edit `claude/`, run `python tools/sync_codex_plugin.py`, commit both. The command lines in `codex/hooks/hooks.json` are frozen (Codex trusts each hook by a hash of its entry); change one only with a version bump and a release note that setup will ask to re-trust.
- `install/tests/test_portability.py` enforces the banned patterns. Mark a deliberate exception with `portable-ok: <reason>` on the same line.
- CI must be green on macOS, Ubuntu and Windows before merging to main. Branch protection enforces this.

## Plugin version

- The plugin runs in place from the clone, so a `git pull` is enough for directory installs. Still bump `version` in `claude/.claude-plugin/plugin.json` (and the plugin entry in `.claude-plugin/marketplace.json`) when shipped plugin content changes between releases: cache entries and non-directory installs only update on a new version.
- Codex runs a copy of `codex/` from `$CODEX_HOME/plugins/cache/dryas-workflow/dryas/<version>/`; users get changes by re-running setup (`codex plugin add` refreshes the copy). Bump `version` in `codex/.codex-plugin/plugin.json` when shipped Codex plugin content changes between releases.

## Running the tests

```
python -m pytest -q claude/jev/tests install/tests claude/ruflo/tests
node claude/ruflo/tests/test_ns.cjs
python tools/sync_codex_plugin.py --check
```
