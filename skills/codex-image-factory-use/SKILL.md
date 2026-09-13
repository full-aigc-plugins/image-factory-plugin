---
name: codex-image-factory-use
description: Use when the user wants to produce a batch of images, run an image production round, or continue an image batch that already exists. Routes to `codex-image-factory-run` for a batch that has not been generated yet, to `codex-image-factory-judge` for a batch with results to evaluate or a next round to plan, and to `codex-image-factory-recover` for a batch whose state is unclear or that was interrupted. This skill only picks the entry point and never performs the work itself. For a single ad-hoc image with no batch plan, no skill in this plugin applies — ask Codex for the image directly.
---

# Codex Image Factory

## When to use

Use this skill as the entry point when a request touches image production as a
batch rather than as one picture: the user has several prompts, a reference
style to reproduce across variants, or an existing job they want to continue.

Do not use it to generate one image on request, to design a UI, or to edit a
document.

## Workflow

Step 1. Establish whether a batch plan already exists. Look for a plan file the
user named, or for a job ledger left by an earlier round.

Step 2. Classify the request into exactly one of three situations:

- **Nothing has been generated yet, including requests needing prompt inspiration or a batch plan.** Delegate to `codex-image-factory-run`; its prompt preparation reference covers template search and series consistency.
- **Results exist and need a verdict, or need another round.**
  Delegate to `codex-image-factory-judge`.
- **The state is unclear, a run was interrupted, or the user is asking what
  happened.** Delegate to `codex-image-factory-recover`.

Step 3. State which situation you detected and why, then delegate and stop.

## Routing table

| Situation | Signal | Delegate |
| --- | --- | --- |
| New batch | A plan describing items, no ledger yet | `codex-image-factory-run` |
| Verdict or next round | A ledger in `Completed`, `Partial`, or `Evaluated` | `codex-image-factory-judge` |
| Unclear or interrupted | A ledger in `Running` or `Unknown`, or the user asks what happened | `codex-image-factory-recover` |

## Gotchas

- A ledger without a plan file is not a dead end: the ledger records what was attempted, so recover the state first and ask the user for the plan only if a resume is actually needed.
- A request for one image is not a batch. Routing it here adds a plan, a ledger, and a quote to what should be a single call.
- "Continue the batch" is ambiguous. Check whether it means generating the remaining items or evaluating the ones already produced.
- A completed ledger does not mean the images are good; it means every item produced a verified file. Evaluation is a separate step.
- The delegates are named in full on purpose. Referring to them loosely, as "the run skill", is how a router ends up doing the work itself.

## Never do

- Never perform the batch work in this skill. Route and stop.
- Never install, upgrade, or modify another plugin.
- Never approve a run on the user's behalf, and never run the CLI with
  `--approve` unless the user asked for this batch to be generated.
- Never continue past an ambiguous state: route to `codex-image-factory-recover`
  and read the ledger first.
