"""dryas:lens (spec 2026-10-28-lens-design.md): skill shape, the Canopy contract, and the edition copies."""
import json
import re
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import sync_codex_plugin as scp  # noqa: E402
import sync_opencode as so  # noqa: E402

SKILL = ROOT / "claude/skills/lens/SKILL.md"
REF = ROOT / "claude/skills/lens/reference.md"
CMD = ROOT / "claude/commands/lens.md"
FIXTURE = ROOT / "install/tests/fixtures/lens-block.md"
LABELS = ("dryas:lens design", "dryas:lens product", "dryas:lens design+product")
PREFIXES = ("- Panel: ", "- Focus (Jobs): ", "- Data (Ng): ", "- Craft (Ive): ", "- Verdict: ")


def read(p):
    return Path(p).read_text(encoding="utf-8")


def section(text, title):
    return text.split("## " + title, 1)[1].split("\n## ", 1)[0]


def block_section():
    return read(REF).split("## Lens block", 1)[1]


class LensSkillTest(unittest.TestCase):
    def test_skill_shape(self):
        t = read(SKILL)
        self.assertTrue(t.startswith("---\nname: lens\ndescription: Use when "))
        self.assertNotIn("disable-model-invocation", t.split("---", 2)[1])
        n = len(t.splitlines())
        self.assertTrue(50 <= n <= 150, n)
        self.assertLess(len(read(REF).splitlines()), 500)

    def test_panels_and_lenses(self):
        t = read(SKILL) + read(REF)
        for s in ("design panel", "product panel", "design+product", "3 lens", "focus", "data", "craft",
                  "`impeccable`", "`ui-ux-pro-max`", "(Jobs)", "(Ng)", "(Ive)"):
            self.assertIn(s, t, s)

    def test_labels_and_file_name(self):
        t = read(SKILL)
        for label in LABELS:
            self.assertIn("`%s`" % label, t)
        self.assertIn("-lens.html", t)

    def test_block_prefixes_exact(self):
        block = block_section()
        fixture = read(FIXTURE)
        self.assertIn(fixture.strip(), block)
        tops = [l for l in fixture.splitlines() if l.startswith("- ")]
        self.assertEqual([next(p for p in PREFIXES if l.startswith(p)) for l in tops], list(PREFIXES))
        self.assertTrue(any(l.startswith("  - ") for l in fixture.splitlines()))

    def test_no_insight_cap(self):
        block = block_section()
        self.assertIn("no limit", block)
        self.assertIsNone(re.search(r"at most \d+ (insights|characters)", block))

    def test_skip_rule(self):
        t = read(SKILL)
        self.assertIn("skipped (not available)", t)
        self.assertIn("craft always runs", t)

    def test_rerun_rules(self):
        t = read(SKILL)
        sect = section(t, "Re-run")
        for s in ("`## Lens` block", "claude.ai", "local path", "replace"):
            self.assertIn(s, sect, s)

    def test_guardrails(self):
        t = read(SKILL)
        for s in ("Never quote", "endorsement", "approval stays the gate"):
            self.assertIn(s, t, s)

    def test_orchestrate_never_publishes_unasked(self):
        self.assertIn("only when the user asked for artifacts when starting the run", read(SKILL))

    def test_command(self):
        t = read(CMD)
        self.assertIn("Skill(dryas:lens)", t)
        self.assertIn("Artifact", t.split("---", 2)[1])
        self.assertIn("$ARGUMENTS", t)
        head = t.split("---", 2)[1]
        for s in ("Edit", "Skill(impeccable)", "Skill(impeccable:impeccable)", "Skill(ui-ux-pro-max)",
                  "Skill(ui-ux-pro-max:ui-ux-pro-max)", "Skill(artifact-design)"):
            self.assertIn(s, head, s)
        self.assertNotIn("Bash(open", head)

    def test_orchestrate_mode(self):
        t = read(SKILL)
        self.assertIn("## Inside /orchestrate", t)
        for s in ("skip § Re-run and step 6", "never write or change the spec's `## Lens` block",
                  "`.orchestrate/<branch-slug>-lens.html`", "lens: <finding> — <change>"):
            self.assertIn(s, t, s)
        self.assertNotIn("lens-<branch>", t)
        self.assertNotIn("open <path>", t)
        for p in ("codex/skills/lens/SKILL.md", "opencode/skill/dryas-lens/SKILL.md"):
            self.assertIn("<branch-slug>-lens.html", read(ROOT / p), p)

    def test_panel_runs_in_subagent(self):
        t = read(SKILL)
        for s in ('subagent_type: "general-purpose"', 'model: "haiku"', "designer: lens review",
                  "reply with ONLY", "never run Bash"):
            self.assertIn(s, t, s)
        head = t.split("---", 2)[1]
        tools = [l for l in head.splitlines() if l.startswith("allowed-tools:")][0]
        self.assertIn("Agent", tools.split(": ", 1)[1].split(", "))
        self.assertIn("## Subagent reply", read(REF))
        codex = read(ROOT / "codex/skills/lens/SKILL.md")
        self.assertIn("sub-agent", codex)
        oc = read(ROOT / "opencode/skill/dryas-lens/SKILL.md")
        self.assertIn("task tool", oc)
        self.assertIn("dryas-executor-fast", oc)
        for ed in (codex, oc):
            self.assertNotIn("Artifact tool", ed)

    def test_reply_ends_with_block(self):
        for p in ("claude/skills/lens/SKILL.md", "codex/skills/lens/SKILL.md", "opencode/skill/dryas-lens/SKILL.md"):
            self.assertIn("Always end your reply with the `## Lens` section exactly", read(ROOT / p), p)

    def test_sync_lists(self):
        self.assertEqual(scp.OWN_SKILLS, ("lens",))
        self.assertNotIn("lens", scp.PROCESS_SKILLS)
        self.assertIn("lens", scp.COMMANDS)
        self.assertIn("lens", so.THIN)

    def test_editions_never_name_artifact(self):
        for p in ("codex/skills/lens/reference.md", "opencode/skill/dryas-lens/reference.md"):
            self.assertNotIn("Artifact tool", read(ROOT / p), p)
        for p in ("codex/skills/lens/SKILL.md", "opencode/skill/dryas-lens/SKILL.md"):
            t = read(ROOT / p)
            self.assertNotIn("Artifact tool", t, p)
            self.assertNotIn("claude.ai", t, p)
            self.assertIn("docs/lens/", t, p)
        self.assertIn("$dryas:lens", read(ROOT / "codex/skills/lens/SKILL.md"))
        self.assertIn("Load the `dryas-lens` skill", read(ROOT / "opencode/command/lens.md"))
        self.assertIn("allow_implicit_invocation: true", read(ROOT / "codex/skills/lens/agents/openai.yaml"))


class ArtifactAllowTest(unittest.TestCase):
    def test_artifact_pre_allowed(self):
        frag = json.loads(read(ROOT / "claude/settings.fragment.json"))
        self.assertNotIn("Artifact", frag["core"]["permissions"]["allow"])
        head = read(SKILL).split("---")[1]
        tools = [l for l in head.splitlines() if l.startswith("allowed-tools:")][0]
        self.assertIn("Artifact", tools.split(": ", 1)[1].split(", "))
        self.assertIn("Skill(impeccable)", tools)

    def test_lens_skill_load_pre_allowed(self):
        frag = json.loads(read(ROOT / "claude/settings.fragment.json"))
        self.assertIn("Skill(dryas:lens)", frag["core"]["permissions"]["allow"])


if __name__ == "__main__":
    unittest.main()
