"""Judge providers (owned core, sub-project A).

`provider` decides: "jev" (the remote model through jev_client) or "local" (local_judge, no network).
`shadow` answers too; its answer is logged next to the decision and never acted on. "auto": jev decides
when a key is set or a judge function is injected (tests), else local; the shadow is local when jev
decides, else none. Settings: thresholds `judge.provider`, `judge.shadow` (change with /tune apply)."""
import os
import sys
from typing import Any, Callable, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _has_key() -> bool:
    from jev_client import api_key  # lazy: the ssl/http import is paid only when a judge is needed
    return bool(api_key())


def resolve(th: Dict[str, Any], injected: bool) -> Tuple[str, str]:
    cfg = th.get("judge") if isinstance(th.get("judge"), dict) else {}
    provider, shadow = cfg.get("provider", "auto"), cfg.get("shadow", "auto")
    if provider not in ("local", "jev"):
        provider = "jev" if injected or _has_key() else "local"
    if shadow not in ("local", "jev", "none"):
        shadow = "local" if provider == "jev" else "none"
    return provider, ("none" if shadow == provider else shadow)


def ask(state: Any, questions: Dict[str, Any], local: Dict[str, Any], th: Dict[str, Any],
        judge_fn: Optional[Callable[..., Dict[str, Any]]] = None) -> Dict[str, Any]:
    provider, shadow = resolve(th, judge_fn is not None)
    out: Dict[str, Any] = {"provider": provider, "shadow_provider": shadow}
    remote: Any = None
    if "jev" in (provider, shadow):
        from jev_client import judge
        try:  # any failure, including a malformed response, counts as a Jev failure
            remote = (judge_fn or judge)(state, questions)
            jev_answers = remote["answers"]
        except Exception as e:
            remote = e
    if provider == "jev" and not isinstance(remote, Exception):
        out.update(answers=jev_answers, latency_ms=remote.get("latency_ms"),
                   input_tokens=remote.get("input_tokens"), cost=remote.get("cost"))
        if shadow == "local":
            out.update(shadow_answers=local["answers"], shadow_reasons=local.get("reasons", []))
        return out
    out.update(answers=local["answers"], reasons=local.get("reasons", []))
    if provider == "jev":  # Jev failed: the local judge decides this call
        out.update(provider="local", fallback="local", error=type(remote).__name__, shadow_provider="none")
    elif shadow == "jev":
        if isinstance(remote, Exception):
            out["shadow_error"] = type(remote).__name__
        else:
            out.update(shadow_answers=jev_answers, shadow_cost=remote.get("cost"))
    return out
