import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import cloud_text as ct

SKILLS = ("orchestrate", "brainstorm", "plan", "review-request", "review-receive", "tdd", "debug", "verify",
          "worktree", "interrogate")
COMMANDS = ("orchestrate", "wplan", "wreview", "commit", "tune", "handoff", "dryas-cloud")
COMPS = ("core", "jev", "memory", "pstack-picks")
NM = ct.Names("", SKILLS, COMMANDS, ("executor",))
PX = ct.Names("x-", SKILLS, COMMANDS, ("executor",))


class RewriteTest(unittest.TestCase):
    def test_plugin_paths_become_repo_paths(self):
        src = ('"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/tune.py" report; read '
               '`${CLAUDE_PLUGIN_ROOT}/skills/plan/reference.md` and `${CLAUDE_PLUGIN_ROOT}/pstack/cleanup.md`')
        self.assertEqual(ct.rewrite(src, NM, COMPS),
                         '".dryas/bin/dryas-py" ".dryas/jev/tune.py" report; read `.claude/skills/plan/reference.md` '
                         'and `.dryas/pstack/cleanup.md`')
        self.assertIn("`.claude/skills/x-plan/reference.md`", ct.rewrite(src, PX, COMPS))

    def test_home_state_moves_into_the_repo(self):
        src = "Read(~/.dryas/jev/thresholds.json) ~/.dryas/docs/dryas-workflow.md ~/.dryas ~/.dryas-old ~/project"
        self.assertEqual(ct.rewrite(src, NM, COMPS),
                         "Read(.dryas/state/jev/thresholds.json) .dryas/docs/dryas-workflow.md .dryas/state "
                         "~/.dryas-old ~/project")

    def test_plugin_names_become_project_names(self):
        src = ('Skill(dryas:plan), subagent_type: "dryas:executor", mcp__plugin_dryas_jev__log_dispatch, '
               'mcp__plugin_dryas_jev, `$dryas:plan`, dryas:unknown, dryas@dryas-workflow, <!-- dryas:start -->')
        self.assertEqual(ct.rewrite(src, NM, COMPS),
                         'Skill(plan), subagent_type: "executor", mcp__jev__log_dispatch, mcp__jev, `$dryas:plan`, '
                         'dryas:unknown, dryas@dryas-workflow, <!-- dryas:start -->')
        self.assertIn('Skill(x-plan), subagent_type: "x-executor"', ct.rewrite(src, PX, COMPS))

    def test_prefix_renames_commands_only_as_commands(self):
        src = ("Run /wreview, then /tune apply; see docs/plans/, https://example.com/commit/abc, "
               ".orchestrate/PLAN.md and /cost")
        self.assertEqual(ct.rewrite(src, PX, COMPS),
                         "Run /x-wreview, then /x-tune apply; see docs/plans/, https://example.com/commit/abc, "
                         ".orchestrate/PLAN.md and /cost")
        self.assertEqual(ct.rewrite(src, NM, COMPS), src)

    def test_harness_and_component_blocks(self):
        src = ("a\n<!-- claude -->\nc\n<!-- /claude -->\n<!-- codex -->\nx\n<!-- /codex -->\n"
               "<!-- pstack-picks -->\np\n<!-- /pstack-picks -->\nz\n")
        self.assertEqual(ct.rewrite(src, NM, COMPS), "a\nc\np\nz\n")
        self.assertEqual(ct.rewrite(src, NM, ("core",)), "a\nc\nz\n")

    def test_shipped_files_leave_no_plugin_trace(self):
        bad = re.compile(r"(?<![\w$/.@-])dryas:(%s)(?![\w-])" % "|".join(SKILLS + COMMANDS + ("executor",)))
        files = [p for s in SKILLS for p in sorted((ROOT / "claude/skills" / s).rglob("*.md"))]
        files += [p for p in (ROOT / "claude/commands" / (c + ".md") for c in COMMANDS) if p.is_file()]
        files += [ROOT / "claude/agents/executor.md", ROOT / "claude/CLAUDE.md.template", ROOT / "docs/workflow.md"]
        files += sorted((ROOT / "claude/pstack").rglob("*.md"))
        for names in (NM, PX):
            for f in files:
                text = ct.rewrite(f.read_text(encoding="utf-8"), names, COMPS)
                for token in ("${CLAUDE_PLUGIN_ROOT}", "~/.dryas", "mcp__plugin_dryas_jev", "<!-- codex -->"):
                    self.assertNotIn(token, text, (str(f), token))
                self.assertIsNone(bad.search(text), str(f))
                self.assertIsNone(re.search(r"(?<![\w.~-])/(?:Users|Volumes)/", text), str(f))


class HelpersTest(unittest.TestCase):
    def test_set_name(self):
        self.assertEqual(ct.set_name("---\nname: plan\ndescription: d\n---\nname: body\n", "x-plan"),
                         "---\nname: x-plan\ndescription: d\n---\nname: body\n")
        self.assertEqual(ct.set_name("no front matter\n", "x"), "no front matter\n")

    def test_claude_md_body(self):
        tpl = (ROOT / "claude/CLAUDE.md.template").read_text(encoding="utf-8")
        body = ct.claude_md_body(tpl, NM, COMPS, "9.9.9")
        self.assertTrue(body.startswith("Dryas 9.9.9 runs from this repo's `.dryas/` folder"), body[:80])
        self.assertIn("(`/dryas-cloud check` verifies it)", body)
        for token in ("${CLAUDE_PLUGIN_ROOT}", "~/.dryas", "dryas:brainstorm"):
            self.assertNotIn(token, body)
        self.assertIn("`/x-dryas-cloud check`", ct.claude_md_body(tpl, PX, COMPS, "9.9.9"))

    def test_commit_the_notes_line_only_with_persist_memory(self):
        tpl = (ROOT / "claude/CLAUDE.md.template").read_text(encoding="utf-8")
        line = "Before your final commit, include .dryas/memory/notes/ in it."
        self.assertIn(line, ct.claude_md_body(tpl, NM, COMPS, "9.9.9", persist_memory=True))
        self.assertNotIn(line, ct.claude_md_body(tpl, NM, COMPS, "9.9.9"))
        self.assertNotIn(line, ct.claude_md_body(tpl, NM, COMPS, "9.9.9", persist_memory=False))

    def test_third_party_paths(self):
        src = 'python "${CLAUDE_PLUGIN_ROOT}/.claude/skills/ui-ux-pro-max/scripts/search.py" and "${CLAUDE_SKILL_DIR}/x"'
        self.assertEqual(ct.third_party(src, "./.claude/skills/", {"ui-ux-pro-max": "x-ui-ux-pro-max"}),
                         'python ".claude/skills/x-ui-ux-pro-max/scripts/search.py" and "${CLAUDE_SKILL_DIR}/x"')
        self.assertEqual(ct.third_party("${CLAUDE_PLUGIN_ROOT}/src/data", "skills", {}), "${CLAUDE_PLUGIN_ROOT}/src/data")


class GapTest(unittest.TestCase):
    """Added by the executor: gaps a wrong implementation could pass."""

    def test_prefix_is_applied_once(self):
        src = "`${CLAUDE_PLUGIN_ROOT}/commands/tune.md` Skill(dryas:plan) `/tune`\n/wplan"
        out = ct.rewrite(src, PX, COMPS)
        self.assertEqual(out, "`.claude/commands/x-tune.md` Skill(x-plan) `/x-tune`\n/x-wplan")
        self.assertNotIn("x-x-", out)

    def test_slash_rename_skips_non_commands_and_longer_words(self):
        src = "/plan /commit-msg /tuned /commit. (/handoff) `/dryas-cloud check` a/tune"
        self.assertEqual(ct.rewrite(src, PX, COMPS),
                         "/plan /commit-msg /tuned /x-commit. (/x-handoff) `/x-dryas-cloud check` a/tune")

    def test_windows_line_endings_leave_no_trace(self):
        src = "a\r\n<!-- codex -->\r\nx\r\n<!-- /codex -->\r\n${CLAUDE_PLUGIN_ROOT}/jev/x.py ~/.dryas\r\n"
        out = ct.rewrite(src, NM, COMPS)
        self.assertNotIn("codex", out)
        self.assertNotIn("CLAUDE_PLUGIN_ROOT", out)
        self.assertIn(".dryas/jev/x.py .dryas/state", out)

    def test_set_name_unterminated_front_matter_is_unchanged(self):
        self.assertEqual(ct.set_name("---\nname: plan\n", "x"), "---\nname: plan\n")

    def test_third_party_leaves_other_skills_folder_alone(self):
        src = '"${CLAUDE_PLUGIN_ROOT}/other/ui/x.py"'
        self.assertEqual(ct.third_party(src, "./.claude/skills/", {"ui": "x-ui"}), src)


if __name__ == "__main__":
    unittest.main()
