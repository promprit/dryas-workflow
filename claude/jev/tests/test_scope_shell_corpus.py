import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scope_lock

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN = "## Task 1: corpus\nGoal: g\nScope:\n- src/**\n- tests/**\nDone:\n- d\n"


class CorpusTest(unittest.TestCase):
    def test_corpus(self):
        wt = os.path.realpath(tempfile.mkdtemp())
        os.makedirs(os.path.join(wt, ".orchestrate"))
        with open(os.path.join(wt, ".orchestrate", "PLAN.md"), "w") as f:
            f.write(PLAN)
        with open(os.path.join(wt, ".orchestrate", "active.json"), "w") as f:
            json.dump({"active": ["1"]}, f)
        os.environ["JEV_LOG_DIR"] = tempfile.mkdtemp()
        with open(os.path.join(HERE, "fixtures", "scope_shell_corpus.jsonl"), encoding="utf-8") as f:
            cases = [json.loads(l) for l in f if l.strip()]
        self.assertGreaterEqual(sum(c["expect"] == "allow" for c in cases), 150)
        self.assertGreaterEqual(sum(c["expect"] == "deny" for c in cases), 20)
        wrong = []
        for c in cases:
            out = scope_lock.run({"tool_name": "Bash", "tool_input": {"command": c["cmd"]}, "agent_id": "a1",
                                  "cwd": os.path.join(wt, c["cwd"])})
            got = out["hookSpecificOutput"]["permissionDecision"] if out else "allow"
            if got != c["expect"]:
                wrong.append((c["why"], c["expect"], got, c["cmd"][:120]))
        self.assertEqual(wrong, [])


if __name__ == "__main__":
    unittest.main()
