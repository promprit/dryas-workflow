#!/usr/bin/env python3
"""Minimal stdio MCP server 'jev': jev_judge, log_escalation, log_override. Newline-delimited JSON-RPC."""
import json
import math
import os
import sys
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jev_client
import jevlog
import thresholds

PROTOCOL = "2025-06-18"
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")

TOOLS = [
    {
        "name": "jev_judge",
        "description": ("Ask Jev (TypeSafe System One) narrow typed questions about a named JSON state. "
                        "questions: map name -> {type: noul|choice|score, instructions, criteria}. Choice criteria must "
                        "include a none_of_these option. Batch independent questions in one call. Answers below the "
                        "confidence threshold are listed in 'escalate': Opus decides those."),
        "inputSchema": {"type": "object", "properties": {"state": {}, "questions": {"type": "object"}},
                        "required": ["state", "questions"]},
    },
    {
        "name": "log_escalation",
        "description": ("Record one escalation step with its reason. Ladder: sonnet -> opus -> fable; fable only after an "
                        "Opus executor failed the same task. Required for every step."),
        "inputSchema": {"type": "object", "properties": {k: {"type": "string"} for k in ("task", "reason", "decided_by", "from_model", "to_model")},
                        "required": ["task", "reason", "decided_by", "from_model", "to_model"]},
    },
    {
        "name": "log_override",
        "description": "Record that Opus acted against a Jev answer. Feeds /tune calibration.",
        "inputSchema": {"type": "object", "properties": {"question": {"type": "string"}, "jev_answer": {}, "jev_confidence": {"type": "number"},
                                                         "opus_decision": {}, "reason": {"type": "string"}},
                        "required": ["question", "jev_answer", "opus_decision", "reason"]},
    },
    {
        "name": "log_dispatch",
        "description": "Record one executor dispatch (first or re-dispatch). Feeds /tune: tasks dispatched, GOV-M4, ESC-M1.",
        "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}, "tier": {"type": "string"},
                                                         "role": {"type": "string"}, "attempt": {"type": "integer", "minimum": 1}},
                        "required": ["task", "tier", "role", "attempt"]},
    },
    {
        "name": "log_review",
        "description": "Record one review round of a branch with its finding counts. Feeds /tune: REV-M1, merges without review.",
        "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}, "round": {"type": "integer", "minimum": 1},
                                                         "critical": {"type": "integer", "minimum": 0},
                                                         "important": {"type": "integer", "minimum": 0},
                                                         "minor": {"type": "integer", "minimum": 0}},
                        "required": ["task", "round", "critical", "important", "minor"]},
    },
    {
        "name": "log_merge",
        "description": "Record a local merge of a worktree branch. cost_usd is optional (from /cost). Feeds /tune: EXE-M3.",
        "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}, "branch": {"type": "string"},
                                                         "tasks_merged": {"type": "integer", "minimum": 0},
                                                         "cost_usd": {"type": "number", "minimum": 0}},
                        "required": ["task", "branch", "tasks_merged"]},
    },
]


def _error(mid: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _ok(mid: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _text(mid: Any, obj: Any, is_error: bool = False) -> Dict[str, Any]:
    text = obj if isinstance(obj, str) else json.dumps(obj)
    return _ok(mid, {"content": [{"type": "text", "text": text}], "isError": is_error})


def _coerce_to_str(obj: Any) -> str:
    """Coerce object to string, truncated to 500 chars."""
    if obj is None:
        return "null"
    s = str(obj) if not isinstance(obj, str) else obj
    if len(s) > 500:
        s = s[:500]
    return s


def _coerce_confidence(obj: Any) -> Optional[float]:
    """Coerce to finite float or null."""
    if obj is None:
        return None
    try:
        f = float(obj)
        if math.isfinite(f):
            return f
        return None
    except (TypeError, ValueError):
        return None


def _sanitize_log_escalation(args: Dict[str, Any]) -> Dict[str, Any]:
    """Whitelist and sanitize log_escalation arguments."""
    return {
        "task": _coerce_to_str(args.get("task")),
        "reason": _coerce_to_str(args.get("reason")),
        "decided_by": _coerce_to_str(args.get("decided_by")),
        "from_model": _coerce_to_str(args.get("from_model")),
        "to_model": _coerce_to_str(args.get("to_model")),
    }


def _sanitize_log_override(args: Dict[str, Any]) -> Dict[str, Any]:
    """Whitelist and sanitize log_override arguments."""
    return {
        "question": _coerce_to_str(args.get("question")),
        "jev_answer": _coerce_to_str(args.get("jev_answer")),
        "jev_confidence": _coerce_confidence(args.get("jev_confidence")),
        "opus_decision": _coerce_to_str(args.get("opus_decision")),
        "reason": _coerce_to_str(args.get("reason")),
    }


def _as_int(v: Any) -> Optional[int]:
    """Strict int: real ints or digit strings; never bools or floats."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v.strip())
    return None


# tool name -> (log file, required string fields, required int fields with minimum)
LOG_TOOLS = {
    "log_dispatch": ("dispatch", ("task", "tier", "role"), {"attempt": 1}),
    "log_review": ("review", ("task",), {"round": 1, "critical": 0, "important": 0, "minor": 0}),
    "log_merge": ("merge", ("task", "branch"), {"tasks_merged": 0}),
}


def _validate_log(args: Dict[str, Any], strs: Any, ints: Dict[str, int]) -> Any:
    """Return (record, bad_fields). A record is written only when bad_fields is empty."""
    rec: Dict[str, Any] = {}
    bad = []
    for k in strs:
        v = args.get(k)
        if v is None or not str(v).strip():
            bad.append(k)
        else:
            rec[k] = _coerce_to_str(v)
    for k, lo in ints.items():
        n = _as_int(args.get(k))
        if n is None or n < lo:
            bad.append(k)
        else:
            rec[k] = n
    return rec, bad


def _normalize_questions(questions: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize question shapes before sending to Jev."""
    normalized = {}
    for name, q in questions.items():
        q_copy = dict(q)
        q_type = q_copy.get("type")
        criteria = q_copy.get("criteria")

        # Normalize criteria based on type
        if q_type == "choice" and isinstance(criteria, list):
            # Convert list of strings to {s: s for s in list}
            q_copy["criteria"] = {s: s for s in criteria}
        elif q_type == "score" and isinstance(criteria, dict):
            # Convert dict to list of values in order
            q_copy["criteria"] = list(criteria.values())
        elif q_type == "noul" and isinstance(criteria, list) and len(criteria) == 2:
            # Convert 2-element list to {"true": list[0], "false": list[1]}
            q_copy["criteria"] = {"true": criteria[0], "false": criteria[1]}

        normalized[name] = q_copy
    return normalized


def _validate_questions(questions: Dict[str, Any]) -> Optional[str]:
    """Validate question shapes. Return error message if invalid, None if valid."""
    for name, q in questions.items():
        q_type = q.get("type")
        instructions = q.get("instructions")
        criteria = q.get("criteria")

        # Validate type
        if q_type not in ("noul", "choice", "score"):
            return f'question "{name}": type must be "noul", "choice", or "score"'

        # Validate instructions
        if not isinstance(instructions, str) or not instructions:
            return f'question "{name}": instructions must be a non-empty string'

        # Type-specific validation
        if q_type == "choice":
            if not isinstance(criteria, dict) or not criteria or len(criteria) > 255:
                return f'question "{name}": choice criteria must be a map {{"option": "description"}} with 1–255 options'
        elif q_type == "score":
            if not isinstance(criteria, list) or len(criteria) < 2 or len(criteria) > 10:
                return f'question "{name}": score criteria must be a list of 2–10 strings'
            if not all(isinstance(c, str) for c in criteria):
                return f'question "{name}": score criteria must be a list of strings'
        elif q_type == "noul":
            if criteria is not None:
                if not isinstance(criteria, dict) or set(criteria.keys()) != {"true", "false"}:
                    return f'question "{name}": noul criteria must be absent or a map {{"true": "...", "false": "..."}}'

    return None


def _judge(mid: Any, args: Dict[str, Any], judge_fn) -> Dict[str, Any]:
    if "state" not in args or not isinstance(args.get("questions"), dict) or not args["questions"]:
        return _text(mid, "jev_judge needs 'state' and a non-empty 'questions' map", True)

    # Normalize questions first
    normalized_questions = _normalize_questions(args["questions"])

    # Validate normalized questions
    validation_error = _validate_questions(normalized_questions)
    if validation_error:
        jevlog.append("mcp", {"tool": "jev_judge", "error": "invalid_question"})
        return _text(mid, validation_error, True)

    try:
        res = judge_fn(args["state"], normalized_questions)
    except jev_client.JevUnavailable as e:
        # Extract safe cause message from exception
        cause = str(e) if str(e) else type(e).__name__
        jevlog.append("mcp", {"tool": "jev_judge", "error": cause})
        return _text(mid, "Jev unavailable (%s). Opus decides." % cause, True)

    # Log successfully, but catch and log any post-judge errors
    try:
        th = thresholds.load()["dispatch"]["min_confidence"]
        escalate = sorted(q for q, a in res["answers"].items() if a["confidence"] < th)

        # Cap question names at 64 chars and choice values at 64 chars
        capped_answers = {}
        for q, a in res["answers"].items():
            q_capped = q[:64] if len(q) > 64 else q
            val = a["value"]
            if isinstance(val, str) and len(val) > 64:
                val = val[:64]
            capped_answers[q_capped] = {"value": val, "confidence": round(a["confidence"], 3)}

        jevlog.append("mcp", {"tool": "jev_judge",
                              "answers": capped_answers,
                              "escalate": escalate[:64] if len(escalate) > 64 else escalate,
                              "latency_ms": res["latency_ms"],
                              "input_tokens": res["input_tokens"],
                              "cost": res["cost"]})
    except Exception as e:
        # Log error but still include known cost/tokens
        record = {"tool": "jev_judge", "error": type(e).__name__}
        if res.get("input_tokens"):
            record["input_tokens"] = res["input_tokens"]
        if res.get("cost"):
            record["cost"] = res["cost"]
        jevlog.append("mcp", record)
        return _text(mid, "internal error: %s" % type(e).__name__, True)

    return _text(mid, {"answers": res["answers"], "escalate": escalate, "input_tokens": res["input_tokens"], "cost": res["cost"]})


def handle(msg: Dict[str, Any], judge_fn=None) -> Optional[Dict[str, Any]]:
    # Validate message is a dict
    if not isinstance(msg, dict):
        return _error(None, -32600, "invalid request")

    mid = msg.get("id")
    method = msg.get("method")

    # Notifications (no id) get no reply
    if mid is None:
        return None

    # Validate params is dict if id is present
    params = msg.get("params")
    if params is not None and not isinstance(params, dict):
        return _error(mid, -32602, "invalid params")
    params = params or {}

    if method == "initialize":
        proto = params.get("protocolVersion", PROTOCOL)
        if proto not in SUPPORTED_PROTOCOLS:
            proto = PROTOCOL
        return _ok(mid, {"protocolVersion": proto, "capabilities": {"tools": {}},
                         "serverInfo": {"name": "jev", "version": "1.0.0"}})
    if method == "ping":
        return _ok(mid, {})
    if method == "tools/list":
        return _ok(mid, {"tools": TOOLS})
    if method == "tools/call":
        try:
            name, args = params.get("name"), params.get("arguments") or {}
            if name == "jev_judge":
                return _judge(mid, args, judge_fn or jev_client.judge)
            if name == "log_escalation":
                jevlog.append("escalations", _sanitize_log_escalation(args))
                return _text(mid, "logged")
            if name == "log_override":
                jevlog.append("overrides", _sanitize_log_override(args))
                return _text(mid, "logged")
            if name in LOG_TOOLS:
                file, strs, ints = LOG_TOOLS[name]
                rec, bad = _validate_log(args, strs, ints)
                if bad:
                    return _text(mid, "invalid or missing: %s" % ", ".join(bad), True)
                if name == "log_merge":
                    cost = _coerce_confidence(args.get("cost_usd"))
                    if cost is not None and cost >= 0:
                        rec["cost_usd"] = cost
                jevlog.append(file, rec)
                return _text(mid, "logged")
            name_str =str(name)[:64] if name else "unknown"
            return _text(mid, "unknown tool %r" % name_str, True)
        except Exception as e:
            return _text(mid, "internal error: %s" % type(e).__name__, True)
    return _error(mid, -32601, "method not found")


def main() -> None:
    for line_bytes in sys.stdin.buffer:
        try:
            line = line_bytes.decode("utf-8", "replace").strip()
        except Exception:
            continue
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            sys.stdout.write(json.dumps(_error(None, -32700, "parse error")) + "\n")
            sys.stdout.flush()
            continue
        try:
            resp = handle(msg)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except Exception:
            continue


if __name__ == "__main__":
    main()
