#!/usr/bin/env python3
"""Post-install check for a real machine. Prints PASS/FAIL/SKIP per check; exit 1 if any FAIL.

Read-only: it never writes to the Claude or Codex folders, only to temp dirs.
"""
import argparse
import json
import os
import platform
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
PLAN = "## Task 1: a\nGoal: g\nScope:\n- src/feature/**\nDone:\n- d\n"
MANUAL = """Manual checks (needs the app open):
  1. In Claude Code, send any prompt; the reply context shows a "Jev route:" line (when OPENROUTER_API_KEY is set).
  2. In a scratch git repo, run /orchestrate on a tiny task (or create .orchestrate/PLAN.md and active.json by hand);
     ask Claude to write a file outside the Scope. The scope lock must deny it.
  3. In Codex, ask it to edit a file outside the Scope (apply_patch). It must be denied.
  4. Report the output of this script and these steps in an issue."""


class Report:
    def __init__(self):
        self.fails = 0

    def say(self, status, name, detail=""):
        if status == "FAIL":
            self.fails += 1
        print("%-4s  %s%s" % (status, name, ("  (" + detail + ")") if detail else ""))


def load(d):
    try:
        return json.loads((d / ".dryas-installed.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run_hook(cmd, ev, env):
    event = dict(SAMPLES.get(ev, {}), hook_event_name=ev, cwd=tempfile.gettempdir(), session_id="release-check")
    data = json.dumps(event, ensure_ascii=False).encode("utf-8")
    try:
        r = subprocess.run(cmd, shell=True, input=data, capture_output=True, env=env, timeout=120)  # portable-ok: tests the OS default shell
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
        e = {k: v for k, v in env.items() if k != "OPENROUTER_API_KEY"}
        e["JEV_LOG_DIR"] = str(wt / "logs")
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
    if not env.get("OPENROUTER_API_KEY"):
        return rep.say("SKIP", "Jev route", "OPENROUTER_API_KEY not set")
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", str(chain), "prompt"],
                           input=json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "fix a typo in the readme",
                                             "cwd": tempfile.gettempdir(), "session_id": "release-check"}),
                           capture_output=True, universal_newlines=True, encoding="utf-8", env=env, timeout=120)
        out = r.stdout
    except (OSError, subprocess.TimeoutExpired) as ex:
        out = ""
    rep.say("PASS" if "Jev " in out else "WARN", "Jev route", "" if "Jev " in out else "no 'Jev ' line in output")


def ruflo(rep, cd, env):
    run = cd / "ruflo" / "run.py"
    if not run.is_file():
        return rep.say("SKIP", "Ruflo", "not installed")
    root = Path(env.get("DRYAS_DATA_ROOT") or Path.home() / ".dryas")
    ok = root.is_dir() and os.access(str(root), os.W_OK)
    rep.say("PASS" if ok else "FAIL", "Ruflo data root writable", str(root))
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", str(run), "helper", "node", str(Path(tempfile.gettempdir()) / "dryas-nonexistent-xyz")],
                           input="", capture_output=True, universal_newlines=True, encoding="utf-8", env=env, timeout=120)
        ok = r.returncode == 0 and not r.stdout.strip()
        why = "" if ok else "exit %s %s" % (r.returncode, r.stdout.strip()[:80])
    except (OSError, subprocess.TimeoutExpired) as ex:
        ok, why = False, str(ex)
    rep.say("PASS" if ok else "FAIL", "Ruflo helper runs silently", why)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check a Dryas Workflow install on this machine (read-only).")
    ap.add_argument("--claude-dir", default=str(Path.home() / ".claude"))
    ap.add_argument("--codex-dir", default=os.environ.get("CODEX_HOME") or str(Path.home() / ".codex"))
    a = ap.parse_args(argv)
    cd, cdx = Path(a.claude_dir), Path(a.codex_dir)
    env = dict(os.environ)
    rep = Report()
    print("Environment")
    rep.say("PASS", "OS", "%s %s" % (platform.system(), platform.release()))
    rep.say("PASS", "Python", "%s at %s" % (platform.python_version(), sys.executable))
    for t in ("git", "claude", "codex", "node"):
        p = shutil.which(t)
        rep.say("PASS" if p else "SKIP", t, p or "not on PATH")
    rep.say("PASS" if env.get("OPENROUTER_API_KEY") else "SKIP", "OPENROUTER_API_KEY", "set" if env.get("OPENROUTER_API_KEY") else "not set")
    chain = cd / "jev" / "chain.py"
    rec = load(cd)
    if rec is None:
        rep.say("SKIP", "Claude install", "no .dryas-installed.json in %s" % cd)
    else:
        hooks = [(h[0], h[2]) for h in rec.get("settings", {}).get("hooks", [])]
        check_hooks(rep, "Claude", hooks, env)
        scope_lock(rep, chain, "claude", env)
        jev_route(rep, chain, env)
        ruflo(rep, cd, env)
    crec = load(cdx)
    if crec is None:
        rep.say("SKIP", "Codex install", "no .dryas-installed.json in %s" % cdx)
    else:
        check_hooks(rep, "Codex", codex_hooks(cdx, crec), env)
        scope_lock(rep, chain, "codex", env)
    print()
    print(MANUAL)
    return 1 if rep.fails else 0


if __name__ == "__main__":
    sys.exit(main())
