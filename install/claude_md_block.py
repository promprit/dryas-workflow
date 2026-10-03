import re
from pathlib import Path

START, END = "<!-- dryas:start -->", "<!-- dryas:end -->"


def claude_md(cd: Path, template_text: str, rec: dict) -> None:
    p = cd / "CLAUDE.md"
    block = START + "\n" + template_text.strip() + "\n" + END + "\n"
    if not p.exists():
        rec["claude_md_created"] = True
        text = ""
    else:
        rec.setdefault("claude_md_created", False)
        text = p.read_text()
    if START in text and END in text:
        new = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", lambda m: block, text, count=1, flags=re.S)
    else:
        sep = ""
        if text and not text.endswith("\n\n"):
            sep = "\n" if text.endswith("\n") else "\n\n"
        rec["claude_md_sep"] = sep
        new = text + sep + block
    if new != text:
        p.write_text(new)
    rec["claude_md"] = True


def remove_claude_md(cd: Path, rec: dict) -> None:
    p = cd / "CLAUDE.md"
    if not rec.get("claude_md") or not p.exists():
        return
    text = p.read_text()
    body = re.escape(START) + r".*?" + re.escape(END) + r"\n?"
    sep = rec.get("claude_md_sep", "")
    new, n = re.subn(re.escape(sep) + body, "", text, count=1, flags=re.S) if sep else (text, 0)
    if not n:
        new = re.sub(body, "", text, count=1, flags=re.S)
    if rec.get("claude_md_created") and not new.strip():
        p.unlink()
    elif new != text:
        p.write_text(new)
