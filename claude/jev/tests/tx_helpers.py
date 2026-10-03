"""Shared transcript builders for handoff tests."""
import json


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def user_blocks(*texts):
    return {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": t} for t in texts]}}


def assistant(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def tool_use(tid, name, **inp):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def tool_result(tid, content, is_error=False):
    b = {"type": "tool_result", "tool_use_id": tid, "content": content}
    if is_error:
        b["is_error"] = True
    return {"type": "user", "message": {"role": "user", "content": [b]}}


def write_jsonl(path, records, extra_lines=()):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
        for line in extra_lines:
            f.write(line + "\n")
