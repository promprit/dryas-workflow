"""The plugin's hook and launcher command lines run under the shell Claude Code uses:
sh -c on macOS/Linux, Git Bash on Windows."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
HOOK = '"${DRYAS_PY:-python3}" -X utf8 "${CLAUDE_PLUGIN_ROOT}/jev/echo_hook.py" pretool'
LAUNCH = '"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/echo_hook.py" pretool'
CODEX_HOOK = '"${DRYAS_PY:-python3}" -X utf8 "${PLUGIN_ROOT}/jev/echo_hook.py" pretool --harness codex'
ECHO = "import sys, json\nprint(json.dumps({'argv': sys.argv[1:], 'stdin': sys.stdin.read(), 'utf8': sys.flags.utf8_mode}))\n"


def find_bash() -> Optional[str]:
    """Git Bash on Windows (never WSL's System32 bash), sh elsewhere."""
    if os.name != "nt":
        return shutil.which("sh")
    for cand in (shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe"):
        if cand and "system32" not in cand.lower() and os.path.isfile(cand):
            return cand
    return None


def fwd(p) -> str:
    return str(p).replace("\\", "/")


class HookShellTest(unittest.TestCase):
    def setUp(self):
        self.sh = find_bash()
        if not self.sh:
            self.skipTest("no sh / Git Bash")
        self.root = Path(tempfile.mkdtemp(prefix="dryas plugin "))  # space on purpose
        (self.root / "jev").mkdir()
        (self.root / "jev" / "echo_hook.py").write_text(ECHO, encoding="utf-8")
        (self.root / "bin").mkdir()
        shutil.copy2(str(ROOT / "claude" / "bin" / "dryas-py"), str(self.root / "bin" / "dryas-py"))

    def tearDown(self):
        shutil.rmtree(str(self.root), ignore_errors=True)

    def _run(self, cmd: str, py: Optional[str]):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=fwd(self.root), PLUGIN_ROOT=fwd(self.root))
        env.pop("DRYAS_PY", None)
        if py:
            env["DRYAS_PY"] = fwd(py)
        p = subprocess.run([self.sh, "-c", cmd], input="{\"x\": 1}", capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_hook_form_with_dryas_py(self):
        out = self._run(HOOK, sys.executable)
        self.assertEqual(out["argv"], ["pretool"])
        self.assertEqual(out["stdin"], "{\"x\": 1}")
        self.assertEqual(out["utf8"], 1)

    def test_launcher_form_with_dryas_py(self):
        out = self._run(LAUNCH, sys.executable)
        self.assertEqual(out["argv"], ["pretool"])
        self.assertEqual(out["utf8"], 1)

    def test_hook_form_falls_back_to_python3(self):
        if not shutil.which("python3"):
            self.skipTest("no python3 on PATH")
        self.assertEqual(self._run(HOOK, None)["argv"], ["pretool"])

    def test_codex_hook_form(self):
        out = self._run(CODEX_HOOK, sys.executable)
        self.assertEqual(out["argv"], ["pretool", "--harness", "codex"])
        self.assertEqual(out["utf8"], 1)


if __name__ == "__main__":
    unittest.main()
