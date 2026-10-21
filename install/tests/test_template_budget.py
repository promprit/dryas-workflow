import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRE = ROOT / "install/tests/fixtures/template-pre-2.0"
PAIRS = (("claude/CLAUDE.md.template", "CLAUDE.md.template"), ("codex/AGENTS.md.template", "AGENTS.md.template"))
BUDGET = {"claude/CLAUDE.md.template": 3700, "codex/AGENTS.md.template": 2575}  # measured 3681 and 2546 on 2026-10-21 (REA rule added); claude has no headroom by design


def rows(text, title):
    sect = text.split("## " + title)[1].split("\n## ")[0]
    out = {}
    for line in sect.splitlines():
        m = re.match(r"^\| (.+?) \| (.+?) \|$", line)
        if m and not m.group(1).startswith(("Rule", "---")):
            out[m.group(1).strip()] = m.group(2).strip()
    return out


class BudgetTest(unittest.TestCase):
    def test_sizes_within_budget(self):
        for p, _ in PAIRS:
            self.assertGreater(BUDGET[p], 0, "budget not set")
            self.assertLessEqual(len((ROOT / p).read_bytes()), BUDGET[p], p)

    def test_every_pre_rule_is_covered(self):
        cov = (ROOT / "docs/template-coverage.md").read_text(encoding="utf-8")
        for p, fx in PAIRS:
            table = rows(cov, p)
            for line in (PRE / fx).read_text(encoding="utf-8").splitlines():
                key = line.strip().lstrip("- ").strip()
                if not key or key.startswith("#") or key.startswith("<!--"):
                    continue
                self.assertIn(key[:60], {k[:60] for k in table}, "%s: no coverage row for %r" % (p, key[:60]))
            for target in table.values():
                if target.startswith("pointer: "):
                    path, _, head = target[len("pointer: "):].partition("#")
                    t = (ROOT / path).read_text(encoding="utf-8")
                    self.assertIn(head.replace("-", " ").lower(), t.lower(), target)
