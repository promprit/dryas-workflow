# Local judge scorecard

The local judge decides gate questions with deterministic rules: no key, no network. These are the numbers a keyless install gets, measured on a public corpus and gated in CI: a change that makes them worse fails the build.

## How it is measured

The corpus lives in `reference/judge-corpus/` and is original to this repo. Each command has a class: dangerous (must not be allowed), safe (must be allowed without a question) and tricky (quoting, wrappers and heredocs that hide a dangerous command or only look like one; each row names the verdict it should get). `python3 tools/judge_score.py` scores the judge against it; `--write` regenerates `reference/judge-corpus/SCORECARD.md`, and CI checks this page against that file. Latency (p95) is measured but not gated, because it depends on the machine.

## Today's numbers

<!-- scorecard:start -->
| Measure | Value |
|---|---|
| Commands in corpus | 79 |
| Edits in corpus | 21 |
| Missed dangerous commands | 14 |
| Deny downgraded to ask | 4 |
| Needless asks on safe commands | 0 |
| Always-judged files not judged | 1 |
<!-- scorecard:end -->

## Known gaps

The scorecard counts what the rules miss, in the open. Missed dangerous commands are commands the corpus marks dangerous that the local judge allows; each is a candidate rule, and `/tune` proposes corpus additions from real disagreements. For the strongest judgement, set `OPENROUTER_API_KEY` and use the Jev judge (`--judge jev`); the local judge stays the keyless default.
