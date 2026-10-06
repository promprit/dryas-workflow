import re
import unittest
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]

FRAMEWORK = ["docs/why-dryas.md", "docs/architecture.md", "docs/memory-model.md", "docs/governance.md",
             "docs/execution-model.md", "docs/escalation-model.md", "docs/review-model.md",
             "docs/adoption-guide.md", "docs/metrics.md", "docs/roles.md", "docs/operating-model.md", "docs/roadmap.md", "spec/dryas-spec-v1.md", "reference/README.md",
             "examples/README.md", "examples/walkthrough.md"]
MANIFESTS = ["reference/dryas.yaml", "examples/manifests/minimal-core.yaml", "examples/manifests/codex.yaml"]
MANIFEST_KEYS = ("dryas", "edition", "harness", "conformance", "workflow", "memory", "governance",
                 "execution", "escalation", "review")
RULE = re.compile(r"\*\*((?:WF|MEM|GOV|EXE|ESC|REV)-\d+)\*\*")


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


class FrameworkDocsTest(unittest.TestCase):
    def test_relative_links_resolve(self):
        for rel in FRAMEWORK + ["README.md"]:
            for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", read(rel)):
                if "://" in target:
                    continue
                self.assertTrue((REPO / rel).parent.joinpath(target).exists(), f"{rel} -> {target}")

    def test_conformance_table_matches_spec(self):
        spec = RULE.findall(read("spec/dryas-spec-v1.md"))
        self.assertEqual(len(spec), len(set(spec)), "duplicate rule id in spec")
        table = re.findall(r"^\| ((?:WF|MEM|GOV|EXE|ESC|REV)-\d+) \|", read("reference/README.md"), re.M)
        self.assertEqual(spec, table)

    def test_manifests_have_required_keys(self):
        for rel in MANIFESTS:
            top = set(re.findall(r"^([a-z_]+):", read(rel), re.M))
            for k in MANIFEST_KEYS:
                self.assertIn(k, top, f"{rel}: {k}")

    def test_readme_links_framework(self):
        t = read("README.md")
        for s in ("docs/operating-model.md", "docs/architecture.md", "spec/dryas-spec-v1.md", "reference/README.md", "docs/adoption-guide.md"):
            self.assertIn(s, t, s)

    def test_compound_gate_documented(self):
        self.assertIn("gate.compound", read("docs/governance.md"))
        self.assertIn("plain characters", read("docs/governance.md"))
        self.assertIn("compound true", read("docs/workflow.md"))
        self.assertIn("gate.compound", read("docs/metrics.md"))

    def test_gov_m1_is_judge_latency(self):
        self.assertIn("Judge latency", read("docs/metrics.md"))
        self.assertIn("GOV-M1 < 500 ms", read("docs/adoption-guide.md"))

    def test_metrics_status_matches_logging(self):
        t = read("docs/metrics.md")
        self.assertNotIn("| planned |", t)              # no KPI row left as planned
        self.assertIn("## Logging records", t)
        self.assertNotIn("by hand until", read("docs/adoption-guide.md"))

    def test_no_pinned_versions(self):
        for rel in ("docs/install.md", "docs/workflow.md", "reference/README.md", "reference/dryas.yaml"):
            t = read(rel)
            for bad in ("pinned 3.51.0", "pinned 6.4.1", "pinned 4.3.1", "ruflo@3.51.0"):
                self.assertNotIn(bad, t, f"{rel}: {bad}")


if __name__ == "__main__":
    unittest.main()
