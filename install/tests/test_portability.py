"""Portability guard: shipped files must not reintroduce POSIX-only constructs."""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[2]
MARKER = "portable-ok:"
ALLOWED_FILES = {"install/install.sh"}
SYMLINK_HOME = "install/platform_util.py"

LINE_PATTERNS = [
    (re.compile(r"/usr/bin/env bash"), "hardcoded /usr/bin/env bash"),
    (re.compile(r"/usr/bin/python3"), "hardcoded /usr/bin/python3"),
    (re.compile(r"/bin/bash"), "hardcoded /bin/bash"),
    (re.compile(r"/bin/sh"), "hardcoded /bin/sh"),
    (re.compile(r"shell\s*=\s*True"), "shell=True is not portable"),
    (re.compile(r"[\"']/tmp/"), 'literal "/tmp/" path'),
]
SYMLINK = re.compile(r"os\.symlink\(")
CHMOD = re.compile(r"os\.chmod\(")
CHMOD_GUARD = re.compile(r"os\.name|IS_WINDOWS")


def scan(paths, root=None) -> List[str]:
    """Return one 'file:line: message' string per banned pattern hit."""
    hits = []
    for p in paths:
        p = Path(p)
        rel = p.relative_to(root).as_posix() if root else p.as_posix()
        if rel in ALLOWED_FILES:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lines = text.splitlines()
        for n, line in enumerate(lines, 1):
            if MARKER in line:
                continue
            for rx, msg in LINE_PATTERNS:
                if rx.search(line):
                    hits.append("%s:%d: %s" % (rel, n, msg))
            if SYMLINK.search(line) and rel != SYMLINK_HOME:
                hits.append("%s:%d: os.symlink outside install/platform_util.py" % (rel, n))
        if not CHMOD_GUARD.search(text):
            for n, line in enumerate(lines, 1):
                if CHMOD.search(line) and MARKER not in line:
                    hits.append("%s:%d: os.chmod without os.name/IS_WINDOWS guard in file" % (rel, n))
    return hits


def shipped_files():
    out = subprocess.run(
        ["git", "ls-files", "claude", "codex", "install"],
        cwd=str(ROOT), stdout=subprocess.PIPE, universal_newlines=True, check=True,
    ).stdout.splitlines()
    files = []
    for f in out:
        parts = f.split("/")
        if "tests" in parts:
            continue
        if (ROOT / f).is_file():
            files.append(ROOT / f)
    return files


class PortabilityTest(unittest.TestCase):
    def test_scanner_flags_banned_patterns(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.py"
            f.write_text('subprocess.run("x", shell=True)\n# /bin/sh\n', encoding="utf-8")
            self.assertEqual(len(scan([f])), 2)
            ok = Path(d) / "y.py"
            ok.write_text("x = '/bin/sh'  # portable-ok: test\n", encoding="utf-8")
            self.assertEqual(scan([ok]), [])
            c = Path(d) / "c.py"
            c.write_text("import os\nos.chmod(p, 0o755)\n", encoding="utf-8")
            self.assertEqual(len(scan([c])), 1)

    def test_shipped_files_are_portable(self):
        hits = scan(shipped_files(), root=ROOT)
        self.assertEqual(hits, [], "\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
