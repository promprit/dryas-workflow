"""Installer entry used by install.sh and install.ps1: flags, preflight, then migrate -> setup -> codex -> verify.

  dryas_install.py run [--repo PATH] [--no-jev] [--no-ruflo] [--no-superpowers] [--no-design] [--no-pstack-picks]
                       [--yes] [--force] [--dry-run] [--uninstall] [--purge] [--preflight-only] [--harness claude|codex|both]
                       [--claude-dir DIR] [--flowobserve] [--openrouter-key KEY]

Claude Code: the dryas plugin in one config dir (--claude-dir, else $CLAUDE_CONFIG_DIR, else ~/.claude); a copy
install found there is migrated first. Codex: a runtime-only copy in ~/.claude plus ~/.codex.
--harness claude --uninstall touches only that config dir.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Sequence

import platform_util as pu

HERE = Path(__file__).resolve().parent
OPTIONAL = ("jev", "ruflo", "superpowers", "design", "pstack-picks")
HARNESSES = ("claude", "codex", "both")
NO_SPACE_RUFLO = ("Your Python, Dryas data folder or Dryas plugin path contains a space and has no short form; "
                  "Ruflo's hook override cannot handle that. Re-run with --no-ruflo.")


NO_SPACE_CODEX = ("On Windows, Codex hooks need a Python and Claude folder path without spaces (or with an 8.3 "
                  "short name). Re-run with --harness claude, or install Python to a path without spaces.")


def parse(argv: List[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="install")
    ap.add_argument("--repo", default=str(HERE.parent))
    for c in OPTIONAL:
        ap.add_argument("--no-" + c, action="store_true")
    for f in ("yes", "force", "dry-run", "uninstall", "preflight-only", "flowobserve", "purge"):
        ap.add_argument("--" + f, action="store_true")
    ap.add_argument("--harness", default="claude", choices=HARNESSES)
    ap.add_argument("--claude-dir", default=None)
    ap.add_argument("--openrouter-key", default="")  # explicit only: it reaches the `claude plugin install` argv
    return ap.parse_args(argv)


def components(a: argparse.Namespace) -> List[str]:
    return ["core"] + [c for c in OPTIONAL if not getattr(a, "no_" + c.replace("-", "_"))]


def preflight(comps: List[str], harness: str, claude_dir: Path, ruflo_paths: Sequence[Path] = ()) -> List[str]:
    """Problems that stop the install, as messages; an empty list means go.
    claude_dir: the Codex runtime copy (~/.claude); ruflo_paths: more paths Ruflo's hook override names (the plugin)."""
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
    if "ruflo" in comps:
        root = Path(os.environ.get("DRYAS_DATA_ROOT") or Path.home() / ".dryas")
        if any(pu.space_free(p) is None for p in [sys.executable, root] + list(ruflo_paths)):
            probs.append(NO_SPACE_RUFLO)
    if harness in ("codex", "both") and pu.IS_WINDOWS and \
            (pu.space_free(sys.executable) is None or pu.space_free(claude_dir) is None):
        probs.append(NO_SPACE_CODEX)
    return probs


def _vtuple(v) -> Optional[tuple]:
    """Dotted numeric version as an int tuple (a leading 'v' or 'skill-v' is stripped); None if unparseable."""
    m = re.fullmatch(r"(?:skill-)?v?(\d+(?:\.\d+)*)", str(v).strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def thirdparty(comps: List[str], yes: bool, claude_dir: Path, env: Optional[dict] = None,
               table_path: Optional[Path] = None) -> int:
    """Install third-party tools into `claude_dir` (env carries its CLAUDE_CONFIG_DIR); warn on untested versions.
    superpowers is a plugin dependency now: no commands, only the version check."""
    import dryas_install as di
    table = json.loads(Path(table_path or HERE / "components.json").read_text(encoding="utf-8"))
    sel = [c for c in comps if c in table]
    cmds = [argv for c in sel if c != "superpowers" for argv in table[c]["commands"]]
    if cmds:
        print("Third-party installs:")
        for argv in cmds:
            print("  " + " ".join(argv))
        if yes or di.confirm("Run these?"):
            for argv in cmds:
                rc = di.run(argv, env=env)
                if rc != 0:
                    print("failed (exit %d): %s" % (rc, " ".join(argv)))
                    return rc
        else:
            print("skipped third-party installs")
    p = Path(claude_dir) / "plugins" / "installed_plugins.json"
    try:
        plugins = json.loads(p.read_text(encoding="utf-8")).get("plugins", {})
    except (OSError, ValueError):
        plugins = {}
    for c in sel:
        want, name = table[c].get("plugin_tested", table[c]["tested"]), table[c]["plugin"]
        have = [e.get("version") for e in plugins.get(name, []) if isinstance(e, dict)]
        if not have:
            print("warning: %s is not installed; Dryas Workflow is tested with %s" % (name, want))
            continue
        nums = [_vtuple(h) for h in have]
        wt = _vtuple(want)
        if wt is not None and all(nums) and max(nums) < wt:
            print("warning: %s is %s; Dryas Workflow is tested with %s (older than tested)"
                  % (name, ", ".join(str(h) for h in have), want))
    return 0


def _codex_record_comps(cdx: Path) -> Optional[List[str]]:
    """Components of an existing Codex install (None when there is none)."""
    import codex_target as ct
    p = Path(cdx) / ct.RECORD
    if not p.exists():
        return None
    try:
        comps = json.loads(p.read_text(encoding="utf-8")).get("components", [])
    except (OSError, ValueError, AttributeError):
        comps = []
    return sorted(set(["core"] + [str(c) for c in comps if isinstance(c, str)]))


def _codex(repo: Path, copy_cd: Path, home: Path, comps: List[str], a: argparse.Namespace) -> int:
    """The Codex side: runtime-only copy in copy_cd, then ~/.codex."""
    import codex_target as ct
    import dryas_install as di
    rc = di.install(repo, copy_cd, comps, home=home, force=a.force, dry=a.dry_run, yes=a.yes, claude=False)
    if rc:
        return rc
    mapping = di.mapping_for(comps, home, copy_cd)
    renv = di.ruflo_env(repo, mapping) if "ruflo" in comps else {}
    return ct.install_codex(repo, ct.codex_dir(), home, comps, mapping, renv, di.run, force=a.force, dry=a.dry_run)


def main(argv: Optional[List[str]] = None) -> int:
    import codex_target as ct
    import dryas_install as di
    import migrate
    import plugin_setup as ps
    a = parse(list(sys.argv[1:] if argv is None else argv))
    repo, home = Path(a.repo).resolve(), Path.home()
    cd = ps.claude_dir(a.claude_dir)
    copy_cd = home / ".claude"  # Codex reads its runtime copy here (unchanged)
    comps = components(a)
    codex_cmp = ps.norm(copy_cd)  # cd is resolved; compare like with like (symlinked or 8.3 homes)
    want_claude, want_codex = a.harness in ("claude", "both"), a.harness in ("codex", "both")
    if a.harness == "codex" and not a.uninstall and ("superpowers" in comps or "design" in comps):
        print("note: superpowers and design are Claude Code plugins; skipped for Codex.")
    if a.uninstall:
        rc = ct.uninstall_codex(ct.codex_dir(), home, di.run) if want_codex else 0
        rc = rc or (di.uninstall(copy_cd) if want_codex else 0)
        return rc or (ps.uninstall(cd, a.purge) if want_claude else 0)
    if want_claude and (cd / di.RECORD).exists():
        try:
            if not isinstance(di.load_record(cd), dict):
                raise ValueError("not a JSON object")
        except (OSError, ValueError) as e:
            print("error: %s cannot be read (%s); fix or remove it and re-run (nothing changed)" % (cd / di.RECORD, e))
            return 1
    copy_install = want_claude and migrate.is_copy_install(cd)
    # migrating ~/.claude removes the runtime files an existing Codex install uses: put them back afterwards
    keep_codex = None
    if copy_install and not want_codex and pu.same_path(cd, codex_cmp):
        keep_codex = _codex_record_comps(ct.codex_dir())
    ruflo_paths = ([repo / "claude", cd] if want_claude else []) + \
        ([copy_cd] if want_codex or keep_codex is not None else [])
    # a kept Codex is reinstalled too: run its checks (codex CLI, Windows path spaces)
    probs = preflight(sorted(set(comps) | set(keep_codex or [])), "both" if keep_codex is not None else a.harness,
                      copy_cd, ruflo_paths)
    if probs:
        print("\n".join(probs))
        return 1
    if a.preflight_only:
        print("preflight ok")
        return 0
    if copy_install and a.dry_run:
        print("would migrate the copy install in %s" % cd)
    elif copy_install:
        rc = migrate.migrate(cd, ps.data_root())
        if rc:
            return rc
    if want_claude:
        rc = ps.setup(repo, cd, comps, yes=a.yes, key=a.openrouter_key, flowobserve=a.flowobserve, dry=a.dry_run)
        if rc:
            if copy_install and not a.dry_run:
                print("Your copy install was migrated (state is in %s); plugin setup failed. Fix the error above "
                      "and re-run install.sh to finish." % ps.data_root())
                if want_codex or keep_codex is not None:  # Codex must not be left without its files
                    _codex(repo, copy_cd, home, comps if want_codex else keep_codex, a)
            return rc
    if want_codex:
        rc = _codex(repo, copy_cd, home, comps, a)
        if rc:
            return rc
    elif keep_codex is not None and not a.dry_run:
        rc = _codex(repo, copy_cd, home, keep_codex, a)
        if rc:
            return rc
        print("Codex keeps working: its runtime copy in %s was reinstalled after the migration." % copy_cd)
    if a.dry_run:
        return 0
    fails = ps.verify(cd, comps) if want_claude else 0
    if want_codex or keep_codex is not None:
        fails += ct.verify_codex(ct.codex_dir(), home, comps if want_codex else keep_codex, di.capture, copy_cd)
    return 1 if fails else 0
