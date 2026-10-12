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


def plugin_form(t):
    """The pre-pstack fixtures are old releases: apply the plugin rewrite (no install tokens) to compare."""
    for a, b in (('"{{PY}}" -X utf8 "{{CD}}/', '"%s/bin/dryas-py" "%s/' % (ROOT, ROOT)), ("{{CD}}", ROOT),
                 ("mcp__jev__", "mcp__plugin_dryas_jev__"),
                 ("~/.claude/jev/thresholds.json", "~/.dryas/jev/thresholds.json"),
                 ("~/.claude/jev/thresholds.py", ROOT + "/jev/thresholds.py"),
                 ("~/.claude/skills/orchestrate/", ROOT + "/skills/orchestrate/"),
                 ("`~/.claude/jev/chain.json`", "`jev/chain.json` in the Dryas plugin folder"),
                 ("`~/.claude/pstack/benchmark-checklist.md`", "`pstack/benchmark-checklist.md` in the Dryas plugin folder"),
                 ("`~/.claude/agents/executor.md`", "`agents/executor.md` in the Dryas plugin folder")):
        t = t.replace(a, b)
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
            self.assertEqual(render.gate_blocks(read(rel), []), want, rel)

    def test_orchestrate_on_content(self):
        on = render.gate_blocks(read("claude/skills/orchestrate/SKILL.md"), ["pstack-picks"])
        for s in ('"needs_interrogate"', "interrogate.min_confidence", "${CLAUDE_PLUGIN_ROOT}/skills/interrogate/SKILL.md",
                  "${CLAUDE_PLUGIN_ROOT}/pstack/cleanup.md", "superpowers:systematic-debugging", "same model",
                  "after every build task has left `.orchestrate/active.json`", "none (review)", "none (cleanup)",
                  "${CLAUDE_PLUGIN_ROOT}/pstack/benchmark-checklist.md", "Never put the top rung on the panel"):
            self.assertIn(s, on, s)

    def test_codex_orchestrate_on_content(self):
        on = render.gate_blocks(read("codex/skills/orchestrate/SKILL.md"), ["pstack-picks"])
        for s in ("needs_interrogate", "$interrogate", "{{CD}}/pstack/cleanup.md", "root cause",
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
