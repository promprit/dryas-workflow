#!/usr/bin/env python3
"""Check a repo copy of Dryas (`dryas cloud`, owned core E) against its manifest. Runs from the copy
(.dryas/jev/cloud_check.py, also inside a cloud session or a repo's CI) and from a Dryas checkout
(tools/dryas_cloud.py check, which adds the comparison with the checkout's files).

  cloud_check.py [--repo PATH]   one line per problem and exit 1; exit 0 when the copy is intact

Problems:
- a manifest file missing or hand-edited (drift), or a file under .dryas/ the manifest does not own;
- an absolute Mac path (a path under /Users or /Volumes) in any copied file;
- ~/.dryas or ${CLAUDE_PLUGIN_ROOT} in a copied file outside .dryas/;
- a home or Mac path in Dryas's .claude/settings.json or .mcp.json entries, or any env in its settings.json entries;
- a copied Python file that imports a non-stdlib module (import statements, __import__, importlib.import_module);
- a file without its licence file or NOTICE line;
- .dryas/state/ not git-ignored, or the CLAUDE.md block missing;
- when this Dryas knows its own version (plugin or checkout), a copy made by another version."""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
import sys
import sysconfig
from typing import Any, Dict, Iterable, List, Optional, Set

COPY = ".dryas"
MANIFEST = COPY + "/manifest.json"
NOTICE = COPY + "/NOTICE"
VERSION = COPY + "/VERSION"
START, END = "<!-- dryas:start -->", "<!-- dryas:end -->"
MAC_PATH = re.compile(r"(?<![\w.~-])/(?:Users|Volumes)/")
HOME_STATE = re.compile(r"~/\.dryas(?![\w-])")
PLUGIN_ROOT = "${CLAUDE_PLUGIN_ROOT}"
PLATFORM_STDLIB = frozenset(("msvcrt", "winreg", "_winapi", "winsound", "nt", "posix", "pwd", "grp", "fcntl",
                             "termios", "resource", "_overlapped", "__future__"))
# Under .dryas/ but not copied files: the manifest and VERSION describe the copy, state/ is its runtime data.
UNOWNED_OK = (MANIFEST, VERSION)
UNOWNED_SKIP_DIRS = (COPY + "/state", "__pycache__")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            return sha256(f.read())
    except OSError:
        return None


def files_hash(shas: Dict[str, str]) -> str:
    """One hash over every copied file's path and content (for VERSION and the manifest)."""
    return sha256("".join("%s %s\n" % (k, shas[k]) for k in sorted(shas)).encode("utf-8"))


def load_manifest(repo: str) -> Dict[str, Any]:
    with open(os.path.join(repo, MANIFEST), encoding="utf-8") as f:
        m = json.load(f)
    if not isinstance(m, dict) or not isinstance(m.get("files"), dict):
        raise ValueError('%s has no "files" object' % MANIFEST)
    if not all(isinstance(v, dict) for v in m["files"].values()):
        raise ValueError("%s has a file record that is not an object" % MANIFEST)
    return m


def drift(repo: str, files: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {"missing": [], "changed": []}
    for rel in sorted(files):
        cur = file_sha(os.path.join(repo, rel))
        if cur is None:
            out["missing"].append(rel)
        elif cur != files[rel].get("sha256"):
            out["changed"].append(rel)
    return out


def scan_text(rel: str, text: str) -> List[str]:
    out = []
    inside = rel.startswith(COPY + "/")
    for n, line in enumerate(text.splitlines(), 1):
        if MAC_PATH.search(line.replace("\\/", "/")):  # JSON may escape slashes
            out.append("%s:%d: absolute Mac path" % (rel, n))
        if not inside and HOME_STATE.search(line):
            out.append("%s:%d: ~/.dryas (a repo copy keeps its state in .dryas/state/)" % (rel, n))
        if not inside and PLUGIN_ROOT in line:
            out.append("%s:%d: ${CLAUDE_PLUGIN_ROOT} (a repo copy has no plugin)" % (rel, n))
    return out


def is_stdlib(name: str) -> bool:
    if name in sys.builtin_module_names or name in PLATFORM_STDLIB:
        return True
    names = getattr(sys, "stdlib_module_names", None)
    if names is not None:
        return name in names
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return False
    if spec is None or spec.origin is None:
        return False
    if spec.origin in ("built-in", "frozen"):
        return True
    std = os.path.realpath(sysconfig.get_paths()["stdlib"])
    origin = os.path.realpath(spec.origin)
    return origin.startswith(std + os.sep) and "site-packages" not in origin


def _dynamic_import_name(node: ast.AST) -> Optional[str]:
    """The literal module name of __import__("x") or importlib.import_module("x"), else None."""
    if not isinstance(node, ast.Call) or not node.args:
        return None
    f = node.func
    named = (isinstance(f, ast.Name) and f.id in ("__import__", "import_module")) or (
        isinstance(f, ast.Attribute) and f.attr in ("__import__", "import_module"))
    a = node.args[0]
    if named and isinstance(a, ast.Constant) and isinstance(a.value, str):
        return a.value
    return None


def nonstdlib_imports(text: str, siblings_: Iterable[str]) -> List[str]:
    """Top-level modules a Python file imports that are neither stdlib nor a file beside it."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return ["<unparseable>"]
    local = set(siblings_)
    bad: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            mods = [node.module]
        else:
            dyn = _dynamic_import_name(node)
            if not dyn or dyn.startswith("."):
                continue
            mods = [dyn]
        for m in mods:
            top = m.split(".")[0]
            if top not in local and not is_stdlib(top):
                bad.add(top)
    return sorted(bad)


def siblings(path: str) -> List[str]:
    d = os.path.dirname(path)
    try:
        names = os.listdir(d)
    except OSError:
        return []
    return [n[:-3] if n.endswith(".py") else n for n in names if n.endswith(".py") or os.path.isdir(os.path.join(d, n))]


def _read(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def own_version() -> Optional[str]:
    """This Dryas's version when it runs from the plugin or a checkout (claude/.claude-plugin/plugin.json); None when it
    runs from a repo copy, which has no plugin manifest."""
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".claude-plugin", "plugin.json")
    try:
        with open(p, encoding="utf-8") as f:
            v = json.load(f).get("version")
        return v if isinstance(v, str) else None
    except (OSError, ValueError, AttributeError):
        return None


def _unowned(repo: str, files: Dict[str, Any]) -> List[str]:
    out = []
    for d, dirs, names in os.walk(os.path.join(repo, COPY)):
        rel_d = os.path.relpath(d, repo).replace(os.sep, "/")
        dirs[:] = sorted(x for x in dirs if x != "__pycache__" and rel_d + "/" + x != COPY + "/state")
        for n in sorted(names):
            rel = rel_d + "/" + n
            if rel not in files and rel not in UNOWNED_OK:
                out.append("unowned: " + rel)
    return out


def check(repo: str, version: Optional[str] = None) -> List[str]:
    try:
        m = load_manifest(repo)
    except OSError:
        return ["no Dryas copy here (%s is missing); run dryas cloud init" % MANIFEST]
    except ValueError as e:
        return ["%s is unreadable (%s)" % (MANIFEST, e)]
    files = m["files"]
    d = drift(repo, files)
    probs = ["missing: %s" % r for r in d["missing"]] + ["drift (hand-edited): %s" % r for r in d["changed"]]
    probs += _unowned(repo, files)
    notice = set((_read(os.path.join(repo, NOTICE)) or "").splitlines())
    for rel in sorted(files):
        e = files[rel]
        path = os.path.join(repo, rel)
        text = _read(path)
        if text is not None:
            probs += scan_text(rel, text)
            if rel.endswith(".py"):
                bad = nonstdlib_imports(text, siblings(path))
                if bad:
                    probs.append("%s: imports non-stdlib %s" % (rel, ", ".join(bad)))
        if not e.get("licence"):
            probs.append("%s: no licence recorded" % rel)
        lic = e.get("licence_file")
        if e.get("group") != "own" and not (lic and os.path.isfile(os.path.join(repo, lic))):
            probs.append("%s: licence file %s is missing" % (rel, lic or "(none)"))
        if e.get("notice") and e["notice"] not in notice:
            probs.append("%s: no NOTICE line %r" % (rel, e["notice"]))
    cfg = m.get("config") if isinstance(m.get("config"), dict) else {}
    if ((cfg.get("settings") or {}).get("added") or {}).get("env"):
        probs.append(".claude/settings.json: Dryas entries set env (hooks get it from cloud_hook.py only)")
    for name, rel, key in (("settings", ".claude/settings.json", "added"), ("mcp", ".mcp.json", "entry")):
        blob = json.dumps((cfg.get(name) or {}).get(key) or {})
        if MAC_PATH.search(blob.replace("\\/", "/")) or "~/" in blob:
            probs.append("%s: a Dryas entry names a home or Mac path" % rel)
    ignore = {line.strip() for line in (_read(os.path.join(repo, ".gitignore")) or "").splitlines()}
    if ".dryas/state/" not in ignore:
        probs.append(".gitignore: .dryas/state/ is not ignored")
    md = _read(os.path.join(repo, "CLAUDE.md")) or ""
    i, j = md.find(START), md.find(END)
    if not 0 <= i < j:
        probs.append("CLAUDE.md: the Dryas rules block is missing")
    else:
        probs += scan_text("CLAUDE.md", md[i:j])
    have = (m.get("dryas") or {}).get("version")
    if version and have != version:
        probs.append("copy is Dryas %s, this Dryas is %s: run dryas cloud update" % (have, version))
    return probs


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="dryas cloud check", description="Check this repo's Dryas copy.")
    ap.add_argument("--repo", default=".")
    a = ap.parse_args(argv)
    probs = check(os.path.abspath(a.repo), own_version())
    for p in probs:
        print(p)
    print("dryas cloud check: %d problem%s" % (len(probs), "" if len(probs) == 1 else "s"))
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
