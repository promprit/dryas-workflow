import tempfile
import unittest
from pathlib import Path

from opencode_e2e import Server, opencode_ok

SKIP = opencode_ok()


@unittest.skipIf(SKIP, SKIP)
class MockRoundTripTest(unittest.TestCase):
    def test_plain_prompt_round_trips(self):
        with tempfile.TemporaryDirectory() as d:
            s = Server(Path(d), edition=None)
            try:
                sid = s.prompt("ECHO")
                self.assertEqual([t[:2] for t in s.tools(sid)], [("bash", "completed")])
                self.assertIn("hi", s.tools(sid)[0][2])
                self.assertTrue(any(r["plan"][0] == "tool" for r in s.requests()))
            finally:
                s.close()


if __name__ == "__main__":
    unittest.main()
