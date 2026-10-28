#!/usr/bin/env python3
"""Is the lens release no worse than the previous release on design tasks? Spec 2026-10-28-lens-design.md §8.

  python3 tools/compare_lens.py --old DIR [--runs N] [--claude PATH]   exit 0 PASS, 1 FAIL, 2 setup error

Runs each prompt in tools/fixtures/lens/ headless (`claude -p ... --output-format json --plugin-dir <side>/claude`)
on the old release checkout (DIR) and on this checkout, sides alternating per run, in a fresh temp folder each time.
PASS when, per prompt: the median added time is at most 90 s (wall time of the whole run); the median added
main-session tokens are at most 25k (input + output + cache creation, no cache reads, of the main model only: the
model with the most output tokens in modelUsage, so a fast-tier subagent's tokens do not count; falls back to the
whole-run usage sum when modelUsage is absent); the median added total cost is at most $0.25 (what the user pays,
all models); the new side never has more permission prompts (denials in -p mode) than the old; and every new-side
run produced a ## Lens block (a `## Lens` line, then a `- Panel: ` line and a `- Verdict: ` line).
Prompts are counted as permission_denials in -p mode: a tool that would ask interactively shows up only when it is
denied there. Run logs go to a temp JEV_LOG_DIR, never ~/.dryas/jev/logs.
The account's installed Dryas plugin is switched off for each run with --settings, so only the --plugin-dir copy
loads; the user's settings files are not changed. The allow list is additive: --settings merges with the account's
own settings, so rules the user already allowed apply to both sides. Entries with installer placeholders ($CD and so
on) are dropped on both sides. A missing or unreadable settings fragment is a setup error (exit 2) before any run.
Prompts are compared as the maximum per fixture on each side.
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tools/fixtures/lens"
MAX_MS = 90000
MAX_TOKENS = 25000
MAX_COST_USD = 0.25
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens")
MODEL_TOKEN_KEYS = ("inputTokens", "outputTokens", "cacheCreationInputTokens")


def main_tokens(d: dict) -> int:
    """Tokens of the main session: the model with the most output tokens in modelUsage; else the usage sum."""
    models = [m for m in (d.get("modelUsage") or {}).values() if isinstance(m, dict)]
    if models:
        main = max(models, key=lambda m: int(m.get("outputTokens") or 0))
        return sum(int(main.get(k) or 0) for k in MODEL_TOKEN_KEYS)
    usage = d.get("usage") or {}
    return sum(int(usage.get(k) or 0) for k in TOKEN_KEYS)


def has_lens_block(text: str) -> bool:
    """A `## Lens` line, then (anywhere after it) a `- Panel: ` line and a `- Verdict: ` line."""
    head = re.search(r"^## Lens\s*$", text, re.M)
    if not head:
        return False
    rest = text[head.end():]
    return re.search(r"^- Panel: ", rest, re.M) is not None and re.search(r"^- Verdict: ", rest, re.M) is not None


class RunError(Exception):
    """A headless run failed: a setup error, not a verdict on the release."""


def build_env(tmp: Path) -> dict:
    return {**os.environ, "JEV_LOG_DIR": str(tmp / "logs"), "JEV_THRESHOLDS": str(tmp / "thresholds.json")}


def parse_result(stdout: str) -> Dict[str, object]:
    try:
        d = json.loads(stdout)
    except ValueError as e:
        raise ValueError("not a claude -p json result: %s" % e)
    if not isinstance(d, dict) or "duration_ms" not in d:
        raise ValueError("not a claude -p json result")
    if d.get("is_error"):
        raise ValueError("claude reported an error: %s" % str(d.get("result", ""))[:200])
    return {"ms": int(d["duration_ms"]), "tokens": main_tokens(d),
            "prompts": len(d.get("permission_denials") or []),
            "lens": has_lens_block(str(d.get("result") or "")),
            "cost": float(d.get("total_cost_usd") or 0)}


def verdict(old: List[Dict[str, object]], new: List[Dict[str, object]], max_ms: int = MAX_MS,
            max_tokens: int = MAX_TOKENS) -> Tuple[bool, List[str]]:
    med = lambda runs, k: statistics.median(r[k] for r in runs)
    dms, dtok = med(new, "ms") - med(old, "ms"), med(new, "tokens") - med(old, "tokens")
    dcost = med(new, "cost") - med(old, "cost")
    lines, ok = [], True
    if dms > max_ms:
        ok = False
        lines.append("FAIL time: +%d ms median (limit %d)" % (dms, max_ms))
    if dtok > max_tokens:
        ok = False
        lines.append("FAIL tokens: +%d median (limit %d)" % (dtok, max_tokens))
    if dcost > MAX_COST_USD:
        ok = False
        lines.append("FAIL cost: +$%.2f median (limit $%.2f)" % (dcost, MAX_COST_USD))
    if max(r["prompts"] for r in new) > max(r["prompts"] for r in old):
        ok = False
        lines.append("FAIL prompts: new side asked more often than the old one")
    if not all(r["lens"] for r in new):
        ok = False
        lines.append("FAIL lens: the new side did not produce a ## Lens block")
    lines.append("time +%d ms, main-session tokens +%d" % (dms, dtok))
    lines.append("cost %s$%.4f" % ("+" if dcost >= 0 else "-", abs(dcost)))
    return ok, lines


def side_allow(side: Path) -> List[str]:
    """The core allow list of one side's settings fragment, minus installer placeholders ($CD, $DATA_RULE...).

    Raises RunError when the fragment is missing, not JSON, or has no core.permissions.allow list.
    """
    try:
        frag = json.loads((side / "claude" / "settings.fragment.json").read_text(encoding="utf-8"))
        allow = frag["core"]["permissions"]["allow"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise RunError("%s: settings fragment missing or unreadable: %s" % (side, e))
    if not isinstance(allow, list):
        raise RunError("%s: settings fragment missing or unreadable: no core.permissions.allow list" % side)
    return [r for r in allow if "$" not in r]


def build_cmd(claude: str, side: Path, prompt: str, allow: List[str]) -> List[str]:
    off = json.dumps({"enabledPlugins": {"dryas@dryas-workflow": False}, "permissions": {"allow": allow}})
    return [claude, "-p", prompt, "--output-format", "json", "--settings", off, "--plugin-dir", str(side / "claude")]


def run_once(claude: str, side: Path, prompt: str, name: str, allow: List[str]) -> Dict[str, object]:
    where = "side %s, fixture %s" % (side, name)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            p = subprocess.run(build_cmd(claude, side, prompt, allow), cwd=tmp, env=build_env(Path(tmp)),
                               capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            raise RunError("timed out (900 s): %s" % where)
        if p.returncode != 0:
            raise RunError("claude exited %d: %s; stderr: %s" % (p.returncode, where, p.stderr.strip()[:200]))
        try:
            return parse_result(p.stdout)
        except ValueError as e:
            raise RunError("%s: %s" % (where, e))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--old", required=True, type=Path, help="checkout of the previous release (e.g. v2.5.0)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--claude", default="claude")
    a = ap.parse_args(argv)
    if a.runs < 1:
        print("--runs must be at least 1", file=sys.stderr)
        return 2
    a.old = a.old.resolve()
    if not (a.old / "claude").is_dir():
        print("no claude/ in %s" % a.old, file=sys.stderr)
        return 2
    ok = True
    try:
        allow = {side: side_allow(side) for side in (a.old, REPO)}
        for f in sorted(FIXTURES.glob("*.md")):
            prompt = f.read_text(encoding="utf-8").strip()
            old, new = [], []
            for i in range(a.runs):
                for side, out in ((a.old, old), (REPO, new)) if i % 2 == 0 else ((REPO, new), (a.old, old)):
                    out.append(run_once(a.claude, side, prompt, f.stem, allow[side]))
            good, lines = verdict(old, new)
            ok = ok and good
            print("%s: %s" % (f.stem, "PASS" if good else "FAIL"))
            for l in lines:
                print("  " + l)
    except RunError as e:
        print("setup error: %s" % e, file=sys.stderr)
        return 2
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
