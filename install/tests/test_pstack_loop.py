import sys, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import render
from test_pstack_content import LEAK
from test_pstack_skills import CD_PATH
REPO = HERE.parents[1]
FIX = HERE / "fixtures" / "pre_pstack"
FILES = {"executor.md": "claude/agents/executor.md", "orchestrate-claude.md": "claude/skills/orchestrate/SKILL.md",
         "orchestrate-codex.md": "codex/skills/orchestrate/SKILL.md", "CLAUDE.md.template": "claude/CLAUDE.md.template",
         "AGENTS.md.template": "codex/AGENTS.md.template"}
MODEL_POLICY_OWNERS = {"claude/skills/orchestrate/SKILL.md"}


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def block_lines(text):
    off = set(render.gate_blocks(text, []).splitlines())
    return [l for l in render.gate_blocks(text, ["pstack-picks"]).splitlines() if l not in off]


class PstackLoopTest(unittest.TestCase):
    def test_off_is_byte_identical(self):
        for fix, rel in FILES.items():
            self.assertEqual(render.gate_blocks(read(rel), []), (FIX / fix).read_text(encoding="utf-8"), rel)

    def test_orchestrate_on_content(self):
        on = render.gate_blocks(read("claude/skills/orchestrate/SKILL.md"), ["pstack-picks"])
        for s in ('"needs_interrogate"', "interrogate.min_confidence", "{{CD}}/skills/interrogate/SKILL.md",
                  "{{CD}}/pstack/cleanup.md", "superpowers:systematic-debugging", "same model",
                  "after every build task has left `.orchestrate/active.json`", "none (review)", "none (cleanup)",
                  "{{CD}}/pstack/benchmark-checklist.md", "Never put the top rung on the panel"):
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
            self.assertIn("{{CD}}/pstack/principles/%s.md" % n, on)

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
