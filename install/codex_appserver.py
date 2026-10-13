"""Codex app-server client for hook trust (JSON-RPC over stdio, one JSON object per line, no "jsonrpc" header).
Setup uses it exactly as the Codex TUI's /hooks review does: initialize, initialized, hooks/list, config/batchWrite."""
import json
import os
import queue
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

import platform_util as pu

CLIENT = {"name": "dryas_setup", "title": "Dryas setup", "version": "1.0.0"}
STDERR_TAIL = 4096


class AppServerError(Exception):
    pass


def hook_entries(result: Any) -> List[dict]:
    out: List[dict] = []
    if isinstance(result, dict):
        if "key" in result and "trustStatus" in result:
            return [result]
        for v in result.values():
            out += hook_entries(v)
    elif isinstance(result, list):
        for v in result:
            out += hook_entries(v)
    return out


def untrusted(entries: List[dict], plugin_id: str) -> List[dict]:
    # "modified" counts too, by design: setup re-adds the same plugin and has asked for consent, so a hook whose
    # hash changed with the new plugin version is re-trusted at its current hash.
    return [e for e in entries if e.get("pluginId") == plugin_id and e.get("trustStatus") != "trusted"]


def trust_params(entries: List[dict], plugin_id: Optional[str] = None) -> dict:
    """batchWrite params trusting `entries` at their currentHash. With `plugin_id`, any entry of another plugin
    raises AppServerError (setup never trusts hooks it did not install)."""
    value = {}
    for e in entries:
        if plugin_id is not None and e.get("pluginId") != plugin_id:
            raise AppServerError("refusing to trust hook %s: not from %s" % (e.get("key"), plugin_id))
        if not e.get("key") or not e.get("currentHash"):
            raise AppServerError("hook entry without key or currentHash: %r" % (e.get("key"),))
        value[e["key"]] = {"trusted_hash": e["currentHash"]}
    return {"edits": [{"keyPath": "hooks.state", "value": value, "mergeStrategy": "upsert"}], "reloadUserConfig": True}


class AppServer:
    def __init__(self, env: Dict[str, str], argv: Optional[List[str]] = None, timeout: float = 30.0):
        self.timeout, self.next_id, self.q = timeout, 0, queue.Queue()  # type: ignore[var-annotated]
        self._err, self._closed = "", False
        try:
            self.p = subprocess.Popen(pu.resolve_argv(argv or ["codex", "app-server"]), stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                                      universal_newlines=True, encoding="utf-8", errors="replace")
        except OSError as e:
            raise AppServerError("cannot start codex app-server: %s" % e)
        threading.Thread(target=self._read, daemon=True).start()
        self._err_thread = threading.Thread(target=self._drain, daemon=True)
        self._err_thread.start()

    def _read(self) -> None:
        try:
            for line in self.p.stdout:  # type: ignore[union-attr]
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if isinstance(msg, dict):
                    self.q.put(msg)
        except (OSError, ValueError):
            pass
        finally:
            self.q.put(None)

    def _drain(self) -> None:
        try:
            while True:
                chunk = self.p.stderr.read(1024)  # type: ignore[union-attr]
                if not chunk:
                    return
                self._err = (self._err + chunk)[-STDERR_TAIL:]
        except (OSError, ValueError):
            pass

    def _exited(self, method: str) -> AppServerError:
        self._err_thread.join(1.0)
        tail = self._err.strip()
        return AppServerError("%s: codex app-server exited%s" % (method, (": " + tail) if tail else ""))

    def _send(self, msg: dict) -> None:
        try:
            self.p.stdin.write(json.dumps(msg) + "\n")  # type: ignore[union-attr]
            self.p.stdin.flush()  # type: ignore[union-attr]
        except (OSError, ValueError) as e:
            raise AppServerError("codex app-server closed: %s" % e)

    def notify(self, method: str, params: Optional[dict] = None) -> None:
        self._send({"method": method, "params": params or {}})

    def request(self, method: str, params: dict) -> dict:
        self.next_id += 1
        rid, end = self.next_id, time.monotonic() + self.timeout
        self._send({"id": rid, "method": method, "params": params})
        while True:
            left = end - time.monotonic()
            if left <= 0:
                raise AppServerError("%s: no answer within %ss" % (method, self.timeout))
            try:
                msg = self.q.get(timeout=left)
            except queue.Empty:
                continue
            if msg is None:
                raise self._exited(method)
            if "method" in msg:  # server requests and notifications are ignored
                continue
            if msg.get("id") is None and "error" in msg:  # e.g. a parse error: no id to wait for
                raise AppServerError("%s: %s" % (method, (msg["error"] or {}).get("message", msg["error"])))
            if msg.get("id") == rid:
                if "error" in msg:
                    raise AppServerError("%s: %s" % (method, (msg["error"] or {}).get("message", msg["error"])))
                return msg.get("result") or {}

    def _kill(self) -> None:
        if os.name == "nt":  # the fake (and npm's codex) run under a .cmd launcher: kill the whole tree
            try:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.p.pid)], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=10)
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            self.p.kill()
        except OSError:
            pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        grace = min(5.0, self.timeout)
        try:
            self.p.stdin.close()  # type: ignore[union-attr]
        except (OSError, ValueError):
            pass
        try:
            self.p.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            self._kill()
            try:
                self.p.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                pass
        for f in (self.p.stdout, self.p.stderr):
            try:
                f.close()  # type: ignore[union-attr]
            except (OSError, ValueError):
                pass

    def __enter__(self) -> "AppServer":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _session(env: Dict[str, str], timeout: float) -> AppServer:
    s = AppServer(env, timeout=timeout)
    try:
        s.request("initialize", {"clientInfo": CLIENT})
        s.notify("initialized")
    except BaseException:
        s.close()
        raise
    return s


def list_hooks(env: Dict[str, str], cwd: str, timeout: float = 30.0) -> List[dict]:
    with _session(env, timeout) as s:
        return hook_entries(s.request("hooks/list", {"cwds": [cwd]}))


def write_trust(env: Dict[str, str], entries: List[dict], timeout: float = 30.0,
                plugin_id: Optional[str] = None) -> None:
    if not entries:
        return
    params = trust_params(entries, plugin_id)  # validate before starting the server
    with _session(env, timeout) as s:
        s.request("config/batchWrite", params)
