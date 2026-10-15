"""What `dryas cloud` copies into a repo (owned core E). build() returns bytes per repo path and writes nothing.

- Always: the Dryas core. Its runtime goes in .dryas/ (jev/ without tests, pstack/, bin/dryas-py,
  docs/dryas-workflow.md, licences), its skills, commands and executor agent under .claude/.
- --with-design: the design skills of the plugins install/components.json installs, each only with a confirmed
  licence (its text in .dryas/licenses/, a line in .dryas/NOTICE).
- --with-own NAME: that skill from the user's Claude config dir, after a redact.py scan; a hit stops it until
  --confirm-own NAME.

A skill is skipped and reported, never copied, when:
- its licence is not confirmed;
- a Python file needs a pip package;
- a file names a Mac path, ~/.dryas or a plugin file outside the skill;
- a file is over 5 MB."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
for _d in (ROOT / "tools", ROOT / "install", ROOT / "claude" / "jev"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
import cloud_check as cc  # noqa: E402
import cloud_text as ct  # noqa: E402
import redact  # noqa: E402
import render  # noqa: E402

CORE_SKILLS = ("orchestrate", "brainstorm", "plan", "review-request", "review-receive", "tdd", "debug", "verify",
               "worktree", "interrogate")
CORE_COMMANDS = ("orchestrate", "wplan", "wreview", "commit", "tune", "handoff", "dryas-cloud")
CORE_AGENTS = ("executor",)
COMPS = ("core", "jev", "memory", "pstack-picks")  # chain.json stages and rules blocks a repo copy keeps
DESIGN: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "ui-ux-pro-max@ui-ux-pro-max-skill": ("MIT", ("ui-ux-pro-max", "design", "design-system", "banner-design",
                                                   "brand", "slides", "ui-styling")),
    "impeccable@impeccable": ("Apache-2.0", ("impeccable",)),
}
NOT_COPIED = (
    ("update-my-vault", "its vault and sources are on the Mac"),
    ("fo-iterm", "it drives iTerm on the Mac"),
    ("claude-hud", "a local status line"),
    ("Ruflo", "needs Node and npm"),
    ("Superpowers", "the Dryas process skills replace it"),
    ("Playwright MCP", "needs npm and network"),
    ("Context7 MCP", "needs network"),
    ("GitHub MCP", "needs network"),
    ("Codex files", "cloud sessions run Claude Code"),
)
OWN_EXCLUDED = ("update-my-vault", "fo-iterm", "claude-hud")
CORE_SKIP = frozenset(("rules_inject.py",))  # the plugin's SessionStart hook; the CLAUDE.md block replaces it
SKIP_DIRS = frozenset(("tests", "logs", "compact", "__pycache__", ".pytest_cache"))
TEXT = (".md", ".template")
MAX_FILE = 5 * 1024 * 1024
DRYAS_LICENCE = ".dryas/licenses/LICENSE-dryas"
SP_LICENCE = ".dryas/licenses/LICENSE-superpowers"
PSTACK_LICENCE = ".dryas/pstack/LICENSE"
_OWN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_APACHE = re.compile(r"(?i)apache[- ]?(?:license[- ])?(?:version[- ])?2\.0")
Entry = Dict[str, Any]
Files = Dict[str, Tuple[bytes, bool]]


class _Same(dict):
    """A render.chain_bytes mapping that keeps every placeholder ($CD, $PY, $DRYAS_DATA_ROOT, $HOME): chain.py
    expands them at run time, so the copy names no absolute path."""

    def __contains__(self, key: object) -> bool:
        return True

    def __missing__(self, key: str) -> str:
        return "$" + key


def _walk(base: Path) -> Iterator[Tuple[str, Path]]:
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base)
        if p.is_file() and not p.is_symlink() and not set(rel.parts[:-1]) & SKIP_DIRS and p.suffix != ".pyc" and p.name != ".gitignore":
            yield rel.as_posix(), p


_GIT_EXECS: Dict[str, frozenset] = {}


def _git_execs(d: Path) -> frozenset:
    """Paths git records as 100755 in the work tree holding d (Windows has no exec bit on disk)."""
    key = str(d)
    if key not in _GIT_EXECS:
        try:
            top = subprocess.run(["git", "-C", key, "rev-parse", "--show-toplevel"], capture_output=True,
                                 universal_newlines=True, timeout=30).stdout.strip()
            out = subprocess.run(["git", "-C", top, "ls-files", "-s"], capture_output=True, universal_newlines=True,
                                 timeout=30).stdout if top else ""
        except (OSError, subprocess.SubprocessError):
            top, out = "", ""
        _GIT_EXECS[key] = frozenset(os.path.normcase(os.path.join(top, ln.split("\t", 1)[1]))
                                    for ln in out.splitlines() if ln.startswith("100755 ") and "\t" in ln)
    return _GIT_EXECS[key]


def _exec(p: Path) -> bool:
    if os.name == "nt":
        return os.path.normcase(os.path.abspath(str(p))) in _git_execs(p.parent)
    return os.access(str(p), os.X_OK)


def entry(data: bytes, source: str, group: str, version: str, licence: str, licence_file: str, notice: str,
          exe: bool = False) -> Entry:
    return dict(data=data, source=source, group=group, version=version, licence=licence, licence_file=licence_file,
                notice=notice, exec=exe)


def version(repo: Path) -> str:
    return str(json.loads((repo / "claude/.claude-plugin/plugin.json").read_text(encoding="utf-8")).get("version", ""))


def commit(repo: Path) -> str:
    try:
        p = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30)
        return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def names(prefix: str) -> ct.Names:
    return ct.Names(prefix, CORE_SKILLS, CORE_COMMANDS, CORE_AGENTS)


def dryas_notice(ver: str) -> str:
    return "- Dryas %s (MIT): %s" % (ver, DRYAS_LICENCE)


def core(repo: Path, nm: ct.Names, ver: str, persist_memory: bool) -> Dict[str, Entry]:
    out: Dict[str, Entry] = {}
    dn = dryas_notice(ver)

    def text(f: Path, name: Optional[str] = None) -> bytes:
        t = ct.rewrite(f.read_text(encoding="utf-8"), nm, COMPS)
        return (ct.set_name(t, name) if name else t).encode("utf-8")

    def put(rel: str, f: Path, data: Optional[bytes] = None, lic: str = DRYAS_LICENCE, notice: str = dn) -> None:
        if data is None:
            data = text(f) if f.suffix in TEXT else f.read_bytes()
        out[rel] = entry(data, f.relative_to(repo).as_posix(), "dryas", ver, "MIT", lic, notice, _exec(f))

    for rel, f in _walk(repo / "claude/jev"):
        if rel in CORE_SKIP:
            continue
        put(".dryas/jev/" + rel, f, render.chain_bytes(f, list(COMPS), _Same()) if rel == "chain.json" else None)
    for rel, f in _walk(repo / "claude/pstack"):
        put(".dryas/pstack/" + rel, f, lic=PSTACK_LICENCE,
            notice="- pstack picks (MIT; see .dryas/pstack/NOTICE.md): " + PSTACK_LICENCE)
    put(".dryas/bin/dryas-py", repo / "claude/bin/dryas-py")
    put(".dryas/docs/dryas-workflow.md", repo / "docs/workflow.md")
    put(DRYAS_LICENCE, repo / "claude/LICENSE")
    put(SP_LICENCE, repo / "claude/skills/LICENSE-superpowers", lic=SP_LICENCE,
        notice="- Superpowers (MIT), adapted in the Dryas process skills: " + SP_LICENCE)
    for s in CORE_SKILLS:
        for rel, f in _walk(repo / "claude/skills" / s):
            name = nm.name(s) if rel == "SKILL.md" and nm.prefix else None
            put(".claude/skills/%s/%s" % (nm.name(s), rel), f, text(f, name) if f.suffix in TEXT else None)
    for c in CORE_COMMANDS:
        put(".claude/commands/%s.md" % nm.name(c), repo / "claude/commands" / (c + ".md"))
    for a in CORE_AGENTS:
        f = repo / "claude/agents" / (a + ".md")
        put(".claude/agents/%s.md" % nm.name(a), f, text(f, nm.name(a)))
    if persist_memory:
        out[".dryas/memory/notes/.gitkeep"] = entry(b"", "dryas cloud --persist-memory", "dryas", ver, "MIT",
                                                    DRYAS_LICENCE, dn)
    return out


def design_plugins(repo: Path) -> List[str]:
    """The design plugins install/components.json installs (its `claude plugin install <id>` commands)."""
    comp = json.loads((repo / "install/components.json").read_text(encoding="utf-8")).get("design", {})
    return [c[3] for c in comp.get("commands", []) if c[:3] == ["claude", "plugin", "install"] and len(c) > 3]


def _installed(claude_dir: Path, pid: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads((claude_dir / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        recs = data.get("plugins", {}).get(pid) or []
        rec = recs[0] if isinstance(recs, list) and recs else None
        return rec if isinstance(rec, dict) and rec.get("installPath") else None
    except (OSError, ValueError, AttributeError):
        return None


def _skills_rel(install: Path) -> str:
    try:
        v = json.loads((install / ".claude-plugin/plugin.json").read_text(encoding="utf-8")).get("skills", "./skills/")
    except (OSError, ValueError, AttributeError):
        v = "./skills/"
    v = v[0] if isinstance(v, list) and v else v
    v = v if isinstance(v, str) else "./skills/"
    return (v[2:] if v.startswith("./") else v).strip("/")


def _licence_text(dirs: Tuple[Path, ...], licence: str) -> Optional[bytes]:
    for d in dirs:
        try:
            data = (d / "LICENSE").read_bytes()
        except OSError:
            continue
        head = data[:600].decode("utf-8", "replace")
        if licence == "MIT" and "MIT License" in head:
            return data
        if licence == "Apache-2.0" and "Apache License" in head and "Version 2.0" in head:
            return data
    return None


def _front_licence(skill_md: Path) -> str:
    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    if not text.startswith("---") or text.count("---") < 2:
        return ""
    m = re.search(r"(?m)^license:\s*(.+)$", text.split("---", 2)[1])
    return m.group(1).strip() if m else ""


def _skill_files(src: Path, dst: str, fix_md: Callable[[str], str]) -> Tuple[Files, str]:
    """({repo path: (bytes, executable)}, "") or ({}, why the skill is skipped)."""
    out: Files = {}
    for rel, f in _walk(src):
        if f.stat().st_size > MAX_FILE:
            return {}, "%s is over 5 MB" % rel
        data = f.read_bytes()
        try:
            text: Optional[str] = data.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        if text is not None and f.suffix in TEXT:
            text = fix_md(text)
            data = text.encode("utf-8")
            if ct.PLUGIN in text:
                return {}, "%s names a plugin file outside the skill folder" % rel
        if text is not None:
            if cc.MAC_PATH.search(text):
                return {}, "%s names an absolute Mac path" % rel
            if cc.HOME_STATE.search(text):
                return {}, "%s names ~/.dryas" % rel
            if f.suffix == ".py":
                bad = cc.nonstdlib_imports(text, cc.siblings(str(f)))
                if bad:
                    return {}, "%s needs %s (not stdlib)" % (rel, ", ".join(bad))
        out["%s/%s" % (dst, rel)] = (data, _exec(f))
    return out, ""


def _named(files: Files, nm: ct.Names, skill: str) -> Files:
    """With --prefix, the copied SKILL.md carries the new name."""
    k = ".claude/skills/%s/SKILL.md" % nm.name(skill)
    if nm.prefix and k in files:
        data, exe = files[k]
        files[k] = (ct.set_name(data.decode("utf-8"), nm.name(skill)).encode("utf-8"), exe)
    return files


def design(repo: Path, claude_dir: Path, nm: ct.Names, skipped: List[Tuple[str, str]]) -> Dict[str, Entry]:
    out: Dict[str, Entry] = {}
    for pid in design_plugins(repo):
        if pid not in DESIGN:
            skipped.append((pid, "licence not confirmed (not in the cloud licence table)"))
            continue
        licence, skills = DESIGN[pid]
        rec = _installed(claude_dir, pid)
        if rec is None:
            skipped.append((pid, "not installed in this Claude config dir"))
            continue
        install, ver = Path(str(rec["installPath"])), str(rec.get("version") or "?")
        mkt = claude_dir / "plugins" / "marketplaces" / pid.split("@", 1)[1]
        rel_root = _skills_rel(install)
        text = _licence_text((install, mkt), licence)
        if licence == "Apache-2.0" and not _APACHE.search(_front_licence(install / rel_root / skills[0] / "SKILL.md")):
            text = None
        if text is None:
            skipped.append((pid, "licence not confirmed (%s text not found)" % licence))
            continue
        short = pid.split("@", 1)[0]
        lic = ".dryas/licenses/%s-LICENSE" % short
        notice = "- %s %s (%s): %s" % (pid, ver, licence, lic)

        def put(rel: str, data: bytes, src: str, exe: bool = False) -> None:
            out[rel] = entry(data, src, "design", ver, licence, lic, notice, exe)

        put(lic, text, "plugin:%s/LICENSE" % pid)
        for nf in ("NOTICE", "NOTICE.md"):  # Apache-2.0 asks redistributors to carry the NOTICE file
            found = next((d / nf for d in (install, mkt) if (d / nf).is_file()), None)
            if found is not None:
                put(".dryas/licenses/%s-%s" % (short, nf), found.read_bytes(), "plugin:%s/%s" % (pid, nf))
                break
        renames = {s: nm.name(s) for s in skills}
        for s in skills:
            src = install / rel_root / s
            if not (src / "SKILL.md").is_file():
                skipped.append(("%s/%s" % (pid, s), "not found in the installed plugin"))
                continue
            files, why = _skill_files(src, ".claude/skills/" + nm.name(s),
                                      lambda t, r=rel_root, n=renames: ct.third_party(t, r, n))
            if why:
                skipped.append(("%s/%s" % (pid, s), why))
                continue
            for rel, (data, exe) in _named(files, nm, s).items():
                put(rel, data, "plugin:%s/%s/%s" % (pid, rel_root, s), exe)
    return out


def _binaries(src: Path) -> List[str]:
    bad: List[str] = []
    for rel, f in _walk(src):
        try:
            f.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            bad.append(rel)
        except OSError:
            continue
    return bad


def _secret_lines(src: Path) -> List[str]:
    hits: List[str] = []
    for rel, f in _walk(src):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        hits += ["%s:%d" % (rel, n) for n, line in enumerate(text.splitlines(), 1) if redact.redact(line) != line]
    return hits


def confirm_sha(src: Path) -> str:
    """sha256 of what an own skill's --confirm-own covers: its redaction hits (place and text) and each file it
    cannot scan (path and sha256), so `dryas cloud` keeps a confirmation until one of them changes."""
    parts = []
    for hit in _secret_lines(src):
        rel, n = hit.rsplit(":", 1)
        lines = (src / rel).read_text(encoding="utf-8").splitlines()
        parts.append("%s\0%s" % (hit, lines[int(n) - 1]))
    parts += ["%s\0%s" % (rel, cc.sha256((src / rel).read_bytes())) for rel in _binaries(src)]
    return cc.sha256("\n".join(parts).encode("utf-8"))


def own(claude_dir: Path, wanted: List[str], confirmed: List[str], nm: ct.Names,
        skipped: List[Tuple[str, str]]) -> Dict[str, Entry]:
    out: Dict[str, Entry] = {}
    reasons = dict(NOT_COPIED)
    for name in wanted:
        src = claude_dir / "skills" / name
        if not _OWN_NAME.match(name):
            skipped.append((name, "not a skill folder name"))
            continue
        if name.lower() in OWN_EXCLUDED:
            skipped.append((name, "excluded: " + reasons[name.lower()]))
            continue
        if not (src / "SKILL.md").is_file():
            skipped.append((name, "no skills/%s/SKILL.md in the Claude config dir" % name))
            continue
        if any(p.name.upper().startswith(("LICENSE", "LICENCE", "COPYING")) for p in src.iterdir()):
            skipped.append((name, "it has a licence file, so it is not an own skill"))
            continue
        hits = _secret_lines(src)
        if hits and name not in confirmed:
            skipped.append((name, "secret-shaped text at %s; review it, then pass --confirm-own %s"
                            % (", ".join(hits[:5]), name)))
            continue
        blobs = _binaries(src)
        if blobs and name not in confirmed:
            skipped.append((name, "binary file %s cannot be scanned; review it, then pass --confirm-own %s"
                            % (", ".join(blobs[:5]), name)))
            continue
        files, why = _skill_files(src, ".claude/skills/" + nm.name(name), lambda t: t)
        if why:
            skipped.append((name, why))
            continue
        notice = "- own skill %s (the repo owner's; not licensed by Dryas)" % name
        for rel, (data, exe) in _named(files, nm, name).items():
            out[rel] = entry(data, "own:" + name, "own", "", "own", "", notice, exe)
    return out


def build(repo: Path, opts: Dict[str, Any], claude_dir: Path) -> Dict[str, Any]:
    nm = names(str(opts.get("prefix") or ""))
    ver = version(repo)
    skipped: List[Tuple[str, str]] = []
    files = core(repo, nm, ver, bool(opts.get("persist_memory")))
    if opts.get("design"):
        files.update(design(repo, Path(claude_dir), nm, skipped))
    if opts.get("own"):
        files.update(own(Path(claude_dir), list(opts["own"]), list(opts.get("confirm_own") or []), nm, skipped))
    return dict(files=files, skipped=skipped, names=nm, version=ver, commit=commit(repo))


def _component(rec: Any) -> List[str]:
    """The plan's skip names a manifest record belongs to: an own skill, a design plugin or one of its skills."""
    src = str((rec or {}).get("source") or "")
    if src.startswith("own:"):
        return [src[4:]]
    if src.startswith("plugin:"):
        pid, _, rest = src[7:].partition("/")
        return [pid, pid + "/" + rest.rsplit("/", 1)[-1]]
    return []


def why_skipped(rec: Any, skipped: Dict[str, str]) -> Optional[str]:
    return next((skipped[k] for k in _component(rec) if k in skipped), None)


def finish(plan: Dict[str, Any]) -> None:
    """Add .dryas/NOTICE (every licence line) and .dryas/VERSION (version, commit, hash of every other file)."""
    files, ver = plan["files"], plan["version"]
    dn = dryas_notice(ver)
    lines = sorted({e["notice"] for e in files.values() if e["notice"]} | {dn})
    head = "Dryas %s, copied into this repo by `dryas cloud`. Licences of the copied material:\n" % ver
    files[cc.NOTICE] = entry((head + "\n".join(lines) + "\n").encode("utf-8"), "dryas cloud", "dryas", ver, "MIT",
                             DRYAS_LICENCE, dn)
    shas = {rel: cc.sha256(e["data"]) for rel, e in files.items() if rel != cc.VERSION}
    text = "version: %s\ncommit: %s\nfiles: %s\n" % (ver, plan["commit"], cc.files_hash(shas))
    files[cc.VERSION] = entry(text.encode("utf-8"), "dryas cloud", "dryas", ver, "MIT", DRYAS_LICENCE, dn)
