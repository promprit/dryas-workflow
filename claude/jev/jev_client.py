"""One call to Jev (typesafe/jev-1.13) through OpenRouter's System One endpoint.

The key comes from OPENROUTER_API_KEY, then the plugin option (DRYAS_OPENROUTER_KEY in the MCP server,
CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY in hooks) at call time and is never stored. State is redacted
before sending. Every failure raises JevUnavailable so callers can fail open.
Under a .dryas-judge marker (judge_policy.py) nothing is sent: JevUnavailable("project_local").
"""
import http.client
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Optional

import judge_policy
from redact import redact_obj

ENDPOINT = "https://openrouter.ai/api/v1/systemone"
MODEL = "typesafe/jev-1.13"
TIMEOUT_S = 3.0  # one deadline for the whole call (connect + request + response), not per socket op
_CHUNK = 64 * 1024


class JevUnavailable(Exception):
    pass


def _normalize(answers: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    try:
        for name, a in answers.items():
            t = a.get("type")
            if t == "noul":
                p = float(a["noul"])
                if not (-1 <= p <= 2):  # Catch inf, -inf, and out-of-range values
                    raise ValueError("noul probability out of range")
                out[name] = {"type": "noul", "value": p, "confidence": max(p, 1.0 - p)}
            elif t == "choice":
                out[name] = {"type": "choice", "value": str(a["choice"]), "confidence": float(a["confidence"]),
                             "probabilities": a.get("probabilities", {})}
            elif t == "score":
                s = float(a["score"])
                if not (-1 <= s <= 3):  # Catch inf and out-of-range values
                    raise ValueError("score out of range")
                out[name] = {"type": "score", "value": s, "confidence": float(a["confidence"]),
                             "legend": a.get("legend", {})}
            else:
                raise JevUnavailable("unknown answer type %r" % (t,))
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as e:
        raise JevUnavailable("malformed answer: %s" % type(e).__name__)
    return out


def api_key() -> str:
    """OPENROUTER_API_KEY (shell), then DRYAS_OPENROUTER_KEY (MCP env from the plugin option), then
    CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY (hook processes). Blank or unexpanded "${...}" values are unset. Never stored.
    A cloud session without DRYAS_JUDGE=jev gets no key, so callers outside providers (PreCompact, /handoff) stay local."""
    from providers import env_key  # lazy: providers imports this module lazily too
    return env_key()


def _read_by(resp: Any, deadline: float) -> bytes:
    """Read the body in chunks, each socket op limited to the time left; past the deadline -> JevUnavailable."""
    parts = []
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise JevUnavailable("deadline exceeded")
        try:
            resp.fp.raw._sock.settimeout(left)  # urllib exposes no per-call deadline; best effort, may not exist
        except Exception:
            pass
        chunk = resp.read(_CHUNK)
        if not chunk:
            return b"".join(parts)
        parts.append(chunk)


def judge(state: Any, questions: Dict[str, Any], timeout: float = TIMEOUT_S,
          opener: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
    cwd = state.get("cwd") if isinstance(state, dict) else None
    if judge_policy.project_local(cwd if isinstance(cwd, str) else None):
        raise JevUnavailable("project_local")
    key = api_key()
    if not key:
        raise JevUnavailable("OPENROUTER_API_KEY not set")

    t0 = time.monotonic()
    deadline = t0 + timeout
    try:
        body = json.dumps({"model": MODEL, "state": redact_obj(state), "questions": questions}).encode("utf-8")
        req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as resp:
            data = json.loads(_read_by(resp, deadline).decode("utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
            raise JevUnavailable("no answers in response")
        usage = data.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise JevUnavailable("invalid usage format")
        usage = usage or {}
        answers = _normalize(data["answers"])
        input_tokens = int(usage.get("input_tokens") or 0)
        cost = usage.get("cost")
        return {
            "answers": answers,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "input_tokens": input_tokens,
            "cost": cost,
        }
    except JevUnavailable:
        raise
    except urllib.error.HTTPError as e:
        raise JevUnavailable("HTTPError %d" % e.code) from None
    except Exception as e:
        raise JevUnavailable(type(e).__name__) from None
