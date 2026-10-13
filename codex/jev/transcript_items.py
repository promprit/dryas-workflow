#!/usr/bin/env python3
"""Shared extractor: Claude Code JSONL transcript -> ordered session items (user, assistant, tool).

Used by handoff.py (scored /handoff) and compact_keep.py (PreCompact). Never raises on bad input.
A tool item joins one tool_use block with its tool_result (tool_use.id == tool_result.tool_use_id).
"""
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

MAX_LINE = 1000000
MAX_TEXT = 1000
RESULT_HEAD = 300
MAX_FILES = 40
LAST_USER = 10
USER_KEEP_CHARS = 500

# User text that Claude Code or hooks injected (not typed by the user). Prefix match after
# lstrip; deliberately conservative so real prompts that merely mention these are kept.
INJECTED_PREFIXES = ("<system-reminder>", "<command-", "<local-command", "Caveat:", "<task-notification>", "[SYSTEM NOTIFICATION",
                     "[Request interrupted by user", "<bash-input>", "<bash-stdout>", "<bash-stderr>")

EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
PATH_TOOLS = EDIT_TOOLS + ("Read",)
PATTERN_TOOLS = ("Grep", "Glob")
DESC_TOOLS = ("Agent", "Task")
# A test run is a command (start of the line or after && ; | ), not a mere mention in a message or argument.
_RUN = (r"(?:\S*/)?(?:python3?\s+-m\s+)?(?:pytest|vitest|jest)\b|(?:npx|pnpm exec|pnpm dlx|yarn)\s+(?:vitest|jest)\b"
        r"|(?:npm|pnpm|yarn)\s+(?:run\s+)?test\b|go test\b|cargo test\b|swift test\b|xcodebuild\b[^;&|]*\btest\b")
TEST_RE = re.compile(r"(?:^|&&|;|\|\|?)\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*(?:%s)" % _RUN)
COMMIT_RE = re.compile(r"\[[^\]]*\b[0-9a-f]{7,40}\]")
SHORT_ARG = 200


def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _blocks_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))
    return ""


# Hand-backs from other sessions/subagents: kept as kind "agent", never counted as user.
AGENT_PREFIXES = ("Another Claude session sent a message", "<agent-message")
# Skill loads (also isMeta in real transcripts).
SKILL_RE = re.compile(r"^\s*(Base directory for this skill:|Skill /[^\n]*was loaded)")
# Leading IDE/browser context blocks: stripped, real text after them is kept.
TAG_BLOCK_RE = re.compile(r"^\s*<(ide_selection|ide_opened_file|browser_instruction)>.*?</\1>", re.S)
TAG_OPEN_RE = re.compile(r"^\s*<(?:ide_selection|ide_opened_file|browser_instruction)>")


def _injected(text: str) -> bool:
    return text.lstrip().startswith(INJECTED_PREFIXES) or bool(SKILL_RE.match(text))


def _strip_tags(text: str) -> str:
    while True:
        new = TAG_BLOCK_RE.sub("", text, count=1)
        if new == text:
            break
        text = new
    return "" if TAG_OPEN_RE.match(text) else text.strip()


def _key_arg(name: str, inp: Any) -> Tuple[str, Optional[str]]:
    """(key arg text, path or None)."""
    if not isinstance(inp, dict):
        return "", None
    if name == "Bash" and isinstance(inp.get("command"), str):
        return _collapse(inp["command"]), None
    if name in PATH_TOOLS and isinstance(inp.get("file_path"), str):
        return inp["file_path"], inp["file_path"]
    if name == "NotebookEdit" and isinstance(inp.get("notebook_path"), str):
        return inp["notebook_path"], inp["notebook_path"]
    if name in PATTERN_TOOLS and isinstance(inp.get("pattern"), str):
        return _collapse(inp["pattern"]), None
    if name in DESC_TOOLS and isinstance(inp.get("description"), str):
        return _collapse(inp["description"]), None
    for v in inp.values():
        if isinstance(v, str) and 0 < len(v) <= SHORT_ARG:
            return _collapse(v), None
    return "", None


def _set_text(item: Dict[str, Any]) -> None:
    item["text"] = ("%s %s: %s" % (item["tool"], item.get("_arg", ""), item.get("_head") or ("(no result)" if item.get("_pending") else ""))).replace("  ", " ")[:MAX_TEXT].rstrip()


def extract_items(path: str, max_items: Optional[int] = None) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    by_id: Dict[str, Dict[str, Any]] = {}
    seen: Set[str] = set()  # record uuids: transcripts replay history after compaction/resume
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if len(line) > MAX_LINE:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict) or rec.get("type") not in ("user", "assistant"):
                    continue
                uid = rec.get("uuid")
                if isinstance(uid, str) and uid:
                    if uid in seen:
                        continue
                    seen.add(uid)
                msg = rec.get("message")
                content = msg.get("content") if isinstance(msg, dict) else None
                if rec["type"] == "user":
                    if isinstance(content, list):
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "tool_result":
                                it = by_id.get(str(b.get("tool_use_id")))
                                if it is not None:
                                    it["_head"] = _collapse(_blocks_text(b.get("content")))[:RESULT_HEAD]
                                    it.pop("_pending", None)
                                    if b.get("is_error"):
                                        it["is_error"] = True
                                    _set_text(it)
                    text = _blocks_text(content).strip()
                    if text.startswith(AGENT_PREFIXES):
                        items.append({"kind": "agent", "text": text[:MAX_TEXT]})
                    elif text and not rec.get("isMeta") and not rec.get("isCompactSummary"):
                        text = _strip_tags(text)
                        if text and not _injected(text):
                            items.append({"kind": "user", "text": text[:MAX_TEXT]})
                else:
                    if isinstance(content, str):
                        content = [{"type": "text", "text": content}]
                    for b in content if isinstance(content, list) else []:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "text" and isinstance(b.get("text"), str) and b["text"].strip():
                            items.append({"kind": "assistant", "text": b["text"].strip()[:MAX_TEXT]})
                        elif b.get("type") == "tool_use" and isinstance(b.get("name"), str):
                            arg, p = _key_arg(b["name"], b.get("input"))
                            it: Dict[str, Any] = {"kind": "tool", "tool": b["name"], "_arg": arg, "_head": "", "_pending": True}
                            if p:
                                it["path"] = p
                            _set_text(it)
                            items.append(it)
                            if isinstance(b.get("id"), str):
                                by_id[b["id"]] = it
    except OSError:
        pass
    out = items if max_items is None else (items[-max_items:] if max_items > 0 else [])
    for it in out:
        it.pop("_head", None)
    return out


def _is_test(it: Dict[str, Any]) -> bool:
    return it.get("tool") == "Bash" and not it.get("_pending") and bool(TEST_RE.search(_command(it)))


def _command(it: Dict[str, Any]) -> str:
    return it.get("_arg", "") if it.get("tool") == "Bash" else ""


def _line(it: Dict[str, Any]) -> str:
    t = it["text"].replace("\n", " ")
    if it["kind"] == "tool":
        return t + (" [error]" if it.get("is_error") else "")
    return "%s: %s" % (it["kind"], t)


def always_keep_split(items: List[Dict[str, Any]]) -> Tuple[List[str], Set[int]]:
    """Deterministic keep set (no Jev). Returns (lines, indexes of items those lines represent)."""
    idx: Set[int] = set()
    lines: List[str] = []
    users = [i for i, it in enumerate(items) if it["kind"] == "user"][-LAST_USER:]
    for i in users:
        idx.add(i)
        lines.append(_line(items[i])[:USER_KEEP_CHARS + len("user: ")])
    touched: Dict[str, int] = {}
    for i, it in enumerate(items):
        if it["kind"] == "tool" and it.get("tool") in EDIT_TOOLS and it.get("path"):
            touched.pop(it["path"], None)
            touched[it["path"]] = i
            idx.add(i)
    if touched:
        lines.append("Files touched: " + ", ".join(list(touched)[-MAX_FILES:]))
    latest: Dict[str, int] = {}
    for i, it in enumerate(items):
        if _is_test(it):
            latest[_command(it)] = i
    for i in sorted(latest.values()):
        idx.add(i)
        lines.append(_line(items[i]))
    for i, it in enumerate(items):
        if it.get("tool") == "Bash" and not it.get("_pending") and "git commit" in _command(it) and not it.get("is_error") and COMMIT_RE.search(it["text"]):
            idx.add(i)
            lines.append(_line(it))
    return lines, idx


def always_keep(items: List[Dict[str, Any]]) -> List[str]:
    return always_keep_split(items)[0]
