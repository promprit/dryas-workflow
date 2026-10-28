import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import sync_codex_plugin as scp  # noqa: E402
import sync_opencode as so  # noqa: E402


class OpenCodeSyncTest(unittest.TestCase):
    def test_names_rewrite_codex_text(self):
        text = ("Call `jev_judge` (server `jev`), then `memory_store`. Run `$dryas:orchestrate`, load "
                "`$dryas:brainstorm`, read `<dryas-root>/skills/tdd/SKILL.md`. Codex sub-agents help.")
        self.assertEqual(so.names(text),
                         "Call `jev_jev_judge`, then `jev_memory_store`. Run `/orchestrate`, load "
                         "`dryas-brainstorm`, read `<dryas-root>/../skill/dryas-tdd/SKILL.md`. OpenCode subagents help.")

    def test_names_rewrite_claude_text(self):
        text = ('Use dryas:verify and mcp__plugin_dryas_jev__memory_search; run '
                '"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/planfile.py"; read '
                '${CLAUDE_PLUGIN_ROOT}/skills/plan/reference.md and ${CLAUDE_PLUGIN_ROOT}/commands/commit.md. '
                'Keep dryas@dryas-workflow.')
        self.assertEqual(so.names(text),
                         'Use dryas-verify and jev_memory_search; run '
                         '"<dryas-py>" -X utf8 "<dryas-root>/jev/planfile.py"; read '
                         '<dryas-root>/../skill/dryas-plan/reference.md and <dryas-root>/../command/commit.md. '
                         'Keep dryas@dryas-workflow.')

    def test_opencode_block_kept_only_for_opencode(self):
        text = "a\n<!-- opencode -->\nX\n<!-- /opencode -->\n<!-- codex -->\nY\n<!-- /codex -->\nb\n"
        self.assertEqual(scp.harness_blocks(text, "opencode"), "a\nX\nb\n")
        self.assertEqual(scp.harness_blocks(text, "codex"), "a\nY\nb\n")

    def test_plan_shape(self):
        p = so.plan(REPO)
        for rel in ("opencode/dryas/jev/chain.py", "opencode/dryas/pstack/cleanup.md",
                    "opencode/dryas/AGENTS.md.template", "opencode/skill/dryas-brainstorm/SKILL.md",
                    "opencode/command/orchestrate.md", "opencode/command/commit.md",
                    "opencode/agent/dryas-executor-fast.md", "opencode/agent/dryas-executor-frontier.md",
                    "opencode/skill/dryas-lens/SKILL.md", "opencode/command/lens.md"):
            self.assertIn(rel, p)
        self.assertIn("Load the `dryas-lens` skill", p["opencode/command/lens.md"])
        self.assertFalse(any(k.startswith("opencode/dryas/jev/tests/") for k in p))
        self.assertFalse(any(k.startswith("opencode/plugin/") for k in p))
        self.assertFalse(any(k == "opencode/skill/dryas-%s/SKILL.md" % h for h in so.HAND for k in p))
        skill = p["opencode/skill/dryas-brainstorm/SKILL.md"]
        self.assertTrue(skill.startswith('---\nname: dryas-brainstorm\ndescription: "'))
        self.assertIn(so.MARK, skill)
        agent = p["opencode/agent/dryas-executor-strong.md"]
        self.assertIn("mode: subagent\nmodel: {{MODEL}}\n", agent)
        self.assertIn("Tier: strong.", agent)
        thin = p["opencode/command/orchestrate.md"]
        self.assertIn("Load the `dryas-orchestrate` skill", thin)
        self.assertIn("$ARGUMENTS", p["opencode/command/commit.md"])
        rules = p["opencode/dryas/AGENTS.md.template"]
        self.assertIn("# Dryas Workflow (OpenCode)", rules)
        self.assertIn("dryas-executor-fast", rules)
        self.assertNotIn("Not available in Codex", rules)

    def test_handoff_command_and_rules_tail(self):
        out = so.plan(REPO)
        self.assertIn(so.MARK, out["opencode/command/handoff.md"])
        self.assertNotIn("Not yet on OpenCode", out["opencode/dryas/AGENTS.md.template"])
        self.assertIn("/handoff", out["opencode/dryas/AGENTS.md.template"])

    def test_repo_has_no_drift_or_leaks(self):
        self.assertEqual(so.drift(REPO), [])
        self.assertEqual(so.leaks(REPO), [])

    def test_sync_rebuilds_a_copy(self):
        with tempfile.TemporaryDirectory() as d:
            for sub in ("claude/jev", "claude/pstack", "claude/skills", "claude/agents", "codex/skills", "opencode"):
                if (REPO / sub).is_dir():
                    shutil.copytree(str(REPO / sub), str(Path(d) / sub))
            shutil.copy(str(REPO / "codex/AGENTS.md.template"), str(Path(d) / "codex/AGENTS.md.template"))
            (Path(d) / "opencode/command/commit.md").unlink()
            (Path(d) / "opencode/command/stray.md").write_text("x", encoding="utf-8")
            self.assertIn("missing opencode/command/commit.md", so.drift(Path(d)))
            self.assertIn("extra opencode/command/stray.md", so.drift(Path(d)))
            so.sync(Path(d))
            self.assertEqual(so.drift(Path(d)), [])


if __name__ == "__main__":
    unittest.main()
