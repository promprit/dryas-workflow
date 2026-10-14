"""Process skills are one source in claude/skills, rendered for Codex by tools/sync_codex_plugin.py (owned core C)."""
import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import sync_codex_plugin as scp

SRC = ("---\nname: brainstorm\ndescription: Use before work.\nallowed-tools: Read\n---\n\n"
       "Shared line.\n<!-- claude -->\nClaude only: use the Skill tool.\n<!-- /claude -->\n"
       "<!-- codex -->\nOn Codex: get the user's approval of a design.\n<!-- /codex -->\nEnd.\n")


class RenderTest(unittest.TestCase):
    def test_codex_keeps_codex_block_drops_claude(self):
        out = scp.render_skill(SRC, "codex")
        self.assertIn("On Codex: get the user's approval of a design.\n", out)
        self.assertNotIn("Claude only", out)
        self.assertNotIn("<!--", out)
        self.assertIn("Shared line.\nOn Codex", out)

    def test_claude_keeps_claude_block(self):
        out = scp.render_skill(SRC, "claude")
        self.assertIn("Claude only: use the Skill tool.\n", out)
        self.assertNotIn("On Codex", out)
        self.assertIn("allowed-tools: Read", out)

    def test_codex_front_matter_trimmed(self):
        out = scp.render_skill(SRC, "codex")
        self.assertTrue(out.startswith("---\nname: brainstorm\ndescription: Use before work.\n---\n"), out[:80])

    def test_codex_rewrites_claude_names(self):
        src = ("---\nname: x\ndescription: d\n---\n"
               "Read `${CLAUDE_PLUGIN_ROOT}/skills/plan/plan-reviewer-prompt.md`.\n"
               "Call `mcp__plugin_dryas_jev__log_review`. Then use the `dryas:verify` skill, then /wreview and /commit.\n"
               "Keep `.orchestrate/PLAN.md` and skills/orchestrate/SKILL.md and dryas@dryas-workflow as they are.\n")
        out = scp.render_skill(src, "codex")
        self.assertIn("`<dryas-root>/skills/plan/plan-reviewer-prompt.md`", out)
        self.assertIn("`log_review`", out)
        self.assertIn("`$dryas:verify`", out)
        self.assertIn("then $dryas:wreview and $dryas:commit.", out)
        self.assertIn("`.orchestrate/PLAN.md` and skills/orchestrate/SKILL.md and dryas@dryas-workflow", out)

    def test_unbalanced_marker_raises(self):
        for bad in ("<!-- codex -->\nx\n", "<!-- /codex -->\n", "<!-- codex -->\n<!-- claude -->\n<!-- /claude -->\n"):
            with self.assertRaises(ValueError):
                scp.harness_blocks(bad, "codex")

    def test_other_html_comments_kept(self):
        src = "<!-- pstack-picks -->\nx\n<!-- /pstack-picks -->\n"
        self.assertEqual(scp.harness_blocks(src, "codex"), src)


class TreeTest(unittest.TestCase):
    def _tree(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        for s, _ in scp.TREES:
            (t / s).mkdir(parents=True)
        d = t / "claude/skills/brainstorm"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(SRC, encoding="utf-8")
        (d / "spec-reviewer-prompt.md").write_text("Use ${CLAUDE_PLUGIN_ROOT}/x.\n", encoding="utf-8")
        (t / "claude/skills/UPSTREAM.md").write_text("# Upstream\n", encoding="utf-8")
        (t / "codex/skills/wplan").mkdir(parents=True)
        (t / "codex/skills/wplan/SKILL.md").write_text("hand-written\n", encoding="utf-8")
        (t / "codex/skills/wplan/agents").mkdir()
        (t / "codex/skills/wplan/agents/openai.yaml").write_text(scp.openai_yaml(False), encoding="utf-8")
        (t / "claude/commands").mkdir(parents=True)
        (t / "claude/commands/wplan.md").write_text("---\ndisable-model-invocation: true\n---\n", encoding="utf-8")
        return t

    def test_missing_differs_extra_and_sync(self):
        t = self._tree()
        self.assertEqual(scp.drift(t), ["missing codex/skills/UPSTREAM.md", "missing codex/skills/brainstorm/SKILL.md",
                                        "missing codex/skills/brainstorm/agents/openai.yaml",
                                        "missing codex/skills/brainstorm/spec-reviewer-prompt.md"])
        scp.sync(t)
        self.assertEqual(scp.drift(t), [])
        self.assertEqual((t / "codex/skills/brainstorm/spec-reviewer-prompt.md").read_text(encoding="utf-8"),
                         "Use <dryas-root>/x.\n")
        self.assertEqual((t / "codex/skills/wplan/SKILL.md").read_text(encoding="utf-8"), "hand-written\n")
        (t / "codex/skills/brainstorm/SKILL.md").write_text("edited\n", encoding="utf-8")
        (t / "codex/skills/brainstorm/old.md").write_text("", encoding="utf-8")
        self.assertEqual(scp.drift(t), ["differs codex/skills/brainstorm/SKILL.md", "extra codex/skills/brainstorm/old.md"])
        scp.sync(t)
        self.assertEqual(scp.drift(t), [])
        self.assertFalse((t / "codex/skills/brainstorm/old.md").exists())

    def test_absent_source_is_skipped(self):
        t = self._tree()
        shutil.rmtree(str(t / "claude/skills/brainstorm"))
        (t / "claude/skills/UPSTREAM.md").unlink()
        self.assertEqual(scp.drift(t), [])
        self.assertEqual(scp.harness_drift(t), [])

    def test_crlf_copy_is_not_drift(self):
        t = self._tree()
        scp.sync(t)
        p = t / "codex/skills/brainstorm/SKILL.md"
        p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(scp.drift(t), [])

    def test_harness_required_missing_reported(self):
        t = self._tree()
        (t / "claude/skills/brainstorm/SKILL.md").write_text(SRC.replace("get the user's approval of a design", "go"),
                                                              encoding="utf-8")
        self.assertEqual(scp.harness_drift(t),
                         ["skill brainstorm: the Codex copy lacks \"get the user's approval of a design\""])

    def test_bad_marker_reported_not_raised(self):
        t = self._tree()
        (t / "claude/skills/brainstorm/SKILL.md").write_text("<!-- codex -->\nunclosed\n", encoding="utf-8")
        for argv in (["--check", "--repo", str(t)], ["--repo", str(t)]):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(scp.main(argv), 1)
            self.assertIn("error: claude/skills/brainstorm/SKILL.md: unclosed <!-- codex --> marker", buf.getvalue())
        self.assertFalse((t / "codex/skills/brainstorm").exists())

    def test_check_passes_on_synced_tree(self):
        t = self._tree()
        scp.sync(t)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(scp.main(["--check", "--repo", str(t)]), 0)


if __name__ == "__main__":
    unittest.main()
