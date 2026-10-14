# Notice

This repository is MIT-licensed (see [LICENSE](LICENSE)). Third-party tools are fetched from upstream by the installer, with two exceptions.

## Vendored material

`claude/pstack/` holds adapted files from [pstack-claude](https://github.com/michael-denyer/pstack-claude) at commit `dc8e617` (MIT, (c) 2026 Lauren Tan and (c) 2026 Michael Denyer), a port of [cursor/plugins/pstack](https://github.com/cursor/plugins/tree/main/pstack), plus `deslop` from Cursor's cursor-team-kit (MIT, (c) 2026 Cursor). License texts, provenance and every edit: [claude/pstack/NOTICE.md](claude/pstack/NOTICE.md) and [claude/pstack/UPSTREAM.md](claude/pstack/UPSTREAM.md).

`claude/skills/{brainstorm,worktree,debug,verify,plan,review-request,review-receive,tdd}` are rewritten from [Superpowers](https://github.com/obra/superpowers) 6.4.1 at commit `5bf4e78` (MIT, (c) 2025 Jesse Vincent). License text, provenance and the coverage tables of every upstream rule: [claude/skills/LICENSE-superpowers](claude/skills/LICENSE-superpowers) and [claude/skills/UPSTREAM.md](claude/skills/UPSTREAM.md), which indexes one `UPSTREAM.md` per skill folder.

## Generated copies

`codex/jev` and `codex/pstack` are generated copies of `claude/jev` and `claude/pstack` (made by `tools/sync_codex_plugin.py`) for the Codex plugin; `codex/pstack` carries the same license texts, notice and provenance. The eight process skills in `codex/skills/`, with `codex/skills/UPSTREAM.md` and `LICENSE-superpowers`, are rendered from `claude/skills/` by the same tool. `claude/LICENSE` and `codex/LICENSE` are copies of [LICENSE](LICENSE), since Claude Code and Codex copy only the plugin folder.

## Ideas

The skill-writing rules in CONTRIBUTING.md, the brainstorm question rounds, the debug feedback loop and the parallel three-stage review draw on ideas from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT). No text is copied.

The minimum-code ladder and the over-engineering review stage draw on ideas only from [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail). No text is copied.
