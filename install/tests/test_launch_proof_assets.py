import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "claude" / "jev"))
import scope_lock  # noqa: E402

ASSETS = REPO / "docs" / "assets"
MAX_BYTES = 307200


def real_deny_line():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".orchestrate").mkdir()
        (root / ".orchestrate" / "active.json").write_text(json.dumps({"active": [2]}), encoding="utf-8")
        (root / ".orchestrate" / "PLAN.md").write_text(
            "## Task 2: Rate-limit the login endpoint\n\nGoal: x\nScope:\n- src/auth/**\nDone:\n- y\n", encoding="utf-8")
        return scope_lock.check(str(root), str(root / "src" / "billing" / "invoice.ts"))


class ProofAssetsTest(unittest.TestCase):
    def test_card_shows_real_deny_line(self):
        line = real_deny_line()
        self.assertEqual(line, "scope lock: src/billing/invoice.ts is outside the scope of active task(s) 2")
        self.assertIn(line, (ASSETS / "src" / "scope-lock.html").read_text(encoding="utf-8"))

    def test_card_pngs(self):
        for t in ("light", "dark"):
            p = ASSETS / ("scope-lock-%s.png" % t)
            b = p.read_bytes()
            self.assertEqual(b[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", b[16:24]), (2800, 960))
            self.assertLessEqual(len(b), MAX_BYTES, p)

    def test_flowobserve_jpeg(self):
        p = ASSETS / "flowobserve.jpg"
        b = p.read_bytes()
        self.assertEqual(b[:3], b"\xff\xd8\xff")
        self.assertLessEqual(len(b), MAX_BYTES)


if __name__ == "__main__":
    unittest.main()
