"""Shared helpers for the dryas cloud tests (owned core E): temp git repos, the CLI runner, and a Claude config dir
with the two design plugins laid out the way `claude plugin install` leaves them."""
import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
GIT = ["git", "-c", "user.email=dev@example.com", "-c", "user.name=Dev", "-c", "commit.gpgsign=false",
       "-c", "init.defaultBranch=main", "-c", "gc.auto=0"]  # no background gc while a test walks the repo
MIT = "MIT License\n\nCopyright (c) 2026 Example Author\n\nPermission is hereby granted, free of charge.\n"
APACHE = ("\n                                 Apache License\n                           Version 2.0, January 2004\n"
          "                        http://www.apache.org/licenses/\n\n   TERMS AND CONDITIONS\n")
UI_SKILLS = ("ui-ux-pro-max", "design", "design-system", "banner-design", "brand", "slides", "ui-styling")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(GIT + ["-C", str(repo)] + list(args), capture_output=True, text=True, check=True,
                          timeout=60).stdout


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return p


def commit_all(repo: Path, msg: str = "snapshot") -> None:
    git(repo, "add", "-A")
    if git(repo, "status", "--porcelain").strip():
        git(repo, "commit", "-qm", msg)


def git_repo(path: Path, files: Optional[Dict[str, str]] = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(GIT + ["init", "-q", str(path)], capture_output=True, check=True, timeout=60)
    for rel, text in (files or {"README.md": "# demo\n"}).items():
        _write(path / rel, text)
    commit_all(path, "init")
    return path


def git_status(repo: Path) -> str:
    return git(repo, "status", "--porcelain").strip()


def snapshot(repo: Path) -> Dict[str, bytes]:
    """Every file of the work tree (never walks into .git), by repo-relative path."""
    out: Dict[str, bytes] = {}
    for d, dirs, files in os.walk(str(repo)):
        dirs[:] = sorted(x for x in dirs if x != ".git")
        for f in files:
            p = Path(d) / f
            out[p.relative_to(repo).as_posix()] = p.read_bytes()
    return out


def run_cli(argv: List[str]) -> Tuple[int, str]:
    if str(ROOT / "tools") not in sys.path:
        sys.path.insert(0, str(ROOT / "tools"))
    import dryas_cloud
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        rc = dryas_cloud.main(argv)
    return rc, out.getvalue()


def design_config(base: Path, impeccable_licence: bool = True, pip_skill: Optional[str] = None) -> Path:
    cd = base / "claude-config"
    ui = cd / "plugins/cache/ui-ux-pro-max-skill/ui-ux-pro-max/9.9.9"
    imp = cd / "plugins/cache/impeccable/impeccable/9.9.9"
    _write(ui / ".claude-plugin/plugin.json", json.dumps({"name": "ui-ux-pro-max", "skills": "./.claude/skills/"}))
    _write(ui / "LICENSE", MIT)
    for s in UI_SKILLS:
        _write(ui / ".claude/skills" / s / "SKILL.md", "---\nname: %s\ndescription: d\n---\nRun `python "
               "\"${CLAUDE_PLUGIN_ROOT}/.claude/skills/%s/scripts/search.py\" <query>`.\n" % (s, s))
        _write(ui / ".claude/skills" / s / "scripts/search.py",
               "import json\nimport sys\n" + ("import numpy\n" if s == pip_skill else ""))
    _write(imp / ".claude-plugin/plugin.json", json.dumps({"name": "impeccable", "skills": "./skills/"}))
    _write(imp / "skills/impeccable/SKILL.md", "---\nname: impeccable\ndescription: d\nlicense: Apache 2.0\n---\n"
           "Run `\"${CLAUDE_SKILL_DIR}/scripts/impeccable\" context`.\n")
    launcher = _write(imp / "skills/impeccable/scripts/impeccable", "#!/usr/bin/env sh\necho ok\n")
    launcher.chmod(0o755)
    if impeccable_licence:
        _write(cd / "plugins/marketplaces/impeccable/LICENSE", APACHE)
        _write(cd / "plugins/marketplaces/impeccable/NOTICE.md", "Impeccable\nCopyright 2026 Example Author\n")
    _write(cd / "plugins/installed_plugins.json", json.dumps({"version": 2, "plugins": {
        "ui-ux-pro-max@ui-ux-pro-max-skill": [{"scope": "user", "installPath": str(ui), "version": "9.9.9"}],
        "impeccable@impeccable": [{"scope": "user", "installPath": str(imp), "version": "9.9.9"}]}}))
    return cd


def own_skill(claude_dir: Path, name: str, text: str) -> Path:
    return _write(claude_dir / "skills" / name / "SKILL.md", text)
