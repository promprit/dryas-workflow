# Glossary

One word per meaning; skills, templates and docs point here instead of re-explaining.

## Terms

- **Jev**: the judge layer; answers narrow typed questions (gates, routing), never writes code or plans; provider local or the Jev model.
- **judge**: the function behind every Jev question, `judge(question, state)`.
- **provider**: who fills a slot (judge local|jev, memory dryas|ruflo|none, process dryas|superpowers).
- **shadow**: a second provider whose answer is logged next to the deciding one, never acted on.
- **fallback**: the local answer used when the Jev model is unavailable, recorded as such.
- **tier**: fast, standard, strong, frontier.
- **rung**: one step of the ladder.
- **ladder**: fast → standard → strong → frontier, climbed only on failure.
- **scope lock**: the hook that denies edits outside a task's Scope globs.
- **worktree loop**: one task, one worktree, one agent.
- **task id**: the id on every gate, dispatch, review and merge record.
- **baseline**: the window `/tune` compares a switch against.
- **inventory**: the 1.x no-loss snapshot checked by `tools/inventory.py`.
- **extra**: an optional third-party component (Ruflo, Superpowers, the design plugins).
- **local judge**: deterministic rules, no network.
- **Dryas memory**: the SQLite store at `~/.dryas/dryas.db`.
- **observe stage**: a hook stage whose output is ignored.
- **corpus**: the labelled judge cases in `reference/judge-corpus/`.
