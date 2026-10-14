# Rebuilding Ruflo tools

Date: 2026-10-14
Decision: Ruflo tools no rule or hook calls are not rebuilt.
Reason: nothing in the loop uses them, and they stay available with `--with-ruflo`.
