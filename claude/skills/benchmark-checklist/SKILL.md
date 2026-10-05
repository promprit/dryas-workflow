---
name: benchmark-checklist
description: Vet a performance number you measured (limiter, tuning, limits, errors, repeatability, relevance, whether the work ran) before you report or act on it. Runs from a PLAN.md Done line, the CLAUDE.md rule, or /benchmark-checklist.
disable-model-invocation: true
---

# Benchmark checklist

Read `{{CD}}/pstack/benchmark-checklist.md` in full. Answer each of its questions with evidence from a run, not a guess about the code. Report in its Report format: verdict first, then the number with unit, run count, range and limiter. Call the result inconclusive when its rules say so.
