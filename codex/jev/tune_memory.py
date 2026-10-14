"""/tune lines for the memory store (owned core D): consolidation skipped inside hooks and background runs."""
from typing import Any, Dict, List


def summary(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    s = {"skipped_budget": 0, "skipped_deadline": 0, "background_runs": 0, "background_failed": 0}
    for r in rows:
        if r.get("error") == "ConsolidateSkipped":
            s["skipped_deadline" if r.get("detail") == "deadline" else "skipped_budget"] += 1
        elif r.get("stage") == "consolidate":
            s["background_runs" if r.get("ok") is True else "background_failed"] += 1
    return s


def lines(s: Dict[str, int]) -> List[str]:
    n = s["skipped_budget"] + s["skipped_deadline"]
    return ["- Memory consolidation skipped in hooks: %d (budget %d, deadline %d)" % (n, s["skipped_budget"],
                                                                                   s["skipped_deadline"]),
            "- Background consolidation runs: %d ok, %d failed" % (s["background_runs"], s["background_failed"])]
