import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OLD = re.compile(r"Sonnet → Opus → Fable|sonnet -> opus -> fable|\[sonnet, opus, fable\]|\{sonnet: 2, opus: 1\}|^\s*executor: sonnet\s*$", re.M)
NEW_PREFIX = re.compile(r"(Haiku → |haiku -> )$")


def files():
    roots = [REPO / "docs", REPO / "reference", REPO / "spec", REPO / "claude" / "skills", REPO / "claude" / "commands"]
    out = [REPO / "README.md", REPO / "claude" / "CLAUDE.md.template"]
    for r in roots:
        out += [p for p in r.rglob("*") if p.is_file() and p.suffix in (".md", ".yaml", ".yml", ".template")]
    # dated history: specs and plans keep the words they were written with
    return [p for p in out if "superpowers" not in p.parts and "plans" not in p.parts]


def test_no_three_tier_ladder():
    hits = []
    for p in files():
        text = p.read_text(encoding="utf-8")
        for m in OLD.finditer(text):
            if NEW_PREFIX.search(text[max(0, m.start() - 10):m.start()]):
                continue  # part of the four-tier ladder
            hits.append("%s:%d" % (p.relative_to(REPO).as_posix(), text.count("\n", 0, m.start()) + 1))
    assert hits == []
