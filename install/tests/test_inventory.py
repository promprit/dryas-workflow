"""No-loss inventory (owned core, plan 0): every 1.x surface stays or is mapped."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import inventory as inv  # noqa: E402


def _static(repo):
    got = set()
    for c in inv.STATIC:
        got |= c(repo)
    return got


class StaticTest(unittest.TestCase):
    def test_static_surfaces_of_this_repo(self):
        got = _static(ROOT)
        for e in (
            "mcp_server:claude:jev", "mcp_server:codex:jev",
            "plugin_dep:claude:superpowers", "plugin_config:claude:openrouter_key",
            "command:claude:commit", "command:claude:wplan", "command:claude:orchestrate",
            "skill:claude:orchestrate", "skill:codex:wplan", "agent:claude:executor",
            "allowed_tool:claude:skill/orchestrate:mcp__plugin_ruflo-core_ruflo__swarm_init",
            "allowed_tool:claude:skill/orchestrate:Skill(superpowers:brainstorming)",
            "allowed_tool:claude:command/wplan:Skill(superpowers:writing-plans)",
            "skill_ref:claude:superpowers:brainstorming", "tool_ref:codex:memory_search",
            "plugin_hook:claude:PreToolUse:Bash|Edit|Write|MultiEdit|NotebookEdit:chain.py pretool",
            "plugin_hook:codex:PreToolUse:Bash|apply_patch|Edit|Write:chain.py pretool --harness codex",
            "plugin_hook:claude:PreCompact:*:compact_keep.py",
            "chain_stage:pretool:scope-lock:core", "chain_stage:pretool:ruflo-pre-bash:ruflo",
            "chain_stage:prompt:jev-route:jev",
            "settings_hook:ruflo:PostToolUse:Write|Edit|MultiEdit:hook-handler.cjs post-edit",
            "permission:core:deny:Skill(superpowers:executing-plans)",
            "env:ruflo:CLAUDE_FLOW_MEMORY_PATH", "setting:core:model",
            "component:ruflo", "component:superpowers", "component:design",
        ):
            self.assertIn(e, got)

    def test_allowed_tools_keep_parenthesised_commas(self):
        got = _static(ROOT)
        planfile = [e for e in got if e.startswith("allowed_tool:claude:skill/orchestrate:Bash(") and "planfile.py" in e]
        self.assertEqual(len(planfile), 1, planfile)

    def test_generated_codex_copies_are_not_scanned(self):
        self.assertFalse([e for e in _static(ROOT) if ":jev/" in e or ":pstack/" in e])


class MalformedTest(unittest.TestCase):
    def test_bad_json_names_the_file(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        (t / "claude/jev").mkdir(parents=True)
        (t / "claude/jev/chain.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(inv.InventoryError) as cm:
            inv._hooks(t)
        self.assertIn("chain.json", str(cm.exception))
