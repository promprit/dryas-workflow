"""Installer entry used by install.sh and install.ps1: flags, preflight, then thirdparty -> install -> verify.

  dryas_install.py run [--repo PATH] [--no-jev] [--no-ruflo] [--no-superpowers] [--no-design] [--no-pstack-picks]
                       [--yes] [--force] [--dry-run] [--uninstall] [--preflight-only] [--harness claude|codex|both]
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Optional

import platform_util as pu

HERE = Path(__file__).resolve().parent
OPTIONAL = ("jev", "ruflo", "superpowers", "design", "pstack-picks")
HARNESSES = ("claude", "codex", "both")
NO_SPACE_RUFLO = ("Your Python or Claude folder path contains a space and has no short form; "
                  "Ruflo's hook override cannot handle that. Re-run with --no-ruflo.")


NO_SPACE_CODEX = ("On Windows, Codex hooks need a Python and Claude folder path without spaces (or with an 8.3 "
                  "short name). Re-run with --harness claude, or install Python to a path without spaces.")


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
    return ["core"] + [c for c in OPTIONAL if not getattr(a, "no_" + c.replace("-", "_"))]


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
    if harness in ("codex", "both") and pu.IS_WINDOWS and \
            (pu.space_free(sys.executable) is None or pu.space_free(claude_dir) is None):
        probs.append(NO_SPACE_CODEX)
    return probs


def _vtuple(v) -> Optional[tuple]:
    """Dotted numeric version as an int tuple (a leading 'v' or 'skill-v' is stripped); None if unparseable."""
    m = re.fullmatch(r"(?:skill-)?v?(\d+(?:\.\d+)*)", str(v).strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def thirdparty(comps: List[str], yes: bool, home: Optional[Path] = None, table_path: Optional[Path] = None) -> int:
    import dryas_install as di
    table = json.loads(Path(table_path or HERE / "components.json").read_text(encoding="utf-8"))
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


def main(argv: Optional[List[str]] = None) -> int:
    import codex_target as ct
    import dryas_install as di
    a = parse(list(sys.argv[1:] if argv is None else argv))
    repo, home = Path(a.repo).resolve(), Path.home()
    cd = home / ".claude"
    comps = components(a)
    want_claude, want_codex = a.harness in ("claude", "both"), a.harness in ("codex", "both")
    if a.harness == "codex" and not a.uninstall and ("superpowers" in comps or "design" in comps):
        print("note: superpowers and design are Claude Code plugins; skipped for Codex.")
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
