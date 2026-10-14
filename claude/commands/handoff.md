---
description: Score this session with Jev and save a handoff; then /clear starts fresh with only what matters
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/handoff.py" save:*)
disable-model-invocation: true
---

Run exactly this command with the Bash tool, then show its one-line output to the user:

```
"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/handoff.py" save --cwd "$PWD"
```

Then tell the user to type `/clear` (Claude cannot run `/clear` itself). Do nothing else.
