---
description: Score this session with Jev and save a handoff; then /clear starts fresh with only what matters (/handoff move: for a session on another account)
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/handoff.py" save:*)
disable-model-invocation: true
---

Only if the arguments are empty or contain nothing but letters, digits, spaces and hyphens, run this command with the Bash tool exactly as written, then show its one-line output to the user. Otherwise run nothing and reply: "/handoff takes no argument, or move."

```
"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/handoff.py" save --cwd "$PWD" --mode '$ARGUMENTS'
```

If the output says the handoff was saved for another account, tell the user to type `/exit` and start the new session as the output says. If it says a handoff was saved, tell the user to type `/clear` (Claude cannot run `/clear` itself). Otherwise only show the output. Do nothing else.
