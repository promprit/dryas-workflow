import sys, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import render
from test_pstack_content import LEAK
import re
CD_PATH = re.compile(r"(?:\{\{CD\}\}|\$\{CLAUDE_PLUGIN_ROOT\})/([A-Za-z0-9_./-]+)")
ROOT = "${CLAUDE_PLUGIN_ROOT}"
REPO = HERE.parents[1]
FIX = HERE / "fixtures" / "pre_pstack"
FILES = {"executor.md": "claude/agents/executor.md", "orchestrate-claude.md": "claude/skills/orchestrate/SKILL.md",
         "orchestrate-codex.md": "codex/skills/orchestrate/SKILL.md", "CLAUDE.md.template": "claude/CLAUDE.md.template",
         "AGENTS.md.template": "codex/AGENTS.md.template"}
MODEL_POLICY_OWNERS = {"claude/skills/orchestrate/SKILL.md"}


SETTINGS = "the account's settings.json (`$CLAUDE_CONFIG_DIR/settings.json`, default `~/.claude/settings.json`)"


def plugin_form(t):
    """The pre-pstack fixtures are old releases: apply the plugin rewrite (no install tokens) to compare."""
    for a, b in (('"{{PY}}" -X utf8 "{{CD}}/', '"%s/bin/dryas-py" "%s/' % (ROOT, ROOT)), ("{{CD}}", ROOT),
                 ("mcp__jev__", "mcp__plugin_dryas_jev__"),
                 ("~/.claude/jev/thresholds.json", "~/.dryas/jev/thresholds.json"),
                 ("~/.claude/jev/thresholds.py", ROOT + "/jev/thresholds.py"),
                 ("~/.claude/skills/orchestrate/", ROOT + "/skills/orchestrate/"),
                 ("`~/.claude/jev/chain.json`", "`jev/chain.json` in the Dryas plugin folder"),
                 ("`~/.claude/pstack/benchmark-checklist.md`", "`pstack/benchmark-checklist.md` in the Dryas plugin folder"),
                 ("`~/.claude/agents/executor.md`", "`agents/executor.md` in the Dryas plugin folder"),
                 ("`subagent_type: executor`", "`subagent_type: dryas:executor`"),
                 ("`~/.claude/docs/dryas-workflow.md` (installed from", "`~/.dryas/docs/dryas-workflow.md` (written by setup from"),
                 ("`~/.claude/docs/dryas-local.md`", "`~/.dryas/docs/dryas-local.md`"),
                 ("then re-run the installer. Never hand-edit the installed copies or this block.",
                  "then re-run setup (`install/install.sh`, once per Claude config dir). Never hand-edit the plugin files, the copy in `~/.dryas/docs`, or these injected rules."),
                 ("`~/.claude/settings.json`. Show", SETTINGS + ". Show"),
                 ("(`\"model\": \"opus\"` in ~/.claude/settings.json)", "(`\"model\": \"opus\"`, set by setup in " + SETTINGS + ")"),
                 ("`agents/executor.md` in the Dryas plugin folder stays", "the plugin's `dryas:executor` agent stays"),
                 ("plain Claude on Opus.", "plain Claude on the strong tier."),
                 ("- Orchestrator: Opus, always", "- Orchestrator: strong tier, always"),
                 ("- Executors: Haiku first.", "- Executors: fast tier first."),
                 ("(or Opus judgment) starts", "(or strong-tier judgment) starts"),
                 ("agent stays Sonnet so review dispatches never run on Haiku.", "agent stays on the standard tier so review dispatches never run on the fast tier."),
                 ("Haiku → Sonnet → Opus → Fable. A task Haiku fails", "fast → standard → strong → frontier (tier-to-model table in `~/.dryas/docs/dryas-workflow.md`). A task the fast tier fails"),
                 ("goes to Sonnet; a task Sonnet can't finish goes to an Opus executor; Fable is used only if the Opus executor also fails",
                  "goes to the standard tier; a task the standard tier can't finish goes to a strong executor; the frontier tier is used only if the strong executor also fails"),
                 ("escalate → Opus decides.", "escalate → the strong tier decides."),
                 ("Fable dispatches", "frontier dispatches"),
                 ("with the Opus orchestrator, Haiku-first executors", "with the strong-tier orchestrator, fast-first executors"),
                 ("you (Opus) decide", "you (the strong tier) decide"),
                 ("as Opus orchestrator with Haiku-first executors (Sonnet, Opus, Fable on escalation)", "as strong-tier orchestrator with fast-first executors (standard, strong, frontier on escalation)"),
                 ("You (Opus) plan,", "You (the strong tier) plan,"),
                 ("so ESC-M1 counts it the same way as before Haiku;", "so ESC-M1 counts it the same way as before the fast tier;"),
                 ("no `model` (Sonnet from the agent's frontmatter)", "no `model` (standard tier from the agent's frontmatter)"),
                 ("no `model` (Sonnet), after", "no `model` (standard tier), after"),
                 ("Never dispatch Fable here: Fable is only reached through §7. Review, interrogate and cleanup dispatches (§7b) never use Haiku: they start on Sonnet (no `model`)",
                  "Never dispatch the frontier tier here: it is only reached through §7. Review, interrogate and cleanup dispatches (§7b) never use the fast tier: they start on the standard tier (no `model`)"),
                 ("Ladder: **Haiku → Sonnet → Opus → Fable**. Fable is used only when Opus also could not do the task.",
                  "Ladder: **fast → standard → strong → frontier**. The frontier tier is used only when the strong tier also could not do the task."),
                 ("First Sonnet failure: re-dispatch once more on Sonnet with the failure details; the second Sonnet failure escalates to Opus.",
                  "First standard-tier failure: re-dispatch once more on standard with the failure details; the second standard failure escalates to strong."),
                 ("1. A Haiku executor that fails", "1. A fast-tier executor that fails"),
                 ("is re-dispatched with no `model` (Sonnet). Call", "is re-dispatched with no `model` (standard tier). Call"),
                 ("From there the Sonnet rules below apply, starting at zero Sonnet failures.", "From there the standard-tier rules below apply, starting at zero standard failures."),
                 ("2. A Sonnet executor that fails", "2. A standard-tier executor that fails"),
                 ("3. If the Opus executor succeeds, stop: no Fable.", "3. If the strong executor succeeds, stop: no frontier."),
                 ("4. Only if the Opus executor fails", "4. Only if the strong executor fails"),
                 ("reason naming what Opus could not resolve). If Fable is unavailable", "reason naming what the strong tier could not resolve). If the frontier tier is unavailable"),
                 ("5. A Fable failure comes", "5. A frontier failure comes")):
        t = t.replace(a, b)
    return with_rea_line(t, "- Design work")


REA_LINE = "- Reverse-engineering work (how software you don't have the source for does something): use REA; brainstorm says when it recommends it, the user can decline."


def with_rea_line(t, anchor):
    """The REA rule came after the fixtures: insert it on its own line right after the anchor line."""
    return re.sub(r"^(%s.*\n)" % re.escape(anchor), lambda m: m.group(1) + REA_LINE + "\n", t, count=1, flags=re.M)


CODEX_SKILLS = re.compile(r"\$(benchmark-checklist|orchestrate|interrogate|wreview|commit|wplan|tune)(?![A-Za-z0-9_-])")
CODEX_ROOT_LINE = ("`<dryas-root>` and `<dryas-py>` are given in the Dryas rules (\"Dryas paths:\"). If they are missing, "
                   "the Dryas hooks are not trusted: tell the user to run /hooks in Codex and stop.\n\n")


def codex_form(t, rel):
    """The plugin rewrite of a pre-pstack Codex file: $dryas:<skill> names; skills use <dryas-root>/<dryas-py>
    (given by the rules hook); AGENTS.md keeps {{CD}} (rendered by the hook) and points at ~/.dryas/docs."""
    t = CODEX_SKILLS.sub(r"$dryas:\1", t)
    if rel.endswith("AGENTS.md.template"):
        t = t.replace("Full reference: `{{CD}}/docs/dryas-workflow.md`.",
                      "Full reference: `~/.dryas/docs/dryas-workflow.md` (local notes, if present: "
                      "`~/.dryas/docs/dryas-local.md`).")
        return with_rea_line(t, "- Brainstorm first")
    for a, b in (('"{{PY}}" -X utf8 "{{CD}}/jev/', '"<dryas-py>" -X utf8 "<dryas-root>/jev/'),
                 ("{{CD}}/jev/thresholds.json", "~/.dryas/jev/thresholds.json"), ("{{CD}}/", "<dryas-root>/")):
        t = t.replace(a, b)
    if rel.endswith("orchestrate/SKILL.md"):
        t = t.replace("# Orchestrate (Codex)\n\n", "# Orchestrate (Codex)\n\n" + CODEX_ROOT_LINE, 1)
    return t


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def block_lines(text):
    off = set(render.gate_blocks(text, []).splitlines())
    return [l for l in render.gate_blocks(text, ["pstack-picks"]).splitlines() if l not in off]


class PstackLoopTest(unittest.TestCase):
    def test_off_is_byte_identical(self):
        for fix, rel in FILES.items():
            want = (FIX / fix).read_text(encoding="utf-8")
            if rel.startswith("claude/"):
                want = plugin_form(want)
            else:
                want = codex_form(want, rel)
            self.assertEqual(render.gate_blocks(read(rel), []), want, rel)

    def test_tier_words_in_rules(self):
        t = read("claude/CLAUDE.md.template")
        self.assertIn("fast → standard → strong → frontier", t)
        prose = re.sub(r"`[^`]*`", "", t)
        self.assertIsNone(re.search(r"Haiku|Sonnet|Opus|Fable", prose))

    def test_orchestrate_on_content(self):
        on = render.gate_blocks(read("claude/skills/orchestrate/SKILL.md"), ["pstack-picks"])
        for s in ('"needs_interrogate"', "interrogate.min_confidence", "${CLAUDE_PLUGIN_ROOT}/skills/interrogate/SKILL.md",
                  "${CLAUDE_PLUGIN_ROOT}/pstack/cleanup.md", "dryas:debug", "same model",
                  "after every build task has left `.orchestrate/active.json`", "none (review)", "none (cleanup)",
                  "${CLAUDE_PLUGIN_ROOT}/pstack/benchmark-checklist.md", "Never put the top rung on the panel"):
            self.assertIn(s, on, s)

    def test_codex_orchestrate_on_content(self):
        on = render.gate_blocks(read("codex/skills/orchestrate/SKILL.md"), ["pstack-picks"])
        for s in ("needs_interrogate", "$dryas:interrogate", "<dryas-root>/pstack/cleanup.md", "root cause",
                  "after every build task has left `.orchestrate/active.json`"):
            self.assertIn(s, on, s)
        self.assertNotIn("Fable", on)

    def test_executor_principles(self):
        on = render.gate_blocks(read("claude/agents/executor.md"), ["pstack-picks"])
        for n in ("fix-root-causes", "prove-it-works", "test-behavior-not-implementation", "subtract-before-you-add"):
            self.assertIn("${CLAUDE_PLUGIN_ROOT}/pstack/principles/%s.md" % n, on)

    def test_block_text_has_no_leaks_and_paths_resolve(self):
        for rel in FILES.values():
            lines = block_lines(read(rel))
            self.assertTrue(lines, rel)
            for line in lines:
                if rel not in MODEL_POLICY_OWNERS:
                    self.assertIsNone(LEAK.search(line), (rel, line))
                for p in CD_PATH.findall(line):
                    self.assertTrue((REPO / "claude" / p.rstrip(".`")).exists(), (rel, p))


if __name__ == "__main__":
    unittest.main()
