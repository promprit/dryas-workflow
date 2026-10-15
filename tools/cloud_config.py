"""Repo config that a Dryas copy adds and takes out again (owned core E):
- .claude/settings.json: hooks and one allow rule, never env (it would also reach the plugin's own hooks on a Mac);
- .mcp.json: the jev server;
- the CLAUDE.md rules block;
- the .gitignore lines.

Every function takes and returns text (None: the file does not exist, or should not), so `dryas cloud` can print a
dry run before it writes. A file that is not valid JSON, or not a JSON object, stops the run: Dryas never overwrites
what it cannot parse."""
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "install") not in sys.path:
    sys.path.insert(0, str(ROOT / "install"))
import claude_md_block as cmb  # noqa: E402
import settings_merge as sm  # noqa: E402

ENTRY = '"${DRYAS_PY:-python3}" -X utf8 "$CLAUDE_PROJECT_DIR/.dryas/jev/cloud_hook.py" '
_HOOK = re.compile(r'"\$\{CLAUDE_PLUGIN_ROOT\}/jev/([A-Za-z0-9_]+\.py)"(.*)$')
SKIP_SCRIPTS = ("rules_inject.py",)  # the CLAUDE.md block carries the rules in a repo copy
ALLOW = ("mcp__jev",)
GITIGNORE = (".dryas/state/", ".dryas/**/__pycache__/", ".claude/skills/**/__pycache__/", ".orchestrate/")
PROJ = "${CLAUDE_PROJECT_DIR:-.}"


class CloudError(Exception):
    """Stops a dryas cloud run before anything is written."""


def hooks(plugin_hooks: Dict[str, Any]) -> Dict[str, Any]:
    """The plugin's hook groups (claude/hooks/hooks.json), each command re-pointed at the repo copy through
    cloud_hook.py; rules_inject.py is left out."""
    out: Dict[str, Any] = {}
    for ev, groups in (plugin_hooks.get("hooks") or {}).items():
        for g in groups:
            hs = []
            for h in g.get("hooks", []):
                m = _HOOK.search(str(h.get("command", "")))
                if m and m.group(1) not in SKIP_SCRIPTS:
                    hs.append(dict(type="command", command=ENTRY + m.group(1) + m.group(2), timeout=h.get("timeout", 10)))
            if hs:
                out.setdefault(ev, []).append(dict(matcher=g["matcher"], hooks=hs) if "matcher" in g else dict(hooks=hs))
    return out


def fragment(plugin_hooks: Dict[str, Any]) -> Dict[str, Any]:
    """Dryas's .claude/settings.json entries. No env: hooks get theirs from cloud_hook.py, the jev server from .mcp.json."""
    return dict(permissions=dict(allow=list(ALLOW)), hooks=hooks(plugin_hooks))


def mcp_entry() -> Dict[str, Any]:
    """The jev MCP server run from the copy: the argv shape claude_mcp.py registers, with repo-relative paths and its
    own env (Claude Code expands ${VAR:-default} here; paths._env_path copes when a client does not)."""
    return dict(command="${DRYAS_PY:-python3}", args=["-X", "utf8", PROJ + "/.dryas/jev/jev_mcp.py"],
                env=dict(CLAUDE_PLUGIN_ROOT=PROJ + "/.dryas", DRYAS_DATA_ROOT=PROJ + "/.dryas/state"))


def parse(name: str, text: Optional[str]) -> Dict[str, Any]:
    if text is None:
        return {}
    try:
        obj = json.loads(text)
    except ValueError as e:
        raise CloudError("%s is not valid JSON (%s); nothing changed" % (name, e))
    if not isinstance(obj, dict):
        raise CloudError("%s is not a JSON object; nothing changed" % name)
    return obj


_INDENT = re.compile(r"\n([ \t]+)\S")


def dump(obj: Dict[str, Any], like: Optional[str] = None) -> str:
    """obj as JSON in the format of the text `like` (the file as it is): its indent (a tab or N spaces, default 2),
    line ends and final newline; non-ASCII text stays readable."""
    m = _INDENT.search(like or "")
    indent = (2 if m is None else "\t" if m.group(1).startswith("\t") else len(m.group(1)))
    out = json.dumps(obj, indent=indent, ensure_ascii=False)
    if like is None or like.endswith("\n"):
        out += "\n"
    return out.replace("\n", "\r\n") if like and "\r\n" in like else out


def restore(obj: Dict[str, Any], original: Optional[str], text: str) -> Optional[str]:
    """Text for obj once Dryas's entries are out: the original bytes when nothing else changed, None when Dryas
    created the file and nothing is left, else obj in the format of the current text."""
    if original is not None:
        try:
            if json.loads(original) == obj:
                return original
        except ValueError:
            pass
    elif not obj:
        return None
    return dump(obj, text)


def add_settings(text: Optional[str], frag: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """The fragment has only permissions and hooks, which merge adds to and never conflict."""
    new, added, _ = sm.merge(parse(".claude/settings.json", text), frag, track_created=True)
    return dump(new, text), added


def remove_settings(text: Optional[str], added: Dict[str, Any], original: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return restore(sm.unmerge(parse(".claude/settings.json", text), added), original, text)


def add_mcp(text: Optional[str], owned: Optional[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    obj = parse(".mcp.json", text)
    servers = obj.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise CloudError('.mcp.json: "mcpServers" is not an object; nothing changed')
    cur = servers.get("jev")
    if cur is not None and cur != mcp_entry() and cur != owned:
        raise CloudError(".mcp.json already has a jev server that Dryas did not write; nothing changed")
    servers["jev"] = mcp_entry()
    return dump(obj, text), mcp_entry()


def remove_mcp(text: Optional[str], entry: Optional[Dict[str, Any]], original: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    obj = parse(".mcp.json", text)
    servers = obj.get("mcpServers")
    if isinstance(servers, dict) and entry is not None and servers.get("jev") == entry:
        del servers["jev"]
        if not servers and "mcpServers" not in parse(".mcp.json", original):
            del obj["mcpServers"]
    return restore(obj, original, text)


def _via_file(text: Optional[str], edit: Callable[[Path], None]) -> Optional[str]:
    """Run a claude_md_block edit on a temp copy, so the repo is written only after the dry run."""
    d = tempfile.mkdtemp()
    try:
        p = Path(d) / "CLAUDE.md"
        if text is not None:
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        edit(p)
        if not p.exists():
            return None
        with open(p, encoding="utf-8", newline="") as f:
            return f.read()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def claude_md(text: Optional[str], body: str, rec: Dict[str, Any]) -> Optional[str]:
    return _via_file(text, lambda p: cmb.insert_block(p, body, rec, "claude_md"))


def undo_claude_md(text: Optional[str], rec: Dict[str, Any]) -> Optional[str]:
    return _via_file(text, lambda p: cmb.remove_block(p, rec, "claude_md"))


def add_gitignore(text: Optional[str]) -> Tuple[Optional[str], Dict[str, Any]]:
    have = {line.strip() for line in (text or "").splitlines()}
    lines = [line for line in GITIGNORE if line not in have]
    if not lines:
        return text, dict(added=[], sep="", created=False)
    base = text or ""
    sep = "\n" if base and not base.endswith("\n") else ""
    return base + sep + "".join(line + "\n" for line in lines), dict(added=lines, sep=sep, created=text is None)


def remove_gitignore(text: Optional[str], rec: Dict[str, Any]) -> Optional[str]:
    if text is None:
        return None
    added = list(rec.get("added") or [])
    block = rec.get("sep", "") + "".join(line + "\n" for line in added)
    if added and text.endswith(block):
        new = text[:len(text) - len(block)]
    else:
        out = []
        for line in text.splitlines(True):
            if line.strip() in added:
                added.remove(line.strip())
                continue
            out.append(line)
        new = "".join(out)
    if rec.get("created") and not new.strip():
        return None
    return new
