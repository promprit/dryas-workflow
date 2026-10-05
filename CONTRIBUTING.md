# Contributing

## Portability (macOS, Linux, WSL, Windows)

- All scripts are Python 3.9+ standard library. Node is used only for the Ruflo MCP shim. There are no shell scripts except the two thin installer wrappers.
- Hook and MCP commands use the `$PY` and `$CD` placeholders and `-X utf8`. Never hardcode an interpreter or `$HOME`.
- Paths go through `install/platform_util.py` (`fwd`, `make_dir_link`, `remove_path`, `resolve_argv`).
- Read and write text files with `encoding="utf-8"`.
- `install/tests/test_portability.py` enforces the banned patterns. Mark a deliberate exception with `portable-ok: <reason>` on the same line.
- CI must be green on macOS, Ubuntu and Windows before merging to main. Branch protection enforces this.

## Running the tests

```
python -m pytest -q claude/jev/tests install/tests claude/ruflo/tests
node claude/ruflo/tests/test_ns.cjs
```
