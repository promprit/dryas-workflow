"""Installer entry used by install.sh and install.ps1: flags, preflight, then codex -> migrate -> setup -> verify.

  dryas_install.py run [--repo PATH] [--judge local|jev] [--memory dryas|ruflo|none] [--with-ruflo] [--with-superpowers] [--with-design]
                       [--no-jev] [--no-ruflo] [--no-superpowers] [--no-design] [--no-rea] [--with-rea] [--no-pstack-picks]
                       [--yes] [--force] [--dry-run] [--uninstall] [--purge] [--keep-extras] [--preflight-only]
                       [--harness claude|codex|both|opencode|all] [--claude-dir DIR] [--codex-dir DIR] [--opencode-dir DIR]
                       [--tier-fast|--tier-standard|--tier-strong|--tier-frontier PROVIDER/MODEL]
                       [--flowobserve|--no-flowobserve] [--openrouter-key KEY]

Claude Code: the dryas plugin in one config dir (--claude-dir, else $CLAUDE_CONFIG_DIR, else ~/.claude); a copy
install found there is migrated first. Codex: the dryas plugin in one CODEX_HOME (--codex-dir, else $CODEX_HOME,
else ~/.codex); a Codex copy install found there is migrated.
OpenCode: the edition copied into one config dir (--opencode-dir, else $XDG_CONFIG_HOME/opencode, else ~/.config/opencode).
--uninstall touches only that config dir / CODEX_HOME; --purge also removes the data root once no account uses it.
Both list what they will remove and ask first; --yes answers every question. The third-party plugins setup installed
are offered for removal too (--keep-extras leaves them, --yes removes them).
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import platform_util as pu

HERE = Path(__file__).resolve().parent
TIERS = ("fast", "standard", "strong", "frontier")  # executor tiers; opencode_setup reuses it
OPTIONAL = ("jev", "memory", "ruflo", "superpowers", "design", "pstack-picks", "rea")
EXTRAS = ("ruflo", "superpowers")  # off unless selected or already installed
FRESH = ("jev", "memory", "design", "pstack-picks", "rea")
WITH = ("ruflo", "superpowers", "design", "rea")  # --with-<c> flags
NO_STAGES = ("rea",)  # optional components with no chain stage (kept out of chain.local.json "off")
HARNESSES = ("claude", "codex", "both", "opencode", "all")
CLAUDE_H, CODEX_H, OPENCODE_H = ("claude", "both", "all"), ("codex", "both", "all"), ("opencode", "all")
NO_SPACE_RUFLO = ("Your Python, Dryas data folder or Dryas plugin path contains a space and has no short form; "
                  "Ruflo's hook override cannot handle that. Re-run without --with-ruflo (--no-ruflo on an upgrade that has it).")
LEGACY_REFUSAL = ("A Codex copy install (%s) uses %s; run install.sh --harness both (install.ps1 on Windows) to move "
                  "Claude Code and Codex to their plugins. If you no longer use Codex, remove its copy install first "
                  "with install.sh --uninstall --harness codex (Claude Code is not touched), then re-run. Nothing changed.")
NO_PYTHON3 = "Codex runs the Dryas hooks with python3: install Python 3.9+ as python3 and re-run."
NO_RUFLO_EFFECT = {"claude": "Claude Code then runs without Ruflo's orchestration, memory and hooks",
                   "codex": "Codex then runs without the Ruflo MCP server",
                   "both": "Claude Code then runs without Ruflo's orchestration, memory and hooks, Codex without "
                           "the Ruflo MCP server",
                   "opencode": "OpenCode never uses Ruflo",
                   "all": "Claude Code and Codex then run without Ruflo"}
NO_PYTHON_WIN = ("warning: `python` is not on PATH; on Windows Codex runs the Dryas hooks with `python` "
                 "(install Python 3.9+ from python.org and tick \"Add python.exe to PATH\").")


def parse(argv: List[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="install")
    ap.add_argument("--repo", default=str(HERE.parent))
    for c in OPTIONAL:
        ap.add_argument("--no-" + c, action="store_true")
    for c in WITH:
        ap.add_argument("--with-" + c, action="store_true")
    ap.add_argument("--judge", default=None, choices=("local", "jev"))
    ap.add_argument("--memory", default=None, choices=("dryas", "ruflo", "none"))
    for f in ("yes", "force", "dry-run", "uninstall", "preflight-only", "purge", "keep-extras"):
        ap.add_argument("--" + f, action="store_true")
    fo = ap.add_mutually_exclusive_group()  # tri-state: None keeps the setting, True on, False off
    fo.add_argument("--flowobserve", dest="flowobserve", action="store_const", const=True, default=None)
    fo.add_argument("--no-flowobserve", dest="flowobserve", action="store_const", const=False)
    ap.add_argument("--harness", default="claude", choices=HARNESSES)
    ap.add_argument("--claude-dir", default=None)
    ap.add_argument("--codex-dir", default=None)
    ap.add_argument("--opencode-dir", default=None)
    for t in TIERS:
        ap.add_argument("--tier-" + t, default=None, metavar="PROVIDER/MODEL")
    ap.add_argument("--openrouter-key", default="")  # explicit only: it reaches the `claude plugin install` argv
    a = ap.parse_args(argv)
    for c in WITH:
        if getattr(a, "with_" + c) and getattr(a, "no_" + c):
            ap.error("--with-%s and --no-%s together" % (c, c))
    for bad, why in ((a.judge == "local" and a.openrouter_key, "--judge local with --openrouter-key"),
                     (a.memory == "ruflo" and a.no_ruflo, "--memory ruflo with --no-ruflo"),
                     (a.memory == "dryas" and a.no_memory, "--memory dryas with --no-memory"),
                     (a.memory == "none" and a.with_ruflo, "--memory none with --with-ruflo")):
        if bad:
            ap.error(why + " contradict each other")
    return a


def _no(a: argparse.Namespace, c: str) -> bool:
    return bool(getattr(a, "no_" + c.replace("-", "_")))


def select(a: argparse.Namespace, recorded: Optional[List[str]]) -> List[str]:
    """Components to install. Fresh: the owned core. Upgrade (recorded components): keep them, plus core."""
    if recorded is None:
        have = set(FRESH)
    else:
        have = set(recorded)
    for c in WITH:
        if getattr(a, "with_" + c):
            have.add(c)
    for c in OPTIONAL:
        if _no(a, c):
            have.discard(c)
    if a.memory == "ruflo":
        have.add("ruflo")
        have.discard("memory")
    elif a.memory == "none":
        have -= {"ruflo", "memory"}
    elif a.memory == "dryas":
        have.add("memory")
    if "memory" not in have and "ruflo" not in have and a.memory != "none" and not a.no_memory:
        have.add("memory")
    if a.judge or a.no_jev or a.openrouter_key:
        have.add("jev")
    return ["core"] + [c for c in OPTIONAL if c in have]


def components(a: argparse.Namespace) -> List[str]:
    return select(a, None)


def providers(a: argparse.Namespace, comps: List[str], recorded: Optional[List[str]]) -> Dict[str, Optional[str]]:
    """Provider slots to record. Without a judge flag the current judge.provider is recorded (and left alone)."""
    if a.judge:
        judge = a.judge
    elif a.openrouter_key:
        judge = "jev"
    elif a.no_jev:
        judge = "local"
    else:
        sys.path.insert(0, str(Path(a.repo) / "claude" / "jev"))
        import thresholds
        judge = thresholds.load()["judge"]["provider"]
    mem = "dryas" if "memory" in comps else "ruflo" if "ruflo" in comps else "none"
    return {"judge": judge, "memory": mem, "process": "dryas"}


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
    if harness in CLAUDE_H and not pu.which("claude"):
        missing.append("claude(Claude Code CLI)")
    if harness in CODEX_H and not pu.which("codex"):
        missing.append("codex(Codex CLI)")
    node = [t for t in ("node", "npm") if not pu.which(t)] if "ruflo" in comps else []
    missing += node
    probs = []
    if missing and len(node) == len(missing):  # only Ruflo needs Node: say so and name the way around it
        probs.append("Missing: %s. Only Ruflo needs them: install Node.js (node and npm) and re-run, or re-run with "
                     "without --with-ruflo (or with --no-ruflo on an upgrade) to skip Ruflo (%s). This installer never installs system packages."
                     % (" ".join(node), NO_RUFLO_EFFECT[harness]))
    elif missing:
        probs.append("Missing: %s. Install them and re-run (this installer never installs system packages)."
                     % " ".join(missing))
    if "ruflo" in comps:
        root = Path(os.path.expanduser(os.environ.get("DRYAS_DATA_ROOT") or str(Path.home() / ".dryas")))
        if any(pu.space_free(p) is None for p in [sys.executable, root] + list(ruflo_paths)):
            probs.append(NO_SPACE_RUFLO)
    if harness in CODEX_H and pu.which("codex"):
        import codex_plugin_setup as cps
        ver, want = codex_version(), cps.MIN_CODEX
        if ver is None or ver < want:
            probs.append("Dryas needs Codex CLI %s or newer (found: %s). Update it (npm install -g @openai/codex) and "
                         "re-run." % (".".join(map(str, want)), ".".join(map(str, ver)) if ver else "no version"))
    if harness in CODEX_H:
        import codex_plugin_setup as cps
        if pu.IS_WINDOWS:
            if not pu.which("python"):
                print(NO_PYTHON_WIN)
        elif not cps.python3_ok():
            probs.append(NO_PYTHON3)
    if harness in OPENCODE_H:
        import opencode_setup as ocs
        if not pu.which("opencode"):
            probs.append("Missing: opencode (OpenCode CLI). Install it and re-run (this installer never installs it).")
        else:
            ver = ocs.installed_version()
            if ver is None or ver < ocs.MIN_OPENCODE:
                probs.append("Dryas needs OpenCode %s or newer (found: %s). Update it and re-run."
                             % (".".join(map(str, ocs.MIN_OPENCODE)), ".".join(map(str, ver)) if ver else "no version"))
    return probs


def _vtuple(v) -> Optional[tuple]:
    """Dotted numeric version as an int tuple (a leading 'v' or 'skill-v' is stripped); None if unparseable."""
    m = re.fullmatch(r"(?:skill-)?v?(\d+(?:\.\d+)*)", str(v).strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def thirdparty(comps: List[str], yes: bool, claude_dir: Path, env: Optional[dict] = None,
               table_path: Optional[Path] = None, ran: Optional[List[List[str]]] = None) -> int:
    """Install third-party tools into `claude_dir` (env carries its CLAUDE_CONFIG_DIR); warn on untested versions.
    Superpowers is an optional extra (owned core C): installed by its command like ruflo and design.
    ran: when given, every command that ran and succeeded is appended (setup records them for uninstall)."""
    import dryas_install as di
    table = json.loads(Path(table_path or HERE / "components.json").read_text(encoding="utf-8"))
    sel = [c for c in comps if c in table]
    cmds = [(c, argv) for c in sel for argv in table[c]["commands"]]
    if cmds:
        print("Third-party installs:")
        for _, argv in cmds:
            print("  " + " ".join(argv))
        if yes or di.confirm("Run these?"):
            for c, argv in cmds:
                rc = di.run(argv, env=env)
                if rc != 0 and c == "superpowers":
                    print("warning: %s failed (exit %d); Superpowers is optional, Dryas setup continues"
                          % (" ".join(argv), rc))
                    continue
                if rc != 0:
                    print("failed (exit %d): %s" % (rc, " ".join(argv)))
                    return rc
                if ran is not None:
                    ran.append(list(argv))
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
    import opencode_setup as ocs
    a = parse(list(sys.argv[1:] if argv is None else argv))
    repo, home = Path(a.repo).resolve(), Path.home()
    cd = ps.claude_dir(a.claude_dir)
    rec = ps._load_json(cd / ps.RECORD, {}) if (cd / ps.RECORD).is_file() else {}
    recorded = (rec.get("components") or None) if isinstance(rec, dict) else None
    comps = select(a, recorded)
    want_claude, want_codex, want_oc = a.harness in CLAUDE_H, a.harness in CODEX_H, a.harness in OPENCODE_H
    od = ocs.opencode_dir(a.opencode_dir)
    tiers = {t: getattr(a, "tier_" + t) for t in TIERS}
    cdx = cps.codex_home(a.codex_dir)
    legacy = cps.legacy_components(cdx)
    no_flags = not (any(_no(a, c) for c in OPTIONAL) or any(getattr(a, "with_" + c) for c in WITH)
                    or a.judge or a.memory)
    codex_comps = legacy if (legacy is not None and no_flags) else comps
    if a.harness in ("codex", "opencode") and not a.uninstall and ("superpowers" in comps or "design" in comps):
        print("note: superpowers and design are Claude Code plugins; skipped for %s." % ("Codex" if a.harness == "codex" else "OpenCode"))
    if a.harness == "opencode" and not a.uninstall and "rea" in comps:
        print("note: REA is not set up for OpenCode; skipped.")
    if a.uninstall:  # Codex first: Claude's --purge then sees whether a CODEX_HOME still uses the data root
        plan = []
        if want_codex and (cdx / cps.RECORD).exists():
            plan.append("Codex: `codex plugin remove %s` for %s, the Dryas block in its config.toml, the hook trust "
                        "setup recorded, %s" % (cps.ID, cdx, cdx / cps.RECORD))
        if want_oc and (od / ocs.RECORD).exists():
            plan.append("OpenCode: the files Dryas wrote into %s (listed in %s)" % (od, od / ocs.RECORD))
        if want_claude:
            plan += ps.uninstall_plan(cd, a.purge)
        elif a.purge:
            plan += ps.purge_plan()
        if plan:
            print("--uninstall will remove:")
            for line in plan:
                print("  " + line)
            if not (a.yes or di.confirm("Proceed?")):
                print("nothing removed")
                return 1
        extras, legacy = [], []
        if want_claude:
            others = ps.other_accounts(cd, cdx if want_codex else None, od if want_oc else None)
            extras = ps.extras_commands(ps._load_json(cd / ps.RECORD, {}), last_account=not others)
            if extras and a.keep_extras:
                extras = []
            elif extras:
                print("Third-party tools setup installed for %s (kept with --keep-extras):" % cd)
                for argv in extras:
                    print("  " + ps.shown(cd, argv))
                if not (a.yes or di.confirm("Remove them too?")):
                    extras = []
            if not a.keep_extras and (cd / ps.RECORD).exists():  # only an account Dryas set up
                legacy = ps.legacy_items(cd, ps._load_json(cd / ps.RECORD, {}), last_account=not others)
                if legacy:
                    if a.yes:
                        print("Legacy Ruflo pieces (not removed with --yes; commands printed):")
                    else:
                        print("Legacy Ruflo pieces (each asked separately):")
                    for label, _, _ in legacy:
                        print("  " + label)
        cextras = cps.rea_extras(cdx) if want_codex else []
        if cextras and a.keep_extras:
            print("kept REA for Codex; to remove it: %s" % "; ".join("CODEX_HOME=%s %s" % (cdx, " ".join(c)) for c in cextras))
            cextras = []
        elif cextras:
            print("Third-party tools setup installed for %s (kept with --keep-extras):" % cdx)
            for argv in cextras:
                print("  CODEX_HOME=%s %s" % (cdx, " ".join(argv)))
            if not (a.yes or di.confirm("Remove them too?")):
                cextras = []
        rc = max(cps.uninstall(cdx, extras=cextras) if want_codex else 0, ocs.uninstall(od) if want_oc else 0)
        if rc:
            return rc
        if want_claude:
            rc = ps.uninstall(cd, a.purge, extras=extras)
            if legacy and ps.run_legacy(legacy, a.yes, cd):
                print("warning: some legacy Ruflo pieces were not removed")
            return rc
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
    pre = sorted(set(comps) | set(codex_comps if want_codex else []))
    if a.harness == "opencode":
        pre = [c for c in pre if c != "ruflo"]
    probs = preflight(pre, a.harness, cd,
                      [repo / "claude", cd] if want_claude else [])
    if probs:
        print("\n".join(probs))
        return 1
    if a.preflight_only:
        print("preflight ok")
        return 0
    if want_codex:
        rc = cps.setup(repo, cdx, list(codex_comps), yes=a.yes, dry=a.dry_run)
        if rc:
            return rc
    if want_oc:
        rc = ocs.setup(repo, od, comps, tiers, dry=a.dry_run)
        if rc:
            return rc
    if want_claude:
        if copy_install and a.dry_run:
            print("would migrate the copy install in %s" % cd)
        elif copy_install:
            rc = migrate.migrate(cd, ps.data_root())
            if rc:
                return rc
        rc = ps.setup(repo, cd, comps, yes=a.yes, key=a.openrouter_key, flowobserve=a.flowobserve, dry=a.dry_run,
                      providers=providers(a, comps, recorded))
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
    if want_oc:
        fails += ocs.verify(od)
    return 1 if fails else 0
