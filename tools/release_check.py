#!/usr/bin/env python3
"""Post-install check for a real machine. Prints PASS/FAIL/SKIP per check; exit 1 if any FAIL.

Claude Code: the dryas plugin per --claude-dir (repeatable, one per account). Codex: the dryas plugin per
--codex-dir (repeatable, one per CODEX_HOME): listed and enabled, hooks trusted, hook command lines run, scope lock.
OpenCode: the edition per --opencode-dir (repeatable): version, files, jev MCP, rules hook, scope lock, tiers.
Never writes to the Claude or Codex folders or to ~/.dryas (the codex CLI may keep its own logs in CODEX_HOME): hooks
run with their logs, state, data root and chain.local.json in a temp dir and without an OpenRouter key. Only the Jev
route check calls OpenRouter (when a key is set).
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
sys.path.insert(0, str(REPO / "install"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import codex_appserver as ca  # noqa: E402  (stdlib only; tools never import tests)
import platform_util as pu  # noqa: E402
import release_check_opencode as rco  # noqa: E402
PLAN = "## Task 1: a\nGoal: g\nScope:\n- src/feature/**\nDone:\n- d\n"
MANUAL = """Manual checks (needs the app open):
  1. In Claude Code, send any prompt; the reply context shows a "Jev route:" line (when an OpenRouter key is set).
  2. In a scratch git repo, run /orchestrate on a tiny task (or create .orchestrate/PLAN.md and active.json by hand);
     ask Claude to write a file outside the Scope. The scope lock must deny it.
  3. In Codex (each CODEX_HOME): send a prompt; the context shows a "Jev route:" line (with OPENROUTER_API_KEY set).
     Ask "which workflow rules apply here?"; the answer names the Dryas Workflow. Ask it to edit a file outside
     the Scope (apply_patch): it must be denied.
  4. Report the output of this script and these steps in an issue.
  5. In each account's Claude Code, run /plugin and check dryas is enabled; if hooks did not fire, check for allowManagedHooksOnly in managed settings (docs/install.md).
  6. Run /tune and /handoff once in each account; both must run without a permission prompt.
  7. Codex: type $dryas:orchestrate in the TUI and note the syntax that works (record it in docs/install.md if it
     differs). On Windows also: steps 3 and 7, and codex mcp list shows jev.
  8. OpenCode (each config dir): run /orchestrate on a tiny task in a scratch repo; ask it to edit a file outside the Scope: it must be denied. Ask for a destructive command (git reset --hard): it must be blocked with a `dryas allow <code>` message; typing that code allows it once."""


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
                           encoding="utf-8", errors="replace", timeout=120, env=pu.claude_env(cd))
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


def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        return ex


def codex_manifest_problems(repo: Path) -> list:
    """A light shape check of the Codex plugin manifest and the .agents marketplace (Codex has no validate command)."""
    bad = []
    mp, man = repo / ".agents" / "plugins" / "marketplace.json", repo / "codex" / ".codex-plugin" / "plugin.json"
    m = _json(man)
    if not isinstance(m, dict):
        bad.append("codex/.codex-plugin/plugin.json: %s" % (m if isinstance(m, Exception) else "not an object"))
    elif m.get("name") != PLUGIN_ID.split("@")[0] or not isinstance(m.get("version"), str) or not m["version"] \
            or not isinstance(m.get("interface", {}), dict):
        bad.append("codex/.codex-plugin/plugin.json: needs name %r, a version and an interface object"
                   % PLUGIN_ID.split("@")[0])
    d = _json(mp)
    entries = d.get("plugins") if isinstance(d, dict) else None
    ours = [e for e in entries if isinstance(e, dict) and e.get("name") == PLUGIN_ID.split("@")[0]] \
        if isinstance(entries, list) else []
    if not isinstance(d, dict) or d.get("name") != PLUGIN_ID.split("@")[1] or len(ours) != 1 \
            or ours[0].get("source") != "./codex":
        bad.append(".agents/plugins/marketplace.json: needs name %r and one plugin %r with source ./codex"
                   % (PLUGIN_ID.split("@")[1], PLUGIN_ID.split("@")[0]))
    return bad


VERSION_FILES = ("claude/.claude-plugin/plugin.json", "codex/.codex-plugin/plugin.json",
                 ".claude-plugin/marketplace.json", "CHANGELOG.md", "claude/jev/jev_mcp.py")


def versions(repo: Path) -> dict:
    """The release version as each shipped file states it: the two plugin manifests, the dryas entry in the
    Claude marketplace, the first `## X.Y.Z` heading in CHANGELOG.md (an `X.Y.Z - unreleased` heading is skipped) and the Jev MCP serverInfo version.
    A file that cannot be read or has no version maps to None."""
    repo = Path(repo)
    out = {}
    for rel in VERSION_FILES[:2]:
        d = _json(repo / rel)
        out[rel] = d.get("version") if isinstance(d, dict) else None
    d = _json(repo / VERSION_FILES[2])
    ours = [p for p in (d.get("plugins") or []) if isinstance(p, dict) and p.get("name") == PLUGIN_ID.split("@")[0]] \
        if isinstance(d, dict) else []
    out[VERSION_FILES[2]] = ours[0].get("version") if ours else None
    try:
        m = re.search(r"^## (\d+\.\d+\.\d+)\b(?! - unreleased)", (repo / VERSION_FILES[3]).read_text(encoding="utf-8"), re.M)
        out[VERSION_FILES[3]] = m.group(1) if m else None
    except OSError:
        out[VERSION_FILES[3]] = None
    try:
        m = re.search(r'"serverInfo"\s*:\s*\{[^}]*"version"\s*:\s*"([^"]+)"',
                      (repo / VERSION_FILES[4]).read_text(encoding="utf-8"))
        out[VERSION_FILES[4]] = m.group(1) if m else None
    except OSError:
        out[VERSION_FILES[4]] = None
    return out


def version_problems(repo: Path) -> list:
    """[] when every file in VERSION_FILES states the same version; else one line per disagreeing file."""
    found = versions(repo)
    if None in found.values():
        return ["%s: no version found" % rel for rel, v in found.items() if v is None]
    if len(set(found.values())) == 1:
        return []
    return ["%s: %s" % (rel, v) for rel, v in found.items()]


def release_versions(rep):
    bad = version_problems(REPO)
    rep.say("FAIL" if bad else "PASS", "release versions agree", "; ".join(bad) if bad else
            next(iter(versions(REPO).values())))


def no_node(rep, repo, tmp):
    """Preflight passes with Node stripped from PATH (the default install needs none)."""
    home = Path(tempfile.mkdtemp(dir=str(tmp)))
    env = sandbox(os.environ, home)
    env.update(HOME=str(home), USERPROFILE=str(home))
    # nvm and Homebrew put claude, codex and git next to node: link them into a shim dir before node's dir is dropped.
    shim = Path(tempfile.mkdtemp(dir=str(tmp)))
    for tool in ("claude", "codex", "git", "python3", "python"):
        src = shutil.which(tool)
        if not src:
            continue
        dst = shim / os.path.basename(src)
        try:
            if os.name == "nt":
                shutil.copy2(src, str(dst))
            else:
                os.symlink(src, str(dst))
        except OSError:
            pass
    # which() honours PATHEXT, so node.cmd and node.exe shims on Windows are dropped too
    env["PATH"] = os.pathsep.join([str(shim)] + [d for d in env.get("PATH", "").split(os.pathsep)
                                  if d and not shutil.which("node", path=d)])
    argv = [sys.executable, str(Path(repo) / "install" / "dryas_install.py"), "preflight", "--harness", "claude",
            "--claude-dir", str(home / ".claude")]
    try:
        r = subprocess.run(argv, capture_output=True, universal_newlines=True, encoding="utf-8", errors="replace",
                           env=env, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        rep.say("FAIL", "no-node install", str(e))
        return
    if r.returncode == 0 and "preflight ok" in r.stdout:
        rep.say("PASS", "no-node install")
    else:
        rep.say("FAIL", "no-node install", ("exit %s: %s" % (r.returncode, (r.stdout + r.stderr).strip()))[-200:])


def manifests(rep, claude):
    """`claude plugin validate` on the marketplace and the plugin (schema is not checked anywhere else), plus a light
    shape check of the Codex manifest and marketplace."""
    bad = codex_manifest_problems(REPO)
    if not claude:
        if bad:
            return rep.say("FAIL", "plugin manifests valid", "; ".join(bad))
        return rep.say("SKIP", "plugin manifests valid", "claude not on PATH")
    for target in (REPO, REPO / "claude"):
        try:
            r = subprocess.run([claude, "plugin", "validate", str(target)], capture_output=True, universal_newlines=True,
                               encoding="utf-8", errors="replace", timeout=120)
            if r.returncode != 0:
                bad.append("%s: %s" % (target.name or str(target), (r.stdout + r.stderr).strip()[-200:]))
        except (OSError, subprocess.TimeoutExpired) as ex:
            bad.append(str(ex))
    rep.say("FAIL" if bad else "PASS", "plugin manifests valid", "; ".join(bad))


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


def _codex_entry(cdx, codex, env):
    """dryas@dryas-workflow from `codex plugin list --json` in cdx; None when not listed or the call failed."""
    if not Path(cdx).is_dir():  # the real CLI errors on a missing CODEX_HOME; the check never creates one
        return None
    try:
        r = subprocess.run([codex, "plugin", "list", "--json"], capture_output=True, universal_newlines=True,
                           encoding="utf-8", errors="replace", timeout=120, env=env)
        items = json.loads(r.stdout).get("installed", []) if r.returncode == 0 else []
    except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
        items = []
    return next((p for p in items if isinstance(p, dict) and p.get("pluginId") == PLUGIN_ID), None)


def _ev(name):
    return re.sub(r"[_\s]", "", str(name)).lower()  # PreToolUse, preToolUse and pre_tool_use are one event


def codex_trust(rep, env):
    """Every Dryas hook Codex lists is trusted, and each event the plugin ships (codex/hooks/hooks.json) is listed."""
    name = "Codex hooks trusted"
    try:
        mine = [h for h in ca.list_hooks(env, str(Path.home())) if h.get("pluginId") == PLUGIN_ID]
    except ca.AppServerError as ex:
        return rep.say("FAIL", name, "%s; run /hooks in Codex" % ex)
    try:
        shipped = json.loads((REPO / "codex" / "hooks" / "hooks.json").read_text(encoding="utf-8")).get("hooks", {})
    except (OSError, ValueError, AttributeError):
        shipped = {}
    seen = {_ev(h.get("eventName") or (str(h.get("key", "")).split(":") + ["", "", ""])[2]) for h in mine}
    missing = sorted(ev for ev in shipped if _ev(ev) not in seen)
    bad = sorted({str(h.get("eventName") or h.get("key")) for h in mine if h.get("trustStatus") != "trusted"})
    detail = (["not trusted: %s; run /hooks in Codex" % ", ".join(bad)] if bad else []) + \
        (["missing: %s; re-run install.sh --harness codex" % ", ".join(missing)] if missing else []) + \
        ([] if mine else ["no Dryas hooks listed; run /hooks in Codex"])
    rep.say("FAIL" if detail else "PASS", name, "; ".join(detail))


def codex_hook_argv(h, bash):
    """(command, argv) the way Codex runs a plugin hook: commandWindows in the OS shell on Windows (argv None),
    else command under bash; None when there is nothing to run it with."""
    if os.name == "nt" and h.get("commandWindows"):
        return h["commandWindows"], None
    return (h["command"], [bash, "-c", h["command"]]) if bash else None


def rules_output(rep, h, env, bash):
    """The SessionStart command prints the Codex rules as hook JSON, with the resolved <dryas-root> paths line."""
    name = "Codex rules hook output"
    cmd, argv = codex_hook_argv(h, bash)
    try:
        r = subprocess.run(argv or cmd, shell=argv is None, input=sample("SessionStart"), capture_output=True,  # portable-ok: commandWindows runs in cmd
                           env=env, timeout=60)
        ctx = json.loads(r.stdout.decode("utf-8", "replace"))["hookSpecificOutput"]["additionalContext"]
        ok = "Dryas Workflow" in ctx and "Dryas paths:" in ctx
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError):
        ok = False
    rep.say("PASS" if ok else "FAIL", name, "" if ok else "no Dryas rules in the SessionStart output")


def codex_plugin(rep, cdx, codex, bash, hook_env):
    """One CODEX_HOME: no legacy copy install, the plugin listed and enabled, its hooks trusted, the installed hook
    command lines run as Codex runs them, with sample events; the rules hook output and the scope lock on apply_patch."""
    print()
    print("Codex: %s" % cdx)
    legacy = (Path(cdx) / ".dryas-installed.json").exists()
    rep.say("FAIL" if legacy else "PASS", "legacy Codex copy install",
            "still present: re-run install.sh --harness codex" if legacy else "none")
    env = dict(os.environ, CODEX_HOME=str(cdx))
    if not codex:
        return rep.say("SKIP", "dryas plugin installed (Codex)", "codex not on PATH")
    ent = _codex_entry(cdx, codex, env)
    ok = bool(ent and ent.get("enabled"))
    rep.say("PASS" if ok else "FAIL", "dryas plugin installed (Codex)",
            "version %s" % ent.get("version") if ok else "%s not installed and enabled in %s" % (PLUGIN_ID, cdx))
    if not ok:
        return
    codex_trust(rep, env)
    root = Path(cdx) / "plugins" / "cache" / "dryas-workflow" / "dryas" / str(ent.get("version"))
    try:
        hooks = json.loads((root / "hooks" / "hooks.json").read_text(encoding="utf-8")).get("hooks", {})
    except (OSError, ValueError, AttributeError) as ex:
        return rep.say("FAIL", "Codex plugin hooks.json", str(ex))
    e = dict(hook_env, PLUGIN_ROOT=fwd(root), CLAUDE_PLUGIN_ROOT=fwd(root), CODEX_HOME=str(cdx))
    for ev in ("SessionStart", "UserPromptSubmit", "PreToolUse"):
        name = "Codex plugin hooks run (%s)" % ev
        cmds = [h for g in hooks.get(ev, []) for h in g.get("hooks", []) if h.get("command")]
        runs = [codex_hook_argv(h, bash) for h in cmds]
        if not cmds or None in runs:
            rep.say("SKIP", name, "no shell to run the hook line" if cmds else "no hooks")
            continue
        bad = []
        for h, (cmd, argv) in zip(cmds, runs):
            ok, why = run_hook(cmd, ev, e, argv, h.get("timeout") or 60)
            if not ok or why.startswith("WARN"):
                bad.append(why)
        rep.say("FAIL" if bad else "PASS", name, "; ".join(bad))
        if ev == "SessionStart" and not bad:
            rules_output(rep, cmds[0], e, bash)
    scope_lock(rep, root / "jev" / "chain.py", "codex", dict(os.environ))


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
    ap.add_argument("--codex-dir", action="append", help="a Codex home (CODEX_HOME); repeat for each "
                    "(default: $CODEX_HOME or ~/.codex)")
    ap.add_argument("--opencode-dir", action="append", help="an OpenCode config dir; repeat for each "
                    "(default: $XDG_CONFIG_HOME/opencode or ~/.config/opencode)")
    a = ap.parse_args(argv)
    cds = [Path(d) for d in (a.claude_dir or [str(Path.home() / ".claude")])]
    cdxs = [Path(d) for d in (a.codex_dir or [os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")])]
    ods = [Path(d) for d in (a.opencode_dir or [str(rco.ocs.opencode_dir(None))])]
    env = dict(os.environ)
    rep = Report()
    print("Environment")
    rep.say("PASS", "OS", "%s %s" % (platform.system(), platform.release()))
    rep.say("PASS", "Python", "%s at %s" % (platform.python_version(), sys.executable))
    for t in ("git", "claude", "codex", "opencode", "node"):
        p = shutil.which(t)
        rep.say("PASS" if p else "SKIP", t, p or "not on PATH")
    rep.say("PASS" if api_key(env) else "SKIP", "OpenRouter key", "set" if api_key(env) else "not set in this shell")
    manifests(rep, shutil.which("claude"))
    release_versions(rep)
    bash = find_bash()
    tmp = tempfile.mkdtemp(prefix="dryas-release-check-")
    try:
        no_node(rep, REPO, tmp)
        return _checks(rep, cds, cdxs, env, bash, tmp, ods)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def claude_config(rep, cd, env):
    """Warn (never write) about leftovers of older installers: a jev MCP entry whose script is gone, and the stub
    ~/.claude/.claude.json that Claude Code ignores unless CLAUDE_CONFIG_DIR is set."""
    stale = pu.stale_jev(cd, env)
    if stale:
        rep.say("WARN", "jev MCP entry", "%s is missing; re-run the Dryas setup to remove the entry" % stale[0])
    else:
        rep.say("PASS", "jev MCP entry")
    default = Path.home() / ".claude"
    if "CLAUDE_CONFIG_DIR" in pu.claude_env(cd, env) or Path(cd).expanduser().resolve() != default.resolve():
        return
    stub = default / ".claude.json"
    if stub.exists():
        rep.say("WARN", "stub config", "%s may have been created by an older Dryas installer (or a run with "
                "CLAUDE_CONFIG_DIR=~/.claude); Claude Code reads %s; check it holds nothing you need before deleting" % (stub, Path.home() / ".claude.json"))
    else:
        rep.say("PASS", "stub config")


def _checks(rep, cds, cdxs, env, bash, tmp, ods=()):
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
        claude_config(rep, cd, env)
        penv = dict(env, CLAUDE_PLUGIN_ROOT=fwd(root), DRYAS_PY=fwd(sys.executable), CLAUDE_CONFIG_DIR=str(cd))
        chain = Path(root) / "jev" / "chain.py"
        scope_lock(rep, chain, "claude", penv)
        jev_route(rep, chain, penv)
        ruflo(rep, cd, root, penv, dict(hook_env, CLAUDE_PLUGIN_ROOT=fwd(root)))
    for cdx in cdxs:
        codex_plugin(rep, cdx, shutil.which("codex"), bash, hook_env)
    for od in ods:
        rco.check(rep, od, shutil.which("opencode"), hook_env)
    print()
    print(MANUAL)
    return 1 if rep.fails else 0


if __name__ == "__main__":
    sys.exit(main())
