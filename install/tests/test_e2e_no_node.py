"""End to end with no Node on PATH: a fresh install (no flags) then the scripted loop through chain.py."""
import json, os, shutil, sqlite3, subprocess, sys, tempfile, time, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_e2e_install as e2e
REPO = e2e.REPO

CHAIN = str(REPO / "claude" / "jev" / "chain.py")
NODES = ("node", "node.exe")


def path_without_node(path: str) -> str:
    """PATH with every entry that holds a node or node.exe executable removed."""
    keep = [d for d in path.split(os.pathsep)
            if not any(os.path.isfile(os.path.join(d, n)) for n in NODES)]
    return os.pathsep.join(keep)


class NoNodeLoopTest(unittest.TestCase):
    # the e2e fixtures and installer by reference

    def installer(self, *args):
        """A fresh install with no component flags: the defaults must need no Node."""
        return subprocess.run([sys.executable, str(REPO / "install" / "dryas_install.py"), "run", "--repo", str(REPO),
                               "--yes"] + list(args), capture_output=True, text=True, env=self.env, timeout=900)

    def setUp(self):
        e2e.E2ETest.setUp(self)
        fb = str(self.tmp / "bin")
        self.env["PATH"] = fb + os.pathsep + path_without_node(self.env["PATH"])
        self.db = self.tmp / "dryas.db"
        self.env.update(DRYAS_DB=str(self.db), DRYAS_DATA_ROOT=str(self.home / ".dryas"),
                        DRYAS_NOTES_DIR=str(self.tmp / "notes"))
        self.assertIsNone(shutil.which("node", path=self.env["PATH"]))
        self.repo = self.tmp / "proj"
        (self.repo / ".orchestrate").mkdir(parents=True)
        (self.repo / "src").mkdir()
        (self.repo / ".orchestrate" / "active.json").write_text(json.dumps({"active": [1]}), encoding="utf-8")
        (self.repo / ".orchestrate" / "PLAN.md").write_text(
            "## Task 1: a\nGoal: g\nScope:\n- src/**\nDone:\n- d\n", encoding="utf-8")

    def chain(self, kind, event, *flags):
        event = dict(event, cwd=str(self.repo), session_id="nn")
        r = subprocess.run([sys.executable, CHAIN, kind] + list(flags), input=json.dumps(event), capture_output=True,
                           text=True, env=self.env, timeout=120)
        self.assertEqual(r.returncode, 0, "%s: %s" % (kind, r.stderr))
        self.assertIsNone(shutil.which("node", path=self.env["PATH"]))
        return r.stdout

    def tearDown(self):
        e2e.E2ETest.tearDown(self)

    def edit(self, rel):
        return {"tool_name": "Edit", "tool_input": {"file_path": str(self.repo / rel), "old_string": "a", "new_string": "b"}}

    def rows(self, sql):
        if not self.db.exists():
            return []
        c = sqlite3.connect(str(self.db))
        try:
            return c.execute(sql).fetchall()
        finally:
            c.close()

    def test_install_and_loop_without_node(self):
        p = self.installer("--harness", "both")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        rec = json.loads((self.home / ".claude" / ".dryas-plugin.json").read_text(encoding="utf-8"))
        for gone in ("ruflo", "superpowers"):
            self.assertNotIn(gone, rec["components"])
        self.assertIn("memory", rec["components"])
        self.chain("prompt", {"prompt": "hello"})
        self.assertNotIn("deny", self.chain("pretool", self.edit("src/a.py")))
        self.assertIn("deny", self.chain("pretool", self.edit("docs/a.md")).lower())
        self.chain("post", self.edit("src/a.py"))
        self.assertTrue(self.rows("SELECT file FROM edits"), "no edits row")
        self.chain("session-end", {"hook_event_name": "SessionEnd"})
        for _ in range(50):
            rows = self.rows("SELECT summary FROM sessions WHERE summary IS NOT NULL AND summary != ''")
            if rows:
                break
            time.sleep(0.2)
        self.assertTrue(rows, "no sessions row with a summary")
        out = self.chain("pretool", {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}})
        self.assertNotIn("deny", out.lower())
        patch = "*** Begin Patch\n*** Add File: src/n.txt\n+x\n*** End Patch\n"
        self.chain("pretool", {"tool_name": "apply_patch", "tool_input": {"command": patch}}, "--harness", "codex")
        self.chain("session-start", {"source": "startup"}, "--harness", "codex")


if __name__ == "__main__":
    unittest.main()
