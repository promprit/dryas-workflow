"""Judge providers (owned core, sub-project A).

`provider` decides: "jev" (the remote model through jev_client) or "local" (local_judge, no network).
`shadow` answers too; its answer is logged next to the decision and never acted on. "auto": jev decides
when a key is set or a judge function is injected (tests), else local; the shadow is local when jev
decides, else none. Settings: thresholds `judge.provider`, `judge.shadow` (change with /tune apply).
In a claude.ai/code cloud session (CLAUDE_CODE_REMOTE=true) "auto" is local even with a key, unless the environment
opted into Jev with DRYAS_JUDGE=jev (owned core E)."""
import os
import sys
from typing import Any, Callable, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


KEY_VARS = ("OPENROUTER_API_KEY", "DRYAS_OPENROUTER_KEY", "CLAUDE_PLUGIN_OPTION_OPENROUTER_KEY")


def _cloud_without_jev() -> bool:
    """A cloud session that did not opt into Jev: no OpenRouter call, whatever key the environment holds."""
    remote = os.environ.get("CLAUDE_CODE_REMOTE", "").strip().lower() == "true"
    return remote and os.environ.get("DRYAS_JUDGE", "").strip().lower() != "jev"


def env_key() -> str:
    if _cloud_without_jev():
        return ""
    for name in KEY_VARS:
        v = os.environ.get(name, "").strip()
        if v and not v.startswith("${"):
            return v
    return ""


def _has_key() -> bool:
    return bool(env_key())


def resolve(th: Dict[str, Any], injected: bool) -> Tuple[str, str]:
    cfg = th.get("judge") if isinstance(th.get("judge"), dict) else {}
    provider, shadow = cfg.get("provider", "auto"), cfg.get("shadow", "auto")
    if provider not in ("local", "jev"):
        provider = "jev" if injected or (not _cloud_without_jev() and _has_key()) else "local"
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
