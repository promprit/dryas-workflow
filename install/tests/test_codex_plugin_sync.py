"""codex/jev and codex/pstack are generated from claude/ (Codex copies plugins and drops symlinks)."""
import shutil, sys, tempfile, unittest
from unittest import mock
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

    def test_skips_runtime_dirs_and_gitignore(self):
        t = self._tree()
        for d in ("logs", "compact"):
            (t / "claude/jev" / d).mkdir()
            (t / "claude/jev" / d / "x.log").write_bytes(b"x")
        (t / "claude/jev/.gitignore").write_bytes(b"logs/\n")
        self.assertEqual(sorted(scp.plan(t)), ["codex/jev/a.py", "codex/pstack/p.md"])

    def test_binary_compared_exactly(self):
        t = self._tree()
        (t / "claude/jev/b.bin").write_bytes(b"\xff\x00a\r\nb")
        scp.sync(t)
        (t / "codex/jev/b.bin").write_bytes(b"\xff\x00a\nb")
        self.assertEqual(scp.drift(t), ["differs codex/jev/b.bin"])

    def test_strays_in_skipped_dirs_are_extra(self):
        t = self._tree()
        scp.sync(t)
        for rel in ("tests/t.py", "logs/l.log", "compact/c.json", ".gitignore"):
            f = t / "codex/jev" / rel
            f.parent.mkdir(exist_ok=True)
            f.write_bytes(b"")
        (t / "codex/jev/__pycache__").mkdir()
        (t / "codex/jev/__pycache__/a.pyc").write_bytes(b"")
        self.assertEqual(scp.drift(t), sorted("extra codex/jev/" + r for r in
                                              ("tests/t.py", "logs/l.log", "compact/c.json", ".gitignore")))
        scp.sync(t)
        self.assertEqual(scp.drift(t), [])

    def test_repo_skills_have_no_drift(self):
        self.assertEqual(scp.skill_drift(ROOT), [], "edit the Codex skill or SKILL_ALLOW in tools/sync_codex_plugin.py")
        for name in scp.SKILLS:
            for h in ("claude", "codex"):
                self.assertTrue((ROOT / h / "skills" / name / "SKILL.md").is_file(), (h, name))

    def _skills(self, claude, codex, name="orchestrate"):
        t = self._tree()
        for h, text in (("claude", claude), ("codex", codex)):
            d = t / h / "skills" / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(text, encoding="utf-8")
        return t

    def test_skill_drift_names_only_one_edition_has(self):
        t = self._skills("Call `mcp__plugin_dryas_jev__jev_judge` with `needs_opus`; read `${CLAUDE_PLUGIN_ROOT}/pstack/cleanup.md`;"
                         " `Failing test first: none (review)`; `.orchestrate/active.json`; `interrogate.min_confidence`\n",
                         "Call `jev_judge` with `needs_stronger_model`; read `<dryas-root>/pstack/cleanup.md`;"
                         " `none (review)`; `.orchestrate/active.json`; `interrogate.min_confidence`\n")
        with mock.patch.object(scp, "SKILL_ALLOW", {}):
            self.assertEqual(scp.skill_drift(t), [
                "skill orchestrate: claude names needs_opus but codex does not",
                "skill orchestrate: codex names needs_stronger_model but claude does not"])
            self.assertEqual(scp.main(["--check", "--repo", str(t)]), 1)
        allow = {"orchestrate": {"claude": {"needs_opus", "swarm_init"}, "codex": {"needs_stronger_model"}}}
        with mock.patch.object(scp, "SKILL_ALLOW", allow):
            self.assertEqual(scp.skill_drift(t), ["skill orchestrate: SKILL_ALLOW['claude'] lists swarm_init, which no longer differs"])
        allow["orchestrate"]["claude"].discard("swarm_init")
        with mock.patch.object(scp, "SKILL_ALLOW", allow):
            self.assertEqual(scp.skill_drift(t), [])
            self.assertFalse([r for r in scp.sync(t) if "skills" in r])  # sync copies jev/pstack, never a skill
            self.assertEqual(scp.main(["--check", "--repo", str(t)]), 0)

    def test_skill_drift_ignores_prose_and_missing_files(self):
        t = self._skills("# Orchestrate\nYou (the strong tier) plan with `log_dispatch`.\n",
                         "# Orchestrate (Codex)\nWorkers; after every dispatch call `log_dispatch`.\n")
        with mock.patch.object(scp, "SKILL_ALLOW", {}):
            self.assertEqual(scp.skill_drift(t), [])  # only the shared names count, the prose may differ
        self.assertEqual(scp.skill_drift(self._tree()), [])  # no skills at all: nothing to compare

    def test_check_exit_code(self):
        t = self._tree()
        self.assertEqual(scp.main(["--check", "--repo", str(t)]), 1)
        scp.main(["--repo", str(t)])
        self.assertEqual(scp.main(["--check", "--repo", str(t)]), 0)


if __name__ == "__main__":
    unittest.main()
