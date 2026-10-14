import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import thresholds
import tune_judge

G = lambda **k: dict({"tool": "Bash", "provider": "jev", "decision": "none"}, **k)


class DisagreementTest(unittest.TestCase):
    def test_counts_only_real_disagreements(self):
        rows = [G(head="make deploy", decision="ask", shadow_provider="local", shadow_decision="none"),
                G(head="make deploy", decision="ask", shadow_provider="local", shadow_decision="none"),
                G(head="ls", decision="none", shadow_provider="local", shadow_decision="none"),
                G(head="ls", decision="skipped"),
                G(head="git push", decision="deny", shadow_provider="local", shadow_decision="ask")]
        d = tune_judge.disagreements(rows)
        self.assertEqual([(x["pattern"], x["count"]) for x in d], [("make deploy", 2), ("git push", 1)])

    def test_disagreement_patterns_are_redacted(self):
        rows = [G(head="mysql -pS3cretPassw0rd", decision="deny", shadow_provider="local", shadow_decision="none")]
        self.assertNotIn("S3cretPassw0rd", repr(tune_judge.disagreements(rows)))

    def test_file_pattern_is_tool_and_suffix_only(self):
        rows = [G(tool="Edit", rel="src/secret_plans/app.py", decision="ask", shadow_provider="local",
                  shadow_decision="none"),
                G(tool="Write", rel=["a/b.env", "c.txt"], decision="none", shadow_provider="jev",
                  shadow_decision="deny"),
                G(tool="Edit", rel="<outside>", decision="ask", shadow_provider="local", shadow_decision="none")]
        pats = sorted(x["pattern"] for x in tune_judge.disagreements(rows))
        self.assertEqual(pats, ["Edit:.py", "Edit:<outside>", "Write:.env"])

    def test_lines_have_stable_labels_and_corpus_json(self):
        g = [G(head="make deploy", decision="ask", shadow_provider="local", shadow_decision="none")]
        text = "\n".join(tune_judge.lines({"disagreements": tune_judge.disagreements(g), "approved": {"rg": 4, "jq": 3}}))
        self.assertIn("- Judge disagreements (deciding vs shadow): 1 patterns", text)
        self.assertIn("- Approved local asks: 7 (2 patterns)", text)
        self.assertIn('CORPUS_CANDIDATES_JSON: [{"pattern": "make deploy"', text)


class ProposalTest(unittest.TestCase):
    def rows(self, head, n, ids_ran=True):
        g = [G(head=head, provider="local", decision="ask", tool_use_id="%s-%d" % (head, i)) for i in range(n)]
        o = [{"tool_use_id": r["tool_use_id"], "tool": "Bash"} for r in g] if ids_ran else []
        return g, o

    def test_repeated_approvals_become_a_proposal(self):
        g, o = self.rows("jq", 3)
        p = tune_judge.allowlist_proposal(tune_judge.approved_asks(g, o), ["ls"], 3)
        self.assertEqual(p["new"], ["ls", "jq"])

    def test_below_min_or_already_covered_is_not_proposed(self):
        g, o = self.rows("rg", 2)
        self.assertIsNone(tune_judge.allowlist_proposal(tune_judge.approved_asks(g, o), [], 3))
        g, o = self.rows("ls", 5)
        self.assertIsNone(tune_judge.allowlist_proposal(tune_judge.approved_asks(g, o), ["ls"], 3))

    def test_unapproved_asks_do_not_count(self):
        g, o = self.rows("rg", 5, ids_ran=False)
        self.assertIsNone(tune_judge.allowlist_proposal(tune_judge.approved_asks(g, o), [], 3))

    def test_jev_asks_and_denies_are_not_approvals(self):
        g, o = self.rows("rg", 5)
        g = [dict(r, provider="jev") for r in g[:3]] + [dict(r, decision="deny") for r in g[3:]]
        self.assertEqual(tune_judge.approved_asks(g, o), {})

    def test_dangerous_prefix_never_proposed(self):
        g1, o1 = self.rows("rm -rf", 9)
        g2, o2 = self.rows("git push --force", 9)
        g3, o3 = self.rows("mkfs.ext4 x", 9)
        g4, o4 = self.rows("psql -c 'drop table x'", 9)
        g5, o5 = self.rows("rm", 9)
        g6, o6 = self.rows("pwsh -ec abc", 9)
        g7, o7 = self.rows("psql", 9)
        approved = tune_judge.approved_asks(g1 + g2 + g3 + g4 + g5 + g6 + g7, o1 + o2 + o3 + o4 + o5 + o6 + o7)
        self.assertEqual(len(approved), 7)
        self.assertIsNone(tune_judge.allowlist_proposal(approved, [], 3))

    def test_apply_refuses_dangerous_allowlist_entry(self):
        self.assertIsNotNone(thresholds.validate("gate.allowlist", ["ls", "rm -rf"]))
        self.assertIsNotNone(thresholds.validate("gate.allowlist", ["ls", "mkfs.ext4 x"]))
        self.assertIsNotNone(thresholds.validate("gate.allowlist", ["ls", "psql -c 'drop table x'"]))
        self.assertIsNone(thresholds.validate("gate.allowlist", ["ls", "rg"]))

    def test_min_approvals_default(self):
        self.assertEqual(thresholds.load()["gate"]["allowlist_min_approvals"], 3)



class LoadAllowlistTest(unittest.TestCase):
    def load_with(self, allowlist):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "thresholds.json")
        with open(path, "w") as f:
            json.dump({"gate": {"allowlist": allowlist}}, f)
        p = mock.patch.dict(os.environ, {"JEV_THRESHOLDS": path})
        p.start()
        self.addCleanup(p.stop)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            got = thresholds.load()["gate"]["allowlist"]
        self.assertEqual((out.getvalue(), err.getvalue()), ("", ""))
        return got

    def test_only_refused_entries_are_dropped(self):
        self.assertEqual(self.load_with(["ls", "rg", "rm -rf"]), ["ls", "rg"])
        self.assertEqual(self.load_with(["ls", "rg", "mkfs.ext4 x"]), ["ls", "rg"])

    def test_safe_custom_entries_load_unchanged(self):
        self.assertEqual(self.load_with(["ls", "rg", "jq", "git status"]), ["ls", "rg", "jq", "git status"])

    def test_validate_stays_strict(self):
        self.assertIsNotNone(thresholds.validate("gate.allowlist", ["ls", "rg", "rm -rf"]))


if __name__ == "__main__":
    unittest.main()
