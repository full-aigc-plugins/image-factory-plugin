---
name: codex-image-factory-recover
description: >
  Use when an image batch was interrupted, when a ledger reports a state the
  user does not understand, or when the user asks what happened to a batch or
  whether it is safe to continue. Reads the job ledger, maps the current state to
  the single legal next step, and reports it without spending anything. Use when
  the state is `Running`, `Unknown`, or `Partial`, or when a previous attempt
  stopped unexpectedly. For a batch that has not been started use
  `codex-image-factory-run`.
---

# Recover an image batch

## When to use

Use this skill whenever a batch's condition is uncertain: a run that was
interrupted, a command that timed out, a state the user does not recognise, or a
question about what already exists.

Do not use it to generate anything, and do not use it to evaluate results.

## Workflow

1. **Read the ledger before doing anything else.**

   ```bash
   bin/image-factory status --job job.json --json
   ```

   The ledger is the record of what was actually attempted, so read it rather
   than inferring the situation from files on disk.

2. **Validate the plan that is still on disk**, so you know what the batch was
   supposed to do:

   ```bash
   bin/image-factory validate-plan plan.json --json
   ```

3. **Map the state to the single legal next step.** Do not improvise beyond it.

   | State | Meaning | Next step |
   | --- | --- | --- |
   | `Draft` | The job exists and nothing was validated | Validate the plan, then run |
   | `PlanValidated` | The plan passed validation and was not approved | Obtain approval, then run |
   | `Approved` | Approved and not yet started | Run |
   | `Running` | A run was in progress and did not finish | Read the item states, then resume with `run`; finished items are skipped |
   | `Evaluated` | A verdict was reached | Judge the outcome or optimize the failing items |
   | `Optimized` | A next round exists | Run the next round, then evaluate it |
   | `Completed` | Every item produced a verified artifact | Evaluate the batch |
   | `Partial` | The run finished with at least one failed item | Read the failure categories, then decide |
   | `Failed` | The job cannot proceed and is terminal | Report why, and start a new job if the user wants to try again |
   | `Unknown` | An interruption left the outcome unresolved | Query the state; do not re-run to find out |

4. **Report the failure categories and the usage limit if one is present.** A
   ledger carrying `quota_exceeded` holds the reset time for the image
   allowance. Report it and wait.

5. **Tell the user what continuing would cost** before resuming: how many items
   are still pending, and therefore how many generation calls the resume would
   make. Only the items with no recorded attempt are pending.

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

- A missing or unreadable ledger is reported as an error rather than treated as
  an empty job. A ledger that cannot be read is a fact to surface, not a blank
  slate to overwrite.
- A ledger holding anything resembling a credential is refused on read. Report
  that as a problem with the file rather than working around it.

## Never do

- Never re-run a batch to discover its state. Read the ledger first; a re-run is
  how an interrupted batch becomes a double charge.
- Never treat an unreadable ledger as an empty one, and never overwrite it to
  continue.
- Never resume past `Failed`: it is terminal on purpose, and continuing requires
  a new job.
- Never retry an item that has a recorded attempt. Only items with no attempt
  are pending.
- Never continue while a usage limit is in force; report the reset time instead.
