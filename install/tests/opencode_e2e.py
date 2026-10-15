"""Drive a real `opencode serve` against fixtures/mock_llm.py, with the Dryas edition (opencode/) copied in as an
install would place it. HOME, the OpenCode config, data and state dirs and the Dryas data root all live in the temp
dir; the OpenCode download cache is shared (DRYAS_E2E_CACHE, default <system temp>/dryas-opencode-e2e-cache) so the
mock provider's npm package is fetched once. No API key reaches the server."""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock
from typing import List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
MIN = (1, 18, 0)
KEYS = ("OPENROUTER_API_KEY", "DRYAS_OPENROUTER_KEY")


def opencode_ok() -> str:
    """"" when opencode 1.18+ is on PATH, else why the end-to-end tests skip."""
    exe = shutil.which("opencode")
    if not exe:
        return "opencode not on PATH"
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        return "opencode --version failed: %s" % e
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", out or "")
    if not m or tuple(int(x) for x in m.groups()) < MIN:
        return "opencode %s is older than 1.18.0" % (out or "").strip()
    return ""


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Server:
    def __init__(self, tmp: Path, edition: Optional[Path] = REPO / "opencode", config_extra: Optional[dict] = None,
                 env_extra: Optional[dict] = None, install: bool = False):
        self.tmp = Path(tmp)
        self.proj = self.tmp / "proj"
        (self.proj / "src").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.proj)], check=True)
        self._log = self.tmp / "llm.jsonl"
        self._log.touch()
        self._mock = subprocess.Popen([sys.executable, str(REPO / "install/tests/fixtures/mock_llm.py"), str(self._log)],
                                      stdout=subprocess.PIPE, universal_newlines=True)
        mport = int(self._mock.stdout.readline())
        cfg = self.tmp / "xdg/config/opencode"
        self.data = self.tmp / "dryas-data"
        self.data.mkdir()
        if install and edition == REPO / "opencode":
            import opencode_setup
            mm = "mock/m2"
            with mock.patch.dict(os.environ, {"DRYAS_DATA_ROOT": str(self.data)}):
                rc = opencode_setup.setup(REPO, cfg, ["core", "jev"], dict.fromkeys(opencode_setup.TIERS, mm))
            if rc:
                raise RuntimeError("opencode_setup.setup failed (%d)" % rc)
        elif edition is not None:
            shutil.copytree(str(edition), str(cfg), ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
            for a in (cfg / "agent").glob("dryas-executor-*.md"):
                a.write_text(a.read_text(encoding="utf-8").replace("model: {{MODEL}}", "model: mock/m2"), encoding="utf-8")
            (cfg / "dryas/install.json").write_text(json.dumps({"py": sys.executable.replace("\\", "/")}), encoding="utf-8")
        cfg.mkdir(parents=True, exist_ok=True)
        conf = {"$schema": "https://opencode.ai/config.json", "model": "mock/m1",
                "provider": {"mock": {"npm": "@ai-sdk/openai-compatible", "name": "Mock",
                                      "options": {"baseURL": "http://127.0.0.1:%d/v1" % mport, "apiKey": "x"},
                                      "models": {"m1": {"name": "m1", "limit": {"context": 200000, "output": 8000}},
                                                 "m2": {"name": "m2"}}}}}
        conf.update(config_extra or {})
        (cfg / "opencode.json").write_text(json.dumps(conf), encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k not in KEYS}
        env.update(HOME=str(self.tmp), USERPROFILE=str(self.tmp), XDG_CONFIG_HOME=str(self.tmp / "xdg/config"),
                   XDG_DATA_HOME=str(self.tmp / "xdg/data"), XDG_STATE_HOME=str(self.tmp / "xdg/state"),
                   XDG_CACHE_HOME=os.environ.get("DRYAS_E2E_CACHE") or os.path.join(tempfile.gettempdir(), "dryas-opencode-e2e-cache"),
                   DRYAS_DATA_ROOT=str(self.data), DRYAS_PY=sys.executable,
                   JEV_CHAIN_LOCAL=str(self.data / "chain.local.json"))
        env.update(env_extra or {})
        port = _free_port()
        self._base = "http://127.0.0.1:%d" % port
        self._q = "?directory=" + urllib.parse.quote(str(self.proj))
        self._serve_log = open(str(self.tmp / "serve.log"), "w")
        self._srv = subprocess.Popen([shutil.which("opencode") or "opencode", "serve", "--port", str(port)],
                                     cwd=str(self.proj), env=env, stdout=self._serve_log, stderr=subprocess.STDOUT)
        self.events: List[dict] = []
        self._ready()
        threading.Thread(target=self._listen, daemon=True).start()
        time.sleep(1)

    def _http(self, method: str, path: str, body=None, timeout: float = 180):
        req = urllib.request.Request(self._base + path + self._q, method=method,
                                     data=None if body is None else json.dumps(body).encode("utf-8"),
                                     headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode("utf-8")
        return json.loads(text) if text.strip() else None

    def _ready(self):
        for _ in range(240):
            try:
                self._http("GET", "/session", timeout=2)
                return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("opencode serve did not start; see %s" % (self.tmp / "serve.log"))

    def _listen(self):
        try:
            with urllib.request.urlopen(self._base + "/event" + self._q, timeout=900) as r:
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    if line.startswith("data:"):
                        try:
                            self.events.append(json.loads(line[5:]))
                        except ValueError:
                            pass
        except Exception:
            pass

    def prompt(self, text: str, wait: bool = True) -> str:
        sid = self._http("POST", "/session", {})["id"]
        self._http("POST", "/session/%s/%s" % (sid, "message" if wait else "prompt_async"),
                   {"parts": [{"type": "text", "text": text}]})
        return sid

    def tools(self, sid: str) -> List[Tuple[str, str, str]]:
        out = []
        for msg in self._http("GET", "/session/%s/message" % sid) or []:
            for p in msg.get("parts", []):
                if p.get("type") == "tool":
                    st = p.get("state", {})
                    out.append((p.get("tool"), st.get("status"), str(st.get("error") or st.get("output") or "")))
        return out

    def children(self, sid: str) -> List[str]:
        return [c["id"] for c in self._http("GET", "/session/%s/children" % sid) or []]

    def asked(self, sid: str, timeout: float = 20.0) -> Optional[dict]:
        end = time.time() + timeout
        while time.time() < end:
            for ev in list(self.events):
                if ev.get("type") == "permission.asked" and ev.get("properties", {}).get("sessionID") == sid:
                    return ev["properties"]
            time.sleep(0.3)
        return None

    def reply(self, sid: str, permission_id: str, response: str) -> None:
        self._http("POST", "/session/%s/permissions/%s" % (sid, permission_id), {"response": response})

    def requests(self) -> List[dict]:
        return [json.loads(l) for l in self._log.read_text(encoding="utf-8").splitlines() if l.strip()]

    def close(self) -> None:
        for p in (self._srv, self._mock):
            p.terminate()
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                p.kill()
        self._serve_log.close()
