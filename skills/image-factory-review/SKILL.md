---
name: image-factory-review
description: Use when a governed Factory round needs an independent dimensioned critique of its generated images, when convergence across rounds must be shown with named-dimension evidence, or when a single opaque advisory score cannot direct the next rewrite. Writes the machine-readable advisory document that `evaluate` and `optimize` consume; the user-facing verdict stays with `image-factory-judge`.
---

# Independent dimensioned review

## When to use

Use this skill inside a governed Factory batch, after a round has artifacts and
before the next round is planned. It produces one thing: a dimensioned advisory
document for the round's `evaluate` step. It never generates images, never
spends the allowance, and never delivers a verdict to the user.

Do not use it for direct (Baoyu) generation, for approvals or receipts, or as a
second opinion on a batch that already has the user's decision. For presenting
results and capturing the user's decision, hand off to the
**`image-factory-judge`** skill and its conversation contract.

## Workflow

1. **Review in a separate context.** Take only three inputs: the round's
   artifacts, the requirements the plan declared for each item, and the previous
   round's critique when one exists. Do not read the conversation that produced
   the images, and do not score artifacts you generated yourself in this
   session. The review is only as independent as its inputs.

2. **Score named dimensions, not a mood.** For each item, record bounded
   per-dimension scores, each with a short gap statement that names observable
   evidence ("the mark reads amber, not the declared deep emerald"), together
   with the total score between 0 and 1. Write the advisory file in the object
   form the evaluator accepts:

   ```json
   {
     "item-01": {
       "score": 0.72,
       "reason": "close to the declared layout",
       "dimensions": [
         {"name": "character_identity", "score": 0.9, "evidence": "the left eyebrow scar and round glasses match the identity anchor"},
         {"name": "wardrobe", "score": 0.5, "evidence": "the coat is amber rather than the declared deep emerald"}
       ]
     }
   }
   ```

   A dimension whose statement names no observable evidence is left without
   evidence; the evaluator records it as incomplete, so it is reported but
   never counted as a gap. A missing dimension is honest; an invented one is
   not.

   For a series item, names are closed to `character_identity`, `wardrobe`,
   `prop_continuity`, `style`, `scene_state`, `text_absence`, and
   `aspect_ratio`. OCR, anatomy, identity similarity, and semantic continuity
   remain advisory observations; do not rewrite them as deterministic failures.

3. **Let the score fall.** Compare against the previous critique for
   consistency, but do not match or raise the previous total to appear
   consistent. When this round is worse, record the lower total; the drop is
   kept and reported as a regression. Do not settle for a flattering number.

4. **Stay inside the platform.** Every gap you record must be addressable by a
   different prompt or different reference images. Never record a gap whose fix
   requires a size, quality, background, image count, or model change, and
   never describe a further attempt that would start without an explicit
   instruction for that item.

5. **Stop at the document.** Hand the advisory file to the `evaluate` step of
   **`image-factory-judge`**. The deterministic gates, the human labels, and
   the user conversation stay there. This skill is part of the evidence chain,
   not of the conversation.

## Never do

- Never score artifacts you generated yourself, and never read the generation
  conversation as review input.
- Never present the critique, to the user or in the record, as a verdict. It is
  advisory: it cannot fail a batch and cannot outrank a human rejection.
- Never raise a total to keep continuity with a previous round when the images
  got worse.
- Never record a gap that requires a generation parameter this plugin does not
  control, and never describe an attempt that would occur without an explicit
  per-item instruction.
- Never copy the body of another skill; hand off by name.
- Never promise a visual match beyond what the recorded evidence shows.
