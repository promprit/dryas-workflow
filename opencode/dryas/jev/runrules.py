#!/usr/bin/env python3
"""Run rules for the Jev gate during an unattended run: is a risky command already decided?

covered(cmd, root, cwd) -> "planned" | "orchestrator" | None
  The command is covered when at least one of its simple commands matches an entry and every simple command the
  local judge calls risky (destructive or dangerous) is matched:
  - planned: an entry of `## Risky actions` in <root>/.orchestrate/PLAN.md (the user approved it with the plan),
    exact, or a prefix ending in `*` matched word by word ("pnpm db:reset*" matches "pnpm db:reset --force",
    not "pnpm db:resetall");
  - orchestrator: an exact "cmd" of <root>/.orchestrate/approved.json, {"commands": [{"cmd", "task", "reason"}]},
    which only the orchestrator (main thread) writes.
  Human-only actions (human_only) are matched only by an exact plan entry: never by a plan prefix or approved.json.
Never raises: unreadable files cover nothing.
"""
import json
import os
import shlex
import sys
from typing import Any, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_judge as lj
import planfile
import shellwrites

HUMAN_ONLY_HEADS = {"vercel", "netlify", "fly", "flyctl", "heroku", "firebase", "wrangler", "terraform", "pulumi",
                    "gcloud", "az", "aws", "kubectl", "helm", "eas", "fastlane", "supabase"}
HUMAN_ONLY_SUBS = {"git": {"push"}, "gh": {"release", "repo", "secret", "workflow", "pr"}}


def _read(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _words(entry: str) -> List[str]:
    try:
        return shlex.split(entry)
    except ValueError:
        return []


def human_only(words: List[str], root: str, cwd: str) -> bool:
    """Push, deploy and cloud commands, and deletes or writes whose readable target is outside the worktree."""
    h, _ = lj.head_index(words)
    if h >= len(words):
        return False
    name, rest = lj.base(words[h]), [w for w in words[h + 1:] if not w.startswith("-")]
    if name in HUMAN_ONLY_HEADS or (rest and rest[0] in HUMAN_ONLY_SUBS.get(name, ())):
        return True
    a = shellwrites.analyse(" ".join(shlex.quote(w) for w in words), cwd)
    real_root = os.path.realpath(root)
    return any(not (os.path.realpath(p) + os.sep).startswith(real_root + os.sep) for p in a.paths)


def covered(cmd: str, root: str, cwd: str) -> Optional[str]:
    try:
        entries = planfile.risky(_read(os.path.join(root, ".orchestrate", "PLAN.md")))
        try:
            approved = [str(c.get("cmd", "")) for c in json.loads(_read(os.path.join(root, ".orchestrate",
                                                                                      "approved.json")) or "{}")
                        .get("commands", []) if isinstance(c, dict)]
        except (ValueError, AttributeError):
            approved = []
        exact = [_words(e) for e in entries if not e.endswith("*")]
        prefix = [_words(e[:-1]) for e in entries if e.endswith("*")]
        mine = [_words(c) for c in approved]
        rule, matched = None, False
        for c in lj.simple_commands(cmd):
            w = c.words
            if not w:
                continue
            ho = human_only(w, root, cwd)
            if w in exact:
                hit = "planned"
            elif not ho and any(p and w[:len(p)] == p for p in prefix):
                hit = "planned"
            elif not ho and w in mine:
                hit = "orchestrator"
            else:
                hit = None
            text = " ".join(shlex.quote(x) for x in w)
            if hit:
                matched, rule = True, rule or hit
            elif ho or lj.destructive(text) or lj.danger(text):
                return None
        return rule if matched else None
    except Exception:
        return None
