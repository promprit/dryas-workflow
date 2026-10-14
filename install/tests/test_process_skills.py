"""Dryas process skills (owned core C): shape, no Superpowers names, clean Codex copies, complete coverage tables."""
import os
import re
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import sync_codex_plugin as scp

SKILLS = ROOT / "claude" / "skills"
UPSTREAM = SKILLS / "UPSTREAM.md"
UPSTREAM_OF = {"brainstorm": "brainstorming", "worktree": "using-git-worktrees", "debug": "systematic-debugging",
               "verify": "verification-before-completion", "plan": "writing-plans",
               "review-request": "requesting-code-review", "review-receive": "receiving-code-review",
               "tdd": "test-driven-development"}
PHRASE_FILES = {"template": ROOT / "claude/CLAUDE.md.template", "executor": ROOT / "claude/agents/executor.md",
                "orchestrate": SKILLS / "orchestrate/SKILL.md"}
SECTION = re.compile(r"^([a-z-]+/[A-Za-z0-9_.-]+\.md) § (.+)$")
PHRASE = re.compile(r'^(template|executor|orchestrate): "(.+)"$')
SP_NAME = re.compile(r"\bsuperpowers:[a-z]")
CLAUDE_ONLY = ("${CLAUDE_PLUGIN_ROOT}", "mcp__plugin_", "Skill(", "subagent_type", "EnterWorktree")
CLAUDE_COMMAND = re.compile(r"(?<![\w$/.<-])/(orchestrate|wplan|wreview|commit|tune|interrogate)\b(?![/\w-]|\.\w)")


def present():
    return [n for n in scp.PROCESS_SKILLS if (SKILLS / n / "SKILL.md").is_file()]


def tables():
    """Dryas skill -> list of (upstream cell, target cell) rows."""
    out = {}
    for f in [UPSTREAM] + [SKILLS / n / "UPSTREAM.md" for n in scp.PROCESS_SKILLS]:
        if f.is_file():
            parse_table(f, out)
    return out


def parse_table(f, out):
    cur = None
    for line in f.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## ([a-z-]+)$", line)
        if m:
            cur = out.setdefault(m.group(1), [])
        elif cur is not None and line.startswith("| ") and not line.startswith(("| Upstream item", "|---")):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            cur.append(tuple(cells))


def upstream_dir():
    env = os.environ.get("DRYAS_SUPERPOWERS_SKILLS")
    if env:
        return Path(env)
    for p in sorted(Path.home().glob(".claude*/plugins/cache/claude-plugins-official/superpowers/6.4.1/skills")):
        return p
    return None


def headings(text):
    out, fence = [], None  # the open fence's backtick run: ```` blocks may hold ``` blocks
    for line in text.splitlines():
        m = re.match(r"^(`{3,})", line)
        if m:
            if fence is None:
                fence = m.group(1)
            elif line.strip() == fence:
                fence = None
        elif fence is None:
            m = re.match(r"^#{2,3} (.+?)\s*$", line)
            if m:
                out.append(m.group(1))
    return out


class ProcessSkillsTest(unittest.TestCase):
    def test_present_skills(self):
        # Task 2 lands brainstorm and plan; Tasks 3 and 4 extend this tuple until it is all eight
        self.assertEqual(set(present()), {"brainstorm", "plan", "worktree", "verify", "debug"})

    def test_shape(self):
        for n in present():
            text = (SKILLS / n / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\nname: %s\ndescription: " % n), n)
            desc = re.search(r"^description: (.+)$", text, re.M).group(1)
            self.assertLessEqual(len(desc), 1024, n)
            for f in (SKILLS / n).glob("*.md"):
                self.assertLess(len(f.read_text(encoding="utf-8").splitlines()), 500, f)
        for f in [UPSTREAM] + list(SKILLS.glob("*/UPSTREAM.md")):
            self.assertLess(len(f.read_text(encoding="utf-8").splitlines()), 500, f)

    def test_no_superpowers_names(self):
        files = [UPSTREAM] + [f for n in scp.PROCESS_SKILLS for f in (SKILLS / n).glob("*.md")]
        for f in files:
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                self.assertIsNone(SP_NAME.search(line), (f.name, i, line))

    def test_codex_copies_have_no_claude_names(self):
        for rel, text in scp.skill_plan(ROOT).items():
            if rel.endswith(scp.SKILL_FILES):
                continue
            for s in CLAUDE_ONLY:
                self.assertNotIn(s, text, (rel, s))
            self.assertIsNone(CLAUDE_COMMAND.search(text), rel)

    def test_provenance(self):
        up = UPSTREAM.read_text(encoding="utf-8")
        self.assertIn("5bf4e78011075bcfc0dc295f0724994cd123ee71", up)
        self.assertIn("Jesse Vincent", (SKILLS / "LICENSE-superpowers").read_text(encoding="utf-8"))
        self.assertIn("claude/skills/UPSTREAM.md", (ROOT / "NOTICE.md").read_text(encoding="utf-8"))

    def test_every_present_skill_has_a_table(self):
        t = tables()
        for n in present():
            self.assertTrue(t.get(n), "no coverage table for %s in claude/skills/<skill>/UPSTREAM.md" % n)

    def test_coverage_targets_resolve(self):
        for skill, rows in tables().items():
            for row in rows:
                self.assertEqual(len(row), 2, (skill, row))
                up, target = row
                self.assertTrue(up and target, (skill, row))
                for t in target.split("; "):
                    if t == "extra:superpowers":
                        continue
                    m, p = SECTION.match(t), PHRASE.match(t)
                    if m:
                        f = SKILLS / m.group(1)
                        self.assertTrue(f.is_file(), (skill, t))
                        self.assertIn(m.group(2), headings(f.read_text(encoding="utf-8"))
                                      + re.findall(r"^#{1,4} (.+?)\s*$", f.read_text(encoding="utf-8"), re.M), (skill, t))
                    elif p:
                        self.assertIn(p.group(2), PHRASE_FILES[p.group(1)].read_text(encoding="utf-8"), (skill, t))
                    else:
                        self.fail("bad target %r in %s" % (t, skill))

    def test_coverage_complete_against_upstream(self):
        base = upstream_dir()
        if base is None:
            self.skipTest("Superpowers 6.4.1 not installed here (set DRYAS_SUPERPOWERS_SKILLS)")
        t = tables()
        for n in present():
            ups = [r[0] for r in t.get(n, [])]
            src = base / UPSTREAM_OF[n]
            for h in headings((src / "SKILL.md").read_text(encoding="utf-8")):
                self.assertTrue(any(u == h or u.startswith(h + " — ") for u in ups), "%s: no row for heading %r" % (n, h))
            for f in sorted(src.iterdir()):
                if f.name == "SKILL.md":
                    continue
                name = f.name + ("/" if f.is_dir() else "")
                self.assertTrue(any(u == name or u.startswith(name + " — ") for u in ups), "%s: no row for %s" % (n, name))


if __name__ == "__main__":
    unittest.main()
