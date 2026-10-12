"""codex/jev and codex/pstack are generated from claude/ (Codex copies plugins and drops symlinks)."""
import shutil, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import sync_codex_plugin as scp


class SyncTest(unittest.TestCase):
    def test_repo_has_no_drift(self):
        self.assertEqual(scp.drift(ROOT), [], "run: python tools/sync_codex_plugin.py")

    def test_plan_skips_tests_and_caches(self):
        rels = list(scp.plan(ROOT))
        self.assertIn("codex/jev/chain.py", rels)
        self.assertIn("codex/jev/chain.json", rels)
        self.assertIn("codex/pstack/benchmark-checklist.md", rels)
        self.assertFalse([r for r in rels if "/tests/" in r or "__pycache__" in r or r.endswith(".pyc")])

    def _tree(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        for s, _ in scp.TREES:
            (t / s).mkdir(parents=True)
        (t / "claude/jev/a.py").write_bytes(b"x = 1\n")
        (t / "claude/jev/tests").mkdir()
        (t / "claude/jev/tests/test_a.py").write_bytes(b"")
        (t / "claude/pstack/p.md").write_bytes(b"p\n")
        return t

    def test_drift_kinds_and_sync(self):
        t = self._tree()
        self.assertEqual(scp.drift(t), ["missing codex/jev/a.py", "missing codex/pstack/p.md"])
        self.assertEqual(sorted(scp.sync(t)), ["codex/jev/a.py", "codex/pstack/p.md"])
        self.assertEqual(scp.drift(t), [])
        (t / "codex/jev/a.py").write_bytes(b"x = 2\n")
        (t / "codex/jev/old.py").write_bytes(b"")
        self.assertEqual(scp.drift(t), ["differs codex/jev/a.py", "extra codex/jev/old.py"])
        scp.sync(t)
        self.assertFalse((t / "codex/jev/old.py").exists())
        self.assertEqual(scp.drift(t), [])

    def test_crlf_is_not_drift(self):
        t = self._tree()
        scp.sync(t)
        (t / "codex/jev/a.py").write_bytes(b"x = 1\r\n")
        self.assertEqual(scp.drift(t), [])

    def test_check_exit_code(self):
        t = self._tree()
        self.assertEqual(scp.main(["--check", "--repo", str(t)]), 1)
        scp.main(["--repo", str(t)])
        self.assertEqual(scp.main(["--check", "--repo", str(t)]), 0)


if __name__ == "__main__":
    unittest.main()
