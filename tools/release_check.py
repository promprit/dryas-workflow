#!/usr/bin/env python3
"""Post-install check for a real machine. Prints PASS/FAIL/SKIP per check; exit 1 if any FAIL.

Claude Code: the dryas plugin per --claude-dir (repeatable, one per account). Codex: its copy install.
Never writes to the Claude or Codex folders or to ~/.dryas: hooks run with their logs, state, data root and
chain.local.json in a temp dir and without an OpenRouter key. Only the Jev route check calls OpenRouter (when a key is set).
"""
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SAMPLES = {
    "PreToolUse": {"tool_name": "Write", "tool_input": {"file_path": "notes.txt", "content": "café → ok"}},
    "UserPromptSubmit": {"prompt": ""},
    "SessionStart": {"source": "startup"},
    "PreCompact": {"trigger": "manual"},
}
PLUGIN_ID = "dryas@dryas-workflow"
RECORD = ".dryas-plugin.json"
KEY_VARS = ("OPENROUTER_API_KEY", "DRYAS_OPENROUTER_KEY", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY")
REPO = Path(__file__).resolve().parents[1]
PLAN = "## Task 1: a\nGoal: g\nScope:\n- src/feature/**\nDone:\n- d\n"
MANUAL = """Manual checks (needs the app open):
  1. In Claude Code, send any prompt; the reply context shows a "Jev route:" line (when an OpenRouter key is set).
  2. In a scratch git repo, run /orchestrate on a tiny task (or create .orchestrate/PLAN.md and active.json by hand);
     ask Claude to write a file outside the Scope. The scope lock must deny it.
  3. In Codex, ask it to edit a file outside the Scope (apply_patch). It must be denied.
  4. Report the output of this script and these steps in an issue.
  5. In each account's Claude Code, run /plugin and check dryas is enabled; if hooks did not fire, check for allowManagedHooksOnly in managed settings (docs/install.md).
  6. Run /tune and /handoff once in each account; both must run without a permission prompt."""


class Report:
    def __init__(self):
        self.fails = 0

    def say(self, status, name, detail=""):
        if status == "FAIL":
            self.fails += 1
        print("%-4s  %s%s" % (status, name, ("  (" + detail + ")") if detail else ""))


def api_key(env) -> str:
    """Same rule as jev_client.api_key: the first of KEY_VARS that is not blank or an unexpanded "${...}"."""
    for name in KEY_VARS:
        v = env.get(name, "").strip()
        if v and not v.startswith("${"):
            return v
    return ""


def find_bash():
    """Git Bash on Windows (never WSL's System32 bash), sh elsewhere. Same as install/tests/test_hook_shell.py."""
    if os.name != "nt":
        return shutil.which("sh")
    for cand in (shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe"):
        if cand and "system32" not in cand.lower() and os.path.isfile(cand):
            return cand
    return None


def fwd(p) -> str:
    return str(p).replace("\\", "/")


def _plugin_entry(cd, claude):
    """dryas@dryas-workflow from `claude plugin list --json` for cd ({} = not listed); None = no CLI or the call failed."""
    if not claude:
        return None
    try:
        r = subprocess.run([claude, "plugin", "list", "--json"], capture_output=True, universal_newlines=True,
                           encoding="utf-8", errors="replace", timeout=120, env=dict(os.environ, CLAUDE_CONFIG_DIR=str(cd)))
        data = json.loads(r.stdout) if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        data = None
    if not isinstance(data, list):
        return None
    return next((p for p in data if isinstance(p, dict) and p.get("id") == PLUGIN_ID), {})


def _install_path(cd, entry):
    """The plugin root Claude Code runs (as plugin_setup.install_path): readFromFolder (a directory marketplace
    loads the plugin in place), else installPath; installed_plugins.json when the CLI call failed."""
    if entry is not None:
        return entry.get("readFromFolder") or entry.get("installPath") or None
    try:
        data = json.loads((Path(cd) / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        entries = data.get("plugins", {}).get(PLUGIN_ID, [])
        paths = [e.get("installPath") for e in entries if isinstance(e, dict) and e.get("installPath")]
        return paths[0] if paths else None
    except (OSError, ValueError, AttributeError):
        return None


def load(d):
    try:
        return json.loads((d / ".dryas-installed.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sample(ev):
    event = dict(SAMPLES.get(ev, {}), hook_event_name=ev, cwd=tempfile.gettempdir(), session_id="release-check")
    return json.dumps(event, ensure_ascii=False).encode("utf-8")


def run_hook(cmd, ev, env, argv=None, timeout=120):
    try:
        r = subprocess.run(argv or cmd, shell=argv is None, input=sample(ev), capture_output=True, env=env,  # portable-ok: Codex hooks run in the OS default shell
                           timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    if r.returncode != 0:
        return False, "exit %s: %s" % (r.returncode, r.stderr.decode("utf-8", "replace").strip()[:200])
    out = r.stdout.decode("utf-8", "replace").strip()
    if out:
        try:
            json.loads(out)
        except ValueError:
            return True, "WARN: stdout is not JSON: " + out[:60].replace("\n", " ")
    return True, ""


def check_hooks(rep, label, hooks, env):
    if not hooks:
        rep.say("SKIP", label + " hooks", "none recorded")
    for ev, cmd in hooks:
        ok, why = run_hook(cmd, ev, env)
        warn = ok and why.startswith("WARN")
        rep.say("WARN" if warn else ("PASS" if ok else "FAIL"), "%s hook %s" % (label, ev), why or cmd[:60])


def sandbox(env, tmp):
    """env for hook runs: no OpenRouter key; logs, handoffs, compaction notes, data root and chain.local.json in tmp."""
    e = {k: v for k, v in env.items() if k not in KEY_VARS}
    local = Path(tmp) / "chain.local.json"  # {}: optional local stages (FlowObserve) stay off
    if not local.exists():
        local.write_text("{}", encoding="utf-8")
    e.update(JEV_LOG_DIR=str(Path(tmp) / "logs"), JEV_HANDOFF_DIR=str(Path(tmp) / "handoff"),
             JEV_COMPACT_DIR=str(Path(tmp) / "compact"), JEV_CHAIN_LOCAL=str(local), DRYAS_DATA_ROOT=str(Path(tmp) / "data"))
    return e


def plugin_hooks(rep, root, cd, bash, env):
    """Run each hooks.json command of the installed plugin the way Claude Code does: bash -c with the plugin env."""
    try:
        hooks = json.loads((Path(root) / "hooks" / "hooks.json").read_text(encoding="utf-8")).get("hooks", {})
    except (OSError, ValueError, AttributeError) as e:
        return rep.say("FAIL", "plugin hooks.json", str(e))
    e = dict(env, CLAUDE_PLUGIN_ROOT=fwd(root), DRYAS_PY=fwd(sys.executable), CLAUDE_CONFIG_DIR=str(cd))
    for ev in SAMPLES:
        name = "plugin hooks run (%s)" % ev
        cmds = [h for g in hooks.get(ev, []) for h in g.get("hooks", []) if h.get("command")]
        if not cmds:
            rep.say("SKIP", name, "no hooks")
            continue
        if bash is None:
            rep.say("SKIP", name, "no bash (Windows needs Git Bash)")
            continue
        bad = []
        for h in cmds:
            ok, why = run_hook(h["command"], ev, e, [bash, "-c", h["command"]], h.get("timeout") or 60)
            if not ok or why.startswith("WARN"):
                bad.append(why)
        rep.say("FAIL" if bad else "PASS", name, "; ".join(bad))


def manifests(rep, claude):
    """`claude plugin validate` on the marketplace and the plugin (schema is not checked anywhere else)."""
    if not claude:
        return rep.say("SKIP", "plugin manifests valid", "claude not on PATH")
    bad = []
    for target in (REPO, REPO / "claude"):
        try:
            r = subprocess.run([claude, "plugin", "validate", str(target)], capture_output=True, universal_newlines=True,
                               encoding="utf-8", errors="replace", timeout=120)
            if r.returncode != 0:
                bad.append("%s: %s" % (target.name or str(target), (r.stdout + r.stderr).strip()[-200:]))
        except (OSError, subprocess.TimeoutExpired) as ex:
            bad.append(str(ex))
    rep.say("FAIL" if bad else "PASS", "plugin manifests valid", "; ".join(bad))


def codex_chain(rec):
    """chain.py the Codex hooks call (Codex keeps a runtime-only copy in a Claude config dir)."""
    for h in rec.get("hooks", {}).get("hooks", []):
        m = re.search(r'"([^"]*[/\\]jev[/\\]chain\.py)"', str(h[2]))
        if m:
            return Path(m.group(1))
    return Path.home() / ".claude" / "jev" / "chain.py"


def codex_hooks(cdx, rec):
    recorded = {h[2] for h in rec.get("hooks", {}).get("hooks", [])}
    out = []
    try:
        data = json.loads((cdx / "hooks.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [(h[0], h[2]) for h in rec.get("hooks", {}).get("hooks", [])]
    for ev, groups in data.get("hooks", {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                if h.get("command") in recorded:
                    cmd = h.get("commandWindows") if os.name == "nt" and h.get("commandWindows") else h["command"]
                    out.append((ev, cmd))
    return out


def scope_lock(rep, chain, harness, env):
    name = "Scope lock (%s)" % harness
    if not chain.is_file():
        return rep.say("FAIL", name, "missing " + str(chain))
    wt = Path(tempfile.mkdtemp())
    try:
        (wt / ".orchestrate").mkdir()
        (wt / ".orchestrate" / "PLAN.md").write_text(PLAN, encoding="utf-8")
        (wt / ".orchestrate" / "active.json").write_text(json.dumps({"active": ["1"]}), encoding="utf-8")
        if harness == "codex":
            patch = "*** Begin Patch\n*** Add File: src/other.ts\n+x\n*** End Patch\n"
            event = {"tool_name": "apply_patch", "tool_input": {"command": patch}, "cwd": str(wt)}
            extra = ["--harness", "codex"]
        else:
            event = {"tool_name": "Write", "tool_input": {"file_path": "src/other.ts", "content": "x"}, "cwd": str(wt)}
            extra = []
        e = sandbox(env, wt)
        r = subprocess.run([sys.executable, "-X", "utf8", str(chain), "pretool"] + extra, input=json.dumps(event),
                           capture_output=True, universal_newlines=True, encoding="utf-8", env=e, timeout=120)
        try:
            ok = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
        except (ValueError, KeyError, TypeError):
            ok = False
        rep.say("PASS" if ok else "FAIL", name, "" if ok else "out-of-scope write was not denied")
    except (OSError, subprocess.TimeoutExpired) as ex:
        rep.say("FAIL", name, str(ex))
    finally:
        shutil.rmtree(str(wt), ignore_errors=True)


def jev_route(rep, chain, env):
    if not api_key(env):
        return rep.say("SKIP", "Jev route", "no OpenRouter key in this shell (a plugin option key is seen only inside Claude Code: manual step 1)")
    tmp = tempfile.mkdtemp()
    try:
        local = Path(tmp) / "chain.local.json"  # {}: the user's stage choices are not read, local stages stay off
        local.write_text("{}", encoding="utf-8")
        # the one networked check; its logs stay out of ~/.dryas
        env = dict(env, JEV_LOG_DIR=str(Path(tmp) / "logs"), JEV_CHAIN_LOCAL=str(local))
        r = subprocess.run([sys.executable, "-X", "utf8", str(chain), "prompt"],
                           input=json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "fix a typo in the readme",
                                             "cwd": tempfile.gettempdir(), "session_id": "release-check"}),
                           capture_output=True, universal_newlines=True, encoding="utf-8", env=env, timeout=120)
        out = r.stdout
    except (OSError, subprocess.TimeoutExpired) as ex:
        out = ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rep.say("PASS" if "Jev " in out else "WARN", "Jev route", "" if "Jev " in out else "no 'Jev ' line in output")


def ruflo(rep, cd, root_dir, env, run_env):
    """env names the real data root (checked, never written); the helper runs with run_env (temp data root)."""
    try:
        comps = json.loads((cd / RECORD).read_text(encoding="utf-8")).get("components", [])
    except (OSError, ValueError, AttributeError):
        comps = []
    if "ruflo" not in comps:
        return rep.say("SKIP", "Ruflo", "not set up in %s" % cd)
    run = Path(root_dir) / "ruflo" / "run.py"
    root = Path(env.get("DRYAS_DATA_ROOT") or Path.home() / ".dryas")
    ok = root.is_dir() and os.access(str(root), os.W_OK)
    rep.say("PASS" if ok else "FAIL", "Ruflo data root writable", str(root))
    hh = root / "ruflo" / "helpers" / "hook-handler.cjs"
    rep.say("PASS" if hh.is_file() else "FAIL", "Ruflo helpers in data root", str(hh))
    Path(run_env["DRYAS_DATA_ROOT"]).mkdir(parents=True, exist_ok=True)  # an existing (temp) root: not a vacuous run
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", str(run), "helper", "node", str(Path(tempfile.gettempdir()) / "dryas-nonexistent-xyz")],
                           input="", capture_output=True, universal_newlines=True, encoding="utf-8", env=run_env, timeout=120)
        ok = r.returncode == 0 and not r.stdout.strip()
        why = "" if ok else "exit %s %s" % (r.returncode, r.stdout.strip()[:80])
    except (OSError, subprocess.TimeoutExpired) as ex:
        ok, why = False, str(ex)
    rep.say("PASS" if ok else "FAIL", "Ruflo helper runs silently", why)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check a Dryas Workflow install on this machine (read-only).")
    ap.add_argument("--claude-dir", action="append", help="a Claude Code config dir; repeat for each account "
                    "(default: ~/.claude)")
    ap.add_argument("--codex-dir", default=os.environ.get("CODEX_HOME") or str(Path.home() / ".codex"))
    a = ap.parse_args(argv)
    cds = [Path(d) for d in (a.claude_dir or [str(Path.home() / ".claude")])]
    cdx = Path(a.codex_dir)
    env = dict(os.environ)
    rep = Report()
    print("Environment")
    rep.say("PASS", "OS", "%s %s" % (platform.system(), platform.release()))
    rep.say("PASS", "Python", "%s at %s" % (platform.python_version(), sys.executable))
    for t in ("git", "claude", "codex", "node"):
        p = shutil.which(t)
        rep.say("PASS" if p else "SKIP", t, p or "not on PATH")
    rep.say("PASS" if api_key(env) else "SKIP", "OpenRouter key", "set" if api_key(env) else "not set in this shell")
    manifests(rep, shutil.which("claude"))
    bash = find_bash()
    tmp = tempfile.mkdtemp(prefix="dryas-release-check-")
    try:
        return _checks(rep, cds, cdx, env, bash, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _checks(rep, cds, cdx, env, bash, tmp):
    hook_env = sandbox(env, tmp)
    claude = shutil.which("claude")
    for cd in cds:
        print()
        print("Claude Code: %s" % cd)
        entry = _plugin_entry(cd, claude)
        root = _install_path(cd, entry)
        if not root:
            rep.say("FAIL", "dryas plugin installed", "%s not installed in %s" % (PLUGIN_ID, cd))
            continue
        rep.say("PASS", "dryas plugin installed", root)
        if not claude:
            rep.say("SKIP", "dryas loads without errors", "claude not on PATH")
        else:
            errs = ["`claude plugin list --json` failed"] if entry is None else \
                [str(e) for e in entry.get("errors") or []] + ([] if entry.get("enabled") else ["not enabled"])
            rep.say("FAIL" if errs else "PASS", "dryas loads without errors", "; ".join(errs))
        plugin_hooks(rep, root, cd, bash, hook_env)
        penv = dict(env, CLAUDE_PLUGIN_ROOT=fwd(root), DRYAS_PY=fwd(sys.executable), CLAUDE_CONFIG_DIR=str(cd))
        chain = Path(root) / "jev" / "chain.py"
        scope_lock(rep, chain, "claude", penv)
        jev_route(rep, chain, penv)
        ruflo(rep, cd, root, penv, dict(hook_env, CLAUDE_PLUGIN_ROOT=fwd(root)))
    print()
    crec = load(cdx)
    if crec is None:
        rep.say("SKIP", "Codex install", "no .dryas-installed.json in %s" % cdx)
    else:
        check_hooks(rep, "Codex", codex_hooks(cdx, crec), hook_env)
        scope_lock(rep, codex_chain(crec), "codex", env)
    print()
    print(MANUAL)
    return 1 if rep.fails else 0


if __name__ == "__main__":
    sys.exit(main())
