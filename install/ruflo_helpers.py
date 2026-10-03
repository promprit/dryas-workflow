"""Generate the Ruflo helper files with a sandboxed `ruflo init`, then apply pinned local patches (ruflo 3.51.0)."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

HELPERS = ("auto-memory-hook.mjs", "hook-handler.cjs", "intelligence.cjs", "memory.cjs", "router.cjs", "session.cjs")
INIT_FLAGS = ["init", "--only-claude", "--no-global", "--no-mods", "--no-plugin-install", "--no-skills-sh",
              "--no-signup", "--no-codex-detect"]
INIT_TIMEOUT = 300
HINT = " (patches are pinned to ruflo 3.51.0; install that version or use --no-ruflo)"

PATCHES = [
    ("hook-handler.cjs",
     "function spawnDetachedHookRefresh(subcommand) {\n",
     "function spawnDetachedHookRefresh(subcommand) {\n"
     "  return; // LIFT PATCH: never spawn npx/CLI from a hook (unpinned, uncontrolled). Funnel/advisor refresh disabled.\n"),
    ("hook-handler.cjs",
     "function firstRunAutoEnableIfEligible() {\n",
     "function firstRunAutoEnableIfEligible() {\n"
     "  return; // LIFT PATCH: first-run auto-enable spawns npx/CLI and writes ~/.ruflo; disabled.\n"),
    ("intelligence.cjs",
     "const DATA_DIR = path.join(PROJECT_ROOT, '.claude-flow', 'data');\n",
     "// RUFLO_DATA_ROOT (set by ~/.claude/ruflo/run.sh): keep data off the project tree; PROJECT_ROOT still identifies the project.\n"
     "const DATA_ROOT = process.env.RUFLO_DATA_ROOT ? path.resolve(process.env.RUFLO_DATA_ROOT) : PROJECT_ROOT;\n"
     "const DATA_DIR = path.join(DATA_ROOT, '.claude-flow', 'data');\n"),
    ("intelligence.cjs",
     "const SESSION_DIR = path.join(PROJECT_ROOT, '.claude-flow', 'sessions');\n",
     "const SESSION_DIR = path.join(DATA_ROOT, '.claude-flow', 'sessions');\n"),
    ("auto-memory-hook.mjs",
     "const DATA_DIR = join(PROJECT_ROOT, '.claude-flow', 'data');\n",
     "// RUFLO_DATA_ROOT (set by ~/.claude/ruflo/run.sh): keep data off the project tree.\n"
     "const DATA_ROOT = process.env.RUFLO_DATA_ROOT ? resolve(process.env.RUFLO_DATA_ROOT) : PROJECT_ROOT;\n"
     "const DATA_DIR = join(DATA_ROOT, '.claude-flow', 'data');\n"),
]


class HelperError(Exception):
    pass


def init_argv(ruflo_bin: str) -> List[str]:
    return [ruflo_bin] + INIT_FLAGS


def patch_text(name: str, text: str, strict: bool = True) -> str:
    """Apply the file's patches. Each anchor must occur at most once; strict also demands exactly once
    (non-strict still raises if none of the file's anchors is found)."""
    mine = [(old, new) for f, old, new in PATCHES if f == name]
    counts = [text.count(old) for old, _ in mine]
    for (old, _), n in zip(mine, counts):
        if n > 1 or (n == 0 and (strict or not any(counts))):
            raise HelperError("%s: patch anchor must occur exactly once (found %d): %r%s" % (name, n, old, HINT))
    for (old, new), n in zip(mine, counts):
        if n:
            text = text.replace(old, new)
    return text


def generate(ruflo_bin: str) -> Dict[str, Tuple[bytes, int]]:
    """Run `ruflo init` in a temp sandbox; return {name: (bytes, mode)}."""
    if not ruflo_bin:
        raise HelperError("ruflo binary not found; cannot generate the Ruflo helpers")
    t = Path(tempfile.mkdtemp())
    try:
        (t / "home").mkdir()
        (t / "proj").mkdir()
        env = dict(os.environ, HOME=str(t / "home"), RUFLO_NO_SKILLS_SH="1", RUFLO_NO_AUTO_ENABLE="1",
                   RUFLO_DAEMON_AUTOSTART="0")
        try:
            r = subprocess.run(init_argv(ruflo_bin), cwd=str(t / "proj"), env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=INIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise HelperError("ruflo init timed out after %d s" % INIT_TIMEOUT)
        except OSError as e:
            raise HelperError("could not run %s: %s" % (ruflo_bin, e))
        if r.returncode != 0:
            tail = "\n".join((r.stderr or b"").decode("utf-8", errors="replace").splitlines()[-10:])
            raise HelperError("ruflo init failed (exit %d)%s" % (r.returncode, ": " + tail if tail else ""))
        out = {}
        for n in HELPERS:
            p = t / "proj" / ".claude" / "helpers" / n
            if not p.is_file():
                raise HelperError("ruflo init did not produce helper %s" % n)
            out[n] = (p.read_bytes(), p.stat().st_mode & 0o777)
        return out
    finally:
        shutil.rmtree(str(t), ignore_errors=True)


def patched_helpers(ruflo_bin: str) -> Dict[str, Tuple[bytes, int]]:
    """Generate and patch all helpers; raises HelperError before anything is written."""
    gen = generate(ruflo_bin)
    out = {}
    for n in HELPERS:
        if n not in gen:
            raise HelperError("generator did not produce helper %s" % n)
        data, mode = gen[n]
        out[n] = (patch_text(n, data.decode("utf-8"), strict=True).encode("utf-8"), mode)
    return out


def check(hdir: Path) -> List[str]:
    """Problems with the installed helpers (empty list = all present and patched)."""
    probs = []
    for n in HELPERS:
        p = Path(hdir) / n
        if not p.is_file():
            probs.append("%s missing" % n)
            continue
        text = p.read_text(errors="replace")
        for f, _, new in PATCHES:
            if f == n and new not in text:
                probs.append("%s not patched" % n)
                break
    return probs
