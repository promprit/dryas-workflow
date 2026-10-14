"""The release version is stated in five places; they must agree (tools/release_check.py fails on a mismatch too).

  claude/.claude-plugin/plugin.json   version
  codex/.codex-plugin/plugin.json     version
  .claude-plugin/marketplace.json     the dryas plugin entry's version
  CHANGELOG.md                        the first `## X.Y.Z` heading
  claude/jev/jev_mcp.py               serverInfo version
"""
import json, shutil, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools"))
import release_check


class ReleaseVersionTest(unittest.TestCase):
    def test_versions_agree(self):
        found = release_check.versions(REPO)
        self.assertEqual(set(found), set(release_check.VERSION_FILES))
        self.assertEqual(release_check.version_problems(REPO), [],
                         "bump every file to the same version: %s" % json.dumps(found, indent=2))

    def test_mismatch_and_missing_detected(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        for rel in release_check.VERSION_FILES:
            (t / rel).parent.mkdir(parents=True, exist_ok=True)
        (t / "claude/.claude-plugin/plugin.json").write_text(json.dumps({"version": "2.0.0"}), encoding="utf-8")
        (t / "codex/.codex-plugin/plugin.json").write_text(json.dumps({"version": "2.0.0"}), encoding="utf-8")
        (t / ".claude-plugin/marketplace.json").write_text(
            json.dumps({"plugins": [{"name": "other", "version": "9"}, {"name": "dryas", "version": "2.0.0"}]}), encoding="utf-8")
        (t / "CHANGELOG.md").write_text("# Changelog\n\nintro ## 1.0.0 not a heading\n\n## 2.0.0 - 2026-10-13\n\n## 1.9.0\n",
                                        encoding="utf-8")
        (t / "claude/jev/jev_mcp.py").write_text('x = {"serverInfo": {"name": "jev", "version": "2.0.0"}}\n', encoding="utf-8")
        self.assertEqual(release_check.version_problems(t), [])
        self.assertEqual(set(release_check.versions(t).values()), {"2.0.0"})
        (t / "CHANGELOG.md").write_text("## 2.0.1 - 2026-10-14\n\n## 2.0.0\n", encoding="utf-8")
        bad = release_check.version_problems(t)
        self.assertEqual(len(bad), len(release_check.VERSION_FILES), bad)
        self.assertTrue(any(b.startswith("CHANGELOG.md: 2.0.1") for b in bad), bad)
        (t / "CHANGELOG.md").write_text("no heading\n", encoding="utf-8")
        self.assertEqual(release_check.version_problems(t), ["CHANGELOG.md: no version found"])

    def test_release_check_fails_on_mismatch(self):
        rep = release_check.Report()
        from unittest import mock
        import contextlib, io
        with mock.patch.object(release_check, "version_problems", lambda repo: ["CHANGELOG.md: 1.0.1"]), \
                contextlib.redirect_stdout(io.StringIO()) as buf:
            release_check.release_versions(rep)
        self.assertEqual(rep.fails, 1)
        self.assertIn("FAIL  release versions agree  (CHANGELOG.md: 1.0.1)", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
