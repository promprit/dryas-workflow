---
name: dryas-brainstorm
description: "Use before any creative or multi-step work (features, components, new behavior, changes to behavior). Establishes intent and gets the user's approval of a design on the right path (spike, bounded, architectural) before anything is built or dispatched. The Dryas \"brainstorm first, always\" gate."
---
<!-- dryas-managed -->

# Brainstorm

Turn ideas into fully formed designs and specs through natural, collaborative dialogue. Classify how much process the request needs first, then work through that path: understand the context, refine the idea, present a design, and get your human partner's approval.

## Shared understanding

The outcome is an understanding your partner can recognize and correct, grounded in what they want to accomplish.

1. **Discover intent.** From the request and the context, identify the intended outcome, who it is for and what success looks like. When that is missing, ask one focused question about purpose or intended use before proposing features or an approach. Knowing the app genre does not tell you why your partner wants it. Gathering missing requirements does not ask them to authorize the task again.
2. **Write back your understanding.** Summarize the intended outcome, relevant constraints and success criteria in a short note your partner can assess. Separate what they said from your assumptions. Invite correction and incorporate the answer before treating the note as the design brief.
3. **Carry intent into the design.** Keep the agreed understanding in the path's design artifact (the written spec for architectural work, the in-chat design or probe for bounded work and spikes). Check proposed features and technical choices against it.

When the request already supplies purpose and constraints, reflect that understanding instead of asking the same questions again. Keep the note concise; its accuracy and the chance to correct it are what matter.

## Hard gate

Before any implementation action (invoking an implementation skill, writing product code, scaffolding, installing product dependencies, creating an external project, dispatching an executor), complete the selected path's prerequisites:

- **Spike:** the partner approves the question and the probe.
- **Bounded:** the partner approves the short in-chat design.
- **Architectural:** the partner reviews and approves the written spec, then reviews the written implementation plan; the plan's execution method in Dryas is `/orchestrate`. Conversational design approval only permits writing the spec; written-spec approval only permits invoking the `dryas-plan` skill (`/wplan`).

A reply approves the stage actually presented. Approval of an idea or a feature scope does not approve artifacts that do not exist yet. Resume at the earliest incomplete stage; never turn one approval into permission to skip the rest of the path. Read-only project exploration is allowed while prerequisites are incomplete.

## Three paths

Before your first question, classify the request and say the classification out loud ("this looks bounded, so I'll present a short design here rather than write a spec") so your partner can override it.

- **Spike**: a feasibility question ("can we...", "is it possible...", "quick and dirty is fine") whose output is an answer, not code you keep. Present the question and what you will try in 2-3 sentences, get a nod, then find out as cheaply as correctness allows. No design doc, no spec file. Report findings as a recommendation; anything you built stays labeled throwaway.
- **Bounded**: a well-scoped change to code that already exists in this repo (a new flag, a small endpoint, a one-file fix). Understanding the kind of app is not enough: bounded means the flow you are changing is already here to read. No existing flow to change means not bounded. Ask the clarifying questions that matter, present a short design IN CHAT (a few sentences to a few short paragraphs), and STOP. Implementation starts only after your partner says yes to that design; a bounded approval is as hard a gate as an architectural one. No spec file, no plan document.
- **Architectural**: new projects, new subsystems, changes that restructure how components fit together or alter interfaces others depend on. Full process: questions, approaches, sectioned design, written spec, then the `dryas-plan` skill.

In doubt between two paths, take the heavier one. The ratchet is one-way: hidden complexity found mid-task upgrades the path (stop, say so, step up). Nothing downgrades mid-task. "Too simple to need approval" is an anti-pattern: scale the artifact to the path, never skip its approval (when tempted, read `<dryas-root>/../skill/dryas-brainstorm/reference.md` § Too simple to need approval).

## Question rounds

Ask in numbered rounds of at most five questions, one topic per question; a topic that needs more becomes several questions. Each question carries your recommended answer, phrased so that "yes" accepts it; offer choices where they help, open questions where they do not. When a question is a fact about the code, docs or history, look it up yourself and state what you found; bring only decisions to the user. A round ends when the user has answered it. The questioning ends when every open decision the selected path needs has an answer, listed before you present the design. The hard gate still applies.

## Red flags

| Thought | Reality |
|---|---|
| "This is too simple to need a design" | Follow the path: bounded gets a short chat design; architectural gets the written spec and planning hand-offs. |
| "I'll call it bounded and skip the spec" | Reaching for a label to skip work IS the doubt: take the heavier path. |
| "It's bounded and the design is obvious, I'll start while they read it" | The gate is the approval, not the design's length. Present, then stop until you hear yes. |
| "I understand this kind of app, so it's bounded" | Bounded measures the repo, not your familiarity. A new project has no existing flow: architectural. |
| "The spike works, so I'll keep the code" | A spike's output is an answer. Keeping the code is a new request: classify it. |
| "It grew, but I'm almost done, no need to re-classify" | Hidden complexity upgrades the path mid-task. Stop and say so. |
| "They approved the spike, so the follow-up change is approved too" | Each task gets its own classification and its own approval. |

## Checklist

Classify first, announce the path, then create a task for each item on your path and complete them in order. Each item ends where its bound says.

**Spike:**
1. Explore project context: until you can name what the probe touches.
2. Present question and probe plan: 2-3 sentences.
3. Get approval: a nod is enough.
4. Investigate: as cheaply as correctness allows, until the question has an answer.
5. Report findings: one recommendation; anything built is labeled throwaway.

**Bounded:**
1. Explore project context: files, docs, recent commits; until you can name the files the change touches.
2. Ask clarifying questions: question rounds, until every open decision has an answer.
3. Present a short design in chat: approach, files touched, testing.
4. Get approval: STOP and wait for an explicit yes; presenting the design and starting in the same breath is skipping the gate.
5. Implement: the normal development workflow (test first applies); no plan document.

**Architectural:**
1. Explore project context: files, docs, recent commits.
2. Ask clarifying questions: question rounds on purpose, constraints and success criteria, until every open decision has an answer.
3. Propose 2-3 approaches: trade-offs and your recommendation.
4. Present the design: in sections scaled to their complexity; get approval after each section.
5. Write the design doc: see "After the design"; it is committed.
6. Spec self-review: no placeholder, contradiction, ambiguity or scope problem left.
7. User reviews the written spec: an explicit approval.
8. Transition to implementation: invoke the `dryas-plan` skill to write the implementation plan.

## The process

From approaches on it is architectural depth; for bounded work, context plus a question round plus a short in-chat design is the whole process, and a spike stops at "present the probe, get a nod".

- When exploring the idea, proposing approaches or presenting the design, read `<dryas-root>/../skill/dryas-brainstorm/reference.md` § Understanding the idea, § Exploring approaches, § Presenting the design, § Design for isolation and clarity and § Working in existing codebases.
- When you want the whole flow as a graph, read `<dryas-root>/../skill/dryas-brainstorm/reference.md` § Process flow.

Design work (UI/UX, layout, visual style, components, on-screen copy) also uses the design skills the rules name, when installed.

**Terminal states are path-bound.** Architectural: the ONLY skill you invoke after brainstorming is the `dryas-plan` skill, never a frontend-design, mcp-builder or other implementation skill. Bounded: after approval, implementation goes straight through the normal development workflow; no plan document. Spike: the terminal state is a reported recommendation.

## After the design

Architectural path.

1. Save the spec as `docs/specs/YYYY-MM-DD-<topic>-design.md` (or under `docs/superpowers/specs/` if the project uses that), commit it, and review it with `<dryas-root>/../skill/dryas-brainstorm/spec-reviewer-prompt.md` before asking the user to read it. When choosing the location or the writing style, read `<dryas-root>/../skill/dryas-brainstorm/reference.md` § Spec documentation.
2. Right after writing it, run the self-review in `<dryas-root>/../skill/dryas-brainstorm/reference.md` § Spec self-review; fix inline.
3. **User review gate:** ask the user to review the written spec: "Spec written and committed to `<path>`. Please review it and let me know if you want any changes before we write the implementation plan." Wait for the response. If they ask for changes, make them and re-run the review. Proceed only once the user approves.
4. Invoke the `dryas-plan` skill (`/wplan`) to write the detailed implementation plan. Invoke no other skill: the plan skill is the next step.

## Contested

The written spec states `Contested: yes` or `Contested: no`: yes when it changes a numbered rule, an interface other modules depend on, or how components fit together. `/orchestrate` reads it to decide on `/interrogate`.
