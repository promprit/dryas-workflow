"""User-invoked skills orchestrate; model-invoked skills hold discipline; both editions agree (owned core C)."""
import re
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
USER_RUNS = (r"(runs|run|invoke|invokes|logs)\s+`?/(wreview|commit|orchestrate|tune|handoff|interrogate)\b",
             r"`/(wreview|commit)` logs",
             r"run\s+`?\$dryas:(wreview|commit|orchestrate|tune|handoff|interrogate)\b")
sys.path.insert(0, str(ROOT / "tools"))
import sync_codex_plugin as scp


class InvocationTest(unittest.TestCase):
    def test_user_invoked_on_claude(self):
        for n in scp.USER_INVOKED:
            self.assertIs(scp.user_invoked(ROOT, n), True, n)
        for n in scp.PROCESS_SKILLS:
            self.assertIs(scp.user_invoked(ROOT, n), False, n)

    def test_editions_agree(self):
        self.assertEqual(scp.invocation_drift(ROOT), [])
        for d in sorted((ROOT / "codex/skills").iterdir()):
            if (d / "SKILL.md").is_file():
                y = (d / "agents/openai.yaml").read_text(encoding="utf-8")
                want = "false" if d.name in scp.USER_INVOKED else "true"
                self.assertIn("allow_implicit_invocation: %s" % want, y, d.name)

    def test_user_invoked_never_calls_user_invoked(self):
        for n in scp.USER_INVOKED:
            for p in (ROOT / "claude/skills" / n / "SKILL.md", ROOT / "claude/commands" / (n + ".md")):
                if p.is_file():
                    head = p.read_text(encoding="utf-8").split("---", 2)[1]
                    for other in scp.USER_INVOKED:
                        self.assertNotIn("Skill(dryas:%s)" % other, head, (p, other))

    def test_orchestrate_finish_uses_skills(self):
        text = (ROOT / "claude/skills/orchestrate/SKILL.md").read_text(encoding="utf-8")
        for want in ("dryas:review-request", "log_review", "commands/commit.md"):
            self.assertIn(want, text)
        self.assertNotIn("Run `/wreview`", text)

    def test_bodies_never_run_user_invoked(self):
        for n in scp.PROCESS_SKILLS:
            for f in sorted((ROOT / "claude/skills" / n).glob("*.md")):
                if f.name == "UPSTREAM.md":
                    continue
                text = f.read_text(encoding="utf-8")
                for rx in USER_RUNS[:2]:
                    self.assertIsNone(re.search(rx, text), (str(f), rx))
        text = (ROOT / "codex/skills/orchestrate/SKILL.md").read_text(encoding="utf-8")
        self.assertIsNone(re.search(USER_RUNS[2], text))
        self.assertIn("skills/interrogate/SKILL.md", text)

    def test_drift_reports_disagreement(self):
        import shutil, tempfile
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(t), True)
        (t / "claude/commands").mkdir(parents=True)
        (t / "claude/commands/tune.md").write_text("---\ndescription: d\ndisable-model-invocation: true\n---\n", encoding="utf-8")
        (t / "codex/skills/tune/agents").mkdir(parents=True)
        (t / "codex/skills/tune/SKILL.md").write_text("---\nname: tune\ndescription: d\n---\n", encoding="utf-8")
        (t / "codex/skills/tune/agents/openai.yaml").write_text(scp.openai_yaml(True), encoding="utf-8")
        self.assertEqual(scp.invocation_drift(t), ["skill tune: codex allow_implicit_invocation is true, "
                                                   "claude says user-invoked"])

    def test_orchestrate_allows_commit_tools(self):
        """/orchestrate's finish runs the commit steps, so it may use every tool /commit lists."""
        import inventory

        def tools(rel):
            m = re.search(r"^allowed-tools:\s*(.+)$", (ROOT / rel).read_text(encoding="utf-8"), re.M)
            return {t.strip() for t in inventory._SPLIT.split(m.group(1)) if t.strip()}
        want = tools("claude/commands/commit.md")
        self.assertTrue(want)
        for rel in ("claude/skills/orchestrate/SKILL.md", "claude/commands/orchestrate.md"):
            self.assertEqual(want - tools(rel), set(), rel)


if __name__ == "__main__":
    unittest.main()
