"""Installer entry used by install.sh and install.ps1: flags, preflight, then codex -> migrate -> setup -> verify.

  dryas_install.py run [--repo PATH] [--no-jev] [--no-ruflo] [--no-superpowers] [--no-design] [--no-pstack-picks]
                       [--yes] [--force] [--dry-run] [--uninstall] [--purge] [--preflight-only] [--harness claude|codex|both]
                       [--claude-dir DIR] [--codex-dir DIR] [--flowobserve|--no-flowobserve] [--openrouter-key KEY]

Claude Code: the dryas plugin in one config dir (--claude-dir, else $CLAUDE_CONFIG_DIR, else ~/.claude); a copy
install found there is migrated first. Codex: the dryas plugin in one CODEX_HOME (--codex-dir, else $CODEX_HOME,
else ~/.codex); a Codex copy install found there is migrated.
--uninstall touches only that config dir / CODEX_HOME; --purge also removes the data root once no account uses it.
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
LEGACY_REFUSAL = ("A Codex copy install (%s) uses %s; run install.sh --harness both (install.ps1 on Windows) to move "
                  "Claude Code and Codex to their plugins. If you no longer use Codex, remove its copy install first "
                  "with install.sh --uninstall --harness codex (Claude Code is not touched), then re-run. Nothing changed.")
NO_PYTHON3 = "Codex runs the Dryas hooks with python3: install Python 3.9+ as python3 and re-run."
NO_PYTHON_WIN = ("warning: `python` is not on PATH; on Windows Codex runs the Dryas hooks with `python` "
                 "(install Python 3.9+ from python.org and tick \"Add python.exe to PATH\").")


def parse(argv: List[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="install")
    ap.add_argument("--repo", default=str(HERE.parent))
    for c in OPTIONAL:
        ap.add_argument("--no-" + c, action="store_true")
    for f in ("yes", "force", "dry-run", "uninstall", "preflight-only", "purge"):
        ap.add_argument("--" + f, action="store_true")
    fo = ap.add_mutually_exclusive_group()  # tri-state: None keeps the setting, True on, False off
    fo.add_argument("--flowobserve", dest="flowobserve", action="store_const", const=True, default=None)
    fo.add_argument("--no-flowobserve", dest="flowobserve", action="store_const", const=False)
    ap.add_argument("--harness", default="claude", choices=HARNESSES)
    ap.add_argument("--claude-dir", default=None)
    ap.add_argument("--codex-dir", default=None)
    ap.add_argument("--openrouter-key", default="")  # explicit only: it reaches the `claude plugin install` argv
    return ap.parse_args(argv)


def components(a: argparse.Namespace) -> List[str]:
    return ["core"] + [c for c in OPTIONAL if not getattr(a, "no_" + c.replace("-", "_"))]


def codex_version() -> Optional[tuple]:
    """`codex --version` as an int tuple; None when it does not run or prints no version."""
    import codex_plugin_setup as cps
    import dryas_install as di
    rc, out = di.capture(["codex", "--version"], timeout=60)
    return cps.codex_version(out) if rc == 0 else None


def preflight(comps: List[str], harness: str, claude_dir: Path, ruflo_paths: Sequence[Path] = ()) -> List[str]:
    """Problems that stop the install, as messages; an empty list means go.
    claude_dir: the Claude config dir (unused by the checks); ruflo_paths: more paths Ruflo's hook override names."""
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
        root = Path(os.path.expanduser(os.environ.get("DRYAS_DATA_ROOT") or str(Path.home() / ".dryas")))
        if any(pu.space_free(p) is None for p in [sys.executable, root] + list(ruflo_paths)):
            probs.append(NO_SPACE_RUFLO)
    if harness in ("codex", "both") and pu.which("codex"):
        import codex_plugin_setup as cps
        ver, want = codex_version(), cps.MIN_CODEX
        if ver is None or ver < want:
            probs.append("Dryas needs Codex CLI %s or newer (found: %s). Update it (npm install -g @openai/codex) and "
                         "re-run." % (".".join(map(str, want)), ".".join(map(str, ver)) if ver else "no version"))
    if harness in ("codex", "both"):
        import codex_plugin_setup as cps
        if pu.IS_WINDOWS:
            if not pu.which("python"):
                print(NO_PYTHON_WIN)
        elif not cps.python3_ok():
            probs.append(NO_PYTHON3)
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


def main(argv: Optional[List[str]] = None) -> int:
    import codex_plugin_setup as cps
    import codex_target as ct
    import dryas_install as di
    import migrate
    import plugin_setup as ps
    a = parse(list(sys.argv[1:] if argv is None else argv))
    repo, home = Path(a.repo).resolve(), Path.home()
    cd = ps.claude_dir(a.claude_dir)
    comps = components(a)
    want_claude, want_codex = a.harness in ("claude", "both"), a.harness in ("codex", "both")
    cdx = cps.codex_home(a.codex_dir)
    legacy = cps.legacy_components(cdx)
    no_flags = not any(getattr(a, "no_" + c.replace("-", "_")) for c in OPTIONAL)
    codex_comps = legacy if (legacy is not None and no_flags) else comps
    if a.harness == "codex" and not a.uninstall and ("superpowers" in comps or "design" in comps):
        print("note: superpowers and design are Claude Code plugins; skipped for Codex.")
    if a.uninstall:  # Codex first: Claude's --purge then sees whether a CODEX_HOME still uses the data root
        rc = cps.uninstall(cdx) if want_codex else 0
        if rc:
            return rc
        if want_claude:
            return ps.uninstall(cd, a.purge)
        if a.purge:
            ps.purge_shared()
        return 0
    if want_claude and (cd / di.RECORD).exists():
        try:
            if not isinstance(di.load_record(cd), dict):
                raise ValueError("not a JSON object")
        except (OSError, ValueError) as e:
            print("error: %s cannot be read (%s); fix or remove it and re-run (nothing changed)" % (cd / di.RECORD, e))
            return 1
    copy_install = want_claude and migrate.is_copy_install(cd)
    # migrating ~/.claude would pull the runtime files a legacy Codex copy install runs: move both together instead
    if copy_install and not want_codex and legacy is not None and pu.same_path(cd, ps.norm(home / ".claude")):
        print(LEGACY_REFUSAL % (cdx / ct.RECORD, cd))
        return 1
    if want_codex and a.openrouter_key:
        print("note: --openrouter-key is not used for Codex; Codex reads OPENROUTER_API_KEY from your shell.")
    probs = preflight(sorted(set(comps) | set(codex_comps if want_codex else [])), a.harness, cd,
                      [repo / "claude", cd] if want_claude else [])
    if probs:
        print("\n".join(probs))
        return 1
    if a.preflight_only:
        print("preflight ok")
        return 0
    if want_codex:
        rc = cps.setup(repo, cdx, codex_comps, yes=a.yes, dry=a.dry_run)
        if rc:
            return rc
    if want_claude:
        if copy_install and a.dry_run:
            print("would migrate the copy install in %s" % cd)
        elif copy_install:
            rc = migrate.migrate(cd, ps.data_root())
            if rc:
                return rc
        rc = ps.setup(repo, cd, comps, yes=a.yes, key=a.openrouter_key, flowobserve=a.flowobserve, dry=a.dry_run)
        if rc:
            if copy_install and not a.dry_run:
                print("Your copy install was migrated (state is in %s); plugin setup failed. Fix the error above "
                      "and re-run install.sh to finish." % ps.data_root())
            return rc
    if a.dry_run:
        return 0
    fails = ps.verify(cd, comps) if want_claude else 0
    if want_codex:
        fails += cps.verify(cdx, codex_comps)
    return 1 if fails else 0
