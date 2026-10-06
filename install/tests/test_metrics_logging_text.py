from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def test_orchestrate_texts_log_dispatch_and_merge():
    for rel in ("claude/skills/orchestrate/SKILL.md", "codex/skills/orchestrate/SKILL.md"):
        t = read(rel)
        for s in ("log_dispatch", "log_merge", "<question>.<task>"):
            assert s in t, (rel, s)


def test_wreview_texts_log_review():
    for rel in ("claude/commands/wreview.md", "codex/skills/wreview/SKILL.md"):
        assert "log_review" in read(rel), rel
