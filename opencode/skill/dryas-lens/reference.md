# Lens reference

## Lenses

Our own interpretation of each person's known principles, not quotes.

| Lens | Panel | Question |
| --- | --- | --- |
| Focus (Jobs) | product | What is the one thing this must do or say? Cut whatever does not change what the user does next. Judge the whole experience end to end. |
| Craft (Ive) | both | Reduction and care. Remove until only the essential remains; calm by default, emphasis only for attention; precise type, spacing and motion. |
| Data (Ng) | product | Data first and actionable. What will we measure, does every metric point to a next action, and does any AI part have an eval and a way to find its errors? |
| `impeccable` | design | Its critique pass: hierarchy, cognitive load, accessibility, states, anti-patterns. |
| `ui-ux-pro-max` | design | Style, palette, font pairing, UX guidelines and stack patterns, checked against its data. |

## Page

In this order:

1. Title (the design topic) and the overall verdict (`pass` when every lens passed, else `change`).
2. The design or mockup itself, when there is one: screenshot, comp or embedded markup.
3. One table per lens that ran: `Finding | Change made | Lens`. A skipped lens shows one row: `skipped (not available)`.
4. "Not done yet": suggestions not applied, each with the lens that made it.

Self-contained HTML that reads well at phone width and in dark mode.

## Lens block

The block goes into the in-chat design or the spec, verbatim in this shape:

```
## Lens
- Panel: design+product
- Focus (Jobs): The board must say which session needs you; everything else is secondary.
  - Drop the per-agent token column from the first screen; it never changes what you do next.
  - Merge the two status chips into one.
- Data (Ng): Every number on the card points to an action.
  - Show escalation rate per stage, with the worst stage first.
- Craft (Ive): Calm by default; only the waiting card glows.
- Verdict: change — artifact: https://claude.ai/artifact/EXAMPLE
```

- `Panel:` is `design`, `product` or `design+product`.
- Each lens line has a one-sentence headline, then any number of insights: no limit on count or length. A lens with nothing more stays one line.
- A design-only run writes `- Focus (Jobs): n/a` and `- Data (Ng): n/a` with no insights; the `impeccable` and `ui-ux-pro-max` findings stay on the page, not in the block.
- A product or design+product run fills all three lenses.
- No line quotes a real person.

Parsing rules (FlowObserve's Canopy relies on these): the block starts at the `## Lens` heading and ends at the next heading or end of file; its top-level lines start with exactly `- Panel: `, `- Focus (Jobs): `, `- Data (Ng): `, `- Craft (Ive): `, `- Verdict: `, in that order; insights are lines starting with two spaces and `- ` under a lens line. Anything else in the block is ignored.
