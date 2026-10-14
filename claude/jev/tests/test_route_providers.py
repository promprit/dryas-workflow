import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import route

NOKEY = {"OPENROUTER_API_KEY": "", "DRYAS_OPENROUTER_KEY": "", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY": ""}
RES = {"answers": {"route": {"type": "choice", "value": "swarm", "confidence": 0.9, "probabilities": {}},
                   "opus": {"type": "noul", "value": 0.2, "confidence": 0.8}},
       "latency_ms": 3, "input_tokens": 9, "cost": 0.000001}


class RouteProvidersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, dict(NOKEY, JEV_LOG_DIR=self.tmp, JEV_THRESHOLDS=os.path.join(self.tmp, "t.json")))
        p.start()
        self.addCleanup(p.stop)

    def last(self):
        with open(os.path.join(self.tmp, "route.jsonl")) as f:
            return [json.loads(l) for l in f][-1]

    def test_local_provider_injects_nothing_and_logs_it(self):
        self.assertIsNone(route.run({"prompt": "build x"}))
        rec = self.last()
        self.assertEqual((rec["provider"], rec["injected"]), ("local", False))

    def test_explicit_local_wins_over_injected_judge(self):
        with open(os.environ["JEV_THRESHOLDS"], "w") as f:
            json.dump({"judge": {"provider": "local"}}, f)
        calls = []
        self.assertIsNone(route.run({"prompt": "build x"}, lambda s, q: calls.append(1) or RES))
        self.assertEqual(calls, [])

    def test_jev_route_record_names_provider(self):
        self.assertTrue(route.run({"prompt": "build x"}, lambda s, q: RES).startswith("Jev route: swarm"))
        self.assertEqual(self.last()["provider"], "jev")
