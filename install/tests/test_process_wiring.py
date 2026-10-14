"""Rules, commands, skills and agents name the Dryas process skills, never Superpowers ones (owned core C)."""
import re
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import inventory as inv

SP_NAME = re.compile(r"\bsuperpowers:[a-z]")
USES = {
    "claude/CLAUDE.md.template": ("dryas:brainstorm", "dryas:verify"),
    "claude/skills/orchestrate/SKILL.md": ("Skill(dryas:brainstorm)", "Skill(dryas:worktree)", "Skill(dryas:debug)",
                                           "Skill(dryas:verify)", "${CLAUDE_PLUGIN_ROOT}/skills/tdd/SKILL.md"),
    "claude/commands/orchestrate.md": ("Skill(dryas:brainstorm)", "Skill(dryas:worktree)", "Skill(dryas:debug)",
                                       "Skill(dryas:verify)"),
    "claude/commands/wplan.md": ("Skill(dryas:plan)", "dryas:plan skill", "/orchestrate"),
    "claude/commands/wreview.md": ("Skill(dryas:review-request)", "Skill(dryas:review-receive)"),
    "claude/agents/executor.md": ("skills/tdd/SKILL.md", "skills/debug/SKILL.md"),
}


class WiringTest(unittest.TestCase):
    def test_rules_name_only_dryas_process_skills(self):
        for rel, needles in USES.items():
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIsNone(SP_NAME.search(text), rel)
            for n in needles:
                self.assertIn(n, text, (rel, n))

    def test_only_settings_name_superpowers_skills(self):
        for ed in ("claude", "codex"):
            for p in sorted((ROOT / ed).rglob("*")):
                if p.suffix in (".md", ".template", ".json") and p.is_file() and "tests" not in p.parts:
                    if p.name == "settings.fragment.json":
                        continue
                    self.assertIsNone(SP_NAME.search(p.read_text(encoding="utf-8")), p)

    def test_deny_rules_unchanged(self):
        import json
        deny = json.loads((ROOT / "claude/settings.fragment.json").read_text(encoding="utf-8"))["core"]["permissions"]["deny"]
        self.assertEqual(sorted(r for r in deny if r.startswith("Skill(superpowers:")), sorted(
            "Skill(superpowers:%s)" % s for s in ("subagent-driven-development", "executing-plans",
                                                    "dispatching-parallel-agents", "finishing-a-development-branch",
                                                    "diagnosing-superpowers")))

    def test_inventory_maps_to_dryas_skills(self):
        m = inv._json(ROOT / inv.MAP)
        self.assertEqual(m["skill_ref:claude:superpowers:brainstorming"], "skill:claude:brainstorm")
        self.assertEqual(m["allowed_tool:claude:command/wplan:Skill(superpowers:writing-plans)"],
                         "allowed_tool:claude:command/wplan:Skill(dryas:plan)")


if __name__ == "__main__":
    unittest.main()
