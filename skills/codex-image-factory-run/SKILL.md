---
name: codex-image-factory-run
description: >
  Use when a batch plan exists and its images have not been produced yet, or when
  the user asks to generate the images in a plan. Validates the plan, quotes the
  batch, obtains approval, generates one image per item through Codex, and
  collects a hash-verified receipt for every artifact. Use when the user says
  "run this batch" or "generate these". For evaluating results that already
  exist use `codex-image-factory-judge`; for a run whose state is unclear use
  `codex-image-factory-recover`.
---

# Run an image batch

## When to use

Use this skill when the user has a batch plan and wants its images produced.
The plan is a JSON document conforming to `schemas/image_batch.schema.json`.

Do not use it to re-run items that already produced a receipt, and do not use it
to decide whether the results are good.

## Workflow

1. **Validate the plan before anything else.**

   ```bash
   bin/image-factory validate-plan plan.json --json
   ```

   A non-zero exit means the plan is rejected and nothing will be spent. Fix the
   reported errors and validate again. A plan that asks for a size, a quality
   tier, or a model is rejected on purpose: the built-in image tool accepts only a
   prompt and reference images, so those fields cannot be honoured and are
   refused rather than ignored.

2. **Quote the batch and show the user the size.**

   ```bash
   bin/image-factory quote plan.json --json
   ```

   Report the image count and make clear that each item costs one generation call
   against the Codex account's image allowance. Quoting itself spends nothing.

3. **Obtain approval.** Run the batch only when the user has agreed to generate
   these images. If the plan sets `require_approval_before_run`, the command
   refuses to start without `--approve`.

4. **Run it.**

   ```bash
   bin/image-factory run --plan plan.json --job job.json --destination out/ --approve --json
   ```

   Items already carrying a receipt are skipped, so a resumed run does not
   regenerate finished work.

5. **Report what happened from the output, not from expectation.** The command
   prints the receipts it collected and the final ledger state. An item is
   `Generated` only when a new image file was found and verified on disk; an exit
   code of zero from Codex without a file is recorded as a failure.

## Inputs

- A batch plan validated against `schemas/image_batch.schema.json`.
- Reference images named by the plan, each no larger than the platform's limit of
  five per item.

## Outputs

- One published image per successful item under `--destination`.
- One receipt per image, conforming to `schemas/artifact_receipt.schema.json`.
- A job ledger conforming to `schemas/factory_job.schema.json`, ending in
  `Completed`, `Partial`, `Failed`, or `Unknown`.

## Platform boundaries

State these to the user rather than working around them:

- Size, quality, background, and image count are fixed by the built-in tool.
  Batch items differ only by prompt and reference images.
- One tool call produces one image, so a fifty-item batch is fifty calls.
- Each call consumes the account's image allowance. A run that hits the limit
  stops there and records the reset time.

## Errors

- `approval_required` — the plan asks for approval and `--approve` was not given.
- `capability_unavailable` — the environment cannot generate; show the probe's
  guidance instead of retrying.
- `quota_exceeded` — the account's image allowance is exhausted. Report the reset
  time and stop.
- `artifact_missing`, `timeout`, `generation_failed` — recorded per item. The
  batch continues with the remaining items.

## Never do

- Never pass `--approve` without the user's agreement.
- Never bypass approvals or the sandbox. The plugin never passes
  `--dangerously-bypass-approvals-and-sandbox`, and neither should you.
- Never run the batch again to "fix" a failed item. The command never retries a
  failed item, and a silent second attempt is how one bad prompt becomes a large
  bill. Report the failure and let the user decide.
- Never claim a batch succeeded because the command exited zero: read the
  `state` and the receipts.
- Never accept a result the plan did not ask for: if an item produced no new
  file, say so.
