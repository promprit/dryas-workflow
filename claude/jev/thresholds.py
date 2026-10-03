"""All tunable Jev thresholds. Defaults here; overrides in thresholds.json (written by /tune after approval)."""
import copy
import json
import math
import os
import re
import tempfile
from typing import Any, Dict, Optional

DEFAULTS: Dict[str, Dict[str, Any]] = {
    "gate": {
        "deny_safe_below": 0.2,
        "min_confidence": 0.7,
        "ask_risk": "destructive",
        "allowlist": [
            "ls", "cat", "head", "tail", "wc", "pwd",
            "git status", "git diff", "git log", "git show",
            "pnpm test", "npm test", "pnpm lint", "pnpm typecheck",
            "pytest", "python3 -m pytest", "swift test",
        ],
    },
    "route": {"min_confidence": 0.7, "swarm_min": 0.7},
    "dispatch": {"min_confidence": 0.7},
    # Ladder: sonnet -> opus -> fable. Fable only after the Opus executor also failed.
    "escalation": {"executor_confidence_below": 0.5, "sonnet_failures_before_opus": 2, "opus_failures_before_fable": 1},
    "commit": {"min_confidence": 0.7},
    "compact": {"keep_above": 0.5},
    "handoff": {"keep_min": 0.5},
    "context": {"warn_pct": 0.65},
}


def path() -> str:
    return os.environ.get("JEV_THRESHOLDS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "thresholds.json"))


def _read_file() -> Dict[str, Any]:
    try:
        with open(path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _type_check(value: Any, default_value: Any) -> bool:
    """Check if value matches the type of the default. Returns True if valid."""
    if isinstance(default_value, bool):
        return isinstance(value, bool)
    if isinstance(default_value, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(default_value, int):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(default_value, list):
        return isinstance(value, list)
    if isinstance(default_value, dict):
        return isinstance(value, dict)
    return type(value) == type(default_value)


def validate(dotted: str, value: Any) -> Optional[str]:
    """Validate a threshold value against DEFAULTS. Returns error message if invalid, None if valid."""
    keys = dotted.split(".")
    if len(keys) != 2:
        return f"Key must be section.key (got {dotted})"
    section, key = keys
    if section not in DEFAULTS:
        return f"Unknown section: {section}"
    if key not in DEFAULTS[section]:
        return f"Unknown key: {section}.{key}"
    default_val = DEFAULTS[section][key]

    # Type check
    if not _type_check(value, default_val):
        expected_type = type(default_val).__name__
        actual_type = type(value).__name__
        return f"Type mismatch for {dotted}: expected {expected_type}, got {actual_type}"

    if isinstance(value, float) and not math.isfinite(value):
        return f"{dotted} must be a finite number"

    # Semantic validation
    if key.endswith("_confidence") or key.endswith("_below") or key.endswith("keep_above") or key.endswith("_safe_below") or key == "swarm_min":
        if not isinstance(value, (int, float)) or value < 0.0 or value > 1.0:
            return f"{dotted} must be a float in [0.0, 1.0]"

    if key == "keep_min" and (value < 0.0 or value > 1.0):
        return f"{dotted} must be a float in [0.0, 1.0]"

    if key == "warn_pct" and (value < 0.1 or value > 0.95):
        return f"{dotted} must be a float in [0.1, 0.95]"

    if key.endswith("_failures_before_") or key.endswith("_failures_before_opus") or key.endswith("_failures_before_fable"):
        if not isinstance(value, int) or value < 1 or value > 5:
            return f"{dotted} must be an int in [1, 5]"

    if key == "allowlist":
        if not isinstance(value, list):
            return f"{dotted} must be a list"
        # Dangerous heads set (import from tune module would be circular, so define here)
        DANGEROUS_HEADS = {
            "sh", "bash", "zsh", "fish", "dash",
            "python", "python3", "node", "npx", "npm", "pnpm", "yarn", "bun", "deno",
            "ruby", "perl", "php",
            "env", "sudo", "su", "rm", "mv", "cp", "dd", "chmod", "chown", "ln",
            "git", "curl", "wget", "ssh", "scp", "rsync", "find", "xargs", "make",
            "docker", "kubectl", "brew", "pip", "pip3", "uv", "open", "osascript",
            "eval", "exec", "source", "kill", "pkill", "launchctl", "defaults", "tee",
            "awk", "sed",
        }
        # Existing default entries are always allowed; only check new entries
        default_allowlist = set(DEFAULTS["gate"]["allowlist"])
        for item in value:
            if not isinstance(item, str) or not item:
                return f"{dotted} entries must be non-empty strings"
            if not item.split():
                return f"{dotted} entry '{item}' must contain at least one word"
            # Check if first word is dangerous, but only for entries NOT in DEFAULTS
            if item not in default_allowlist:
                first_word = item.split()[0]
                if first_word in DANGEROUS_HEADS:
                    return f"{dotted} entry '{item}' starts with dangerous head '{first_word}'"

    if key == "ask_risk":
        # Must match gate.QUESTIONS["risk"]["criteria"] keys except "none_of_these"
        # From gate.py: {"routine", "worth_a_look", "destructive", "none_of_these"}
        valid_risks = {"routine", "worth_a_look", "destructive"}
        if value not in valid_risks:
            return f"{dotted} must be one of {valid_risks}, got {value}"

    return None


def load() -> Dict[str, Dict[str, Any]]:
    out = copy.deepcopy(DEFAULTS)
    for section, values in _read_file().items():
        if section in out and isinstance(values, dict):
            for key, value in values.items():
                if key in out[section]:
                    # Use default if value fails type or range validation (NaN/inf, out of range)
                    if _type_check(value, out[section][key]) and validate("%s.%s" % (section, key), value) is None:
                        out[section][key] = value
    return out


def set_value(dotted: str, value: Any) -> None:
    data = _read_file()
    keys = dotted.split(".")
    node = data
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value
    p = path()
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p) or ".", prefix=".thresholds-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, p)
