# Windows and Codex Support Implementation Plan

> **For agentic workers:** Run with `/orchestrate` (Dryas Workflow). Each `## Task N:` section is self-contained: Goal, Scope, Done, Failing test first, then numbered steps with the code. Executors do not commit; the orchestrator commits after review.

**Goal:** One installer that sets up the Dryas Workflow on macOS, Linux, WSL and native Windows, for Claude Code and for Codex (rules, skills, MCP, safety and routing hooks).

**Architecture:** All POSIX shell shims become Python entrypoints; every path and the interpreter are rendered into hook commands at install time (absolute, forward slashes, quoted), so no hook depends on a particular shell. Codex reuses the same Jev code: a normaliser turns Codex `apply_patch` events into per-file `Write` events before the existing hook chain runs.

**Tech Stack:** Python 3.9+ stdlib only (installer, Jev, Ruflo runner), Node 20 (Ruflo MCP shim), pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-05-windows-codex-support-design.md`

## Global Constraints

- Python ≥ 3.9, stdlib only. No new dependencies.
- One implementation; no parallel `.sh` / `.ps1` logic. `install.sh` and `install.ps1` are thin wrappers only.
- Hook commands and `chain.json` stage commands are rendered at install time: absolute paths, forward slashes, every path double-quoted in Claude hook `command` strings, and Python always invoked with `-X utf8`.
- Placeholders: `$NAME` / `${NAME}` in settings fragments and `chain.json` (unmapped = hard error); `{{NAME}}` in copied `.md` files (unknown = hard error). Mapping keys: `HOME`, `DRYAS_DATA_ROOT`, `PY`, `CD`, `PY_SAFE`, `CD_SAFE`, plus the Ruflo keys from `detect()`.
- Every installer read/write of text files uses `encoding="utf-8"`.
- Hooks never exit 2 except to block; the Ruflo runner always exits 0.
- No `ANTHROPIC_API_KEY` anywhere; Jev reads only `OPENROUTER_API_KEY` from the environment.
- External commands are resolved with `shutil.which` before running (finds `npm.cmd`, `claude.cmd`, `codex.cmd` on Windows); never `shell=True` except the one documented `npm.cmd` call in `cli.js`.
- Files stay under 500 lines; add new modules instead of growing `install/dryas_install.py` past that.
- Executors never commit, push, merge or create worktrees.

## Review Focus

1. Windows user folder with a space and no 8.3 short name (`C:\Users\Ana Silva`): Ruflo (and Codex hooks on Windows) are refused at preflight with a message naming `--no-ruflo` / `--harness claude`; nothing half-installs. Tests: Task 8 `test_preflight_ruflo_space_refused`, Task 12 `test_preflight_codex_hooks_space_refused_on_windows`.
2. Python installed under a path with spaces (`C:/Program Files/Python312/python.exe`): rendered Claude hook commands stay valid because every path is quoted. Test: Task 2 `test_render_quotes_paths_with_spaces`.
3. Re-running the installer over an old install where the user added their own hooks: only the installer's stale entries go; the user's hooks stay. Test: Task 7 `test_upgrade_replaces_old_hooks_keeps_user_hooks`.
4. Codex `apply_patch` that escapes the worktree (`../../etc/x`) or hides an out-of-scope file among in-scope ones: denied, naming the file. Tests: Task 10 `test_codex_patch_outside_worktree_denied_by_real_scope_lock`, `test_codex_patch_denies_out_of_scope_file`.
5. Non-ASCII text in prompts or tool input on Windows (`café →`): hooks still run and exit 0 instead of crashing on the console code page. Test: Task 9 e2e event with `café →` content.

---

# Part A — Windows support

## Task 1: Platform helpers

Goal: Add `install/platform_util.py` with the cross-platform primitives every later installer task uses.
Scope:
- install/platform_util.py
- install/tests/test_platform_util.py
Done:
- `python3 -m pytest -q install/tests/test_platform_util.py` passes.
Failing test first: install/tests/test_platform_util.py :: PlatformUtilTest.test_dir_link_roundtrip

**Interfaces:**
- Produces (module `platform_util`, imported as `pu`):
  - `IS_WINDOWS: bool`
  - `fwd(p) -> str` — path string with `/` separators
  - `python_exe() -> str` — `fwd(sys.executable)`
  - `space_free(p) -> Optional[str]` — `p` if no spaces; on Windows its 8.3 short form if that has none; else `None`
  - `which(name: str) -> str` — `shutil.which(name) or ""`
  - `resolve_argv(argv: List[str]) -> List[str]` — `argv[0]` resolved on PATH when found
  - `same_path(a: str, b: str) -> bool`
  - `make_dir_link(target: str, dest: str) -> str` — returns `"symlink"` or `"junction"`
  - `read_dir_link(p: str) -> Optional[str]` — link target or `None`; strips the Windows `\\?\` prefix
  - `remove_path(p: str) -> None` — removes a file, symlink or junction; no-op if missing

- [ ] **Step 1: Write the failing tests** — create `install/tests/test_platform_util.py`:

```python
import os, shutil, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import platform_util as pu


class PlatformUtilTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def test_fwd(self):
        self.assertEqual(pu.fwd("C:\\a\\b c\\d"), "C:/a/b c/d")
        self.assertEqual(pu.fwd("/x/y"), "/x/y")

    def test_python_exe_is_forward_slash_sys_executable(self):
        self.assertEqual(pu.python_exe(), sys.executable.replace("\\", "/"))

    def test_space_free_without_space_is_identity(self):
        self.assertEqual(pu.space_free("/a/b"), "/a/b")

    @unittest.skipIf(os.name == "nt", "POSIX has no short names")
    def test_space_free_with_space_is_none_on_posix(self):
        self.assertIsNone(pu.space_free(str(self.tmp / "a b")))

    @unittest.skipUnless(os.name == "nt", "Windows short names")
    def test_space_free_windows_short_name_or_none(self):
        d = self.tmp / "with space"
        d.mkdir()
        got = pu.space_free(str(d))
        self.assertTrue(got is None or " " not in got)

    def test_which_and_resolve_argv(self):
        git = pu.which("git")
        self.assertTrue(git)
        self.assertEqual(pu.resolve_argv(["git", "--version"]), [git, "--version"])
        self.assertEqual(pu.resolve_argv(["no-such-tool-xyz", "a"]), ["no-such-tool-xyz", "a"])
        self.assertEqual(pu.resolve_argv([]), [])

    def test_dir_link_roundtrip(self):
        target = self.tmp / "target"
        target.mkdir()
        (target / "f.txt").write_text("x", encoding="utf-8")
        dest = self.tmp / "link"
        kind = pu.make_dir_link(str(target), str(dest))
        self.assertIn(kind, ("symlink", "junction"))
        self.assertTrue((dest / "f.txt").exists())
        self.assertTrue(pu.same_path(pu.read_dir_link(str(dest)), str(target)))
        pu.remove_path(str(dest))
        self.assertFalse(os.path.lexists(str(dest)))
        self.assertTrue((target / "f.txt").exists())

    def test_read_dir_link_of_plain_dir_is_none(self):
        self.assertIsNone(pu.read_dir_link(str(self.tmp)))

    def test_remove_path_file_and_missing(self):
        f = self.tmp / "f"
        f.write_text("x", encoding="utf-8")
        pu.remove_path(str(f))
        self.assertFalse(f.exists())
        pu.remove_path(str(f))  # missing: no error


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest -q install/tests/test_platform_util.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'platform_util'`

- [ ] **Step 3: Implement** — create `install/platform_util.py`:

```python
"""Cross-platform helpers for the installer: paths, tool lookup, directory links (symlink or Windows junction)."""
import os
import shutil
import sys
from typing import List, Optional

IS_WINDOWS = os.name == "nt"


def fwd(p) -> str:
    """Path as a string with forward slashes (valid in bash, Git Bash, cmd and Python on every OS)."""
    return str(p).replace("\\", "/")


def python_exe() -> str:
    return fwd(sys.executable)


def space_free(p) -> Optional[str]:
    """p if it has no spaces; on Windows its 8.3 short form if that has none; else None."""
    s = str(p)
    if " " not in s:
        return s
    if IS_WINDOWS:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetShortPathNameW(s, buf, len(buf))
        if 0 < n < len(buf) and " " not in buf.value:
            return buf.value
    return None


def which(name: str) -> str:
    return shutil.which(name) or ""


def resolve_argv(argv: List[str]) -> List[str]:
    """argv with argv[0] resolved on PATH. On Windows this finds npm.cmd / claude.cmd, which CreateProcess would not."""
    if not argv:
        return list(argv)
    return [which(argv[0]) or argv[0]] + list(argv[1:])


def same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def make_dir_link(target: str, dest: str) -> str:
    """Link dest -> directory target. Returns "symlink", or "junction" on Windows without symlink rights."""
    try:
        os.symlink(target, dest, target_is_directory=True)
        return "symlink"
    except OSError:
        if not IS_WINDOWS:
            raise
    import _winapi
    _winapi.CreateJunction(str(target), str(dest))
    return "junction"


def read_dir_link(p: str) -> Optional[str]:
    try:
        t = os.readlink(p)
    except (OSError, ValueError):
        return None
    return t[4:] if t.startswith("\\\\?\\") else t


def remove_path(p: str) -> None:
    """Remove a file, a symlink or a junction. Never removes a real directory's contents."""
    if not os.path.lexists(p):
        return
    if IS_WINDOWS and read_dir_link(p) is not None and os.path.isdir(p):
        os.rmdir(p)  # directory symlinks and junctions on Windows
    else:
        os.unlink(p)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest -q install/tests/test_platform_util.py`
Expected: PASS (Windows-only test skipped on macOS)

## Task 2: Rendering of hook commands, permissions and `.md` tokens

Goal: `settings_merge.render()` substitutes placeholders in env, permissions and hook commands; add `render_str()` and `render_tokens()`.
Scope:
- install/settings_merge.py
- install/tests/test_settings_merge.py
Done:
- `python3 -m pytest -q install/tests/test_settings_merge.py` passes.
Failing test first: install/tests/test_settings_merge.py :: RenderTest.test_render_quotes_paths_with_spaces

**Interfaces:**
- Produces (module `settings_merge`, imported as `sm`):
  - `render_str(s: str, mapping: Dict[str, str], where: str) -> str` — `$NAME`/`${NAME}` substitution; raises `ValueError("unmapped placeholder $NAME in <where>")`
  - `render(fragment: dict, mapping) -> dict` — renders `env` values, `permissions.allow/deny` rules, and every hook's `command` and `commandWindows`
  - `render_tokens(text: str, mapping) -> str` — `{{NAME}}` substitution; raises `ValueError("unmapped token {{NAME}}")`
  - `hook_entries(hooks: dict)` — public alias of `_hook_entries`, yields `(event, matcher, hook_dict)`

- [ ] **Step 1: Write the failing tests** — in `install/tests/test_settings_merge.py`:

Rename `test_env_only` to `test_env_and_hooks` and change its second assertion to:

```python
        self.assertEqual(r["hooks"]["PreToolUse"][0]["hooks"][0]["command"], "/bin/sh \"/h/h.sh\"")
```

In `MergeTest`, every expected hook command `"/bin/sh \"$HOME/h.sh\""` becomes `"/bin/sh \"/h/h.sh\""` (the fragment is rendered in `setUp`).

Add to `RenderTest`:

```python
    def test_render_quotes_paths_with_spaces(self):
        frag = {"permissions": {"allow": ['Bash("$PY" -X utf8 "$CD/jev/planfile.py":*)', "mcp__jev"]},
                "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
                    {"type": "command", "command": '"$PY" -X utf8 "$CD/jev/chain.py" pretool',
                     "commandWindows": "$PY_SAFE -X utf8 $CD_SAFE/jev/chain.py pretool"}]}]}}
        m = {"PY": "C:/Program Files/Python312/python.exe", "CD": "C:/Users/Ana Silva/.claude",
             "PY_SAFE": "C:/PROGRA~1/Python312/python.exe", "CD_SAFE": "C:/Users/ANASIL~1/.claude"}
        r = sm.render(frag, m)
        h = r["hooks"]["PreToolUse"][0]["hooks"][0]
        self.assertEqual(h["command"], '"C:/Program Files/Python312/python.exe" -X utf8 "C:/Users/Ana Silva/.claude/jev/chain.py" pretool')
        self.assertEqual(h["commandWindows"], "C:/PROGRA~1/Python312/python.exe -X utf8 C:/Users/ANASIL~1/.claude/jev/chain.py pretool")
        self.assertEqual(r["permissions"]["allow"],
                         ['Bash("C:/Program Files/Python312/python.exe" -X utf8 "C:/Users/Ana Silva/.claude/jev/planfile.py":*)', "mcp__jev"])
        self.assertIn("$PY", frag["hooks"]["PreToolUse"][0]["hooks"][0]["command"])  # input not mutated

    def test_unmapped_in_hook_fails(self):
        frag = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "$NOPE/x"}]}]}}
        with self.assertRaises(ValueError) as cm:
            sm.render(frag, {})
        self.assertIn("$NOPE", str(cm.exception))

    def test_render_tokens(self):
        t = 'Run `"{{PY}}" "{{CD}}/jev/handoff.py" save --cwd "$PWD"` and {braces} stay'
        self.assertEqual(sm.render_tokens(t, {"PY": "/p", "CD": "/c"}),
                         'Run `"/p" "/c/jev/handoff.py" save --cwd "$PWD"` and {braces} stay')
        with self.assertRaises(ValueError):
            sm.render_tokens("{{NOPE}}", {"PY": "/p"})
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest -q install/tests/test_settings_merge.py`
Expected: FAIL (`test_env_and_hooks` sees the unrendered command; `render_tokens` missing)

- [ ] **Step 3: Implement** — in `install/settings_merge.py` replace `render` and add helpers (keep `_PH`):

```python
_TOK = re.compile(r"\{\{([A-Z_][A-Z0-9_]*)\}\}")


def render_str(s: str, mapping: Dict[str, str], where: str) -> str:
    def sub(m):
        name = m.group(1)
        if name not in mapping:
            raise ValueError("unmapped placeholder $%s in %s" % (name, where))
        return mapping[name]
    return _PH.sub(sub, s)


def render(fragment: dict, mapping: Dict[str, str]) -> dict:
    out = copy.deepcopy(fragment)
    for k, v in out.get("env", {}).items():
        out["env"][k] = render_str(v, mapping, "env " + k)
    for kind in ("allow", "deny"):
        rules = out.get("permissions", {}).get(kind)
        if rules:
            out["permissions"][kind] = [render_str(r, mapping, "permissions." + kind) for r in rules]
    for ev, groups in out.get("hooks", {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                for key in ("command", "commandWindows"):
                    if key in h:
                        h[key] = render_str(h[key], mapping, "hooks." + ev)
    return out


def render_tokens(text: str, mapping: Dict[str, str]) -> str:
    """{{NAME}} tokens in copied .md files. Shell variables such as "$PWD" stay literal."""
    def sub(m):
        name = m.group(1)
        if name not in mapping:
            raise ValueError("unmapped token {{%s}}" % name)
        return mapping[name]
    return _TOK.sub(sub, text)
```

and after `_hook_entries` add:

```python
hook_entries = _hook_entries
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest -q install/tests/test_settings_merge.py`
Expected: PASS

## Task 3: Ruflo runner in Python (`ns.py`, `run.py`)

Goal: Replace `run.sh`, `cli.sh` and `ns.sh` with `claude/ruflo/ns.py` and `claude/ruflo/run.py` (same contract), plus shared namespace vectors.
Scope:
- claude/ruflo/ns.py
- claude/ruflo/run.py
- claude/ruflo/ns_cases.json
- claude/ruflo/tests/test_ns.py
- claude/ruflo/tests/test_run.py
- claude/ruflo/run.sh
- claude/ruflo/cli.sh
- claude/ruflo/ns.sh
- claude/ruflo/test_run.sh
Done:
- `python3 -m pytest -q claude/ruflo/tests` passes (plugin end-to-end tests skip when the ruflo plugin is absent).
- `run.sh`, `cli.sh`, `ns.sh`, `test_run.sh` deleted with `git rm`.
Failing test first: claude/ruflo/tests/test_ns.py :: NsTest.test_vectors

**Interfaces:**
- Produces (module `ns`): `ns_from(start: str, common_dir: Optional[str]) -> str`, `common_dir(start: str) -> Optional[str]`, `ruflo_ns(start: Optional[str] = None) -> str`, `ruflo_root() -> Optional[str]`.
- Produces (script `run.py`): `run.py helper <cmd> <helper-file> [args...]`, `run.py cli [args...]`; always exits 0.
- Produces `claude/ruflo/ns_cases.json`: list of `{"start": str, "common": str|null, "expect": str}` (also read by Task 4's JS test).

- [ ] **Step 1: Write the vectors** — create `claude/ruflo/ns_cases.json`:

```json
[
  {"start": "/x/myrepo", "common": "/x/myrepo/.git", "expect": "myrepo"},
  {"start": "/x/myrepo/.worktrees/main", "common": "/x/myrepo/.git", "expect": "myrepo"},
  {"start": "/x/myrepo/sub/dir", "common": "/x/myrepo/.git", "expect": "myrepo"},
  {"start": "/x/bare.git", "common": "/x/bare.git", "expect": "bare.git"},
  {"start": "/tmp/plain", "common": null, "expect": "plain"},
  {"start": "/tmp/plain/", "common": null, "expect": "plain"},
  {"start": "/tmp/we ird", "common": null, "expect": "we_ird"},
  {"start": "/tmp/café", "common": null, "expect": "caf_"},
  {"start": "/", "common": null, "expect": "_unknown"},
  {"start": "/tmp/..", "common": null, "expect": "_unknown"},
  {"start": "C:\\Users\\ana\\proj", "common": "C:/Users/ana/proj/.git", "expect": "proj"},
  {"start": "C:\\Users\\ana\\proj\\.worktrees\\x", "common": "C:/Users/ana/proj/.git", "expect": "proj"}
]
```

- [ ] **Step 2: Write the failing tests** — create `claude/ruflo/tests/test_ns.py`:

```python
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import ns


def git(*args, cwd):
    subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=t"] + list(args), cwd=str(cwd), check=True,
                   capture_output=True)


class NsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = {k: os.environ.pop(k, None) for k in ("RUFLO_SSD_ROOT", "DRYAS_DATA_ROOT", "CLAUDE_PROJECT_DIR")}

    def tearDown(self):
        for k, v in self.saved.items():
            if v is not None:
                os.environ[k] = v
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def test_vectors(self):
        for c in json.loads((HERE / "ns_cases.json").read_text(encoding="utf-8")):
            self.assertEqual(ns.ns_from(c["start"], c["common"]), c["expect"], c)

    def test_live_repo_and_worktree(self):
        repo = self.tmp / "myrepo"
        repo.mkdir()
        git("init", "-q", cwd=repo)
        git("commit", "-q", "--allow-empty", "-m", "i", cwd=repo)
        git("worktree", "add", "-q", ".worktrees/main", "-b", "wt-main", cwd=repo)
        self.assertEqual(ns.ruflo_ns(str(repo)), "myrepo")
        self.assertEqual(ns.ruflo_ns(str(repo / ".worktrees" / "main")), "myrepo")
        plain = self.tmp / "plain"
        plain.mkdir()
        self.assertEqual(ns.ruflo_ns(str(plain)), "plain")

    def test_ruflo_ns_uses_claude_project_dir(self):
        d = self.tmp / "proj"
        d.mkdir()
        os.environ["CLAUDE_PROJECT_DIR"] = str(d)
        self.assertEqual(ns.ruflo_ns(), "proj")

    def test_ruflo_root(self):
        os.environ["RUFLO_SSD_ROOT"] = str(self.tmp)
        self.assertEqual(ns.ruflo_root(), os.path.join(str(self.tmp), "_caches"))
        os.environ["RUFLO_SSD_ROOT"] = str(self.tmp / "missing")
        self.assertIsNone(ns.ruflo_root())
        del os.environ["RUFLO_SSD_ROOT"]
        os.environ["DRYAS_DATA_ROOT"] = str(self.tmp)
        self.assertEqual(ns.ruflo_root(), str(self.tmp))
        os.environ["DRYAS_DATA_ROOT"] = str(self.tmp / "missing")
        self.assertIsNone(ns.ruflo_root())


if __name__ == "__main__":
    unittest.main()
```

Create `claude/ruflo/tests/test_run.py` (port of `test_run.sh`; fakes are Python scripts with an OS-appropriate launcher):

```python
import hashlib, os, re, shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
RUN = HERE / "run.py"
SHIM = HERE / "mcp-shim" / "bin" / "cli.js"
NODE = shutil.which("node")
PLUG = Path.home() / ".claude/plugins/cache/ruflo/ruflo-core/0.2.6"
HELPERS = Path.home() / ".claude/ruflo/helpers"
STRIP = ("RUFLO_BIN", "RUFLO_JS", "RUFLO_SSD_ROOT", "DRYAS_DATA_ROOT", "CLAUDE_PROJECT_DIR", "RUFLO_DATA_MODE",
         "RUFLO_NODE_FALLBACK", "RUFLO_NODE_MODULES", "RUFLO_DATA_ROOT", "CLAUDE_FLOW_CWD")
ECHO_JS = ("let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{process.stdout.write('GOT:'+d+'|DIR:'+"
           "process.env.RUFLO_DATA_ROOT+'|NAE:'+process.env.RUFLO_NO_AUTO_ENABLE);process.exit(2)})")
FAKE_RUFLO_JS = ("let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{process.stdout.write('PWD:'+process.cwd()+"
                 "'|CWDENV:'+process.env.CLAUDE_FLOW_CWD+'|ARGS:'+process.argv.slice(2).join(' ')+'|IN:'+d);process.exit(2)})")


def make_exe(d: Path, name: str, pycode: str) -> Path:
    """A runnable fake: a Python script plus a launcher (shebang file on POSIX, .cmd on Windows)."""
    d.mkdir(parents=True, exist_ok=True)
    py = d / (name + "_impl.py")
    py.write_text(pycode, encoding="utf-8")
    if os.name == "nt":
        exe = d / (name + ".cmd")
        exe.write_text('@"%s" "%s" %%*\r\n' % (sys.executable, py), encoding="utf-8")
    else:
        exe = d / name
        exe.write_text('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, py), encoding="utf-8")
        exe.chmod(0o755)
    return exe


class RunTest(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        self.ssd = self.t / "ssd"
        self.ssd.mkdir()
        (self.t / "echo.js").write_text(ECHO_JS, encoding="utf-8")
        (self.t / "fakeruflo.js").write_text(FAKE_RUFLO_JS, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(str(self.t), ignore_errors=True)

    def run_py(self, args, stdin="payload", path=None, **env):
        e = {k: v for k, v in os.environ.items() if k not in STRIP}
        e.update(env)
        if path is not None:
            e["PATH"] = path
        p = subprocess.run([sys.executable, str(RUN)] + args, input=stdin, capture_output=True, text=True, env=e,
                           timeout=120)
        return p.returncode, p.stdout + p.stderr

    def cache(self, ns):
        return os.path.join(str(self.ssd), "_caches", "ruflo", ns)

    def test_data_root_missing_is_silent(self):
        rc, out = self.run_py(["helper", "node", str(self.t / "echo.js")], RUFLO_SSD_ROOT=str(self.t / "none"))
        self.assertEqual((rc, out), (0, ""))

    def test_helper_missing_is_silent(self):
        rc, out = self.run_py(["helper", "node", str(self.t / "nope.js")], RUFLO_SSD_ROOT=str(self.ssd))
        self.assertEqual((rc, out), (0, ""))

    def test_command_missing_is_silent(self):
        rc, out = self.run_py(["helper", "no-such-cmd-xyz", str(self.t / "echo.js")], RUFLO_SSD_ROOT=str(self.ssd))
        self.assertEqual((rc, out), (0, ""))

    def test_unknown_subcommand_is_silent(self):
        self.assertEqual(self.run_py(["bogus"]), (0, ""))

    @unittest.skipUnless(NODE, "node not installed")
    def test_helper_runs_in_cache_dir_and_never_exits_2(self):
        proj = str(self.t / "x" / "myproj")
        rc, out = self.run_py(["helper", "node", str(self.t / "echo.js")], stdin="hello-stdin",
                              CLAUDE_PROJECT_DIR=proj, RUFLO_SSD_ROOT=str(self.ssd))
        self.assertEqual(rc, 0)
        self.assertEqual(out, "GOT:hello-stdin|DIR:%s|NAE:1" % self.cache("myproj"))
        self.assertTrue(os.path.isdir(self.cache("myproj")))

    @unittest.skipUnless(NODE, "node not installed")
    def test_env_mode_leaves_data_root_unset(self):
        rc, out = self.run_py(["helper", "node", str(self.t / "echo.js")], stdin="e", RUFLO_DATA_MODE="env",
                              RUFLO_SSD_ROOT=str(self.ssd))
        self.assertEqual(out, "GOT:e|DIR:undefined|NAE:1")

    def test_node_fallback_when_node_not_on_path(self):
        fake = make_exe(self.t / "fb", "fakenode", "import sys\nprint('FALLBACK:' + sys.argv[1])\n")
        (self.t / "h.js").write_text("x", encoding="utf-8")
        empty = self.t / "emptybin"
        empty.mkdir()
        rc, out = self.run_py(["helper", "node", str(self.t / "h.js")], path=str(empty),
                              RUFLO_NODE_FALLBACK=str(fake), RUFLO_SSD_ROOT=str(self.ssd))
        self.assertEqual(out.strip(), "FALLBACK:%s" % (self.t / "h.js"))
        rc, out = self.run_py(["helper", "node", str(self.t / "h.js")], path=str(empty),
                              RUFLO_NODE_FALLBACK=str(self.t / "none"), RUFLO_SSD_ROOT=str(self.ssd))
        self.assertEqual((rc, out), (0, ""))

    def test_cli_noop_without_root_or_binary(self):
        self.assertEqual(self.run_py(["cli", "hooks", "x"], RUFLO_SSD_ROOT=str(self.t / "none"),
                                     RUFLO_BIN=str(self.t / "none")), (0, ""))
        self.assertEqual(self.run_py(["cli", "hooks", "x"], RUFLO_SSD_ROOT=str(self.ssd),
                                     RUFLO_BIN=str(self.t / "nobin")), (0, ""))

    @unittest.skipUnless(NODE, "node not installed")
    def test_cli_runs_ruflo_js_in_cache_dir(self):
        rc, out = self.run_py(["cli", "hooks", "post-command", "-c", "ls"], stdin="stdin-data",
                              CLAUDE_PROJECT_DIR=str(self.t / "x" / "projcli"), RUFLO_SSD_ROOT=str(self.ssd),
                              RUFLO_JS=str(self.t / "fakeruflo.js"))
        d = self.cache("projcli")
        self.assertEqual(rc, 0)
        m = re.fullmatch(r"PWD:(.*)\|CWDENV:(.*)\|ARGS:(.*)\|IN:(.*)", out, re.S)
        self.assertIsNotNone(m, out)
        self.assertTrue(os.path.samefile(m.group(1), d))
        self.assertEqual(m.group(2), d)
        self.assertEqual(m.group(3), "hooks post-command -c ls")
        self.assertEqual(m.group(4), "stdin-data")

    @unittest.skipIf(os.name == "nt", "RUFLO_BIN fake launcher is POSIX-only")
    def test_cli_uses_ruflo_bin_when_no_js(self):
        fake = make_exe(self.t / "rb", "ruflo", "import sys\nprint('BIN:' + ' '.join(sys.argv[1:]))\n")
        rc, out = self.run_py(["cli", "a", "b"], RUFLO_SSD_ROOT=str(self.ssd), RUFLO_BIN=str(fake))
        self.assertEqual(out.strip(), "BIN:a b")

    @unittest.skipUnless(NODE, "node not installed")
    def test_worktree_uses_main_repo_namespace(self):
        repo = self.t / "x" / "myrepo"
        repo.mkdir(parents=True)
        g = ["git", "-c", "user.email=a@b", "-c", "user.name=t"]
        subprocess.run(g + ["init", "-q"], cwd=str(repo), check=True)
        subprocess.run(g + ["commit", "-q", "--allow-empty", "-m", "i"], cwd=str(repo), check=True)
        subprocess.run(g + ["worktree", "add", "-q", ".worktrees/main", "-b", "wt"], cwd=str(repo), check=True)
        wt = str(repo / ".worktrees" / "main")
        rc, out = self.run_py(["cli", "hooks", "y"], stdin="i", CLAUDE_PROJECT_DIR=wt, RUFLO_SSD_ROOT=str(self.ssd),
                              RUFLO_JS=str(self.t / "fakeruflo.js"))
        self.assertIn("CWDENV:%s|" % self.cache("myrepo"), out)
        rc, out = self.run_py(["helper", "node", str(self.t / "echo.js")], stdin="i", CLAUDE_PROJECT_DIR=wt,
                              RUFLO_SSD_ROOT=str(self.ssd))
        self.assertIn("DIR:%s|" % self.cache("myrepo"), out)

    @unittest.skipUnless(NODE, "node not installed")
    def test_mcp_shim_fails_loudly_without_data_root(self):
        e = {k: v for k, v in os.environ.items() if k not in STRIP}
        e["RUFLO_SSD_ROOT"] = str(self.t / "nossd")
        p = subprocess.run([NODE, str(SHIM), "mcp", "start"], stdin=subprocess.DEVNULL, capture_output=True, env=e,
                           timeout=30)
        self.assertEqual(p.returncode, 1)

    # ---- end-to-end against the locally installed ruflo plugin and helpers (skipped elsewhere, e.g. CI)

    def plugin_env(self, proj, ssd):
        e = {k: v for k, v in os.environ.items() if k not in STRIP}
        e.update(CLAUDE_PROJECT_DIR=str(proj), CLAUDE_PLUGIN_ROOT=str(PLUG), RUFLO_SSD_ROOT=str(ssd),
                 RUFLO_HOOK_CLI_OVERRIDE="%s -X utf8 %s cli" % (sys.executable, RUN), RUFLO_HOOK_SKIP_NPX="1")
        return e

    @unittest.skipUnless(PLUG.is_dir() and NODE and shutil.which("ruflo"), "ruflo plugin not installed")
    def test_e2e_post_command_keeps_project_clean(self):
        g = self.t / "gitrepo"
        g.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(g), check=True)
        ev = '{"tool_name":"Bash","tool_input":{"command":"echo e2e"},"tool_response":{"exit_code":0}}'
        js = ("process.argv=[process.argv[0],'x','post-command'];"
              "require(require('path').join(process.env.CLAUDE_PLUGIN_ROOT,'scripts','ruflo-hook.cjs'))")
        subprocess.run([NODE, "-e", js], cwd=str(g), input=ev, text=True, capture_output=True,
                       env=self.plugin_env(g, self.ssd), timeout=120)
        self.assertFalse((g / ".claude-flow").exists())
        self.assertFalse((g / ".swarm").exists())
        self.assertTrue(os.path.isdir(self.cache("gitrepo")))

    @unittest.skipUnless((HELPERS / "hook-handler.cjs").is_file() and NODE, "installed ruflo helpers absent")
    def test_session_restore_never_spawns_npx(self):
        fb = self.t / "fakebin"
        marker = self.t / "npx-marker"
        make_exe(fb, "npx", "open(%r, 'w').close()\n" % str(marker))
        proj = self.t / "proj6"
        proj.mkdir()
        self.run_py(["helper", "node", str(HELPERS / "hook-handler.cjs"), "session-restore"], stdin="{}",
                    path=str(fb) + os.pathsep + os.environ["PATH"], CLAUDE_PROJECT_DIR=str(proj),
                    RUFLO_SSD_ROOT=str(self.ssd))
        time.sleep(1)
        self.assertFalse(marker.exists())

    @unittest.skipUnless((HELPERS / "auto-memory-hook.mjs").is_file() and NODE, "installed ruflo helpers absent")
    def test_auto_memory_import_is_read_only(self):
        proj = self.t / "proj7"
        proj.mkdir()
        key = re.sub(r"[/_:]", "-", str(proj))
        md = self.t / "home" / ".claude" / "projects" / key / "memory"
        md.mkdir(parents=True)
        (md / "MEMORY.md").write_text("# Memory\n\n## Fact one\nSome remembered fact for the test.\n", encoding="utf-8")

        def snap():
            return sorted((str(p.relative_to(md)), hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "")
                          for p in md.rglob("*"))
        before = snap()
        rc, out = self.run_py(["helper", "node", str(HELPERS / "auto-memory-hook.mjs"), "import"], stdin="{}",
                              HOME=str(self.t / "home"), USERPROFILE=str(self.t / "home"),
                              CLAUDE_PROJECT_DIR=str(proj), RUFLO_SSD_ROOT=str(self.ssd))
        self.assertEqual(snap(), before)
        self.assertRegex(out, r"Imported [1-9]")

    @unittest.skipUnless(PLUG.is_dir() and NODE, "ruflo plugin not installed")
    def test_e2e_mcp_store_lands_in_cache(self):
        r2 = self.t / "e2erepo"
        r2.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(r2), check=True)
        ssd2 = self.t / "ssd2"
        ssd2.mkdir()
        p = subprocess.run([NODE, str(HERE / "test_mcp.cjs"), str(r2), str(ssd2)], capture_output=True, text=True,
                           timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual([n for n in os.listdir(str(r2)) if n != ".git"], [])
        self.assertTrue((ssd2 / "_caches" / "ruflo" / "e2erepo" / "ruvector.db").is_file())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run to verify they fail**

Run: `python3 -m pytest -q claude/ruflo/tests`
Expected: FAIL with `ModuleNotFoundError: No module named 'ns'` (and `run.py` missing)

- [ ] **Step 4: Implement `claude/ruflo/ns.py`**

```python
"""Ruflo data namespace and data root. Same rules as mcp-shim/bin/cli.js (shared vectors: ns_cases.json).

Namespace = folder name of the MAIN repo (worktrees map to their main repo), else the basename of the
project dir; sanitized to [A-Za-z0-9._-] per character. Data root: DRYAS_DATA_ROOT, default ~/.dryas
(RUFLO_SSD_ROOT, tests only: <root>/_caches).
"""
import os
import re
import subprocess
from typing import List, Optional

_BAD = re.compile(r"[^A-Za-z0-9._-]")


def _parts(p: str) -> List[str]:
    return p.replace("\\", "/").rstrip("/").split("/")


def ns_from(start: str, common_dir: Optional[str]) -> str:
    name = None
    if common_dir:
        c = _parts(common_dir)
        if len(c) >= 2 and c[-1] == ".git" and c[-2]:
            name = c[-2]
    if name is None:
        name = _parts(start)[-1]
    name = _BAD.sub("_", name)
    return "_unknown" if name in ("", ".", "..") else name


def common_dir(start: str) -> Optional[str]:
    try:
        p = subprocess.run(["git", "-C", start, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    out = p.stdout.strip()
    return out if p.returncode == 0 and out else None


def ruflo_ns(start: Optional[str] = None) -> str:
    start = start or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return ns_from(start, common_dir(start))


def ruflo_root() -> Optional[str]:
    t = os.environ.get("RUFLO_SSD_ROOT")
    if t:
        return os.path.join(t, "_caches") if os.path.isdir(t) else None
    r = os.environ.get("DRYAS_DATA_ROOT") or os.path.join(os.path.expanduser("~"), ".dryas")
    return r if os.path.isdir(r) else None
```

- [ ] **Step 5: Implement `claude/ruflo/run.py`**

```python
#!/usr/bin/env python3
"""Ruflo hook runner (replaces run.sh and cli.sh). Never blocks a hook: always exits 0.

  run.py helper <cmd> <helper-file> [args...]   run one lifted Ruflo hook helper (cmd is usually "node")
  run.py cli [args...]                          run the pinned ruflo CLI (target of RUFLO_HOOK_CLI_OVERRIDE)

Silent no-op (stdin drained) when the data root, the command, the helper or the CLI is missing.
The child's stdout passes through; its exit code is dropped. RUFLO_DATA_MODE=cwd (default) runs the
child in <data root>/ruflo/<namespace> and sets RUFLO_DATA_ROOT there; =env runs in place.
`cli` prefers `node $RUFLO_JS` (portable) and falls back to RUFLO_BIN / `ruflo` on PATH.
"""
import os
import shutil
import subprocess
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ns  # noqa: E402


def _drain() -> int:
    try:
        sys.stdin.buffer.read()
    except Exception:
        pass
    return 0


def _node() -> Optional[str]:
    found = shutil.which("node")
    if found:
        return found
    fb = os.environ.get("RUFLO_NODE_FALLBACK", "")
    return fb if fb and os.path.isfile(fb) and os.access(fb, os.X_OK) else None


def _resolve(cmd: str) -> Optional[str]:
    return _node() if cmd == "node" else shutil.which(cmd)


def _node_modules() -> str:
    nm = os.environ.get("RUFLO_NODE_MODULES", "")
    if nm:
        return nm
    rb = shutil.which("ruflo")
    if not rb:
        return ""
    d = os.path.dirname(rb)
    for cand in (os.path.join(d, "..", "lib", "node_modules", "ruflo", "node_modules"),  # POSIX npm prefix
                 os.path.join(d, "node_modules", "ruflo", "node_modules")):          # Windows %APPDATA%\npm
        if os.path.isdir(cand):
            return cand
    return ""


def _data_dir(root: str) -> Optional[str]:
    d = os.path.join(root, "ruflo", ns.ruflo_ns())
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return None
    return d


def _call(argv: List[str], cwd: Optional[str], env: Dict[str, str]) -> int:
    try:
        sys.stdout.flush()
        subprocess.call(argv, cwd=cwd, env=env)
    except OSError:
        pass
    return 0


def helper(args: List[str]) -> int:
    root = ns.ruflo_root()
    if root is None or len(args) < 2:
        return _drain()
    exe = _resolve(args[0])
    if not exe or not os.path.isfile(args[1]):
        return _drain()
    env = dict(os.environ, RUFLO_NO_AUTO_ENABLE="1")
    nm = _node_modules()
    if nm and os.path.isdir(nm):
        env["NODE_PATH"] = nm + (os.pathsep + env["NODE_PATH"] if env.get("NODE_PATH") else "")
    cwd = None
    if env.get("RUFLO_DATA_MODE", "cwd") == "cwd":
        cwd = _data_dir(root)
        if cwd is None:
            return _drain()
        env["RUFLO_DATA_ROOT"] = cwd
    return _call([exe] + args[1:], cwd, env)


def cli(args: List[str]) -> int:
    root = ns.ruflo_root()
    if root is None:
        return _drain()
    js, node = os.environ.get("RUFLO_JS", ""), _node()
    if js and os.path.isfile(js) and node:
        argv = [node, js]
    else:
        b = os.environ.get("RUFLO_BIN") or shutil.which("ruflo") or ""
        if not b or not os.path.isfile(b):
            return _drain()
        argv = [b]
    d = _data_dir(root)
    if d is None:
        return _drain()
    # a CLI start must never autostart the background daemon (headless claude sessions cost tokens)
    env = dict(os.environ, RUFLO_NO_AUTO_ENABLE="1", RUFLO_DAEMON_AUTOSTART="0", CLAUDE_FLOW_CWD=d)
    return _call(argv + args, d, env)


def main(argv: List[str]) -> int:
    try:
        if len(argv) > 1 and argv[1] == "helper":
            return helper(argv[2:])
        if len(argv) > 1 and argv[1] == "cli":
            return cli(argv[2:])
        return _drain()
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 6: Delete the shell versions**

Run: `git rm claude/ruflo/run.sh claude/ruflo/cli.sh claude/ruflo/ns.sh claude/ruflo/test_run.sh`

- [ ] **Step 7: Run to verify they pass**

Run: `python3 -m pytest -q claude/ruflo/tests`
Expected: PASS. Plugin end-to-end tests run on the maintainer Mac and skip elsewhere.

## Task 4: MCP shim without `/bin/sh`

Goal: `cli.js` computes the namespace itself (same rules as `ns.py`), finds npm on Windows, and is importable for tests.
Scope:
- claude/ruflo/mcp-shim/bin/cli.js
- claude/ruflo/tests/test_ns.cjs
Done:
- `node claude/ruflo/tests/test_ns.cjs` prints only PASS lines and exits 0.
- `grep -n "/bin/sh\|ns.sh" claude/ruflo/mcp-shim/bin/cli.js` finds nothing.
- `python3 -m pytest -q claude/ruflo/tests` still passes.
Failing test first: claude/ruflo/tests/test_ns.cjs (fails: `nsFrom` is not exported)

**Interfaces:**
- Consumes: `claude/ruflo/ns_cases.json` (Task 3).
- Produces: `module.exports = { nsFrom }` in `cli.js`; `main()` runs only when executed directly.

- [ ] **Step 1: Write the failing test** — create `claude/ruflo/tests/test_ns.cjs`:

```js
// Checks nsFrom() in mcp-shim/bin/cli.js against the shared vectors (../ns_cases.json). Usage: node test_ns.cjs
'use strict';
const path = require('path');
const { nsFrom } = require(path.join(__dirname, '..', 'mcp-shim', 'bin', 'cli.js'));
const cases = require(path.join(__dirname, '..', 'ns_cases.json'));
let fail = 0;
for (const c of cases) {
  const got = typeof nsFrom === 'function' ? nsFrom(c.start, c.common) : undefined;
  if (got === c.expect) console.log('PASS ' + JSON.stringify(c.start));
  else { console.log('FAIL ' + JSON.stringify(c) + ' got ' + JSON.stringify(got)); fail = 1; }
}
process.exit(fail);
```

- [ ] **Step 2: Run to verify it fails**

Run: `node claude/ruflo/tests/test_ns.cjs`
Expected: non-zero exit (today `cli.js` runs its main code on `require` and exits 1, or `nsFrom` is undefined)

- [ ] **Step 3: Implement** — replace `claude/ruflo/mcp-shim/bin/cli.js` with:

```js
#!/usr/bin/env node
// Target of RUFLO_MCP_CLI_OVERRIDE: the ruflo-core plugin launcher runs `node <this> mcp start` with cwd = the
// project. This shim moves the server into $DRYAS_DATA_ROOT/ruflo/<ns> (so `.claude-flow/`,
// `.swarm/`, `ruvector.db` land in the data root, not in the project) and runs the PINNED ruflo CLI (no npx).
// Unlike hooks, MCP must fail loudly: data root or pinned CLI missing -> exit 1 (Claude shows the server disconnected).
// (../dist is a symlink or a Windows junction so the launcher's isRunnableCli() check passes.)
// Namespace rules match ../../ns.py; shared vectors: ../../ns_cases.json.
'use strict';
const { spawn, execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');
function fail(m) { process.stderr.write('[ruflo-mcp-shim] ' + m + '\n'); process.exit(1); }
function dataRoot() {
  const t = process.env.RUFLO_SSD_ROOT;
  if (t) return fs.existsSync(t) ? path.join(t, '_caches') : null;
  const r = process.env.DRYAS_DATA_ROOT || path.join(os.homedir(), '.dryas');
  return fs.existsSync(r) ? r : null;
}
function globalRufloJs() {
  try {
    const win = process.platform === 'win32';
    // npm is npm.cmd on Windows and Node refuses to spawn .cmd files without a shell (fixed arguments, no user input).
    const root = execFileSync(win ? 'npm.cmd' : 'npm', ['root', '-g'], { encoding: 'utf8', shell: win }).trim();
    return path.join(root, 'ruflo', 'bin', 'ruflo.js');
  } catch (e) { return ''; }
}
function parts(p) { return p.replace(/\\/g, '/').replace(/\/+$/, '').split('/'); }
function nsFrom(start, common) {
  let name = null;
  if (common) {
    const c = parts(common);
    if (c.length >= 2 && c[c.length - 1] === '.git' && c[c.length - 2]) name = c[c.length - 2];
  }
  if (name === null) { const s = parts(start); name = s[s.length - 1]; }
  name = name.replace(/[^A-Za-z0-9._-]/g, '_');
  return (name === '' || name === '.' || name === '..') ? '_unknown' : name;
}
function rufloNs() {
  const start = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  let common = null;
  try {
    common = execFileSync('git', ['-C', start, 'rev-parse', '--path-format=absolute', '--git-common-dir'],
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim() || null;
  } catch (e) { common = null; }
  return nsFrom(start, common);
}
function main() {
  const ROOT = dataRoot();
  const RUFLO_JS = process.env.RUFLO_JS || globalRufloJs();
  if (!ROOT) fail('data root missing (DRYAS_DATA_ROOT not mounted or not created)');
  if (!RUFLO_JS || !fs.existsSync(RUFLO_JS)) fail('ruflo CLI not found: ' + (RUFLO_JS || '(npm root -g failed)'));
  const ns = rufloNs();
  const dir = path.join(ROOT, 'ruflo', ns);
  try { fs.mkdirSync(dir, { recursive: true }); } catch (e) { fail('cannot create ' + dir + ': ' + e.message); }
  const child = spawn(process.execPath, [RUFLO_JS, ...process.argv.slice(2)], {
    cwd: dir, stdio: 'inherit',
    env: { ...process.env, CLAUDE_FLOW_CWD: dir, RUFLO_NO_AUTO_ENABLE: '1', RUFLO_DAEMON_AUTOSTART: '0', RUFLO_MCP_SKIP_NPX: '1' },
  });
  for (const s of ['SIGINT', 'SIGTERM']) process.on(s, () => child.kill(s));
  child.on('exit', (code, sig) => { if (sig) process.kill(process.pid, sig); else process.exit(code === null ? 1 : code); });
  child.on('error', (e) => fail('spawn failed: ' + e.message));
}
module.exports = { nsFrom };
if (require.main === module) main();
```

- [ ] **Step 4: Run to verify it passes**

Run: `node claude/ruflo/tests/test_ns.cjs && python3 -m pytest -q claude/ruflo/tests`
Expected: only PASS lines, exit 0; pytest PASS.

## Task 5: Shipped config uses placeholders; hook shims removed

Goal: The settings fragment, `chain.json` and the command/skill `.md` files use `$PY`/`$CD` (and `{{PY}}`/`{{CD}}` in `.md`), always with `-X utf8`; the `.sh` hook shims are deleted.
Scope:
- claude/settings.fragment.json
- claude/jev/chain.json
- claude/hooks/**
- claude/jev/hooks/**
- claude/commands/handoff.md
- claude/commands/tune.md
- claude/skills/orchestrate/SKILL.md
- claude/jev/tests/test_chain.py
- install/tests/test_shipped_files.py
Done:
- `python3 -m pytest -q install/tests/test_shipped_files.py claude/jev/tests/test_chain.py` passes.
- `git ls-files claude/hooks claude/jev/hooks` prints nothing.
Failing test first: install/tests/test_shipped_files.py :: ShippedFilesTest.test_no_posix_shell_in_hooks

**Interfaces:**
- Consumes: placeholder grammar from Task 2.
- Produces: shipped files whose only interpreter/path references are `$PY`, `$PY_SAFE`, `$CD`, `$CD_SAFE`, `$HOME`, `$DRYAS_DATA_ROOT` (fragment, chain) and `{{PY}}`, `{{CD}}` (`.md`). The installer renders them in Task 6.

- [ ] **Step 1: Write the failing test** — create `install/tests/test_shipped_files.py`:

```python
import json, unittest
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
CLAUDE = REPO / "claude"


def hook_commands(frag):
    for comp in frag.values():
        for ev, groups in comp.get("hooks", {}).items():
            for g in groups:
                for h in g["hooks"]:
                    yield ev, h["command"]


class ShippedFilesTest(unittest.TestCase):
    def setUp(self):
        self.frag = json.loads((CLAUDE / "settings.fragment.json").read_text(encoding="utf-8"))
        self.chain = json.loads((CLAUDE / "jev" / "chain.json").read_text(encoding="utf-8"))

    def test_no_posix_shell_in_hooks(self):
        text = (CLAUDE / "settings.fragment.json").read_text(encoding="utf-8")
        self.assertNotIn("/bin/sh", text)
        self.assertNotIn("/usr/bin/python3", text)
        for ev, cmd in hook_commands(self.frag):
            self.assertTrue(cmd.startswith('"$PY" -X utf8 "$CD/'), (ev, cmd))

    def test_chain_stages_use_py(self):
        for kind, stages in self.chain.items():
            for st in stages:
                self.assertEqual(st["cmd"][:3], ["$PY", "-X", "utf8"], st["name"])
                self.assertNotIn("/bin/sh", json.dumps(st))

    def test_ruflo_overrides(self):
        env = self.frag["ruflo"]["env"]
        self.assertEqual(env["RUFLO_HOOK_CLI_OVERRIDE"], "$PY_SAFE -X utf8 $CD_SAFE/ruflo/run.py cli")
        self.assertEqual(env["RUFLO_MCP_CLI_OVERRIDE"], "$CD/ruflo/mcp-shim/bin/cli.js")

    def test_md_files_use_tokens(self):
        for p in list((CLAUDE / "commands").glob("*.md")) + list((CLAUDE / "skills").rglob("*.md")):
            self.assertNotIn("/usr/bin/python3", p.read_text(encoding="utf-8"), p)
        self.assertIn('"{{PY}}" -X utf8 "{{CD}}/jev/handoff.py" save --cwd "$PWD"',
                      (CLAUDE / "commands" / "handoff.md").read_text(encoding="utf-8"))

    def test_shims_gone(self):
        self.assertFalse((CLAUDE / "hooks").exists())
        self.assertFalse((CLAUDE / "jev" / "hooks").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest -q install/tests/test_shipped_files.py`
Expected: FAIL (`/bin/sh` found)

- [ ] **Step 3: Rewrite `claude/settings.fragment.json`** — change only these values; everything else stays as it is.

`core.permissions.allow`:

```json
"allow": [
  "Read(~/.claude/jev/**)",
  "Bash(\"$PY\" -X utf8 \"$CD/jev/planfile.py\":*)",
  "Bash(\"$PY\" -X utf8 \"$CD/jev/handoff.py\" save:*)",
  "Bash(\"$PY\" -X utf8 \"$CD/jev/tune.py\" report)"
]
```

`core.hooks` (JSON-escape the quotes in the file, e.g. `"command": "\"$PY\" -X utf8 \"$CD/jev/chain.py\" pretool"`):

| Hook | New `command` |
|---|---|
| PreToolUse `*` | `"$PY" -X utf8 "$CD/jev/chain.py" pretool` |
| UserPromptSubmit | `"$PY" -X utf8 "$CD/jev/chain.py" prompt` |
| SessionStart `compact` | `"$PY" -X utf8 "$CD/jev/compact_restore.py"` |
| SessionStart `clear` | `"$PY" -X utf8 "$CD/jev/handoff_restore.py"` |
| PreCompact | `"$PY" -X utf8 "$CD/jev/compact_keep.py"` |

`ruflo.env`:

```json
"RUFLO_HOOK_CLI_OVERRIDE": "$PY_SAFE -X utf8 $CD_SAFE/ruflo/run.py cli",
"RUFLO_MCP_CLI_OVERRIDE": "$CD/ruflo/mcp-shim/bin/cli.js",
```

`ruflo.hooks`:

| Hook | New `command` |
|---|---|
| PostToolUse `Write\|Edit\|MultiEdit` | `"$PY" -X utf8 "$CD/ruflo/run.py" helper node "$CD/ruflo/helpers/hook-handler.cjs" post-edit` |
| SubagentStop | `"$PY" -X utf8 "$CD/ruflo/run.py" helper node "$CD/ruflo/helpers/hook-handler.cjs" post-task` |
| SessionStart (first) | `"$PY" -X utf8 "$CD/ruflo/run.py" helper node "$CD/ruflo/helpers/hook-handler.cjs" session-restore` |
| SessionStart (second) | `"$PY" -X utf8 "$CD/ruflo/run.py" helper node "$CD/ruflo/helpers/auto-memory-hook.mjs" import` |
| SessionEnd | `"$PY" -X utf8 "$CD/ruflo/run.py" helper node "$CD/ruflo/helpers/hook-handler.cjs" session-end` |
| PreCompact `manual` | `"$PY" -X utf8 "$CD/ruflo/run.py" helper node "$CD/ruflo/helpers/hook-handler.cjs" session-end manual` |
| PreCompact `auto` | `"$PY" -X utf8 "$CD/ruflo/run.py" helper node "$CD/ruflo/helpers/hook-handler.cjs" session-end auto` |

- [ ] **Step 4: Rewrite `claude/jev/chain.json`**

```json
{
  "pretool": [
    {"name": "scope-lock", "component": "core", "cmd": ["$PY", "-X", "utf8", "$CD/jev/scope_lock.py"], "match": "Edit|Write|MultiEdit|NotebookEdit", "timeout": 3},
    {"name": "jev-gate", "component": "jev", "cmd": ["$PY", "-X", "utf8", "$CD/jev/gate.py"], "match": "Bash|Write|Edit", "timeout": 5},
    {"name": "ruflo-pre-bash", "component": "ruflo", "cmd": ["$PY", "-X", "utf8", "$CD/ruflo/run.py", "helper", "node", "$CD/ruflo/helpers/hook-handler.cjs", "pre-bash"], "requires_path": "$DRYAS_DATA_ROOT", "timeout": 5, "match": "Bash", "observe": true},
    {"name": "flowobserve", "component": "flowobserve", "enabled": false, "cmd": ["$PY", "-X", "utf8", "-S", "$HOME/.flowobserve/bin/fo_hook.py"], "timeout": 1, "observe": true}
  ],
  "prompt": [
    {"name": "jev-route", "component": "jev", "cmd": ["$PY", "-X", "utf8", "$CD/jev/route.py"], "timeout": 5},
    {"name": "context-watch", "component": "core", "cmd": ["$PY", "-X", "utf8", "$CD/jev/context_watch.py"], "timeout": 2},
    {"name": "flowobserve", "component": "flowobserve", "enabled": false, "cmd": ["$PY", "-X", "utf8", "-S", "$HOME/.flowobserve/bin/fo_hook.py"], "timeout": 1, "observe": true}
  ]
}
```

- [ ] **Step 5: Update the `.md` files**

`claude/commands/handoff.md` — the code block becomes:

```
"{{PY}}" -X utf8 "{{CD}}/jev/handoff.py" save --cwd "$PWD"
```

`claude/commands/tune.md` — steps 1 and 4 become:

```
1. Run `"{{PY}}" -X utf8 "{{CD}}/jev/tune.py" report`.
4. For each approved proposal only: `"{{PY}}" -X utf8 "{{CD}}/jev/tune.py" apply <key> '<json value>'`. Never apply anything unapproved.
```

`claude/skills/orchestrate/SKILL.md` — §5 item 3 becomes:

```
3. Give each executor ONLY its section: `"{{PY}}" -X utf8 "{{CD}}/jev/planfile.py" section .orchestrate/PLAN.md <N>` plus the absolute worktree path. Never the whole plan.
```

- [ ] **Step 6: Delete the shims and fix the chain test**

Run: `git rm claude/hooks/pretool-chain.sh claude/hooks/prompt-chain.sh claude/jev/hooks/pretool-chain.sh claude/jev/hooks/prompt-chain.sh`

In `claude/jev/tests/test_chain.py` replace `test_wrapper_missing_chain_exits_zero` with:

```python
    def test_main_exits_zero_on_garbage_stdin(self):
        cfg = os.path.join(self.tmp, "chain.json")
        with open(cfg, "w") as f:
            json.dump({"pretool": []}, f)
        env = dict(os.environ, JEV_CHAIN_CONFIG=cfg)
        p = subprocess.run([sys.executable, os.path.join(HERE, "chain.py"), "pretool"], input="not json",
                           capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
```

- [ ] **Step 7: Run to verify**

Run: `python3 -m pytest -q install/tests/test_shipped_files.py claude/jev/tests/test_chain.py`
Expected: PASS

## Task 6: Portable installer core

Goal: `dryas_install.py` uses the discovered interpreter, resolves tools on PATH, renders `chain.json` and `.md` files, links `dist` as symlink or junction, reads/writes UTF-8, and verifies without `/bin/sh`.
Scope:
- install/dryas_install.py
- install/claude_md_block.py
- install/tests/test_dryas_install.py
Done:
- `python3 -m pytest -q install/tests` passes.
- `grep -n '"/bin/sh"\|/usr/bin/python3' install/dryas_install.py` finds nothing.
Failing test first: install/tests/test_dryas_install.py :: InstallTest.test_chain_and_md_rendered

**Interfaces:**
- Consumes: `platform_util` (Task 1); `sm.render_str`, `sm.render_tokens`, `sm.hook_entries` (Task 2).
- Produces:
  - `PY: str` (= `pu.python_exe()`), `PYX: List[str]` (= `[PY, "-X", "utf8"]`)
  - `_mapping(comps: List[str], home: Path, cd: Path) -> Dict[str, str]` with keys `HOME`, `DRYAS_DATA_ROOT`, `PY`, `CD`, `PY_SAFE`, `CD_SAFE` (+ `detect()` keys when `"ruflo" in comps`)
  - `_chain_bytes(f: Path, comps: List[str], mapping: Dict[str, str]) -> bytes`
  - `_put(..., dir_link: bool = False)`; record entries may carry `"link": "symlink" | "junction"`
  - `hook_problems(recorded_hooks: List[list]) -> List[str]`

- [ ] **Step 1: Write the failing tests** — in `install/tests/test_dryas_install.py`:

Right after `import ruflo_helpers as rh` add:

```python
REAL_DETECT = di.detect
```

Change the assertion that expects `"/usr/bin/python3"` in the `claude mcp add` call to:

```python
        self.assertIn(["claude", "mcp", "add", "--scope", "user", "jev", "--", di.PY, "-X", "utf8",
                       di.pu.fwd(self.cd / "jev/jev_mcp.py")], self.calls)
```

In `test_ruflo_shim_dist_link_created_and_removed` replace the two lines `self.assertTrue(link.is_symlink())` and `self.assertEqual(os.readlink(str(link)), str(self.dist))` with:

```python
        self.assertTrue(di.pu.same_path(di.pu.read_dir_link(str(link)), str(self.dist)))
```

and after `rec = json.loads(...)` add:

```python
        self.assertIn(rec["files"]["ruflo/mcp-shim/dist"]["link"], ("symlink", "junction"))
```

Decorate `test_source_symlinks_copied_as_symlinks` with `@unittest.skipIf(os.name == "nt", "file symlinks need admin rights on Windows")`.

Add these tests to `InstallTest`:

```python
    def test_chain_and_md_rendered(self):
        chain = {"pretool": [{"name": "s", "component": "core", "cmd": ["$PY", "-X", "utf8", "$CD/jev/x.py"],
                              "requires_path": "$DRYAS_DATA_ROOT"}], "prompt": []}
        (self.repo / "claude/jev/chain.json").write_text(json.dumps(chain), encoding="utf-8")
        (self.repo / "claude/commands").mkdir(parents=True)
        (self.repo / "claude/commands/h.md").write_text('"{{PY}}" -X utf8 "{{CD}}/jev/h.py" --cwd "$PWD" café\n',
                                                         encoding="utf-8")
        self.install(["core"])
        cd = di.pu.fwd(self.cd)
        got = json.loads((self.cd / "jev/chain.json").read_text(encoding="utf-8"))["pretool"][0]
        self.assertEqual(got["cmd"], [di.PY, "-X", "utf8", cd + "/jev/x.py"])
        self.assertEqual(got["requires_path"], di.pu.fwd(self.home / ".dryas"))
        self.assertEqual((self.cd / "commands/h.md").read_text(encoding="utf-8"),
                         '"%s" -X utf8 "%s/jev/h.py" --cwd "$PWD" café\n' % (di.PY, cd))

    def test_unknown_md_token_aborts_before_any_write(self):
        (self.repo / "claude/commands").mkdir(parents=True)
        (self.repo / "claude/commands/bad.md").write_text("{{NOPE}}", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.install(["core"])
        self.assertEqual(self.snapshot(), before)

    def test_hook_problems(self):
        (self.cd / "jev").mkdir(parents=True, exist_ok=True)
        (self.cd / "jev/c.py").write_text("x", encoding="utf-8")
        ok = '"%s" -X utf8 "%s"' % (di.PY, di.pu.fwd(self.cd / "jev/c.py"))
        self.assertEqual(di.hook_problems([["PreToolUse", "*", ok]]), [])
        self.assertEqual(len(di.hook_problems([["PreToolUse", "*", '/bin/sh "/nope/x.sh"']])), 2)

    def test_detect_without_npm(self):
        orig = di.pu.which
        di.pu.which = lambda n: ""
        try:
            d = REAL_DETECT()
        finally:
            di.pu.which = orig
        self.assertEqual((d["RUFLO_JS"], d["RUFLO_CLI_DIST"], d["RUFLO_NODE_MODULES"]), ("", "", ""))
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q install/tests/test_dryas_install.py`
Expected: FAIL (`di.PY` is `/usr/bin/python3`, `.md` not rendered, `hook_problems` missing)

- [ ] **Step 3: Implement — module head** in `install/dryas_install.py`:

Add `import re` to the imports, and after `import ruflo_helpers  # noqa: E402` add `import platform_util as pu  # noqa: E402`. Replace `PY = "/usr/bin/python3"` with:

```python
PY = pu.python_exe()
PYX = [PY, "-X", "utf8"]
```

Replace `run`, `capture`, `detect`, `load_record`, `save_record`:

```python
def run(argv: List[str]) -> int:
    try:
        return subprocess.call(pu.resolve_argv(argv))
    except OSError:
        return 127


def capture(argv: List[str], input_text: Optional[str] = None, env: Optional[dict] = None) -> Tuple[int, str]:
    try:
        p = subprocess.run(pu.resolve_argv(argv), input=input_text, capture_output=True, text=True, env=env,
                           encoding="utf-8", errors="replace")
    except OSError:
        return 127, ""
    return p.returncode, p.stdout


def detect() -> Dict[str, str]:
    npm, nm = pu.which("npm"), ""
    if npm:
        rc, out = capture([npm, "root", "-g"])
        nm = out.strip() if rc == 0 else ""

    def under(*parts):
        return os.path.join(nm, *parts) if nm else ""
    return {"RUFLO_BIN": pu.which("ruflo"), "RUFLO_JS": under("ruflo", "bin", "ruflo.js"),
            "RUFLO_NODE_FALLBACK": pu.which("node"), "RUFLO_NODE_MODULES": under("ruflo", "node_modules"),
            "RUFLO_CLI_DIST": under("ruflo", "node_modules", "@claude-flow", "cli", "dist")}


def load_record(cd: Path) -> dict:
    p = cd / RECORD
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"components": [], "files": {}, "settings": {"env": {}, "allow": [], "deny": [], "hooks": [], "top": {}},
            "settings_backup": None, "claude_md": False, "mcp": []}


def save_record(cd: Path, rec: dict) -> None:
    (cd / RECORD).write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Implement — rendering and copying.** Replace `_chain_bytes`, `_put`, `copy_files`, `_mapping`, `_fragment` with:

```python
def _chain_bytes(f: Path, comps: List[str], mapping: Dict[str, str]) -> bytes:
    c = json.loads(f.read_text(encoding="utf-8"))
    for stages in c.values():
        for st in stages:
            comp = st.get("component")
            if comp and comp != "core" and comp not in comps:
                st["enabled"] = False
            where = "chain.json stage " + str(st.get("name", "?"))
            st["cmd"] = [sm.render_str(str(x), mapping, where) for x in st.get("cmd", [])]
            if "requires_path" in st:
                st["requires_path"] = sm.render_str(str(st["requires_path"]), mapping, where)
    return (json.dumps(c, indent=2) + "\n").encode("utf-8")


def _rendered(rel: str, f: Path, comps: List[str], mapping: Dict[str, str]) -> bytes:
    if rel == "jev/chain.json":
        return _chain_bytes(f, comps, mapping)
    if rel.endswith(".md"):
        return sm.render_tokens(f.read_text(encoding="utf-8"), mapping).encode("utf-8")
    return f.read_bytes()


def _put(cd: Path, rel: str, rec: dict, force: bool, ts: str, rep: dict, dry: bool,
         data: Optional[bytes] = None, link: Optional[str] = None, mode_src: Optional[Path] = None,
         mode: Optional[int] = None, dir_link: bool = False) -> None:
    dest = cd / rel
    backup = None
    if os.path.lexists(str(dest)):
        cur_link = pu.read_dir_link(str(dest))
        if link is not None:
            same = cur_link is not None and pu.same_path(cur_link, link)
        else:
            same = cur_link is None and dest.is_file() and dest.read_bytes() == data
        if same:
            return
        ours = rel in rec["files"]
        if dest.is_dir() and cur_link is None:
            rep["skipped"].append(rel)
            return
        if not ours and not force:
            rep["skipped"].append(rel)
            return
        if dry:
            rep["replace"].append(rel)
            return
        if ours:
            backup = rec["files"][rel]["backup"]
            pu.remove_path(str(dest))
        else:
            b = cd / (".dryas-backup-" + ts) / rel
            b.parent.mkdir(parents=True, exist_ok=True)
            os.replace(str(dest), str(b))
            backup = str(b)
    elif dry:
        rep["new"].append(rel)
        return
    _mkdirs(cd, dest.parent, rec)
    entry = {"backup": backup}
    if link is not None:
        if dir_link:
            entry["link"] = pu.make_dir_link(link, str(dest))
        else:
            os.symlink(link, str(dest))
            entry["link"] = "symlink"
    else:
        dest.write_bytes(data)
        if mode_src is not None:
            shutil.copymode(str(mode_src), str(dest))
        if mode is not None:
            os.chmod(str(dest), mode)
    rec["files"][rel] = entry
    rep["written"].append(rel)


def copy_files(repo: Path, cd: Path, comps: List[str], rec: dict, force: bool, ts: str, dry: bool = False,
               mapping: Optional[Dict[str, str]] = None) -> dict:
    mapping = mapping if mapping is not None else _mapping(comps, Path.home(), cd)
    rep = {"new": [], "replace": [], "written": [], "skipped": []}
    for rel, f in _plan_files(repo, comps):
        if f.is_symlink():
            _put(cd, rel, rec, force, ts, rep, dry, link=os.readlink(str(f)))
        else:
            _put(cd, rel, rec, force, ts, rep, dry, data=_rendered(rel, f, comps, mapping), mode_src=f)
    if "ruflo" in comps:
        target = (mapping or {}).get("RUFLO_CLI_DIST")
        if target:
            _put(cd, SHIM_LINK, rec, force, ts, rep, dry, link=target, dir_link=True)
        else:
            print("warning: could not find the Ruflo CLI dist folder; %s not linked" % SHIM_LINK)
    return rep


def _mapping(comps: List[str], home: Path, cd: Path) -> Dict[str, str]:
    m = {"HOME": pu.fwd(home), "DRYAS_DATA_ROOT": pu.fwd(os.environ.get("DRYAS_DATA_ROOT", str(Path(home) / ".dryas"))),
         "PY": PY, "CD": pu.fwd(cd),
         "PY_SAFE": pu.fwd(pu.space_free(sys.executable) or ""), "CD_SAFE": pu.fwd(pu.space_free(cd) or "")}
    if "ruflo" in comps:
        m.update(detect())
    return m


def _fragment(repo: Path, comps: List[str], mapping: Dict[str, str]) -> dict:
    p = repo / "claude" / "settings.fragment.json"
    if not p.exists():
        return {}
    by_comp = json.loads(p.read_text(encoding="utf-8"))
    frag = {}
    for c in comps:
        if by_comp.get(c):
            frag = sm.merge(frag, by_comp[c])[0]
    return sm.render(frag, mapping)


def _prevalidate(repo: Path, comps: List[str], mapping: Dict[str, str]) -> None:
    """Render everything once so unmapped placeholders or tokens abort before any write."""
    _fragment(repo, comps, mapping)
    for rel, f in _plan_files(repo, comps):
        if not f.is_symlink() and (rel == "jev/chain.json" or rel.endswith(".md")):
            _rendered(rel, f, comps, mapping)
```

- [ ] **Step 5: Implement — `apply_settings`, `install`, `uninstall`, `verify` edits.**

In `apply_settings`: the default becomes `mapping = mapping if mapping is not None else _mapping(comps, home, cd)` and the write becomes `path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")`.

In `install`: replace the two lines `mapping = _mapping(comps, home)` and `_fragment(repo, comps, mapping)  # unmapped placeholders abort here too` with:

```python
    mapping = _mapping(comps, home, cd)
    _prevalidate(repo, comps, mapping)  # unmapped placeholders or tokens abort here, before any write
```

`claude_md(cd, tpl.read_text(), rec)` becomes `claude_md(cd, tpl.read_text(encoding="utf-8"), rec)`, and the MCP argv becomes:

```python
        argv = ["claude", "mcp", "add", "--scope", "user", "jev", "--"] + PYX + [pu.fwd(cd / "jev/jev_mcp.py")]
```

In `uninstall`, replace the first three lines of the `for rel, info in rec["files"].items():` body with:

```python
        dest = cd / rel
        if info.get("link") or (os.path.lexists(str(dest)) and (dest.is_symlink() or not dest.is_dir())):
            pu.remove_path(str(dest))
```

and `spath.write_text(json.dumps(new, indent=2) + "\n")` gets `encoding="utf-8"`.

Add above `verify`:

```python
_QUOTED = re.compile(r'"([^"]+)"')


def hook_problems(recorded_hooks: List[list]) -> List[str]:
    """Problems with the installer's own hook commands: /bin/sh, or a quoted path that does not exist."""
    probs = []
    for ev, _m, cmd in recorded_hooks:
        if "/bin/sh" in cmd:
            probs.append("%s uses /bin/sh" % ev)
        for p in _QUOTED.findall(cmd):
            if ("/" in p or "\\" in p) and not os.path.exists(p):
                probs.append("%s: missing %s" % (ev, p))
    return probs
```

In `verify`: `run([PY, "-c", "import pytest"])` becomes `run(PYX + ["-c", "import pytest"])`, `run([PY, "-m", "pytest", ...])` becomes `run(PYX + ["-m", "pytest", "-q", str(tdir)])`, remove `hook = cd / "hooks" / "pretool-chain.sh"`, replace `capture(["/bin/sh", str(hook)], json.dumps(event), env)` with `capture(PYX + [str(cd / "jev" / "chain.py"), "pretool"], json.dumps(event), env)`, and before `wt = Path(tempfile.mkdtemp())` add:

```python
    probs = hook_problems(load_record(cd).get("settings", {}).get("hooks", []))
    fails += say("FAIL" if probs else "PASS", "hook commands point at existing files", "; ".join(probs))
```

- [ ] **Step 6: UTF-8 in `install/claude_md_block.py`** — every `p.read_text()` becomes `p.read_text(encoding="utf-8")` and every `p.write_text(new)` becomes `p.write_text(new, encoding="utf-8")`.

- [ ] **Step 7: Run to verify**

Run: `python3 -m pytest -q install/tests`
Expected: PASS

## Task 7: Upgrade path for existing installs

Goal: Re-running the installer removes the settings entries and files the previous version recorded but the new version no longer ships, and keeps everything the user added.
Scope:
- install/upgrade.py
- install/dryas_install.py
- install/tests/test_upgrade.py
- install/tests/test_dryas_install.py
Done:
- `python3 -m pytest -q install/tests` passes.
Failing test first: install/tests/test_dryas_install.py :: InstallTest.test_upgrade_replaces_old_hooks_keeps_user_hooks

**Interfaces:**
- Consumes: `sm.unmerge`, `pu.remove_path`, record format from Task 6.
- Produces (module `upgrade`):
  - `stale_settings(recorded: dict, fragment: dict) -> dict` — same shape as the record's `settings` (`env`, `allow`, `deny`, `hooks`, `top`)
  - `subtract(recorded: dict, stale: dict) -> dict`
  - `has_any(stale: dict) -> bool`
  - `stale_files(recorded_files: Iterable[str], shipped: Iterable[str]) -> List[str]`
- `dryas_install.apply_settings(..., comps_all: Optional[List[str]] = None)`.

- [ ] **Step 1: Write the failing tests** — create `install/tests/test_upgrade.py`:

```python
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import upgrade

REC = {"env": {"A": "1", "OLD": "x"}, "allow": ["Bash(old)", "keep"], "deny": [], "top": {"model": "opus"},
       "hooks": [["PreToolUse", "*", "/bin/sh old"], ["Stop", None, "same"]]}
FRAG = {"model": "opus", "env": {"A": "1"}, "permissions": {"allow": ["keep"]},
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "same"}]}]}}


class UpgradeTest(unittest.TestCase):
    def test_stale_settings(self):
        self.assertEqual(upgrade.stale_settings(REC, FRAG),
                         {"env": {"OLD": "x"}, "allow": ["Bash(old)"], "deny": [], "top": {},
                          "hooks": [["PreToolUse", "*", "/bin/sh old"]]})

    def test_changed_env_value_is_stale(self):
        self.assertEqual(upgrade.stale_settings({"env": {"A": "old"}}, {"env": {"A": "new"}})["env"], {"A": "old"})

    def test_subtract(self):
        st = upgrade.stale_settings(REC, FRAG)
        self.assertEqual(upgrade.subtract(REC, st),
                         {"env": {"A": "1"}, "allow": ["keep"], "deny": [], "top": {"model": "opus"},
                          "hooks": [["Stop", None, "same"]]})

    def test_has_any(self):
        self.assertFalse(upgrade.has_any(upgrade.stale_settings({}, {})))
        self.assertTrue(upgrade.has_any(upgrade.stale_settings(REC, FRAG)))

    def test_stale_files(self):
        self.assertEqual(upgrade.stale_files(["a", "b", "c"], {"a", "c"}), ["b"])


if __name__ == "__main__":
    unittest.main()
```

Add to `InstallTest` in `install/tests/test_dryas_install.py`:

```python
    def test_upgrade_replaces_old_hooks_keeps_user_hooks(self):
        self.install(["core"])
        s = json.loads((self.cd / "settings.json").read_text(encoding="utf-8"))
        s["hooks"]["PreToolUse"].append({"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-hook"}]})
        (self.cd / "settings.json").write_text(json.dumps(s), encoding="utf-8")
        new_core = {"env": {"CORE": "1"}, "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
            {"type": "command", "command": "\"$PY\" -X utf8 \"$CD/jev/chain.py\" pretool"}]}]}}
        (self.repo / "claude/settings.fragment.json").write_text(json.dumps(dict(FRAG, core=new_core)), encoding="utf-8")
        os.unlink(str(self.repo / "claude/hooks/pretool-chain.sh"))
        self.install(["core"])
        s = json.loads((self.cd / "settings.json").read_text(encoding="utf-8"))
        cmds = [h["command"] for g in s["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertIn('"%s" -X utf8 "%s/jev/chain.py" pretool' % (di.PY, di.pu.fwd(self.cd)), cmds)
        self.assertIn("my-own-hook", cmds)
        self.assertFalse(any("/bin/sh" in c for c in cmds))
        self.assertFalse((self.cd / "hooks/pretool-chain.sh").exists())
        rec = json.loads((self.cd / ".dryas-installed.json").read_text(encoding="utf-8"))
        self.assertNotIn("hooks/pretool-chain.sh", rec["files"])
        self.assertFalse(any("/bin/sh" in h[2] for h in rec["settings"]["hooks"]))
        di.uninstall(self.cd)
        s = json.loads((self.cd / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual([h["command"] for g in s["hooks"]["PreToolUse"] for h in g["hooks"]], ["my-own-hook"])

    def test_stale_file_backup_restored(self):
        (self.cd / "hooks").mkdir(parents=True)
        (self.cd / "hooks/pretool-chain.sh").write_text("MINE", encoding="utf-8")
        self.install(["core"], force=True)
        os.unlink(str(self.repo / "claude/hooks/pretool-chain.sh"))
        self.install(["core"])
        self.assertEqual((self.cd / "hooks/pretool-chain.sh").read_text(encoding="utf-8"), "MINE")

    def test_reinstall_with_fewer_components_keeps_earlier_ones(self):
        self.install(["core", "jev", "ruflo"])
        self.install(["core"])
        s = json.loads((self.cd / "settings.json").read_text(encoding="utf-8"))
        self.assertIn("RUFLO_BIN", s["env"])
        self.assertTrue((self.cd / "ruflo/run.sh").exists())
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q install/tests/test_upgrade.py install/tests/test_dryas_install.py`
Expected: FAIL (`No module named 'upgrade'`; old `/bin/sh` hook still present after re-install)

- [ ] **Step 3: Implement `install/upgrade.py`**

```python
"""Upgrade an existing install: find recorded settings entries and files the new version no longer ships."""
from typing import Iterable, List


def stale_settings(recorded: dict, fragment: dict) -> dict:
    """Entries of the installer's settings record that the rendered fragment no longer produces."""
    out = {"env": {}, "allow": [], "deny": [], "hooks": [], "top": {}}
    fenv = fragment.get("env", {})
    for k, v in recorded.get("env", {}).items():
        if fenv.get(k) != v:
            out["env"][k] = v
    perms = fragment.get("permissions", {})
    for kind in ("allow", "deny"):
        out[kind] = [r for r in recorded.get(kind, []) if r not in perms.get(kind, [])]
    have = {(ev, g.get("matcher"), h.get("command"))
            for ev, groups in fragment.get("hooks", {}).items() for g in groups for h in g.get("hooks", [])}
    out["hooks"] = [list(t) for t in recorded.get("hooks", []) if tuple(t) not in have]
    for k, v in recorded.get("top", {}).items():
        if fragment.get(k) != v:
            out["top"][k] = v
    return out


def subtract(recorded: dict, stale: dict) -> dict:
    out = {"env": {k: v for k, v in recorded.get("env", {}).items() if k not in stale["env"]},
           "top": {k: v for k, v in recorded.get("top", {}).items() if k not in stale["top"]}}
    for kind in ("allow", "deny", "hooks"):
        out[kind] = [x for x in recorded.get(kind, []) if x not in stale[kind]]
    return out


def has_any(stale: dict) -> bool:
    return any(stale.get(k) for k in ("env", "allow", "deny", "hooks", "top"))


def stale_files(recorded_files: Iterable[str], shipped: Iterable[str]) -> List[str]:
    keep = set(shipped)
    return sorted(r for r in recorded_files if r not in keep)
```

- [ ] **Step 4: Wire it into `install/dryas_install.py`**

Add `import upgrade  # noqa: E402` next to the other local imports.

Add after `copy_files`:

```python
def _remove_stale_files(repo: Path, cd: Path, comps_all: List[str], rec: dict, dry: bool) -> None:
    shipped = {rel for rel, _ in _plan_files(repo, comps_all)}
    if "ruflo" in comps_all:
        shipped |= {r for r in rec["files"] if r.startswith("ruflo/helpers/")} | {SHIM_LINK}
    for rel in upgrade.stale_files(rec["files"], shipped):
        if dry:
            print("would remove (no longer shipped): %s" % rel)
            continue
        dest = cd / rel
        try:
            pu.remove_path(str(dest))
        except OSError:
            print("kept (could not remove): %s" % rel)
            continue
        b = rec["files"][rel].get("backup")
        if b and os.path.lexists(b):
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(b, str(dest))
        del rec["files"][rel]
        print("removed (no longer shipped): %s" % rel)
```

Change `apply_settings` — signature gains `comps_all: Optional[List[str]] = None`; replace its body from `frag = ...` through the write so it reads:

```python
    mapping = mapping if mapping is not None else _mapping(comps, home, cd)
    frag = _fragment(repo, comps, mapping)
    stale = upgrade.stale_settings(rec.get("settings", {}), _fragment(repo, comps_all or comps, mapping))
    path = cd / "settings.json"
    orig = sm.load_settings(path)
    base = sm.unmerge(orig, stale) if upgrade.has_any(stale) else orig
    merged, added, conflicts = sm.merge(base, frag)
    for c in conflicts:
        print("kept your value for %s" % c)
    diff = sm.diff_text(orig, merged)
    if not diff:
        if not dry and upgrade.has_any(stale):
            rec["settings"] = upgrade.subtract(rec.get("settings", {}), stale)
        print("settings.json: nothing to change")
        return
    print(diff)
    if dry:
        print("dry run: settings.json not changed")
        return
    if not (yes or confirm("Apply these settings changes?")):
        print("settings.json not changed")
        return
    if path.exists():
        b = _unique(cd / ("settings.json.dryas-bak-" + (ts or _ts())))
        shutil.copy2(str(path), str(b))
        if not rec.get("settings_backup"):
            rec["settings_backup"] = str(b)
        rec.setdefault("settings_created", False)
    else:
        rec["settings_created"] = True
    path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    rec["settings"] = upgrade.subtract(rec.get("settings", {}), stale)
    acc = rec["settings"]
    for k, v in added.items():
        if isinstance(v, list):
            acc.setdefault(k, []).extend(x for x in v if x not in acc.get(k, []))
        else:
            acc.setdefault(k, {}).update(v)
```

In `install`, load the record before computing the mapping and use the union of old and new components for mapping, stale detection and file pruning:

```python
    rec = load_record(cd)
    comps_all = sorted(set(rec.get("components", [])) | set(comps))
    mapping = _mapping(comps_all, home, cd)
    _prevalidate(repo, comps, mapping)  # unmapped placeholders or tokens abort here, before any write
```

(delete the later `rec = load_record(cd)` line), after `rep = copy_files(...)` add `_remove_stale_files(repo, cd, comps_all, rec, dry)`, and call `apply_settings(repo, cd, comps, rec, home, ts, mapping, dry, yes=yes, comps_all=comps_all)`.

- [ ] **Step 5: Run to verify**

Run: `python3 -m pytest -q install/tests`
Expected: PASS. Then `wc -l install/dryas_install.py` must print under 500 (Task 8 moves `thirdparty` out).

## Task 8: Installer entry: `run` subcommand and thin wrappers

Goal: Flag parsing, preflight and the thirdparty → install → verify sequence move from `install.sh` into `install/run_cmd.py`; `install.sh` and new `install.ps1` only find Python ≥ 3.9 and forward arguments.
Scope:
- install/run_cmd.py
- install/dryas_install.py
- install/install.sh
- install/install.ps1
- install/tests/fakecli.py
- install/tests/test_run_cmd.py
- install/tests/test_dryas_install.py
Done:
- `python3 -m pytest -q install/tests` passes.
- `wc -l install/dryas_install.py` prints under 500.
Failing test first: install/tests/test_run_cmd.py :: RunCmdTest.test_preflight_ruflo_space_refused

**Interfaces:**
- Consumes: `pu.which`, `pu.space_free` (Task 1); `di.install`, `di.verify`, `di.uninstall`, `di.run`, `di.confirm` (Tasks 6–7).
- Produces (module `run_cmd`):
  - `OPTIONAL = ("jev", "ruflo", "superpowers", "design")`, `HARNESSES = ("claude",)` (Task 12 extends)
  - `parse(argv: List[str]) -> argparse.Namespace` (flags `--repo`, `--no-<component>`, `--yes`, `--force`, `--dry-run`, `--uninstall`, `--preflight-only`, `--harness`)
  - `components(a) -> List[str]`
  - `preflight(comps: List[str], harness: str, claude_dir: Path) -> List[str]`
  - `thirdparty(comps: List[str], yes: bool, home: Optional[Path] = None) -> int` (moved from `dryas_install.py`)
  - `main(argv: Optional[List[str]] = None) -> int`
- `dryas_install.py run ...` and `dryas_install.py preflight ...` delegate to `run_cmd.main`.
- Module `fakecli` (tests): `make(bin_dir: Path, name: str, log: Path, outputs: Optional[dict] = None, fail: Iterable[str] = ()) -> Path`, `calls(log: Path) -> List[List[str]]`.

- [ ] **Step 1: Write the test helper** — create `install/tests/fakecli.py`:

```python
"""Fake command-line tools for installer tests: a Python script plus a launcher that PATH lookup finds on every OS.

Each call appends [name, *args] as one JSON line to `log`. stdout is outputs.get("<arg1> <arg2>", "").
Exit code is 1 when "<arg1> <arg2>" is in `fail`, else 0.
"""
import json
import os
import sys
from pathlib import Path
from typing import Iterable, List, Optional

SCRIPT = '''import json, sys
with open(%(log)r, "a", encoding="utf-8") as f:
    f.write(json.dumps([%(name)r] + sys.argv[1:]) + "\\n")
key = " ".join(sys.argv[1:3])
sys.stdout.write(%(outputs)r.get(key, ""))
sys.exit(1 if key in %(fail)r else 0)
'''


def make(bin_dir: Path, name: str, log: Path, outputs: Optional[dict] = None, fail: Iterable[str] = ()) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    py = bin_dir / (name + "_fake.py")
    py.write_text(SCRIPT % {"name": name, "log": str(log), "outputs": dict(outputs or {}), "fail": list(fail)},
                  encoding="utf-8")
    if os.name == "nt":
        launcher = bin_dir / (name + ".cmd")
        launcher.write_text('@"%s" "%s" %%*\r\n' % (sys.executable, py), encoding="utf-8")
    else:
        launcher = bin_dir / name
        launcher.write_text('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, py), encoding="utf-8")
        launcher.chmod(0o755)
    return launcher


def calls(log: Path) -> List[List[str]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
```

- [ ] **Step 2: Write the failing tests** — create `install/tests/test_run_cmd.py`:

```python
import os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import fakecli
import platform_util as pu
import run_cmd


class RunCmdTest(unittest.TestCase):
    def setUp(self):
        self.orig = (pu.which, pu.space_free)

    def tearDown(self):
        pu.which, pu.space_free = self.orig

    def test_components(self):
        self.assertEqual(run_cmd.components(run_cmd.parse(["--no-ruflo"])), ["core", "jev", "superpowers", "design"])
        self.assertEqual(run_cmd.components(run_cmd.parse([])), ["core", "jev", "ruflo", "superpowers", "design"])

    def test_preflight_missing_lists_tools(self):
        pu.which = lambda n: ""
        probs = run_cmd.preflight(["core", "ruflo"], "claude", Path("/x/.claude"))
        self.assertIn("Missing:", probs[0])
        for t in ("git", "claude", "node", "npm"):
            self.assertIn(t, probs[0])

    def test_preflight_ok(self):
        pu.which = lambda n: "/bin/" + n
        pu.space_free = lambda p: str(p)
        self.assertEqual(run_cmd.preflight(["core", "jev", "ruflo"], "claude", Path("/x/.claude")), [])

    def test_preflight_ruflo_space_refused(self):
        pu.which = lambda n: "/bin/" + n
        pu.space_free = lambda p: None
        probs = run_cmd.preflight(["core", "ruflo"], "claude", Path("/x/Ana Silva/.claude"))
        self.assertTrue(any("--no-ruflo" in p for p in probs), probs)
        self.assertEqual(run_cmd.preflight(["core", "jev"], "claude", Path("/x/Ana Silva/.claude")), [])


class WrapperTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "Jane Doe"
        self.home.mkdir()
        fb = self.tmp / "bin"
        for n in ("claude", "node", "npm", "git"):
            fakecli.make(fb, n, self.tmp / "calls.jsonl")
        path = [str(fb), os.path.dirname(sys.executable)]
        if os.name == "nt":
            sysroot = os.environ.get("SystemRoot", r"C:\Windows")
            path += [sysroot + r"\System32", sysroot + r"\System32\WindowsPowerShell\v1.0"]
        else:
            path += ["/usr/bin", "/bin"]
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home), PATH=os.pathsep.join(path))

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def wrapper(self, *args):
        if os.name == "nt":
            argv = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE.parent / "install.ps1")]
        else:
            argv = ["/bin/sh", str(HERE.parent / "install.sh")]
        return subprocess.run(argv + list(args), capture_output=True, text=True, env=self.env, timeout=120)

    def test_preflight_only(self):
        p = self.wrapper("--preflight-only", "--no-ruflo")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("preflight ok", p.stdout)

    @unittest.skipIf(os.name == "nt", "Windows usually has an 8.3 short name for the space")
    def test_space_in_home_refuses_ruflo(self):
        p = self.wrapper("--preflight-only")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("--no-ruflo", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
```

Delete the `ShellTest` class from `install/tests/test_dryas_install.py` (`WrapperTest` replaces it).

- [ ] **Step 3: Run to verify they fail**

Run: `python3 -m pytest -q install/tests/test_run_cmd.py`
Expected: FAIL with `No module named 'run_cmd'`

- [ ] **Step 4: Implement `install/run_cmd.py`**

```python
"""Installer entry used by install.sh and install.ps1: flags, preflight, then thirdparty -> install -> verify.

  dryas_install.py run [--repo PATH] [--no-jev] [--no-ruflo] [--no-superpowers] [--no-design]
                       [--yes] [--force] [--dry-run] [--uninstall] [--preflight-only] [--harness claude]
"""
import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

import platform_util as pu

HERE = Path(__file__).resolve().parent
OPTIONAL = ("jev", "ruflo", "superpowers", "design")
HARNESSES = ("claude",)
NO_SPACE_RUFLO = ("Your Python or Claude folder path contains a space and has no short form; "
                  "Ruflo's hook override cannot handle that. Re-run with --no-ruflo.")


def parse(argv: List[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="install")
    ap.add_argument("--repo", default=str(HERE.parent))
    for c in OPTIONAL:
        ap.add_argument("--no-" + c, action="store_true")
    for f in ("yes", "force", "dry-run", "uninstall", "preflight-only"):
        ap.add_argument("--" + f, action="store_true")
    ap.add_argument("--harness", default="claude", choices=HARNESSES)
    return ap.parse_args(argv)


def components(a: argparse.Namespace) -> List[str]:
    return ["core"] + [c for c in OPTIONAL if not getattr(a, "no_" + c)]


def preflight(comps: List[str], harness: str, claude_dir: Path) -> List[str]:
    """Problems that stop the install, as messages; an empty list means go."""
    missing = []
    if sys.version_info < (3, 9):
        missing.append("python>=3.9")
    if not pu.which("git"):
        missing.append("git")
    if harness in ("claude", "both") and not pu.which("claude"):
        missing.append("claude(Claude Code CLI)")
    if harness in ("codex", "both") and not pu.which("codex"):
        missing.append("codex(Codex CLI)")
    if "ruflo" in comps:
        missing += [t for t in ("node", "npm") if not pu.which(t)]
    probs = []
    if missing:
        probs.append("Missing: %s. Install them and re-run (this installer never installs system packages)."
                     % " ".join(missing))
    if "ruflo" in comps and (pu.space_free(sys.executable) is None or pu.space_free(claude_dir) is None):
        probs.append(NO_SPACE_RUFLO)
    return probs


def thirdparty(comps: List[str], yes: bool, home: Optional[Path] = None) -> int:
    import dryas_install as di
    table = json.loads((HERE / "components.json").read_text(encoding="utf-8"))
    sel = [c for c in comps if c in table]
    cmds = [argv for c in sel for argv in table[c]["commands"]]
    if cmds:
        print("Third-party installs:")
        for argv in cmds:
            print("  " + " ".join(argv))
        if yes or di.confirm("Run these?"):
            for argv in cmds:
                rc = di.run(argv)
                if rc != 0:
                    print("failed (exit %d): %s" % (rc, " ".join(argv)))
                    return rc
        else:
            print("skipped third-party installs")
    p = Path(home or Path.home()) / ".claude" / "plugins" / "installed_plugins.json"
    try:
        plugins = json.loads(p.read_text(encoding="utf-8")).get("plugins", {})
    except (OSError, ValueError):
        plugins = {}
    for c in sel:
        want, name = table[c]["version"], table[c]["plugin"]
        have = [e.get("version") for e in plugins.get(name, []) if isinstance(e, dict)]
        if want not in have:
            print("warning: %s is %s; Dryas Workflow is tested with %s"
                  % (name, ", ".join(str(h) for h in have) or "not installed", want))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import dryas_install as di
    a = parse(list(sys.argv[1:] if argv is None else argv))
    repo, home = Path(a.repo).resolve(), Path.home()
    cd = home / ".claude"
    comps = components(a)
    if a.uninstall:
        return di.uninstall(cd)
    probs = preflight(comps, a.harness, cd)
    if probs:
        print("\n".join(probs))
        return 1
    if a.preflight_only:
        print("preflight ok")
        return 0
    if not a.dry_run:
        rc = thirdparty(comps, a.yes)
        if rc:
            return rc
    rc = di.install(repo, cd, comps, home=home, force=a.force, dry=a.dry_run, yes=a.yes)
    if rc or a.dry_run:
        return rc
    return 1 if di.verify(cd, comps) else 0
```

- [ ] **Step 5: Delegate from `install/dryas_install.py`** — delete `thirdparty()` and its `thirdparty` subparser/branch from `main`, then make `main` start with:

```python
def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("run", "preflight"):
        import run_cmd
        return run_cmd.main(argv[1:] + (["--preflight-only"] if argv[0] == "preflight" else []))
    ap = argparse.ArgumentParser(prog="dryas_install.py")
```

(the rest of `main` unchanged apart from the removed `thirdparty` parts; `ap.parse_args(argv)` keeps using `argv`).

- [ ] **Step 6: Replace `install/install.sh`**

```sh
#!/bin/sh
# Dryas Workflow installer for macOS, Linux and WSL. Finds Python >= 3.9 and runs install/dryas_install.py.
# Usage: install.sh [--no-jev] [--no-ruflo] [--no-superpowers] [--no-design] [--yes] [--force] [--dry-run]
#                   [--uninstall] [--preflight-only] [--harness claude]   See docs/install.md.
# DRYAS_PYTHON overrides the interpreter.
set -eu
REPO=$(cd "$(dirname "$0")/.." && pwd)
for c in ${DRYAS_PYTHON:-} python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
    exec "$c" "$REPO/install/dryas_install.py" run --repo "$REPO" "$@"
  fi
done
echo "Missing: Python >= 3.9. Install it and re-run (this installer never installs system packages)." >&2
exit 1
```

- [ ] **Step 7: Create `install/install.ps1`**

```powershell
# Dryas Workflow installer for native Windows. Finds Python >= 3.9 and runs install\dryas_install.py.
# Usage: .\install\install.ps1 [--no-jev] [--no-ruflo] [--no-superpowers] [--no-design] [--yes] [--force]
#        [--dry-run] [--uninstall] [--preflight-only] [--harness claude]   See docs\install.md.
# DRYAS_PYTHON overrides the interpreter.
$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo 'install\dryas_install.py'
$candidates = @()
if ($env:DRYAS_PYTHON) { $candidates += ,@($env:DRYAS_PYTHON) }
$candidates += ,@('py', '-3')
$candidates += ,@('python')
$candidates += ,@('python3')
foreach ($c in $candidates) {
  $exe = $c[0]
  $pre = @()
  if ($c.Count -gt 1) { $pre = $c[1..($c.Count - 1)] }
  if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
  & $exe @pre -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>$null
  if ($LASTEXITCODE -eq 0) {
    & $exe @pre $script run --repo $repo @args
    exit $LASTEXITCODE
  }
}
Write-Host 'Missing: Python >= 3.9. Install it and re-run (this installer never installs system packages).'
exit 1
```

- [ ] **Step 8: Run to verify**

Run: `python3 -m pytest -q install/tests && wc -l install/dryas_install.py`
Expected: PASS; line count under 500.

## Task 9: Cross-platform tests, line endings, CI and end-to-end install

Goal: Existing tests pass on Windows, `.gitattributes` fixes line endings, GitHub Actions runs everything on macOS/Ubuntu/Windows, and an end-to-end test installs into a temp home and runs every installed hook command through the real shells.
Scope:
- claude/jev/tests/test_compact.py
- claude/jev/tests/test_context_watch.py
- claude/jev/tests/test_handoff.py
- install/tests/test_ruflo_helpers.py
- install/tests/test_dryas_install.py
- install/tests/test_e2e_install.py
- .gitattributes
- .github/workflows/ci.yml
Done:
- `python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests` passes on macOS.
- After the orchestrator pushes the branch (only with the user's OK), the `ci` workflow is green on all three OSes.
Failing test first: install/tests/test_e2e_install.py :: E2ETest.test_install_hooks_run_and_uninstall

**Interfaces:**
- Consumes: `fakecli` (Task 8); `dryas_install.py run` (Task 8).
- Produces: `.github/workflows/ci.yml` job `test` (matrix `os` × `python`).

- [ ] **Step 1: Write the failing end-to-end test** — create `install/tests/test_e2e_install.py`:

```python
"""End to end: real install into a temp home with a fake `claude`, then run every installed hook command
through the OS shells with a sample event, then uninstall."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fakecli
REPO = HERE.parents[1]
EVENTS = {
    "PreToolUse": {"tool_name": "Write", "tool_input": {"file_path": "notes.txt", "content": "café → ok"}},
    "UserPromptSubmit": {"prompt": ""},
    "SessionStart": {"source": "startup"},
    "PreCompact": {"trigger": "manual"},
}


def shells():
    out = [None]  # None = the OS default shell via shell=True (sh on POSIX, cmd on Windows)
    if os.name == "nt":
        git_bash = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Git", "bin", "bash.exe")
        if os.path.isfile(git_bash):
            out.append(git_bash)
    return out


class E2ETest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.home.mkdir()
        fb = self.tmp / "bin"
        fakecli.make(fb, "claude", self.tmp / "calls.jsonl", outputs={"mcp list": "jev: ok\n"})
        self.env = {k: v for k, v in os.environ.items() if k not in ("OPENROUTER_API_KEY", "DRYAS_DATA_ROOT", "CODEX_HOME")}
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home), PATH=str(fb) + os.pathsep + os.environ["PATH"],
                        JEV_LOG_DIR=str(self.tmp / "logs"), JEV_HANDOFF_DIR=str(self.tmp / "handoff"),
                        JEV_COMPACT_DIR=str(self.tmp / "compact"))

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def installer(self, *args):
        return subprocess.run([sys.executable, str(REPO / "install" / "dryas_install.py"), "run", "--repo", str(REPO),
                               "--yes", "--no-ruflo", "--no-superpowers", "--no-design"] + list(args),
                              capture_output=True, text=True, env=self.env, timeout=900)

    def test_install_hooks_run_and_uninstall(self):
        p = self.installer()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        cd = self.home / ".claude"
        settings = json.loads((cd / "settings.json").read_text(encoding="utf-8"))
        cmds = [(ev, h["command"]) for ev, groups in settings["hooks"].items() for g in groups for h in g["hooks"]]
        self.assertTrue(cmds)
        for ev, cmd in cmds:
            self.assertNotIn("/bin/sh", cmd)
            event = dict(EVENTS.get(ev, {}), hook_event_name=ev, cwd=str(self.tmp), session_id="e2e")
            data = json.dumps(event, ensure_ascii=False).encode("utf-8")
            for sh in shells():
                argv = cmd if sh is None else [sh, "-c", cmd]
                r = subprocess.run(argv, shell=sh is None, input=data, capture_output=True, env=self.env, timeout=120)
                self.assertEqual(r.returncode, 0, "%s via %s: %s" % (cmd, sh or "default shell",
                                                                     r.stderr.decode("utf-8", "replace")))
                out = r.stdout.decode("utf-8", "replace").strip()
                if out:
                    json.loads(out)
        u = self.installer("--uninstall")
        self.assertEqual(u.returncode, 0, u.stdout + u.stderr)
        self.assertFalse((cd / ".dryas-installed.json").exists())
        self.assertFalse((cd / "settings.json").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify** — `python3 -m pytest -q install/tests/test_e2e_install.py`. Expected on macOS: PASS once Tasks 1–8 are in (it is the integration check of Part A). If it fails, the failure names the hook command and shell: fix the cause in the owning file (rendering in `dryas_install.py`, a hook script's stdin handling), not in the test.

- [ ] **Step 3: Make POSIX-only assertions conditional**

- `claude/jev/tests/test_compact.py` (the `S_IMODE(...) == 0o600` assertion near line 127), `claude/jev/tests/test_context_watch.py` (the `0o700` / `0o600` assertions near lines 156–158), `claude/jev/tests/test_handoff.py` (the `0o700` / `0o600` assertions near lines 188–189): wrap each in `if os.name != "nt":` (Windows has no POSIX modes; the `chmod` calls stay in the code).
- `claude/jev/tests/test_handoff.py`: decorate the test that calls `os.symlink(self.cwd, link)` (near line 81) with `@unittest.skipIf(os.name == "nt", "symlinks need admin rights on Windows")`.
- `install/tests/test_ruflo_helpers.py`: decorate class `GenerateTest` with `@unittest.skipIf(os.name == "nt", "fake ruflo binaries are sh scripts")`; decorate `HelperInstallTest.test_patched_output_written_with_mode_and_recorded`, `test_skipped_user_helper_keeps_mode` with `@unittest.skipIf(os.name == "nt", "POSIX file modes")` and `test_dangling_symlink_helper_does_not_crash` with `@unittest.skipIf(os.name == "nt", "symlinks need admin rights on Windows")`.
- `install/tests/test_dryas_install.py`: wrap `self.assertTrue((self.cd / "ruflo/run.sh").stat().st_mode & 0o100)` in `if os.name != "nt":`.

Add `import os` to any of these files that lacks it.

- [ ] **Step 4: Create `.gitattributes`**

```
* text=auto eol=lf
*.ps1 text eol=crlf
*.cmd text eol=crlf
*.png binary
*.jpg binary
```

- [ ] **Step 5: Create `.github/workflows/ci.yml`**

```yaml
name: ci
on:
  push:
  pull_request:
jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [macos-latest, ubuntu-latest, windows-latest]
        python: ["3.9", "3.12"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: python -m pip install pytest
      - run: python -m pytest -q claude/jev/tests install/tests claude/ruflo/tests
      - run: node claude/ruflo/tests/test_ns.cjs
```

If `setup-python` cannot provide 3.9 on `macos-latest` (arm64), add a matrix `exclude` for `{os: macos-latest, python: "3.9"}` and an `include` for `{os: macos-13, python: "3.9"}`.

- [ ] **Step 6: Run locally**

Run: `python3 -m pytest -q claude/jev/tests install/tests claude/ruflo/tests && node claude/ruflo/tests/test_ns.cjs`
Expected: PASS.

- [ ] **Step 7: CI checkpoint (orchestrator, not the executor)** — ask the user before pushing the branch. After the OK: `git push -u origin feat/windows-support`, then `gh run watch` on the `ci` run. Fix Windows-only failures in the task that owns the failing file, then re-run.

---

# Part B — Codex as main harness

## Task 10: Codex event normaliser and harness-aware chain

Goal: `chain.py --harness codex` runs only Codex-enabled stages, splits `apply_patch` into per-file `Write` events (fail closed), and exports `DRYAS_HARNESS`; `route.py` says `escalate:` under Codex.
Scope:
- claude/jev/codex_event.py
- claude/jev/chain.py
- claude/jev/route.py
- claude/jev/chain.json
- claude/jev/tests/test_codex_event.py
- claude/jev/tests/test_chain.py
- claude/jev/tests/test_route.py
- install/tests/test_shipped_files.py
Done:
- `python3 -m pytest -q claude/jev/tests install/tests/test_shipped_files.py` passes.
Failing test first: claude/jev/tests/test_chain.py :: ChainTest.test_codex_patch_outside_worktree_denied_by_real_scope_lock

**Interfaces:**
- Produces (module `codex_event`): `class PatchError(ValueError)`, `patch_text(tool_input) -> str`, `patch_files(patch: str) -> List[Tuple[str, str]]`, `expand(event: dict) -> List[dict]`.
- Produces (module `chain`): `load_stages(kind: str, harness: str = "claude")`, `pretool_codex(event: dict, stages: list) -> Optional[dict]`, CLI `chain.py <pretool|prompt> [--harness claude|codex]`; stages without a `"harness"` key run only for `claude`.
- Produces: `chain.json` stages `scope-lock`, `jev-gate`, `jev-route` carry `"harness": ["claude", "codex"]`.

- [ ] **Step 1: Write the failing tests**

Create `claude/jev/tests/test_codex_event.py`:

```python
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import codex_event as ce

PATCH = ("*** Begin Patch\n*** Update File: src/a.py\n@@\n-x\n+y\n*** Add File: src/b.py\n+new\n"
         "*** Delete File: old.txt\n*** Update File: src/c.py\n*** Move to: lib/c.py\n@@\n-1\n+2\n*** End Patch\n")


class PatchTest(unittest.TestCase):
    def test_headers_in_order_with_move(self):
        files = ce.patch_files(PATCH)
        self.assertEqual([f for f, _ in files], ["src/a.py", "src/b.py", "old.txt", "src/c.py", "lib/c.py"])
        self.assertEqual(files[0][1], "*** Update File: src/a.py\n@@\n-x\n+y")

    def test_crlf_and_spaces_in_path(self):
        files = ce.patch_files("*** Begin Patch\r\n*** Add File: docs/my file.md\r\n+x\r\n*** End Patch\r\n")
        self.assertEqual([f for f, _ in files], ["docs/my file.md"])

    def test_no_headers_raises(self):
        with self.assertRaises(ce.PatchError):
            ce.patch_files("*** Begin Patch\n+x\n*** End Patch\n")
        with self.assertRaises(ce.PatchError):
            ce.patch_files("")

    def test_patch_text_forms(self):
        self.assertEqual(ce.patch_text({"command": "p"}), "p")
        self.assertEqual(ce.patch_text({"input": "p"}), "p")
        self.assertEqual(ce.patch_text({"command": ["apply_patch", "p"]}), "apply_patch\np")
        for bad in ("p", None, {}, {"command": 3}):
            with self.assertRaises(ce.PatchError):
                ce.patch_text(bad)

    def test_expand_apply_patch(self):
        ev = {"tool_name": "apply_patch", "tool_input": {"command": PATCH}, "cwd": "/w", "session_id": "s"}
        out = ce.expand(ev)
        self.assertEqual(len(out), 5)
        self.assertEqual(out[1], {"tool_name": "Write", "tool_input": {"file_path": "src/b.py",
                                  "content": "*** Add File: src/b.py\n+new"}, "cwd": "/w", "session_id": "s"})

    def test_expand_passthrough_and_bash_list(self):
        ev = {"tool_name": "Read", "tool_input": {"file_path": "x"}}
        self.assertEqual(ce.expand(ev), [ev])
        b = ce.expand({"tool_name": "Bash", "tool_input": {"command": ["bash", "-lc", "ls"]}})
        self.assertEqual(b[0]["tool_input"]["command"], "bash -lc ls")


if __name__ == "__main__":
    unittest.main()
```

Add to `ChainTest` in `claude/jev/tests/test_chain.py`:

```python
    SMOKE_PLAN = "## Task 1: a\nGoal: g\nScope:\n- src/feature/**\nDone:\n- d\n"

    def _worktree(self):
        wt = os.path.join(self.tmp, "wt")
        os.makedirs(os.path.join(wt, ".orchestrate"))
        with open(os.path.join(wt, ".orchestrate", "PLAN.md"), "w", encoding="utf-8") as f:
            f.write(self.SMOKE_PLAN)
        with open(os.path.join(wt, ".orchestrate", "active.json"), "w", encoding="utf-8") as f:
            json.dump({"active": ["1"]}, f)
        return wt

    def test_load_stages_filters_by_harness(self):
        cfg = os.path.join(self.tmp, "chain.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"pretool": [{"name": "c", "cmd": ["x"]}, {"name": "both", "cmd": ["x"], "harness": ["claude", "codex"]}]}, f)
        os.environ["JEV_CHAIN_CONFIG"] = cfg
        try:
            self.assertEqual([s["name"] for s in chain.load_stages("pretool")], ["c", "both"])
            self.assertEqual([s["name"] for s in chain.load_stages("pretool", "codex")], ["both"])
        finally:
            del os.environ["JEV_CHAIN_CONFIG"]

    def test_codex_patch_denies_out_of_scope_file(self):
        code = ("import sys,json;e=json.load(sys.stdin);p=e['tool_input']['file_path'];"
                "print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'deny',"
                "'permissionDecisionReason':'out: '+p}}) if p.startswith('out/') else '')")
        patch = "*** Begin Patch\n*** Update File: src/ok.py\n@@\n-a\n+b\n*** Add File: out/bad.py\n+x\n*** End Patch\n"
        ev = {"tool_name": "apply_patch", "tool_input": {"command": patch}, "cwd": self.tmp}
        out = chain.pretool_codex(ev, [stage("lock", code, harness=["claude", "codex"])])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("out/bad.py", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_codex_unparseable_patch_denied(self):
        out = chain.pretool_codex({"tool_name": "apply_patch", "tool_input": {"command": "garbage"}}, [])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("[codex-patch]", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_codex_patch_outside_worktree_denied_by_real_scope_lock(self):
        wt = self._worktree()
        lock = {"name": "scope-lock", "cmd": [sys.executable, os.path.join(HERE, "scope_lock.py")],
                "match": "Edit|Write|MultiEdit|NotebookEdit", "harness": ["claude", "codex"]}
        ok = "*** Begin Patch\n*** Update File: src/feature/a.py\n+x\n*** End Patch\n"
        self.assertIsNone(chain.pretool_codex({"tool_name": "apply_patch", "tool_input": {"command": ok}, "cwd": wt}, [lock]))
        bad = ("*** Begin Patch\n*** Update File: src/feature/a.py\n+x\n"
               "*** Update File: ../../etc/evil\n+y\n*** End Patch\n")
        out = chain.pretool_codex({"tool_name": "apply_patch", "tool_input": {"command": bad}, "cwd": wt}, [lock])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("evil", out["hookSpecificOutput"]["permissionDecisionReason"])
        other = "*** Begin Patch\n*** Add File: src/other.py\n+x\n*** End Patch\n"
        out = chain.pretool_codex({"tool_name": "apply_patch", "tool_input": {"command": other}, "cwd": wt}, [lock])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_main_exports_harness_to_stages(self):
        cfg = os.path.join(self.tmp, "chain.json")
        code = ("import os,sys,json;sys.stdin.read();print(json.dumps({'hookSpecificOutput':{'hookEventName':"
                "'UserPromptSubmit','additionalContext':'h='+os.environ.get('DRYAS_HARNESS','')}}))")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"prompt": [{"name": "p", "cmd": [sys.executable, "-c", code], "harness": ["claude", "codex"]},
                                  {"name": "claude-only", "cmd": [sys.executable, "-c", code.replace("h=", "c=")]}]}, f)
        env = dict(os.environ, JEV_CHAIN_CONFIG=cfg)
        p = subprocess.run([sys.executable, os.path.join(HERE, "chain.py"), "prompt", "--harness", "codex"],
                           input=json.dumps({"prompt": "x"}), capture_output=True, text=True, env=env)
        ctx = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(ctx, "h=codex")
```

Add to `RouteTest` in `claude/jev/tests/test_route.py`:

```python
    def test_codex_wording(self):
        os.environ["DRYAS_HARNESS"] = "codex"
        try:
            self.assertEqual(route.run({"prompt": "build x", "cwd": "/p"}, lambda s, q: answers()),
                             "Jev route: swarm (0.82); escalate: no (0.91)")
        finally:
            del os.environ["DRYAS_HARNESS"]
```

Add to `ShippedFilesTest` in `install/tests/test_shipped_files.py`:

```python
    def test_codex_enabled_stages(self):
        on = {st["name"] for stages in self.chain.values() for st in stages if "codex" in st.get("harness", [])}
        self.assertEqual(on, {"scope-lock", "jev-gate", "jev-route"})
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q claude/jev/tests/test_codex_event.py claude/jev/tests/test_chain.py claude/jev/tests/test_route.py install/tests/test_shipped_files.py`
Expected: FAIL (`No module named 'codex_event'`, `pretool_codex` missing, `opus:` wording, no `harness` keys)

- [ ] **Step 3: Implement `claude/jev/codex_event.py`**

```python
#!/usr/bin/env python3
"""Normalise Codex hook events for the chain (chain.py --harness codex).

Codex sends file edits as tool_name "apply_patch" with the patch text in tool_input.command. Each touched
file becomes one synthetic Write event so the existing stages (scope lock, Jev gate) see a file_path.
A patch that cannot be read raises PatchError; the chain denies it (fail closed).
"""
import re
from typing import Any, Dict, List, Tuple

_HDR = re.compile(r"^\*\*\* (Add File|Update File|Delete File|Move to): (.*\S)\s*$")
_FRAME = ("*** Begin Patch", "*** End Patch", "*** End of File")


class PatchError(ValueError):
    pass


def patch_text(tool_input: Any) -> str:
    if not isinstance(tool_input, dict):
        raise PatchError("tool_input is not an object")
    v = tool_input.get("command", tool_input.get("input", tool_input.get("patch")))
    if isinstance(v, list):
        v = "\n".join(str(x) for x in v)
    if not isinstance(v, str):
        raise PatchError("no patch text")
    return v


def patch_files(patch: str) -> List[Tuple[str, str]]:
    """[(path, hunk text)] in patch order. A move yields both the source and the destination."""
    out: List[Tuple[str, List[str]]] = []
    for line in patch.replace("\r\n", "\n").split("\n"):
        m = _HDR.match(line)
        if m:
            out.append((m.group(2).strip(), [line]))
        elif out and not line.startswith(_FRAME):
            out[-1][1].append(line)
    if not out:
        raise PatchError("no file headers")
    return [(p, "\n".join(h).rstrip("\n")) for p, h in out]


def expand(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Events to run the pretool chain on. Raises PatchError for an unusable apply_patch."""
    tool = event.get("tool_name")
    ti = event.get("tool_input")
    if tool == "Bash" and isinstance(ti, dict) and isinstance(ti.get("command"), list):
        e = dict(event)
        e["tool_input"] = dict(ti, command=" ".join(str(x) for x in ti["command"]))
        return [e]
    if tool != "apply_patch":
        return [event]
    out = []
    for path, hunk in patch_files(patch_text(ti)):
        e = {k: v for k, v in event.items() if k not in ("tool_name", "tool_input")}
        e["tool_name"] = "Write"
        e["tool_input"] = {"file_path": path, "content": hunk}
        out.append(e)
    return out
```

- [ ] **Step 4: Implement the chain changes** in `claude/jev/chain.py`

After `import jevlog` add `import codex_event`. Replace `load_stages` with:

```python
def load_stages(kind: str, harness: str = "claude") -> List[Dict[str, Any]]:
    try:
        with open(config_path(), encoding="utf-8") as f:
            stages = list(json.load(f).get(kind, []))
    except (OSError, ValueError):
        return []
    return [s for s in stages if isinstance(s, dict) and harness in s.get("harness", ["claude"])]
```

Add after `pretool`:

```python
def _deny(reason: str) -> Dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def pretool_codex(event: Dict[str, Any], stages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Codex: run the pretool chain once per touched file; the strictest decision wins."""
    try:
        events = codex_event.expand(event)
    except codex_event.PatchError as e:
        return _deny("[codex-patch] unparseable apply_patch (%s)" % e)
    best: Optional[Dict[str, Any]] = None
    for ev in events:
        out = pretool(ev, json.dumps(ev), stages)
        if out is None:
            continue
        d = out["hookSpecificOutput"]["permissionDecision"]
        if best is None or RANK.get(d, 0) > RANK.get(best["hookSpecificOutput"]["permissionDecision"], 0):
            best = out
    return best


def _harness(argv: List[str]) -> str:
    if "--harness" in argv:
        i = argv.index("--harness")
        if i + 1 < len(argv):
            return argv[i + 1]
    return "claude"
```

In `main`, after `kind = ...` add:

```python
    harness = _harness(argv)
    os.environ["DRYAS_HARNESS"] = harness  # inherited by every stage subprocess
```

and replace the two dispatch branches with:

```python
    if kind == "pretool":
        jevlog.append("calls", {"tool": str(event.get("tool_name", ""))})
        stages = load_stages("pretool", harness)
        out = pretool_codex(event, stages) if harness == "codex" else pretool(event, raw, stages)
    elif kind == "prompt":
        out = prompt(event, raw, load_stages("prompt", harness))
```

- [ ] **Step 5: Route wording** — in `claude/jev/route.py` replace

```python
            parts.append("opus: %s (%.2f)" % ("yes" if float(f["value"]) >= 0.5 else "no", f["confidence"]))
```

with

```python
            label = "escalate" if os.environ.get("DRYAS_HARNESS") == "codex" else "opus"
            parts.append("%s: %s (%.2f)" % (label, "yes" if float(f["value"]) >= 0.5 else "no", f["confidence"]))
```

- [ ] **Step 6: Enable stages for Codex** — in `claude/jev/chain.json` add `"harness": ["claude", "codex"]` to the `scope-lock`, `jev-gate` and `jev-route` stage objects (no other changes).

- [ ] **Step 7: Run to verify**

Run: `python3 -m pytest -q claude/jev/tests install/tests/test_shipped_files.py`
Expected: PASS

## Task 11: Shared block helper and Codex templates

Goal: Generalise the marker-block helper (any file, any markers) and add the Codex templates: `AGENTS.md` block, five skills, hooks fragment.
Scope:
- install/claude_md_block.py
- install/tests/test_claude_md_block.py
- codex/**
- install/tests/test_codex_templates.py
Done:
- `python3 -m pytest -q install/tests` passes.
Failing test first: install/tests/test_claude_md_block.py :: BlockTest.test_custom_markers

**Interfaces:**
- Produces (module `claude_md_block`): `insert_block(p: Path, body: str, rec: dict, key: str, start: str = START, end: str = END) -> None`, `remove_block(p: Path, rec: dict, key: str, start: str = START, end: str = END) -> None`; record keys `<key>`, `<key>_created`, `<key>_sep`. `claude_md` / `remove_claude_md` keep working with key `claude_md`.
- Produces files: `codex/AGENTS.md.template`, `codex/hooks.fragment.json`, `codex/skills/{orchestrate,wreview,wplan,commit,tune}/SKILL.md` (tokens `{{PY}}`, `{{CD}}` only).

- [ ] **Step 1: Write the failing tests**

Create `install/tests/test_claude_md_block.py`:

```python
import shutil, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import claude_md_block as cmb


class BlockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def test_insert_into_missing_then_remove_deletes_file(self):
        p, rec = self.tmp / "AGENTS.md", {}
        cmb.insert_block(p, "rules →", rec, "agents_md")
        self.assertEqual(p.read_text(encoding="utf-8"), cmb.START + "\nrules →\n" + cmb.END + "\n")
        cmb.remove_block(p, rec, "agents_md")
        self.assertFalse(p.exists())

    def test_existing_content_roundtrip(self):
        p, rec = self.tmp / "AGENTS.md", {}
        p.write_text("MINE\n", encoding="utf-8")
        cmb.insert_block(p, "v1", rec, "agents_md")
        cmb.insert_block(p, "v2", rec, "agents_md")
        t = p.read_text(encoding="utf-8")
        self.assertEqual(t.count(cmb.START), 1)
        self.assertIn("v2", t)
        cmb.remove_block(p, rec, "agents_md")
        self.assertEqual(p.read_text(encoding="utf-8"), "MINE\n")

    def test_custom_markers(self):
        p, rec = self.tmp / "config.toml", {}
        p.write_text('model = "x"\n', encoding="utf-8")
        cmb.insert_block(p, "[mcp_servers.jev]", rec, "toml", "# >>> a >>>", "# <<< a <<<")
        self.assertIn("# >>> a >>>\n[mcp_servers.jev]\n# <<< a <<<\n", p.read_text(encoding="utf-8"))
        cmb.remove_block(p, rec, "toml", "# >>> a >>>", "# <<< a <<<")
        self.assertEqual(p.read_text(encoding="utf-8"), 'model = "x"\n')

    def test_claude_md_wrappers_keep_record_keys(self):
        rec = {}
        cmb.claude_md(self.tmp, "P", rec)
        self.assertTrue(rec["claude_md"])
        self.assertTrue(rec["claude_md_created"])
        cmb.remove_claude_md(self.tmp, rec)
        self.assertFalse((self.tmp / "CLAUDE.md").exists())


if __name__ == "__main__":
    unittest.main()
```

Create `install/tests/test_codex_templates.py`:

```python
import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import settings_merge as sm
CODEX = Path(__file__).resolve().parents[2] / "codex"
SKILLS = ("orchestrate", "wreview", "wplan", "commit", "tune")
M = {"PY": "/p", "CD": "/c", "PY_SAFE": "/ps", "CD_SAFE": "/cs"}


class CodexTemplatesTest(unittest.TestCase):
    def test_skills(self):
        for n in SKILLS:
            t = (CODEX / "skills" / n / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(t.startswith("---\nname: %s\ndescription: " % n), n)
            for banned in ("mcp__", "Agent tool", "/usr/bin/python3", "subagent_type", "Fable"):
                self.assertNotIn(banned, t, (n, banned))
            sm.render_tokens(t, M)  # only known tokens
        self.assertFalse((CODEX / "skills" / "handoff").exists())

    def test_agents_template_small(self):
        t = sm.render_tokens((CODEX / "AGENTS.md.template").read_text(encoding="utf-8"), M)
        self.assertLess(len(t.encode("utf-8")), 8 * 1024)
        self.assertIn("$orchestrate", t)

    def test_hooks_fragment(self):
        r = sm.render(json.loads((CODEX / "hooks.fragment.json").read_text(encoding="utf-8")), M)
        pre = r["hooks"]["PreToolUse"][0]
        self.assertEqual(pre["matcher"], "Bash|apply_patch|Edit|Write")
        self.assertEqual(pre["hooks"][0]["command"], '"/p" -X utf8 "/c/jev/chain.py" pretool --harness codex')
        self.assertEqual(pre["hooks"][0]["commandWindows"], "/ps -X utf8 /cs/jev/chain.py pretool --harness codex")
        ups = r["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        self.assertEqual(ups["command"], '"/p" -X utf8 "/c/jev/chain.py" prompt --harness codex')
        self.assertEqual(ups["commandWindows"], "/ps -X utf8 /cs/jev/chain.py prompt --harness codex")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q install/tests/test_claude_md_block.py install/tests/test_codex_templates.py`
Expected: FAIL (`insert_block` missing; `codex/` missing)

- [ ] **Step 3: Implement `install/claude_md_block.py`** (replace the file):

```python
"""Insert / remove one marker-delimited block in a text file, recording exactly what was added.
Used for ~/.claude/CLAUDE.md, ~/.codex/AGENTS.md and the Codex config.toml fallback."""
import re
from pathlib import Path

START, END = "<!-- dryas:start -->", "<!-- dryas:end -->"


def _pattern(start: str, end: str) -> str:
    return re.escape(start) + r".*?" + re.escape(end) + r"\n?"


def insert_block(p: Path, body: str, rec: dict, key: str, start: str = START, end: str = END) -> None:
    block = start + "\n" + body.strip() + "\n" + end + "\n"
    if not p.exists():
        rec[key + "_created"] = True
        text = ""
    else:
        rec.setdefault(key + "_created", False)
        text = p.read_text(encoding="utf-8")
    if start in text and end in text:
        new = re.sub(_pattern(start, end), lambda m: block, text, count=1, flags=re.S)
    else:
        sep = ""
        if text and not text.endswith("\n\n"):
            sep = "\n" if text.endswith("\n") else "\n\n"
        rec[key + "_sep"] = sep
        new = text + sep + block
    if new != text:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(new, encoding="utf-8")
    rec[key] = True


def remove_block(p: Path, rec: dict, key: str, start: str = START, end: str = END) -> None:
    if not rec.get(key) or not p.exists():
        return
    text = p.read_text(encoding="utf-8")
    body = _pattern(start, end)
    sep = rec.get(key + "_sep", "")
    new, n = re.subn(re.escape(sep) + body, "", text, count=1, flags=re.S) if sep else (text, 0)
    if not n:
        new = re.sub(body, "", text, count=1, flags=re.S)
    if rec.get(key + "_created") and not new.strip():
        p.unlink()
    elif new != text:
        p.write_text(new, encoding="utf-8")


def claude_md(cd: Path, template_text: str, rec: dict) -> None:
    insert_block(cd / "CLAUDE.md", template_text, rec, "claude_md")


def remove_claude_md(cd: Path, rec: dict) -> None:
    remove_block(cd / "CLAUDE.md", rec, "claude_md")
```

- [ ] **Step 4: Create `codex/hooks.fragment.json`**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|apply_patch|Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "\"$PY\" -X utf8 \"$CD/jev/chain.py\" pretool --harness codex",
            "commandWindows": "$PY_SAFE -X utf8 $CD_SAFE/jev/chain.py pretool --harness codex",
            "timeout": 20
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$PY\" -X utf8 \"$CD/jev/chain.py\" prompt --harness codex",
            "commandWindows": "$PY_SAFE -X utf8 $CD_SAFE/jev/chain.py prompt --harness codex",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 5: Create `codex/AGENTS.md.template`**

```markdown
# Dryas Workflow (Codex)
Process rules for coding sessions on this machine. Full reference: `{{CD}}/docs/dryas-workflow.md`.

## Always
- Brainstorm first: before new work, clarify intent and get the user's approval of a design (use Superpowers' brainstorming skill if it is installed).
- Multi-step work runs in its own git worktree; merge only after review and verification.
- Plans are files: `.orchestrate/PLAN.md` in the worktree, sections `## Task N:` with Goal, Scope (globs), Done and Failing test first. Never commit `.orchestrate/`.
- Test first. Never claim a pass you did not see.
- Review before merge: spec compliance first, then code quality (`$wreview`).
- Commit only after review, as Conventional Commits; never push without asking.
- Do what was asked, nothing more. Read a file before editing it. Never commit secrets or `.env` files.

## Skills
`$orchestrate` (multi-step tasks), `$wplan` (write a plan), `$wreview` (two-stage review), `$commit` (Jev-gated commit), `$tune` (weekly Jev calibration).

## Jev and Ruflo (MCP servers `jev` and `ruflo`)
- Jev answers narrow typed questions only (`jev_judge`); it never writes code or plans. When it is below threshold, escalates or is unavailable, you decide; log any disagreement with `log_override`.
- Models: start a task on a cheaper model and move to a stronger one when it fails. Log every step with `log_escalation` (task, reason, decided_by, from_model, to_model).
- Ruflo is the memory: `memory_search` before a task, `memory_store` after success; namespace = the main repo's folder name.
- Hooks enforce the scope lock (while `.orchestrate/active.json` exists, edits outside the active tasks' Scope are denied), the Jev gate on risky commands, and a Jev route hint on each prompt.
- On Windows PowerShell, put `& ` before a command that starts with a quoted path.

## Not available in Codex
Context-window warnings, compaction handoff, `$handoff` and the Ruflo hooks run only in Claude Code.
```

- [ ] **Step 6: Create the five skills**

`codex/skills/orchestrate/SKILL.md`:

```markdown
---
name: orchestrate
description: Run a multi-step coding task with a plan file, scope-locked workers, Jev routing and gates, and Ruflo memory. Use for $orchestrate or any multi-file task. Not for single-file fixes.
---

# Orchestrate (Codex)

0. **Brainstorm first.** Plan only from a design the user approved.
1. **Memory.** Call `memory_search` (server `ruflo`, namespace = main repo folder name) for similar tasks. Write the top 3 as `Past: <what worked> / <what failed>`, or say none were found.
2. **Plan as a file.** Create a git worktree for the work (`git worktree add ../<repo>-<topic> -b <branch>`). Write `.orchestrate/PLAN.md` there, one section per task:

   ```
   ## Task <N>: <title>
   Goal: <one sentence>
   Scope:
   - <glob relative to worktree root>
   Done:
   - <verifiable criterion, incl. test command>
   Failing test first: <test file :: test name>
   ```

   Tasks that may run in parallel must not have overlapping scopes. Never commit `.orchestrate/`.
3. **Ask Jev per task.** Call `jev_judge` (server `jev`) with state `{task_section, test_file_exists, last_test_run_tail, past_outcomes}` and questions `specific` (noul: is the task specific enough to finish without questions?), `failing_test_exists` (noul) and `needs_stronger_model` (noul: cross-cutting refactor, concurrency- or security-sensitive code?). Each question's `instructions` must stand alone and name state fields in backticks. Below threshold or unavailable: you decide; when you differ from Jev, call `log_override`.
4. **Test first.** If a failing test does not confidently exist, get it written and failing for the right reason before any implementation.
5. **Dispatch.** Write `.orchestrate/active.json` = `{"active": [<task ids>]}`; this arms the scope-lock hook. Delete it on every exit path. Give each worker only its own section: `"{{PY}}" -X utf8 "{{CD}}/jev/planfile.py" section .orchestrate/PLAN.md <N>` (PowerShell: prefix `& `) plus the absolute worktree path. Use Codex sub-agents when available (independent tasks in parallel); otherwise do the tasks yourself, one at a time. Workers start on a cheaper model; `needs_stronger_model` or your judgment picks the stronger one, after `log_escalation`.
6. **On return.** Check each Done criterion against the report. A failure is retried once on the same model, then moved to the stronger model (`log_escalation` with task, reason, decided_by, from_model, to_model). If the strongest model fails too, stop and report to the user. Store each outcome with `memory_store`.
7. **Finish.** Delete `.orchestrate/active.json`, run `$wreview`, verify (run the tests and read the output), then `$commit`. Merge locally with `git merge --no-ff` only after review and verification; never push; remove the worktree. Name the harness (Codex) and the models used in the plan and the commit body.
```

`codex/skills/wreview/SKILL.md`:

```markdown
---
name: wreview
description: Two-stage review (spec compliance, then code quality) of the current branch or worktree diff. Use for $wreview before any merge.
---

Review the diff from the given base ref (default: the merge-base with the default branch) to HEAD.

1. **Spec compliance.** Compare against `.orchestrate/PLAN.md` or the named plan or spec. List every requirement that is missing, partial or wrong.
2. **Code quality.** Correctness bugs first, then error handling, tests and readability. Check each finding against the code before reporting it.

Report findings ranked by severity with file:line. Change nothing unless asked. If Superpowers' requesting-code-review skill is installed, follow it.
```

`codex/skills/wplan/SKILL.md`:

```markdown
---
name: wplan
description: Write an implementation plan for an approved design, in the plan-file format that $orchestrate runs. Use for $wplan.
---

Use Superpowers' writing-plans skill if it is installed. The plan uses `## Task N:` sections with Goal, Scope (globs), Done and Failing test first, so `$orchestrate` can run it task by task. Save it under the project's `docs/plans/` (or `docs/superpowers/plans/` if the project uses that). When it is written, hand off to `$orchestrate` with the plan path.
```

`codex/skills/commit/SKILL.md`:

```markdown
---
name: commit
description: Conventional commit gated by a secret scan and a Jev "safe to commit?" check. Never pushes. Use for $commit.
---

1. Run `git status --short` and `git diff --cached --stat`. If nothing is staged, stage the named files only; never `git add -A`, never stage `.env*` or other secrets.
2. **Secret scan.** Stop if any staged path (`git diff --cached --name-only`) matches, case-insensitive, `(^|/)\.env($|\.)`, `\.pem$`, `\.key$`, `\.p12$`, `id_rsa`, `id_ed25519`, `credentials`, `\.keychain` or `secrets?\.(json|ya?ml|toml)$`. Then search `git diff --cached -U0` for `sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\.` and stop on any hit (report file and line; never print the secret).
3. Call `jev_judge` (server `jev`) with state `{branch, staged_files, diff_stat, last_test_run_tail, secret_scan: "clean"}` and one noul question `safe_to_commit`: "Is this staged change safe and coherent to commit as one commit?"
4. Commit if the confidence is at least `commit.min_confidence` in `{{CD}}/jev/thresholds.json` and the value is at least 0.5. If Jev is confident it is unsafe, stop and say why. Otherwise you decide; if you commit against Jev's answer, call `log_override`.
5. Message: Conventional Commits (`type(scope): summary`); the body explains why and names the harness (Codex). Never push.
```

`codex/skills/tune/SKILL.md`:

```markdown
---
name: tune
description: Weekly Jev calibration - override rates, judged share, escalations and spend; propose threshold changes for the user to approve. Use for $tune.
---

1. Run `"{{PY}}" -X utf8 "{{CD}}/jev/tune.py" report` (PowerShell: prefix `& `).
2. Present the report and each proposal with its reason. Ask the user to approve or reject each one separately.
3. For each approved proposal only, run `"{{PY}}" -X utf8 "{{CD}}/jev/tune.py" apply <key> '<json value>'`. Never apply anything unapproved.
4. Show the final `{{CD}}/jev/thresholds.json`.
```

- [ ] **Step 7: Run to verify**

Run: `python3 -m pytest -q install/tests`
Expected: PASS

## Task 12: Codex installer target and `--harness`

Goal: `install --harness codex|both` installs the AGENTS.md block, skills, hooks and MCP servers for Codex, recorded for exact uninstall; Jev files are installed once under the Claude directory and shared.
Scope:
- install/codex_target.py
- install/run_cmd.py
- install/dryas_install.py
- install/install.sh
- install/install.ps1
- install/tests/test_codex_target.py
- install/tests/test_run_cmd.py
Done:
- `python3 -m pytest -q install/tests` passes.
- `wc -l install/dryas_install.py install/codex_target.py` both under 500.
Failing test first: install/tests/test_codex_target.py :: CodexTargetTest.test_install_creates_everything

**Interfaces:**
- Consumes: `insert_block`/`remove_block` (Task 11), `sm.render`, `sm.render_tokens`, `sm.merge`, `sm.unmerge`, `sm.load_settings` (Task 2), `codex/` templates (Task 11), `di.install`, `di.verify`, `di.uninstall`, `di.run`, `di.capture` (Tasks 6–8).
- Produces (module `codex_target`):
  - `RECORD = ".dryas-installed.json"`, `SKILLS = ("orchestrate", "wreview", "wplan", "commit", "tune")`, `TOML_START`, `TOML_END`
  - `codex_dir() -> Path` (`$CODEX_HOME` or `~/.codex`), `skills_dir(home: Path) -> Path` (`<home>/.agents/skills`)
  - `servers(comps, mapping, ruflo_env) -> Dict[str, Tuple[str, List[str], Dict[str, str]]]`
  - `install_codex(repo, cdx, home, comps, mapping, ruflo_env, run, force=False, dry=False) -> int`
  - `uninstall_codex(cdx, home, run) -> int`
  - `verify_codex(cdx, home, comps, capture, cd) -> int` (number of failures)
- `dryas_install.install(..., claude: bool = True)`: `claude=False` copies files only (no CLAUDE.md block, no settings, no `claude mcp add`).
- `dryas_install.mapping_for(comps, home, cd) -> Dict[str, str]`, `dryas_install.ruflo_env(repo, mapping) -> Dict[str, str]`.
- `run_cmd.HARNESSES = ("claude", "codex", "both")`.

- [ ] **Step 1: Write the failing tests** — create `install/tests/test_codex_target.py`:

```python
import io, json, os, shutil, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import codex_target as ct
REPO = Path(__file__).resolve().parents[2]
PY = sys.executable.replace("\\", "/")


class CodexTargetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.cdx = self.home / ".codex"
        self.cd = self.home / ".claude"
        self.cd.mkdir(parents=True)
        self.calls = []
        self.rc = 0
        self.mapping = {"PY": PY, "CD": str(self.cd).replace("\\", "/"), "PY_SAFE": PY, "CD_SAFE": str(self.cd).replace("\\", "/"),
                        "HOME": str(self.home).replace("\\", "/"), "DRYAS_DATA_ROOT": "/d"}
        self.ruflo_env = {"DRYAS_DATA_ROOT": "/d", "RUFLO_JS": "/r.js", "RUFLO_NO_AUTO_ENABLE": "1"}

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def run_fake(self, argv):
        self.calls.append(argv)
        return self.rc

    def install(self, comps=("core", "jev", "ruflo"), **kw):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = ct.install_codex(REPO, self.cdx, self.home, list(comps), self.mapping, self.ruflo_env, self.run_fake, **kw)
        return rc, buf.getvalue()

    def uninstall(self):
        with redirect_stdout(io.StringIO()):
            return ct.uninstall_codex(self.cdx, self.home, self.run_fake)

    def test_install_creates_everything(self):
        rc, out = self.install()
        self.assertEqual(rc, 0)
        agents = (self.cdx / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("<!-- dryas:start -->", agents)
        self.assertLess(len(agents.encode("utf-8")), 8 * 1024)
        for n in ct.SKILLS:
            t = (ct.skills_dir(self.home) / n / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("{{", t)
        hooks = json.loads((self.cdx / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("--harness codex", hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"])
        self.assertIn(["codex", "mcp", "add", "jev", "--", PY, "-X", "utf8", self.mapping["CD"] + "/jev/jev_mcp.py"], self.calls)
        ruflo = [c for c in self.calls if c[:4] == ["codex", "mcp", "add", "ruflo"]][0]
        self.assertIn("DRYAS_DATA_ROOT=/d", ruflo)
        self.assertEqual(ruflo[-3:], [self.mapping["CD"] + "/ruflo/mcp-shim/bin/cli.js", "mcp", "start"])
        rec = json.loads((self.cdx / ct.RECORD).read_text(encoding="utf-8"))
        self.assertEqual(rec["mcp"], {"jev": "cli", "ruflo": "cli"})

    def test_reinstall_is_idempotent(self):
        self.install()
        snap = {p: p.read_bytes() for p in self.home.rglob("*") if p.is_file() and p.name != ct.RECORD}
        self.calls.clear()
        self.install()
        self.assertEqual({p: p.read_bytes() for p in self.home.rglob("*") if p.is_file() and p.name != ct.RECORD}, snap)
        self.assertEqual([c for c in self.calls if c[:3] == ["codex", "mcp", "add"]], [])

    def test_uninstall_restores_user_files_byte_identical(self):
        self.cdx.mkdir(parents=True)
        user = {"AGENTS.md": "MINE\n", "config.toml": 'model = "x"\n',
                "hooks.json": json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]}}, indent=2) + "\n"}
        for n, t in user.items():
            (self.cdx / n).write_text(t, encoding="utf-8")
        self.rc = 1  # codex mcp add fails -> TOML fallback
        self.install()
        self.assertIn(ct.TOML_START, (self.cdx / "config.toml").read_text(encoding="utf-8"))
        self.uninstall()
        for n, t in user.items():
            self.assertEqual((self.cdx / n).read_text(encoding="utf-8"), t, n)
        self.assertFalse((self.cdx / ct.RECORD).exists())
        for n in ct.SKILLS:
            self.assertFalse((ct.skills_dir(self.home) / n).exists())

    def test_toml_fallback_block(self):
        self.rc = 1
        self.install(("core", "jev"))
        t = (self.cdx / "config.toml").read_text(encoding="utf-8")
        self.assertIn("[mcp_servers.jev]", t)
        self.assertIn("command = %s" % json.dumps(PY), t)
        self.assertIn('args = ["-X", "utf8", %s]' % json.dumps(self.mapping["CD"] + "/jev/jev_mcp.py"), t)
        self.uninstall()
        self.assertFalse((self.cdx / "config.toml").exists())

    def test_user_mcp_table_kept(self):
        self.cdx.mkdir(parents=True)
        (self.cdx / "config.toml").write_text('[mcp_servers.jev]\ncommand = "mine"\n', encoding="utf-8")
        self.rc = 1
        rc, out = self.install(("core", "jev"))
        t = (self.cdx / "config.toml").read_text(encoding="utf-8")
        self.assertEqual(t.count("[mcp_servers.jev]"), 1)
        self.assertIn("kept your [mcp_servers.jev]", out)
        self.assertEqual([c for c in self.calls if c[:3] == ["codex", "mcp", "add"]], [])

    def test_existing_skill_kept_without_force_and_restored_after_force(self):
        mine = ct.skills_dir(self.home) / "commit" / "SKILL.md"
        mine.parent.mkdir(parents=True)
        mine.write_text("MINE", encoding="utf-8")
        rc, out = self.install()
        self.assertEqual(mine.read_text(encoding="utf-8"), "MINE")
        self.assertIn("kept your skill", out)
        self.install(force=True)
        self.assertNotEqual(mine.read_text(encoding="utf-8"), "MINE")
        self.uninstall()
        self.assertEqual(mine.read_text(encoding="utf-8"), "MINE")

    def test_superpowers_hint(self):
        rc, out = self.install()
        self.assertIn("Superpowers was not found for Codex", out)
        shutil.rmtree(str(self.home))
        self.cd.mkdir(parents=True)
        (ct.skills_dir(self.home) / "brainstorming").mkdir(parents=True)
        rc, out = self.install()
        self.assertNotIn("Superpowers was not found", out)

    def test_dry_run_writes_nothing(self):
        before = sorted(str(p) for p in self.home.rglob("*"))
        rc, out = self.install(dry=True)
        self.assertEqual(sorted(str(p) for p in self.home.rglob("*")), before)
        self.assertEqual(self.calls, [])

    def test_codex_home_env(self):
        os.environ["CODEX_HOME"] = str(self.tmp / "ch")
        try:
            self.assertEqual(ct.codex_dir(), self.tmp / "ch")
        finally:
            del os.environ["CODEX_HOME"]


if __name__ == "__main__":
    unittest.main()
```

Add to `RunCmdTest` in `install/tests/test_run_cmd.py`:

```python
    def test_harness_choices(self):
        self.assertEqual(run_cmd.parse(["--harness", "both"]).harness, "both")
        with self.assertRaises(SystemExit):
            run_cmd.parse(["--harness", "nope"])

    def test_preflight_codex_needs_codex_cli_only(self):
        pu.which = lambda n: "" if n in ("codex", "claude") else "/bin/" + n
        pu.space_free = lambda p: str(p)
        self.assertIn("codex", run_cmd.preflight(["core"], "codex", Path("/x/.claude"))[0])
        self.assertNotIn("claude(", run_cmd.preflight(["core"], "codex", Path("/x/.claude"))[0])

    def test_preflight_codex_hooks_space_refused_on_windows(self):
        pu.which = lambda n: "/bin/" + n
        pu.space_free = lambda p: None
        orig = pu.IS_WINDOWS
        pu.IS_WINDOWS = True
        try:
            probs = run_cmd.preflight(["core"], "codex", Path("/x/Ana Silva/.claude"))
        finally:
            pu.IS_WINDOWS = orig
        self.assertTrue(any("--harness claude" in p for p in probs), probs)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q install/tests/test_codex_target.py install/tests/test_run_cmd.py`
Expected: FAIL (`No module named 'codex_target'`; `--harness both` rejected)

- [ ] **Step 3: Implement `install/codex_target.py`**

```python
"""Codex target: AGENTS.md block, skills, hooks.json entries and MCP servers, recorded for exact uninstall.

Record: <codex dir>/.dryas-installed.json. The Jev code itself lives in the Claude directory (installed by
dryas_install.install, with claude=False when only Codex is selected) and is shared by both harnesses.
"""
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import settings_merge as sm
from claude_md_block import insert_block, remove_block

RECORD = ".dryas-installed.json"
SKILLS = ("orchestrate", "wreview", "wplan", "commit", "tune")
TOML_START, TOML_END = "# >>> dryas-workflow >>>", "# <<< dryas-workflow <<<"
RUFLO_ENV_KEYS = ("DRYAS_DATA_ROOT", "RUFLO_JS", "RUFLO_NO_AUTO_ENABLE", "RUFLO_DAEMON_AUTOSTART", "RUFLO_MCP_SKIP_NPX",
                  "CLAUDE_FLOW_MEMORY_PATH", "CLAUDE_FLOW_DB_PATH", "CLAUDE_FLOW_SWARM_DIR", "RUFLO_STATE_DIR")
SP_HINT = ("Superpowers was not found for Codex. Install it with the Codex steps in the Superpowers README "
           "(https://github.com/obra/superpowers); this installer does not fetch it.")
Server = Tuple[str, List[str], Dict[str, str]]


def codex_dir() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))


def skills_dir(home: Path) -> Path:
    return Path(home) / ".agents" / "skills"


def _load(cdx: Path) -> dict:
    p = cdx / RECORD
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"skills": [], "skill_backups": {}, "hooks": {"hooks": []}, "mcp": {}, "toml_servers": {}}


def _save(cdx: Path, rec: dict) -> None:
    (cdx / RECORD).write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")


def servers(comps: List[str], mapping: Dict[str, str], ruflo_env: Dict[str, str]) -> Dict[str, Server]:
    out: Dict[str, Server] = {}
    if "jev" in comps:
        out["jev"] = (mapping["PY"], ["-X", "utf8", mapping["CD"] + "/jev/jev_mcp.py"], {})
    if "ruflo" in comps:
        out["ruflo"] = ("node", [mapping["CD"] + "/ruflo/mcp-shim/bin/cli.js", "mcp", "start"],
                        {k: ruflo_env[k] for k in RUFLO_ENV_KEYS if k in ruflo_env})
    return out


def _q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)  # a JSON string is a valid TOML basic string


def toml_body(srv: Dict[str, list]) -> str:
    lines: List[str] = []
    for name, (cmd, args, env) in sorted(srv.items()):
        lines += ["[mcp_servers.%s]" % name, "command = %s" % _q(cmd), "args = [%s]" % ", ".join(_q(a) for a in args)]
        if env:
            lines.append("env = { %s }" % ", ".join("%s = %s" % (k, _q(v)) for k, v in env.items()))
        lines.append("")
    return "\n".join(lines).strip()


def _user_has_table(text: str, name: str) -> bool:
    outside = re.sub(re.escape(TOML_START) + r".*?" + re.escape(TOML_END), "", text, flags=re.S)
    return re.search(r"^\s*\[mcp_servers\.%s\]" % re.escape(name), outside, re.M) is not None


def _ts() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def install_codex(repo: Path, cdx: Path, home: Path, comps: List[str], mapping: Dict[str, str],
                  ruflo_env: Dict[str, str], run: Callable[[List[str]], int], force: bool = False,
                  dry: bool = False) -> int:
    repo, cdx, home = Path(repo), Path(cdx), Path(home)
    srv = servers(comps, mapping, ruflo_env)
    if dry:
        print("would add or update the Dryas block in %s" % (cdx / "AGENTS.md"))
        print("would install Codex skills into %s: %s" % (skills_dir(home), ", ".join(SKILLS)))
        print("would merge Codex hooks into %s" % (cdx / "hooks.json"))
        for name in srv:
            print("would register the %s MCP server for Codex" % name)
        return 0
    rec = _load(cdx)
    if not cdx.exists():
        cdx.mkdir(parents=True)
        rec.setdefault("dir_created", True)
    rec.setdefault("dir_created", False)
    tpl = (repo / "codex" / "AGENTS.md.template").read_text(encoding="utf-8")
    insert_block(cdx / "AGENTS.md", sm.render_tokens(tpl, mapping), rec, "agents_md")
    sd = skills_dir(home)
    for name in SKILLS:
        dest = sd / name
        mine = name in rec["skills"]
        if dest.exists() and not mine:
            if not force:
                print("kept your skill: %s (use --force to replace, original is backed up)" % dest)
                continue
            b = cdx / (".dryas-backup-" + _ts()) / "skills" / name
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest), str(b))
            rec["skill_backups"][name] = str(b)
        dest.mkdir(parents=True, exist_ok=True)
        text = (repo / "codex" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        (dest / "SKILL.md").write_text(sm.render_tokens(text, mapping), encoding="utf-8")
        if not mine:
            rec["skills"].append(name)
    if "core" in comps:
        frag = sm.render(json.loads((repo / "codex" / "hooks.fragment.json").read_text(encoding="utf-8")), mapping)
        hp = cdx / "hooks.json"
        rec.setdefault("hooks_created", not hp.exists())
        cur = sm.load_settings(hp)
        merged, added, _ = sm.merge(cur, frag)
        if merged != cur:
            hp.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        rec["hooks"]["hooks"] += [h for h in added["hooks"] if h not in rec["hooks"]["hooks"]]
    cfg = cdx / "config.toml"
    text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    fallback: Dict[str, list] = {}
    for name, (cmd, args, env) in srv.items():
        if name in rec["mcp"]:
            continue
        if _user_has_table(text, name):
            print("kept your [mcp_servers.%s] in %s" % (name, cfg))
            continue
        argv = ["codex", "mcp", "add", name]
        for k, v in env.items():
            argv += ["--env", "%s=%s" % (k, v)]
        if run(argv + ["--", cmd] + args) == 0:
            rec["mcp"][name] = "cli"
        else:
            fallback[name] = [cmd, args, env]
    if fallback:
        rec["toml_servers"].update(fallback)
        insert_block(cfg, toml_body(rec["toml_servers"]), rec, "toml", TOML_START, TOML_END)
        for name in fallback:
            rec["mcp"][name] = "toml"
            print("registered %s in %s (codex mcp add was not available)" % (name, cfg))
    if not any((sd / n).exists() for n in ("superpowers", "brainstorming")):
        print(SP_HINT)
    _save(cdx, rec)
    print("installed the Codex target into %s" % cdx)
    return 0


def uninstall_codex(cdx: Path, home: Path, run: Callable[[List[str]], int]) -> int:
    cdx, home = Path(cdx), Path(home)
    if not (cdx / RECORD).exists():
        return 0
    rec = _load(cdx)
    remove_block(cdx / "AGENTS.md", rec, "agents_md")
    sd = skills_dir(home)
    for name in rec.get("skills", []):
        shutil.rmtree(str(sd / name), ignore_errors=True)
        b = rec.get("skill_backups", {}).get(name)
        if b and os.path.exists(b):
            shutil.move(b, str(sd / name))
    for d in (sd, sd.parent):
        if d.is_dir() and not os.listdir(str(d)):
            d.rmdir()
    hp = cdx / "hooks.json"
    if hp.exists():
        cur = sm.load_settings(hp)
        new = sm.unmerge(cur, rec.get("hooks", {}))
        if rec.get("hooks_created") and new == {}:
            hp.unlink()
        elif new != cur:
            hp.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
    for name, how in rec.get("mcp", {}).items():
        if how == "cli":
            run(["codex", "mcp", "remove", name])
    if rec.get("toml"):
        remove_block(cdx / "config.toml", rec, "toml", TOML_START, TOML_END)
    for bd in cdx.glob(".dryas-backup-*"):
        shutil.rmtree(str(bd), ignore_errors=True)
    (cdx / RECORD).unlink()
    if rec.get("dir_created") and cdx.is_dir() and not os.listdir(str(cdx)):
        cdx.rmdir()
    print("uninstalled the Codex target")
    return 0


SMOKE_PLAN = "## Task 1: a\nGoal: g\nScope:\n- src/feature/**\nDone:\n- d\n"


def verify_codex(cdx: Path, home: Path, comps: List[str], capture: Callable, cd: Path) -> int:
    fails = 0

    def say(ok: bool, name: str, detail: str = "") -> int:
        print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  (" + detail + ")") if detail else ""))
        return 0 if ok else 1

    rec = _load(cdx)
    fails += say("<!-- dryas:start -->" in ((cdx / "AGENTS.md").read_text(encoding="utf-8") if (cdx / "AGENTS.md").exists() else ""),
                 "Codex AGENTS.md block")
    missing = [n for n in rec.get("skills", []) if not (skills_dir(home) / n / "SKILL.md").exists()]
    fails += say(not missing, "Codex skills present", ", ".join(missing))
    cli = [n for n, how in rec.get("mcp", {}).items() if how == "cli"]
    if cli:
        rc, out = capture(["codex", "mcp", "list"])
        absent = [n for n in cli if n not in out]
        fails += say(not absent, "Codex MCP servers registered", ", ".join(absent))
    if "core" in comps:
        wt = Path(tempfile.mkdtemp())
        try:
            (wt / ".orchestrate").mkdir()
            (wt / ".orchestrate" / "PLAN.md").write_text(SMOKE_PLAN, encoding="utf-8")
            (wt / ".orchestrate" / "active.json").write_text(json.dumps({"active": ["1"]}), encoding="utf-8")
            patch = "*** Begin Patch\n*** Add File: src/other.ts\n+x\n*** End Patch\n"
            event = {"tool_name": "apply_patch", "tool_input": {"command": patch}, "cwd": str(wt)}
            env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_API_KEY"}
            env["JEV_LOG_DIR"] = str(wt / "logs")
            rc, out = capture([sys.executable, "-X", "utf8", str(Path(cd) / "jev" / "chain.py"), "pretool", "--harness", "codex"],
                              json.dumps(event), env)
            try:
                ok = json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
            except (ValueError, KeyError, TypeError):
                ok = False
            fails += say(ok, "Codex scope lock blocks an out-of-scope apply_patch")
        finally:
            shutil.rmtree(str(wt), ignore_errors=True)
    return fails
```

- [ ] **Step 4: `dryas_install.py` additions**

`install` gains `claude: bool = True` (last parameter). When `claude` is false, skip the CLAUDE.md block (both the dry-run message and `claude_md(...)`), `apply_settings(...)`, and the `claude mcp add` block; file copying, helpers, data root and the record are unchanged. Add:

```python
def mapping_for(comps: List[str], home: Path, cd: Path) -> Dict[str, str]:
    return _mapping(comps, home, cd)


def ruflo_env(repo: Path, mapping: Dict[str, str]) -> Dict[str, str]:
    return _fragment(repo, ["ruflo"], mapping).get("env", {})
```

- [ ] **Step 5: `run_cmd.py` harness wiring**

Set `HARNESSES = ("claude", "codex", "both")` and add the constant:

```python
NO_SPACE_CODEX = ("On Windows, Codex hooks need a Python and Claude folder path without spaces (or with an 8.3 "
                  "short name). Re-run with --harness claude, or install Python to a path without spaces.")
```

At the end of `preflight`, before `return probs`:

```python
    if harness in ("codex", "both") and pu.IS_WINDOWS and \
            (pu.space_free(sys.executable) is None or pu.space_free(claude_dir) is None):
        probs.append(NO_SPACE_CODEX)
```

Replace `main` with:

```python
def main(argv: Optional[List[str]] = None) -> int:
    import codex_target as ct
    import dryas_install as di
    a = parse(list(sys.argv[1:] if argv is None else argv))
    repo, home = Path(a.repo).resolve(), Path.home()
    cd = home / ".claude"
    comps = components(a)
    want_claude, want_codex = a.harness in ("claude", "both"), a.harness in ("codex", "both")
    if a.uninstall:
        rc = ct.uninstall_codex(ct.codex_dir(), home, di.run)
        return rc or di.uninstall(cd)
    probs = preflight(comps, a.harness, cd)
    if probs:
        print("\n".join(probs))
        return 1
    if a.preflight_only:
        print("preflight ok")
        return 0
    if want_claude and not a.dry_run:
        rc = thirdparty(comps, a.yes)
        if rc:
            return rc
    rc = di.install(repo, cd, comps, home=home, force=a.force, dry=a.dry_run, yes=a.yes, claude=want_claude)
    if rc:
        return rc
    if want_codex:
        mapping = di.mapping_for(comps, home, cd)
        renv = di.ruflo_env(repo, mapping) if "ruflo" in comps else {}
        rc = ct.install_codex(repo, ct.codex_dir(), home, comps, mapping, renv, di.run, force=a.force, dry=a.dry_run)
        if rc:
            return rc
    if a.dry_run:
        return 0
    fails = di.verify(cd, comps) if want_claude else 0
    if want_codex:
        fails += ct.verify_codex(ct.codex_dir(), home, comps, di.capture, cd)
    return 1 if fails else 0
```

- [ ] **Step 6: Wrapper usage lines** — in `install/install.sh` and `install/install.ps1` change `[--harness claude]` in the usage comment to `[--harness claude|codex|both]`.

- [ ] **Step 7: Run to verify**

Run: `python3 -m pytest -q install/tests && wc -l install/dryas_install.py install/codex_target.py`
Expected: PASS; both files under 500 lines.

## Task 13: Documentation

Goal: Users can install on Windows, WSL and with Codex from the docs alone; nothing in the docs still points at removed shell scripts.
Scope:
- docs/install.md
- docs/harnesses.md
- docs/workflow.md
- README.md
Done:
- `grep -rn "run.sh\|cli.sh\|ns.sh\|pretool-chain.sh\|/usr/bin/python3" docs README.md` finds nothing (except history notes that say the scripts were removed).
- `python3 -m pytest -q install/tests` still passes.
Failing test first: none (documentation only; the grep in Done is the check).

**Interfaces:** none.

- [ ] **Step 1: `docs/install.md`** — add, after the existing macOS/Linux steps:

````markdown
## Windows (native)

Prerequisites: Python 3.9 or newer (python.org installer or `winget install Python.Python.3.12`), Git for Windows, Node.js 20+ (for Ruflo), and the Claude Code and/or Codex CLI.

```powershell
git clone https://github.com/promprit/dryas-workflow.git
cd dryas-workflow
.\install\install.ps1
```

If PowerShell refuses to run scripts: `powershell -ExecutionPolicy Bypass -File .\install\install.ps1`.
If your user folder or Python path contains a space and Windows has no short (8.3) name for it, Ruflo and the Codex hooks cannot be installed; the installer says so and suggests `--no-ruflo` / `--harness claude`.

## WSL

Inside WSL, follow the Linux steps (`./install/install.sh`). WSL and native Windows installs are separate: each has its own home folder.

## Codex

`--harness codex` installs for Codex only, `--harness both` for Claude Code and Codex. For Codex the installer adds a rules block to `~/.codex/AGENTS.md` (or `$CODEX_HOME`), the skills `$orchestrate`, `$wplan`, `$wreview`, `$commit` and `$tune` to `~/.agents/skills`, the scope-lock / Jev gate / Jev route hooks to `~/.codex/hooks.json`, and the `jev` and `ruflo` MCP servers (via `codex mcp add`, or a marked block in `config.toml`). Superpowers for Codex is not installed; the installer tells you if it is missing.
````

Also replace every `./install/install.sh` usage line that lists flags so it includes `--harness claude|codex|both`, and change the Jev-tests note to say the tests run with the Python the installer was started with.

- [ ] **Step 2: `docs/harnesses.md`** — replace the Codex section with:

```markdown
## Codex

Supported: rules, skills, MCP, and the safety and routing hooks. Install with `--harness codex` or `--harness both` (see [install.md](install.md)).

Codex gets: the `AGENTS.md` rules block; the skills `$orchestrate`, `$wplan`, `$wreview`, `$commit`, `$tune`; the scope lock (including `apply_patch` edits, which are checked file by file and denied when the patch cannot be read), the Jev gate and the Jev route hint (`escalate: yes/no` instead of `opus: yes/no`); the `jev` and `ruflo` MCP servers.

Claude Code only: context-window warnings, compaction keep/restore, `/handoff`, the Ruflo hooks, the `executor` agent and the Sonnet → Opus → Fable ladder, FlowObserve. In Codex, use its own sub-agents and models: cheaper first, stronger on failure, every step logged with `log_escalation`.
```

- [ ] **Step 3: `docs/workflow.md`** — in §4 (executor section command), §6 (Jev tests command) and §7 (Ruflo wrapper): replace `/usr/bin/python3 $HOME/.claude/jev/planfile.py` with `python -X utf8 ~/.claude/jev/planfile.py` (rendered with the installer's interpreter), and `~/.claude/ruflo/run.sh` with `~/.claude/ruflo/run.py`. In §16 replace the Codex bullets with a pointer to `docs/harnesses.md` and the one-line summary "Codex: rules, skills, MCP and the scope-lock / Jev gate / Jev route hooks are installed by `--harness codex`."

- [ ] **Step 4: `README.md`** — add under the title: `![ci](https://github.com/promprit/dryas-workflow/actions/workflows/ci.yml/badge.svg)`; in the install section add the Windows line `.\install\install.ps1` and a sentence: "Works on macOS, Linux, WSL and Windows, with Claude Code and Codex (`--harness codex|both`)."

- [ ] **Step 5: Check**

Run: `grep -rn "run.sh\|cli.sh\|ns.sh\|pretool-chain.sh\|/usr/bin/python3" docs README.md; python3 -m pytest -q install/tests`
Expected: grep prints nothing (or only lines that say a script was removed); tests PASS.

## Task 14: Source-of-truth switch (manual, after merge — orchestrator with the user)

Goal: The repo becomes the source of truth for `claude/`; the maintainer's Mac installs from the repo; the export pipeline no longer overwrites repo-owned paths.
Scope:
- (none in the worktree — runs after merge, outside the repo; not dispatched to an executor)
Done:
- `~/.claude/release/export.py` no longer syncs `claude/` paths that the repo owns (the deny-term and secret scans still run).
- `~/.claude/.dryas-installed.json` exists; Claude Code on the Mac starts with the new hooks and `/wreview`, `/orchestrate`, `/handoff` work.
- `~/.claude/DryasWorkflow.md` and its backup `$DEV_ROOT/docs/DryasWorkflow.md` updated (§5 hook commands, §10 where things live, §16 harnesses) and identical.
Failing test first: none (manual).

- [ ] **Step 1:** Show the user the planned edit to `~/.claude/release/export.py` (stop staging `claude/` into the clone; keep the scans) and apply it only after their OK.
- [ ] **Step 2:** With the user's OK, back up `~/.claude` (`cp -a ~/.claude ~/.claude.bak-<date>`), then run `./install/install.sh --force` from the merged repo. `--force` backs up every replaced file under `~/.claude/.dryas-backup-<ts>/`.
- [ ] **Step 3:** Start a fresh Claude Code session; confirm the Jev route line appears on a prompt and the scope lock denies an out-of-scope write in a test worktree.
- [ ] **Step 4:** Update both copies of `DryasWorkflow.md` and confirm `diff` shows them identical.
- [ ] **Step 5:** Release check from the spec, by the maintainer or a tester: native Windows (Claude Code and Codex) and WSL — hooks fire, the Jev route line appears, Ruflo memory lands under the data root, Codex `apply_patch` outside scope is denied.
