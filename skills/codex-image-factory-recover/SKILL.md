---
name: codex-image-factory-recover
description: Use when an image batch was interrupted, when a ledger reports a state the user does not understand, or when the user asks what happened to a batch and whether it is safe to continue. Reads the job ledger, maps the current state to the single legal next step, and reports it without spending anything. Use when the state is `Running`, `Unknown`, or `Partial`, or when a previous attempt stopped unexpectedly. For a batch that has not been started use `codex-image-factory-run`.
---

# Recover an image batch

## When to use

Use this skill whenever a batch's condition is uncertain: a run that was
interrupted, a command that timed out, a state the user does not recognise, or a
question about what already exists.

Do not use it to generate anything, and do not use it to evaluate results.

## Workflow

For a goal expressed in conversation, read and follow
[the shared conversation workflow](../codex-image-factory-use/references/conversation-workflow.md).
Recovery is reported in plain language: what finished, what did not, and the one
next action, without JSON or command details unless the user asks for them.

Step 1. **Read the ledger before doing anything else.**

```bash
bin/image-factory status --job job.json --json
```

The ledger is the record of what was actually attempted, so read it rather than
inferring the situation from files on disk. The report gives the state, the
per-state item counts, the bound plan and approval, and any usage limit.

Step 2. **Validate the plan that is still on disk**, so you know what the batch
was supposed to do:

```bash
bin/image-factory validate-plan plan.json --json
```

Step 3. **Reconcile, which is how an interrupted job is settled.**

```bash
bin/image-factory recover --plan plan.json --job job.json --destination out/ --json
```

`recover` makes no generation calls at all. It reads the receipts that already
exist and decides what each interrupted item actually became: an item whose
artifact is on disk and still verifies becomes `Generated`, and an item with no
evidence becomes `Unknown`. It then rebuilds the manifest and settles the job to
`Completed`, `Partial`, or `Unknown`.

Step 4. **Report the counts and exactly one next action.** Say how many items
completed, failed, are pending, and remain unknown, then give the single legal
next step for the resulting state.

Step 5. **Stop when anything is unknown.** `recover` exits with the
recovery-required code and leaves those items `Unknown` on purpose. No automatic
retry can be offered, because the call may already have happened and only a
person can decide whether to accept the existing evidence or start a new job.

## State to next action

| State | Meaning | Next step |
| --- | --- | --- |
| `Draft` | The job exists and nothing was validated | Validate the plan, then run |
| `PlanValidated` | The plan passed validation and was not approved | Obtain approval, then run |
| `PendingApproval` | Waiting on an explicit decision | Decide, then run or optimize |
| `Approved` | Approved and not yet started | Run |
| `Running` | A run was in progress and did not finish | Run `recover`; it settles each interrupted item from evidence |
| `Evaluated` | A verdict was recorded | Optimize the failing items |
| `Optimized` | A next round exists | Run the next round, with a fresh approval |
| `Accepted` | The batch was accepted | Nothing further; start a new job for more work |
| `Completed` | Every item produced a verified artifact | Evaluate the batch |
| `Partial` | The run finished with at least one failed item | Evaluate, then optimize the failures |
| `Failed` | Terminal | Report why; continuing requires a new job |
| `Unknown` | An outcome is unresolved | Run `recover`; never re-run to find out |

## Platform boundaries

Recovery cannot change what a generation call produces. Size, quality,
background, and image count are fixed by the built-in tool, so resuming an item
reproduces the same kind of output as before. If the user wants a different
result, that is a new round with a rewritten prompt, not a recovery.

## Inputs

- A job ledger conforming to `schemas/factory_job.schema.json`.

## Outputs

- A report of the state, the per-item states and failure categories, any usage
  limit with its reset time, and the single legal next step.

## Errors

- `recovery_required` — an item outcome is unresolved. Report which items and
  refuse to offer any automatic repeat.
- A missing or unreadable ledger is reported as an error rather than treated as
  an empty job. A ledger that cannot be read is a fact to surface, not a blank
  slate to overwrite.
- A ledger holding anything resembling a credential is refused on read. Report
  that as a problem with the file rather than working around it.

## Never do

- Never re-run a batch to discover its state. Read the ledger first, then use
  `recover`; a re-run is how an interrupted batch becomes a double charge.
- Never treat an unreadable ledger as an empty one, and never overwrite it to
  continue.
- Never resume past `Failed`: it is terminal on purpose, and continuing requires
  a new job.
- Never retry an item that has a recorded attempt. Only items with no attempt
  are pending.
- Never continue while a usage limit is in force; report the reset time instead.
