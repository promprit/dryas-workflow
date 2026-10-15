"""Plan 2: compaction keep and /handoff on a real opencode serve (no API key: Jev is unavailable, so the engines keep
the always-kept lines and the newest items, which include the user's prompt)."""
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from opencode_e2e import Server, opencode_ok

SKIP = opencode_ok()
HEADER = "Handoff from previous session"


@unittest.skipIf(SKIP, SKIP)
class CompactTest(unittest.TestCase):
    def test_compaction_context_reaches_model(self):
        with tempfile.TemporaryDirectory() as d:
            s = Server(Path(d))
            try:
                sid = s.prompt("WRITE_ALLOWED")
                s._http("POST", "/session/%s/summarize" % sid, {"providerID": "mock", "modelID": "m1"})
                hits = [r for r in s.requests() if HEADER in r.get("user", "")]
                self.assertTrue(hits, [r.get("user", "")[-300:] for r in s.requests()[-3:]])
                self.assertIn("WRITE_ALLOWED", hits[-1]["user"])
            finally:
                s.close()


@unittest.skipIf(SKIP, SKIP)
class HandoffTest(unittest.TestCase):
    def test_handoff_restores_into_next_session_only(self):
        with tempfile.TemporaryDirectory() as d:
            s = Server(Path(d))
            try:
                sid = s.prompt("WRITE_ALLOWED")
                s._http("POST", "/session/%s/command" % sid, {"command": "handoff", "arguments": ""})
                saved = [r for r in s.requests() if "Handoff saved:" in r.get("user", "")]
                self.assertTrue(saved, s.requests()[-1:])
                self.assertIn("/new", saved[-1]["user"])
                n = len(s.requests())
                s.prompt("hello")  # the next root session gets the handoff in its system prompt
                first = s.requests()[n:]
                main = [r for r in first if r.get("tools")]  # title requests carry no tools
                self.assertTrue(any(HEADER in str(x) and "WRITE_ALLOWED" in str(x) for r in main for x in r["system"]), first)
                n = len(s.requests())
                s._http("POST", "/session/%s/message" % sid, {"parts": [{"type": "text", "text": "more"}]})
                self.assertFalse(any(HEADER in str(x) for r in s.requests()[n:] for x in r["system"]))  # an already started session never takes it
                n = len(s.requests())
                s.prompt("hello again")  # the file was used once: a later session starts clean
                self.assertFalse(any(HEADER in str(x) for r in s.requests()[n:] for x in r["system"]))
            finally:
                s.close()

    def test_handoff_without_python_says_nothing_saved(self):
        with tempfile.TemporaryDirectory() as d:
            s = Server(Path(d), env_extra={"DRYAS_PY": str(Path(d) / "no-such-python")})
            try:
                sid = s.prompt("hello")
                s._http("POST", "/session/%s/command" % sid, {"command": "handoff", "arguments": ""})
                self.assertIn("nothing saved", s.requests()[-1].get("user", ""))
                s._http("POST", "/session/%s/summarize" % sid, {"providerID": "mock", "modelID": "m1"})  # still compacts
            finally:
                s.close()


if __name__ == "__main__":
    unittest.main()
