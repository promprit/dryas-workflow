"""Fake accounts and sessions for the bridge tests: temp dirs only, never a real path, account or session id."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from unittest import mock

JEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JEV)

SID_ME = "11111111-1111-4111-8111-111111111111"
SID_B = "22222222-2222-4222-8222-222222222222"
SID_C = "33333333-3333-4333-8333-333333333333"


def ps_start(pid):
    """The process start time the way Claude Code writes procStart (UTC)."""
    r = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                       env=dict(os.environ, TZ="UTC", LC_ALL="C"))
    return " ".join(r.stdout.split())


def write_session(cd, pid, sid, name, proc_start=None, kind="interactive", status="idle", updated=None, extra=None):
    os.makedirs(os.path.join(cd, "sessions"), exist_ok=True)
    rec = {"pid": pid, "sessionId": sid, "cwd": "/work/" + name, "name": name, "kind": kind, "status": status,
           "procStart": ps_start(pid) if proc_start is None else proc_start,
           "updatedAt": int(time.time() * 1000) if updated is None else updated,
           "messagingSocketPath": "/sock/%d.sock" % pid}
    rec.update(extra or {})
    with open(os.path.join(cd, "sessions", "%d.json" % pid), "w", encoding="utf-8") as f:
        json.dump(rec, f)
    with open(os.path.join(cd, "sessions", "%d.deadbeef.key" % pid), "w", encoding="utf-8") as f:
        f.write("not for the bridge")


class Sandbox:
    """A temp data root whose accounts.json lists two fake config dirs (.claude, .claude-two); HOME is the temp dir, so discovery never scans the real home; env patched for the
    test; child processes killed and the folder removed at cleanup."""

    def __init__(self, test, dryas=True):
        import bridge_peers
        if os.getppid() <= 1:
            test.skipTest("the caller's session is found from the parent pid; this test runs under pid 1")
        self.d = tempfile.mkdtemp()
        test.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "data")
        os.makedirs(self.root)
        self.acc1 = os.path.join(self.d, ".claude")
        self.acc2 = os.path.join(self.d, ".claude-two")
        if dryas:
            for a in (self.acc1, self.acc2):
                os.makedirs(a, exist_ok=True)
                with open(os.path.join(a, ".dryas-plugin.json"), "w", encoding="utf-8") as f:
                    f.write("{}")
        with open(os.path.join(self.root, "accounts.json"), "w", encoding="utf-8") as f:
            json.dump({"claude_dirs": [self.acc1, self.acc2]}, f)
        p = mock.patch.dict(os.environ, {"HOME": self.d, "DRYAS_DATA_ROOT": self.root, "CLAUDE_CONFIG_DIR": self.acc1,
                                         "JEV_LOG_DIR": os.path.join(self.d, "logs")})
        p.start()
        test.addCleanup(p.stop)
        bridge_peers._ME.clear()
        test.addCleanup(bridge_peers._ME.clear)
        self.test = test

    def child(self):
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self.test.addCleanup(p.wait)
        self.test.addCleanup(p.kill)
        return p.pid

    def dead_pid(self):
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        return p.pid

    def me(self, name="me"):
        """The caller's own session: the parent of this test process, on account .claude."""
        write_session(self.acc1, os.getppid(), SID_ME, name)
