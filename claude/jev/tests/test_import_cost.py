import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def loaded(stmt, module):
    code = "import sys; sys.path.insert(0, %r); %s; print(%r in sys.modules)" % (HERE, stmt, module)
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip() == "True"


class ImportCostTest(unittest.TestCase):
    def test_scope_lock_does_not_load_prescreen(self):
        self.assertFalse(loaded("import scope_lock, shellwrites", "prescreen"))

    def test_gate_does_not_load_runrules(self):
        self.assertFalse(loaded("import gate", "runrules"))

    def test_gate_does_not_load_tempfile(self):
        self.assertFalse(loaded("import gate", "tempfile"))

    def test_sed_patterns_do_not_drift(self):
        import prescreen
        import shellwrites
        self.assertEqual(prescreen._SED_CMD.pattern, shellwrites._SED_CMD.pattern)
        self.assertEqual(prescreen._SED_CMD.flags, shellwrites._SED_CMD.flags)


if __name__ == "__main__":
    unittest.main()
