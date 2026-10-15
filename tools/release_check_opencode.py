"""OpenCode part of tools/release_check.py: checks one OpenCode config dir, read-only.
Hooks and the jev MCP server run with a temp data root (the sandbox env), never the user's ~/.dryas."""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "install"))
import dryas_install as di  # noqa: E402
import opencode_setup as ocs  # noqa: E402


def _rules_ok(od: Path, env: dict) -> bool:
    rc, out = di.capture(di.PYX + [str(od / "dryas/jev/rules_inject.py"), "--harness", "opencode"], "{}", env=env,
                         timeout=60)
    try:
        return "Dryas paths:" in json.loads(out)["hookSpecificOutput"]["additionalContext"]
    except (ValueError, KeyError, TypeError):
        return False


def _mcp_connected(opencode: str, od: Path, env: dict) -> Tuple[bool, str]:
    """`opencode mcp list` from a temp dir, with XDG_CONFIG_HOME pointing at od's parent when od is named opencode."""
    run_env = dict(env)
    if od.name == "opencode":
        run_env["XDG_CONFIG_HOME"] = str(od.parent)
    try:
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([opencode, "mcp", "list"], cwd=d, env=run_env, capture_output=True,
                               universal_newlines=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    text = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout + r.stderr)
    line = next((l for l in text.splitlines() if re.search(r"\bjev\b", l)), "")
    return ("connected" in line), (line.strip() or "jev not listed")


def check(rep, od: Path, opencode: Optional[str], env: dict) -> None:
    print()
    print("OpenCode: %s" % od)
    if not opencode:
        rep.say("SKIP", "Dryas for OpenCode", "opencode not on PATH")
        return
    try:
        rec = json.loads((od / ocs.RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rep.say("SKIP", "Dryas for OpenCode", "not set up in %s" % od)
        return
    rc, out = di.capture([opencode, "--version"], timeout=60)
    ver = ocs.opencode_version(out) if rc == 0 else None
    ok = ver is not None and ver >= ocs.MIN_OPENCODE
    rep.say("PASS" if ok else "FAIL", "OpenCode %s or newer" % ".".join(map(str, ocs.MIN_OPENCODE)), out.strip())
    files = rec.get("files") if isinstance(rec.get("files"), dict) else {}
    missing = [r for r in files if not (od / r).is_file()]
    edited = [r for r, sha in files.items() if (od / r).is_file()
              and hashlib.sha256((od / r).read_bytes()).hexdigest() != sha]
    rep.say("FAIL" if missing else "PASS", "installed files present", ", ".join(missing[:3]))
    rep.say("WARN" if edited else "PASS", "installed files unchanged",
            ("edited after setup: " + ", ".join(edited[:3])) if edited else "")
    if od.name != "opencode":
        rep.say("SKIP", "jev MCP server connects",
                "OpenCode reads <XDG_CONFIG_HOME>/opencode; re-run with a dir named opencode")
    else:
        ok, why = _mcp_connected(opencode, od, env)
        rep.say("PASS" if ok else "FAIL", "jev MCP server connects", why)
    rep.say("PASS" if _rules_ok(od, env) else "FAIL", "rules hook prints the OpenCode rules")
    rep.say("PASS" if di.scope_smoke(od / "dryas/jev/chain.py", {}, harness="opencode") else "FAIL",
            "scope lock blocks an out-of-scope apply_patch")
    models = set()
    for t in ocs.TIERS:
        p = od / ("agent/dryas-executor-%s.md" % t)
        m = re.search(r"^model:\s*(\S+)", p.read_text(encoding="utf-8"), re.M) if p.is_file() else None
        models.add(m.group(1) if m else "")
    rep.say("WARN" if len(models) <= 1 else "PASS", "executor tiers",
            "all tiers on one model; re-run setup with --tier-*" if len(models) <= 1 else "")
