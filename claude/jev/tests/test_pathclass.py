import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import pathclass
import gate
import task_review


class PathClassModuleTest(unittest.TestCase):
    def test_is_a_leaf_module(self):
        # Defect: pathclass imports another jev module (an import cycle with gate/task_review returns).
        with open(os.path.join(HERE, "pathclass.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        local = {n[:-3] for n in os.listdir(HERE) if n.endswith(".py")}
        names = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                names |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                names.add((n.module or "").split(".")[0])
        self.assertEqual(names & local, set())

    def test_gate_and_task_review_share_it(self):
        # Defect: the two modules keep their own diverging copies of the path rules.
        for rel in ("a/b.jks", "x/secrets.yaml", "Makefile", ".env", "src/app.py", "deploy.sh", "../x.py"):
            self.assertEqual(task_review.always_judged(rel), pathclass.always_judged(rel), rel)
        with open(os.path.join(HERE, "task_review.py"), encoding="utf-8") as f:
            self.assertNotIn("import gate", f.read())

    def test_always_judged_covers_keys_secrets_ci_and_sensitive(self):
        for rel in ("keys/app.jks", "a.keystore", "vault.kdbx", "server.pem", "cfg/secrets.yaml", "aws_credentials",
                    "Jenkinsfile", "azure-pipelines.yml", ".gitlab-ci.yml", ".github/x.yml", "Makefile", "run.sh",
                    "../up.py", "/abs/path.py", ".", ""):
            self.assertTrue(pathclass.always_judged(rel), rel)

    def test_sensitive_keeps_gate_semantics(self):
        for rel in (".git/config", "package.json", "PACKAGE.JSON", "Dockerfile.dev", "requirements-dev.txt",
                    "scripts/deploy.ps1", "certs/server.key", ""):
            self.assertTrue(pathclass.sensitive(rel), rel)
        for rel in ("src/app.py", "docs/guide.md"):
            self.assertFalse(pathclass.sensitive(rel), rel)
            self.assertFalse(pathclass.always_judged(rel), rel)


if __name__ == "__main__":
    unittest.main()
