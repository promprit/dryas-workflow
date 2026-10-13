import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TABLED = [REPO / "docs" / "workflow.md", REPO / "spec" / "dryas-spec-v1.md"]
ROWS = {"fast": "Haiku", "standard": "Sonnet", "strong": "Opus", "frontier": "Fable"}
MODEL_WORD = re.compile(r"\b(Haiku|Sonnet|Opus|Fable)\b")


def mapping_rows(text):
    return [l.strip() for l in text.splitlines() if l.strip().startswith("|")]


def test_mapping_tables():
    for p in TABLED:
        rows = mapping_rows(p.read_text(encoding="utf-8"))
        for tier, model in ROWS.items():
            hit = [r for r in rows if "`%s`" % tier in r and model in r]
            assert hit, "%s: no table row for %s/%s" % (p.name, tier, model)
            if tier == "frontier":
                assert "GPT-6 Astra" in hit[0], p.name


def test_ladder_string():
    assert "fast → standard → strong → frontier" in (REPO / "docs" / "workflow.md").read_text(encoding="utf-8")


def test_no_model_names_in_prose():
    files = sorted((REPO / "docs").glob("*.md")) + [REPO / "README.md", REPO / "reference" / "README.md"]
    files += sorted((REPO / "examples").glob("*.md"))
    hits = []
    for p in files:
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if p in TABLED and line.lstrip().startswith("|") and any("`%s`" % t in line for t in ROWS):
                continue  # the mapping table
            if MODEL_WORD.search(re.sub(r"`[^`]*`", "", line)):
                hits.append("%s:%d" % (p.relative_to(REPO), n))
    assert hits == []
