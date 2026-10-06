"""The weekly latest-Ruflo compatibility workflow must exist and cover the key steps."""
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "latest-compat.yml"


def test_latest_compat_workflow():
    assert WORKFLOW.is_file()
    text = WORKFLOW.read_text(encoding="utf-8")
    for needle in ("schedule", "workflow_dispatch", "npm install -g ruflo", "patched_helpers", "test_ns.cjs"):
        assert needle in text, needle
    assert "ruflo@" not in text
