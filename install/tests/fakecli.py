"""Fake command-line tools for installer tests: a Python script plus a launcher that PATH lookup finds on every OS.

Each call appends [name, *args] as one JSON line to `log`. stdout is outputs.get("<arg1> <arg2>", "").
Exit code is 1 when "<arg1> <arg2>" is in `fail`, else 0.
plugin_list=True: `plugin list --json` prints the plugins in $CLAUDE_CONFIG_DIR/plugins/installed_plugins.json the way
the real CLI does (readFromFolder: $FAKE_READ_FROM or the installPath; errors: $FAKE_PLUGIN_ERRORS, a JSON list;
$FAKE_MISSING_DEP: a dependency id reported unsatisfied while it is not in installed_plugins.json).
"""
import json
import os
import sys
from pathlib import Path
from typing import Iterable, List, Optional

SCRIPT = '''import json, sys
with open(%(log)r, "a", encoding="utf-8") as f:
    f.write(json.dumps([%(name)r] + sys.argv[1:]) + "\\n")
key = " ".join(sys.argv[1:3])
sys.stdout.write(%(outputs)r.get(key, ""))
%(epilogue)s
sys.exit(1 if key in %(fail)r else 0)
'''

PLUGIN_LIST = '''
import os as _os
if sys.argv[1:3] == ["plugin", "list"] and "plugin list" not in %(fail)r:
    try:
        with open(_os.path.join(_os.environ.get("CLAUDE_CONFIG_DIR", ""), "plugins", "installed_plugins.json"),
                  encoding="utf-8") as _f:
            _d = json.load(_f)
    except (OSError, ValueError):
        _d = {}
    _out = []
    _dep = _os.environ.get("FAKE_MISSING_DEP")
    _dep = _dep if _dep and _dep not in _d.get("plugins", {}) else None
    for _id, _es in _d.get("plugins", {}).items():
        for _e in _es:
            _errs = json.loads(_os.environ.get("FAKE_PLUGIN_ERRORS") or "[]")
            _out.append({"id": _id, "version": _e.get("version"), "scope": "user", "enabled": True,
                         "installPath": _e.get("installPath"),
                         "readFromFolder": _os.environ.get("FAKE_READ_FROM") or _e.get("installPath"),
                         "errors": _errs + (["Dependency " + _dep + " is not installed"] if _dep else []),
                         "errorDetails": [{"type": "dependency-unsatisfied", "dependency": _dep}] if _dep else []})
    sys.stdout.write(json.dumps(_out))
'''


def make(bin_dir: Path, name: str, log: Path, outputs: Optional[dict] = None, fail: Iterable[str] = (),
         epilogue: str = "", plugin_list: bool = False) -> Path:
    """`epilogue`: extra Python lines run after logging, before the exit."""
    if plugin_list:
        epilogue = epilogue + PLUGIN_LIST % {"fail": list(fail)}
    bin_dir.mkdir(parents=True, exist_ok=True)
    py = bin_dir / (name + "_fake.py")
    py.write_text(SCRIPT % {"name": name, "log": str(log), "outputs": dict(outputs or {}), "fail": list(fail),
                             "epilogue": epilogue},
                  encoding="utf-8")
    if os.name == "nt":
        launcher = bin_dir / (name + ".cmd")
        launcher.write_text('@"%s" "%s" %%*\r\n' % (sys.executable, py), encoding="utf-8")
    else:
        launcher = bin_dir / name
        launcher.write_text('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, py), encoding="utf-8")
        launcher.chmod(0o755)
    return launcher


def calls(log: Path) -> List[List[str]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


CODEX = r'''
import hashlib as _hl, os as _os, re as _re, shutil as _sh, time as _time
_FAIL = __FAIL__
_home = _os.environ.get("CODEX_HOME") or _os.path.join(_os.path.expanduser("~"), ".codex")
_sp, _cfg, _a = _os.path.join(_home, "fake_codex.json"), _os.path.join(_home, "config.toml"), sys.argv[1:]


def _load():
    try:
        with open(_sp, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"marketplaces": {}, "plugins": {}}


def _save(s):
    _os.makedirs(_home, exist_ok=True)
    with open(_sp, "w", encoding="utf-8") as f:
        json.dump(s, f)


def _toml():
    try:
        with open(_cfg, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _write_toml(text):
    _os.makedirs(_home, exist_ok=True)
    with open(_cfg, "w", encoding="utf-8") as f:
        f.write(text)


def _trust():
    return dict(_re.findall(r'^\[hooks\.state\."([^"]+)"\]\s*\ntrusted_hash = "([^"]+)"', _toml(), _re.M))


def _hooks(s):
    out, trust = [], _trust()
    for pid, p in s["plugins"].items():
        try:
            with open(_os.path.join(p["path"], "hooks", "hooks.json"), encoding="utf-8") as f:
                hk = json.load(f).get("hooks", {})
        except (OSError, ValueError):
            continue
        for ev, groups in hk.items():
            snake = _re.sub(r"(?<!^)(?=[A-Z])", "_", ev).lower()
            camel = ev[:1].lower() + ev[1:]
            for gi, g in enumerate(groups):
                for hi, h in enumerate(g.get("hooks", [])):
                    key = "%s:hooks/hooks.json:%s:%d:%d" % (pid, snake, gi, hi)
                    norm = dict(h, event=ev, matcher=g.get("matcher"))
                    cur = "sha256:" + _hl.sha256(json.dumps(norm, sort_keys=True).encode("utf-8")).hexdigest()
                    have = trust.get(key)
                    out.append({"key": key, "pluginId": pid, "source": "plugin", "eventName": camel,
                                "command": h.get("command"), "currentHash": cur,
                                "trustStatus": "trusted" if have == cur else ("modified" if have else "untrusted")})
    return out


def _out(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _bad_edit(e):
    return e.get("keyPath") != "hooks.state" or e.get("mergeStrategy") != "upsert" or not isinstance(e.get("value"), dict)


def _serve(s):
    # Knobs: FAKE_APPSERVER_SILENT=1 never answers; FAKE_APPSERVER_FAIL=<method> answers with an error;
    # FAKE_APPSERVER_NOISE=1 sends a notification and a server request reusing the id before each response;
    # FAKE_APPSERVER_PARSE_ERROR=1 answers every request with an id-null parse error;
    # FAKE_APPSERVER_CRASH=<method> writes to stderr and exits 3 on that method;
    # FAKE_APPSERVER_HANG=1 keeps running after stdin closes (until killed).
    env = _os.environ.get
    state = {"initialize": False, "initialized": False}
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:  # like the real 0.162.1 server: malformed lines are dropped
            continue
        if not isinstance(msg, dict):
            continue
        if "id" not in msg:
            if msg.get("method") == "initialized" and state["initialize"]:
                state["initialized"] = True
            continue
        if env("FAKE_APPSERVER_SILENT") == "1":
            continue
        m, rid = msg.get("method"), msg["id"]
        if m == env("FAKE_APPSERVER_CRASH"):
            sys.stderr.write("fake crash in %s\n" % m)
            sys.stderr.flush()
            _os._exit(3)
        if env("FAKE_APPSERVER_NOISE") == "1":
            _out({"method": "configWarning", "params": {"summary": "noise"}})
            _out({"id": rid, "method": "item/tool/requestUserInput", "params": {"questions": []}})
        if env("FAKE_APPSERVER_PARSE_ERROR") == "1":
            resp = {"id": None, "error": {"code": -32700, "message": "Parse error"}}
        elif m == env("FAKE_APPSERVER_FAIL"):
            resp = {"id": rid, "error": {"code": -32000, "message": "boom"}}
        elif m == "initialize":
            state["initialize"] = True
            resp = {"id": rid, "result": {"userAgent": "fake"}}
        elif m in ("hooks/list", "config/batchWrite") and not (state["initialize"] and state["initialized"]):
            # The real server only needs `initialize`; the fake also wants `initialized` so clients do the full handshake.
            resp = {"id": rid, "error": {"code": -32600, "message": "Not initialized"}}
        elif m == "config/batchWrite" and any(_bad_edit(e) for e in msg["params"].get("edits", [])):
            # The real server also takes mergeStrategy "replace" and any keyPath; setup must only upsert hooks.state.
            resp = {"id": rid, "error": {"code": -32600, "message": "fake: only upsert of hooks.state"}}
        elif m == "hooks/list":
            resp = {"id": rid, "result": {"data": [{"cwd": c, "hooks": _hooks(s), "warnings": [], "errors": []}
                                                   for c in msg["params"]["cwds"]]}}
        elif m == "config/batchWrite":
            text = _toml()
            for e in msg["params"]["edits"]:
                for k, v in e["value"].items():
                    text = _re.sub(r'\n?\[hooks\.state\."%s"\]\s*\ntrusted_hash = "[^"]*"\n' % _re.escape(k), "\n", text)
                    text += '\n[hooks.state."%s"]\ntrusted_hash = "%s"\n' % (k, v["trusted_hash"])
            _write_toml(text)
            resp = {"id": rid, "result": {"status": "ok"}}
        else:
            resp = {"id": rid, "error": {"code": -32601, "message": "unknown method"}}
        _out(resp)
    while env("FAKE_APPSERVER_HANG") == "1":
        _time.sleep(1)


def _main():
    if _a[:1] == ["--version"]:  # like the real CLI: no state read or written
        sys.stdout.write(_os.environ.get("FAKE_CODEX_VERSION", "codex-cli 0.162.1") + "\n")
        return
    s = _load()
    if _a[:3] == ["plugin", "marketplace", "add"] and "plugin marketplace" not in _FAIL:
        src = _os.path.abspath(_a[3])
        with open(_os.path.join(src, ".agents", "plugins", "marketplace.json"), encoding="utf-8") as f:
            s["marketplaces"][json.load(f)["name"]] = src
    elif _a[:3] == ["plugin", "marketplace", "list"] and "plugin marketplace" not in _FAIL:
        sys.stdout.write(json.dumps({"marketplaces": [{"name": n, "root": r, "source": r}
                                                      for n, r in s["marketplaces"].items()]}))
    elif _a[:3] == ["plugin", "marketplace", "remove"]:
        s["marketplaces"].pop(_a[3], None)
    elif _a[:2] == ["plugin", "add"] and "plugin add" not in _FAIL:
        name, mkt = _a[2].split("@")
        root = s["marketplaces"][mkt]
        with open(_os.path.join(root, ".agents", "plugins", "marketplace.json"), encoding="utf-8") as f:
            ent = [p for p in json.load(f)["plugins"] if p["name"] == name][0]
        src = _os.path.normpath(_os.path.join(root, ent["source"]))
        with open(_os.path.join(src, ".codex-plugin", "plugin.json"), encoding="utf-8") as f:
            ver = json.load(f)["version"]
        dest = _os.path.join(_home, "plugins", "cache", mkt, name, ver)
        _sh.rmtree(dest, ignore_errors=True)
        _sh.copytree(src, dest, ignore=lambda d, ns: [n for n in ns if n == "__pycache__"
                                                      or _os.path.islink(_os.path.join(d, n))])
        s["plugins"][_a[2]] = {"version": ver, "path": dest, "enabled": True}
        if '[plugins."%s"]' % _a[2] not in _toml():
            _write_toml(_toml() + '\n[plugins."%s"]\nenabled = true\n' % _a[2])
        sys.stdout.write(json.dumps({"pluginId": _a[2], "installedPath": dest, "version": ver,
                                     "authPolicy": "ON_INSTALL"}))
    elif _a[:2] == ["plugin", "list"] and "plugin list" not in _FAIL:
        sys.stdout.write(json.dumps({"installed": [{"pluginId": k, "version": v["version"], "installed": True,
                                                    "enabled": v["enabled"], "source": {"path": v["path"]}}
                                                   for k, v in s["plugins"].items()], "available": []}))
    elif _a[:2] == ["plugin", "remove"] and "plugin remove" not in _FAIL:
        p = s["plugins"].pop(_a[2], None)
        if p:
            _sh.rmtree(p["path"], ignore_errors=True)
            _write_toml(_toml().replace('\n[plugins."%s"]\nenabled = true\n' % _a[2], ""))
    elif _a[:2] == ["mcp", "list"]:
        text, out = _toml(), []
        for pid, p in s["plugins"].items():
            off = '[plugins."%s".mcp_servers.jev]\nenabled = false' % pid in text
            if not off and _os.path.exists(_os.path.join(p["path"], ".mcp.json")):
                out.append({"name": "jev", "plugin": pid})
        out += [{"name": n} for n in _re.findall(r"^\[mcp_servers\.([A-Za-z0-9_-]+)\]", text, _re.M)]
        sys.stdout.write(json.dumps(out))
    elif _a[:2] == ["debug", "prompt-input"]:
        for pid, p in s["plugins"].items():
            for n in sorted(_os.listdir(_os.path.join(p["path"], "skills"))):
                sys.stdout.write("- %s:%s\n" % (pid.split("@")[0], n))
    elif _a[:1] == ["app-server"] and "app-server" not in _FAIL:
        _serve(s)
    _save(s)


_main()
'''


def make_codex(bin_dir: Path, log: Path, fail: Iterable[str] = ()) -> Path:
    """A fake `codex` with plugin, marketplace, mcp, debug and app-server subcommands (state under $CODEX_HOME)."""
    return make(bin_dir, "codex", log, fail=fail, epilogue=CODEX.replace("__FAIL__", repr(list(fail))))
