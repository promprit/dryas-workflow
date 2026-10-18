---
description: Score this session with Jev and save a handoff; then /clear starts fresh with only what matters (/handoff move: for a session on another account)
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/handoff.py" save:*)
disable-model-invocation: true
---

Run exactly one of these commands with the Bash tool, then show its one-line output to the user.
If the arguments are `move`, run:

```
"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/handoff.py" save --cwd "$PWD" --move
```

Otherwise run:

```
"${CLAUDE_PLUGIN_ROOT}/bin/dryas-py" "${CLAUDE_PLUGIN_ROOT}/jev/handoff.py" save --cwd "$PWD"
```

Arguments: $ARGUMENTS

After a plain save, tell the user to type `/clear` (Claude cannot run `/clear` itself). After a move, tell the user to type `/exit` and start the new session as the output says. Do nothing else.
