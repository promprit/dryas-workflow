import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class ReleaseRulesTest(unittest.TestCase):
    def test_spec_rules(self):
        s = read("spec/dryas-spec-v1.md")
        self.assertIn("**GOV-12** *(Core)*", s)
        self.assertIn("MUST NOT prompt", s)
        self.assertIn("**REL-1** *(Core)*", s)
        self.assertIn("MUST NOT ship", s)

    def test_conformance_rows(self):
        r = read("reference/README.md")
        self.assertIn("| GOV-12 |", r)
        self.assertIn("| REL-1 |", r)

    def test_injected_rules_and_workflow_doc(self):
        for rel in ("claude/CLAUDE.md.template", "docs/workflow.md"):
            s = read(rel)
            self.assertIn("Nobody is prompted during /orchestrate", s, rel)
            self.assertIn("worse than the last", s, rel)

    def test_release_check_compares(self):
        s = read("tools/release_check.py")
        self.assertIn("compare_v1.py", s)
        self.assertIn("better than previous releases", s)


if __name__ == "__main__":
    unittest.main()
