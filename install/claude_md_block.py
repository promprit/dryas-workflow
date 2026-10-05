"""Insert / remove one marker-delimited block in a text file, recording exactly what was added.
Used for ~/.claude/CLAUDE.md, ~/.codex/AGENTS.md and the Codex config.toml fallback."""
import re
from pathlib import Path

START, END = "<!-- dryas:start -->", "<!-- dryas:end -->"


def _pattern(start: str, end: str) -> str:
    return re.escape(start) + r".*?" + re.escape(end) + r"\n?"


def insert_block(p: Path, body: str, rec: dict, key: str, start: str = START, end: str = END) -> None:
    block = start + "\n" + body.strip() + "\n" + end + "\n"
    if not p.exists():
        rec[key + "_created"] = True
        text = ""
    else:
        rec.setdefault(key + "_created", False)
        with open(p, encoding="utf-8", newline="") as fh:
            text = fh.read()
    if start in text and end in text:
        new = re.sub(_pattern(start, end), lambda m: block, text, count=1, flags=re.S)
    else:
        sep = ""
        if text and not text.endswith("\n\n"):
            sep = "\n" if text.endswith("\n") else "\n\n"
        rec[key + "_sep"] = sep
        new = text + sep + block
    if new != text:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(new)
    rec[key] = True


def remove_block(p: Path, rec: dict, key: str, start: str = START, end: str = END) -> None:
    if not rec.get(key) or not p.exists():
        return
    with open(p, encoding="utf-8", newline="") as fh:
        text = fh.read()
    body = _pattern(start, end)
    sep = rec.get(key + "_sep", "")
    new, n = re.subn(re.escape(sep) + body, "", text, count=1, flags=re.S) if sep else (text, 0)
    if not n:
        new = re.sub(body, "", text, count=1, flags=re.S)
    if rec.get(key + "_created") and not new.strip():
        p.unlink()
    elif new != text:
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(new)


def claude_md(cd: Path, template_text: str, rec: dict) -> None:
    insert_block(cd / "CLAUDE.md", template_text, rec, "claude_md")


def remove_claude_md(cd: Path, rec: dict) -> None:
    remove_block(cd / "CLAUDE.md", rec, "claude_md")
