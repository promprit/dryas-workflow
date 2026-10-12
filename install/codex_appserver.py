"""Codex app-server client for hook trust (JSON-RPC over stdio, one JSON object per line, no "jsonrpc" header).
Setup uses it exactly as the Codex TUI's /hooks review does: initialize, initialized, hooks/list, config/batchWrite."""
import json
import queue
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

import platform_util as pu

CLIENT = {"name": "dryas_setup", "title": "Dryas setup", "version": "1.0.0"}


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
    return [e for e in entries if e.get("pluginId") == plugin_id and e.get("trustStatus") != "trusted"]


def trust_params(entries: List[dict]) -> dict:
    value = {e["key"]: {"trusted_hash": e["currentHash"]} for e in entries}
    return {"edits": [{"keyPath": "hooks.state", "value": value, "mergeStrategy": "upsert"}], "reloadUserConfig": True}


class AppServer:
    def __init__(self, env: Dict[str, str], argv: Optional[List[str]] = None, timeout: float = 30.0):
        self.timeout, self.next_id, self.q = timeout, 0, queue.Queue()  # type: ignore[var-annotated]
        try:
            self.p = subprocess.Popen(pu.resolve_argv(argv or ["codex", "app-server"]), stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
                                      universal_newlines=True, encoding="utf-8", errors="replace")
        except OSError as e:
            raise AppServerError("cannot start codex app-server: %s" % e)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        try:
            for line in self.p.stdout:  # type: ignore[union-attr]
                try:
                    self.q.put(json.loads(line))
                except ValueError:
                    continue
        finally:
            self.q.put(None)

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
                raise AppServerError("%s: codex app-server exited" % method)
            if msg.get("id") == rid and "method" not in msg:  # server requests and notifications are ignored
                if "error" in msg:
                    raise AppServerError("%s: %s" % (method, (msg["error"] or {}).get("message", msg["error"])))
                return msg.get("result") or {}

    def close(self) -> None:
        try:
            self.p.stdin.close()  # type: ignore[union-attr]
            self.p.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            self.p.kill()

    def __enter__(self) -> "AppServer":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _session(env: Dict[str, str], timeout: float) -> AppServer:
    s = AppServer(env, timeout=timeout)
    try:
        s.request("initialize", {"clientInfo": CLIENT})
        s.notify("initialized")
    except AppServerError:
        s.close()
        raise
    return s


def list_hooks(env: Dict[str, str], cwd: str, timeout: float = 30.0) -> List[dict]:
    with _session(env, timeout) as s:
        return hook_entries(s.request("hooks/list", {"cwds": [cwd]}))


def write_trust(env: Dict[str, str], entries: List[dict], timeout: float = 30.0) -> None:
    if not entries:
        return
    with _session(env, timeout) as s:
        s.request("config/batchWrite", trust_params(entries))
