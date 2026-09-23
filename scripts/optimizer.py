#!/usr/bin/env python3
"""Turn one round's evaluation into the next round's plan.

Optimization here is a decision about *what* to redo, not a text generator. The
plugin decides which items need another attempt and which are finished, and it
requires an explicit instruction for each item it is asked to redo. Rewritten
prompts come from Codex; this module validates and carries them.

That split is what keeps the loop honest. If this module also wrote the prompts,
then the same component would produce the work and judge it, and a loop that
grades its own homework converges on whatever the grader likes rather than on
what the operator asked for.

Three properties are structural rather than policy:

* A new round is a new document. The previous plan is never edited, so the round
  number alone links a result back to the instruction that produced it.
* An item that already passed is not regenerated. Re-running it would spend the
  account's allowance to reproduce a file that already exists.
* Reaching the round ceiling is reported as incomplete, never as success.

Convergence evidence follows the same discipline. Regression and two graded
stall states are detected from the ledger's durable numeric history and reported
as signals; a signal never opens a round by itself, and an established stall
stops the loop and hands the decision back to the operator. Rounds without
numbers are excluded, so a batch that never carries an advisory never sees a
stall it cannot have earned.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

import contract_migrations
import story_state as story_state_module

DEFAULT_MAX_ROUNDS = 20
DEFAULT_FULL_STEP = 0.1

NEEDS_WORK_WITHOUT_INSTRUCTION = "optimizer_missing_instruction"
AMBIGUOUS_INSTRUCTION = "optimizer_ambiguous_instruction"
EMPTY_REWRITE = "optimizer_empty_rewrite"
UNEXPECTED_INSTRUCTION = "optimizer_unexpected_instruction"
UNKNOWN_ITEM = "optimizer_unknown_item"
ROUND_CAP_REACHED = "optimizer_round_cap_reached"
STALL_REQUIRES_REWRITE = "optimizer_stall_requires_rewrite"
STALL_ESTABLISHED = "optimizer_stall_established"


@dataclass(frozen=True)
class OptimizeError:
    code: str
    message: str
    item_id: str | None = None


@dataclass(frozen=True)
class ConvergenceSignal:
    """One observed convergence fact, reported but never self-executing."""

    kind: str
    message: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class OptimizeResult:
    complete: bool
    next_plan: dict | None
    errors: tuple[OptimizeError, ...]
    carried_forward: tuple[str, ...] = ()
    rework: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()
    signals: tuple[ConvergenceSignal, ...] = field(default=())


def _gates_by_item(evaluation: dict) -> dict[str, bool]:
    rows = evaluation.get("deterministic_gates", {}).get("per_item", [])
    return {row["item_id"]: bool(row["passed"]) for row in rows}


def _labels_by_item(evaluation: dict) -> dict[str, str]:
    return {row["item_id"]: row["label"] for row in evaluation.get("human_labels", [])}


def _advisory_by_item(evaluation: dict) -> dict[str, float]:
    return {row["item_id"]: row["score"] for row in evaluation.get("advisory", {}).get("items", [])}


def _dimension_gaps_by_item(evaluation: dict, threshold: float) -> dict[str, tuple[str, ...]]:
    """Name the complete dimensions scoring below the threshold, per item.

    A dimension recorded as incomplete (its statement named no observable
    evidence) is reported in the scores document but is never counted here: an
    unnamed impression must not drive a rework decision.
    """
    gaps: dict[str, tuple[str, ...]] = {}
    for row in evaluation.get("advisory", {}).get("items", []):
        named = tuple(
            str(dimension["name"])
            for dimension in (row.get("dimensions") or [])
            if dimension.get("complete", False) and float(dimension["score"]) < threshold
        )
        if named:
            gaps[row["item_id"]] = named
    return gaps


def _materialize_rework_story_transitions(
    current_plan: dict,
    rows: list[dict],
    rework_ids: set[str],
) -> dict[str, list[dict]]:
    """Keep inherited variable state when passed frames are omitted next round."""
    profile = current_plan.get("consistency_profile")
    model, model_errors = story_state_module.build_model(profile)
    if model is None or model_errors:
        return {}

    variable_paths = tuple(path for path, _initial in model.variables)
    current = model.initial_variables()
    snapshots: dict[str, dict[str, str]] = {}
    for row in rows:
        resolved, current, frame_errors = story_state_module.resolve_frame(model, row, current)
        if resolved is None or frame_errors:
            return {}
        bindings = dict(resolved.bindings)
        snapshots[row["id"]] = {path: bindings[path] for path in variable_paths}

    materialized: dict[str, list[dict]] = {}
    next_current = model.initial_variables()
    for row in rows:
        item_id = row["id"]
        if item_id not in rework_ids:
            continue
        desired = snapshots[item_id]
        materialized[item_id] = [
            {"path": path, "from": next_current[path], "to": desired[path]}
            for path in variable_paths
            if next_current[path] != desired[path]
        ]
        next_current = dict(desired)
    return materialized


def needs_rework(
    item_id: str,
    *,
    gates: dict,
    labels: dict,
    advisory: dict,
    policy: dict,
    dimension_gaps: dict | None = None,
) -> bool:
    if not gates.get(item_id, False):
        return True
    if labels.get(item_id) == "rejected":
        return True
    threshold = policy.get("pass_threshold", 0.8)
    if policy.get("advisory_enabled", False):
        score = advisory.get(item_id)
        if score is not None and score < threshold:
            return True
        if dimension_gaps and dimension_gaps.get(item_id):
            return True
    return False


def detect_convergence(
    numeric_history: list | None,
    *,
    full_step: float = DEFAULT_FULL_STEP,
) -> tuple[ConvergenceSignal, ...]:
    """Compare the ledger's per-round numbers; stay silent whenever they are missing.

    Two graded stall states, after the loop's own contract: approaching means the
    best score has not gained a full step in two rounds (or the same dimension was
    named twice in a row) and the next round must be a structural rework;
    established means that rework did not lift the score either, so the loop must
    stop and hand the decision to the operator. An established stall subsumes the
    approaching one. A regression is reported with both rounds' evidence and never
    counts as progress.
    """
    scored = [
        entry
        for entry in (numeric_history or [])
        if isinstance(entry, dict) and isinstance(entry.get("best_score"), (int, float))
    ]
    if len(scored) < 2:
        return ()
    rounds = [int(entry["round"]) for entry in scored]
    bests = [float(entry["best_score"]) for entry in scored]
    dimensions = [frozenset(entry.get("gap_dimensions") or ()) for entry in scored]

    def evidence_window(indices: range) -> tuple[str, ...]:
        return tuple(
            f"round {rounds[index]}: best {bests[index]:.2f}" for index in indices
        )

    signals: list[ConvergenceSignal] = []

    if bests[-1] < bests[-2]:
        signals.append(
            ConvergenceSignal(
                "regression",
                f"round {rounds[-1]} scored below round {rounds[-2]}; the drop is kept, not smoothed over",
                (
                    f"round {rounds[-2]}: best {bests[-2]:.2f}",
                    f"round {rounds[-1]}: best {bests[-1]:.2f}",
                ),
            )
        )

    approaching_reasons: list[str] = []
    approaching_evidence = list(evidence_window(range(len(scored))))
    if len(scored) >= 3:
        baseline = max(bests[:-2])
        if max(bests[-2:]) - baseline < full_step:
            approaching_reasons.append(
                "the best score has not improved by a full step in two rounds"
            )
    if len(dimensions) >= 2 and (dimensions[-1] & dimensions[-2]):
        shared = ", ".join(sorted(dimensions[-1] & dimensions[-2]))
        approaching_reasons.append(f"the same gap dimension was named twice in a row ({shared})")
    if approaching_reasons:
        signals.append(
            ConvergenceSignal(
                "stall_approaching",
                "; ".join(approaching_reasons)
                + "; the next round must be driven by a structural change, not a small tweak",
                tuple(approaching_evidence),
            )
        )

    established_reasons: list[str] = []
    if len(scored) >= 4:
        baseline = max(bests[:-3])
        if max(bests[-3:]) - baseline < full_step:
            established_reasons.append(
                "three rounds without a full step of improvement, including the round after the structural rework was required"
            )
    if len(dimensions) >= 3 and (dimensions[-1] & dimensions[-2] & dimensions[-3]):
        shared = ", ".join(sorted(dimensions[-1] & dimensions[-2] & dimensions[-3]))
        established_reasons.append(f"the same gap dimension persisted across three rounds ({shared})")
    if established_reasons:
        # An established stall subsumes the approaching one: the disposition is
        # no longer "rework differently" but "stop and ask the operator".
        signals = [signal for signal in signals if signal.kind == "regression"]
        signals.append(
            ConvergenceSignal(
                "stall_established",
                "; ".join(established_reasons)
                + "; stop and ask the user whether the current state is acceptable",
                tuple(evidence_window(range(len(scored)))),
            )
        )

    return tuple(signals)


def plan_next_round(
    *,
    current_plan: dict,
    evaluation: dict,
    rewrites: dict | None = None,
    retry_unchanged=(),
    numeric_history: list | None = None,
    full_step: float = DEFAULT_FULL_STEP,
) -> OptimizeResult:
    rewrites = dict(rewrites or {})
    retry_unchanged = set(retry_unchanged)

    rows = list(current_plan.get("items", []))
    identifiers = [row["id"] for row in rows]
    known = set(identifiers)

    instructed = set(rewrites) | retry_unchanged
    unknown = sorted(instructed - known)
    if unknown:
        return OptimizeResult(
            complete=False,
            next_plan=None,
            errors=(
                OptimizeError(
                    UNKNOWN_ITEM,
                    f"instructions were given for items that are not in this plan: {', '.join(unknown)}",
                ),
            ),
        )

    policy = current_plan.get("judge_policy") or {}
    gates = _gates_by_item(evaluation)
    labels = _labels_by_item(evaluation)
    advisory = _advisory_by_item(evaluation)
    dimension_gaps = _dimension_gaps_by_item(evaluation, policy.get("pass_threshold", 0.8))

    rework_ids = [
        item_id
        for item_id in identifiers
        if needs_rework(
            item_id,
            gates=gates,
            labels=labels,
            advisory=advisory,
            policy=policy,
            dimension_gaps=dimension_gaps,
        )
    ]
    carried = [item_id for item_id in identifiers if item_id not in set(rework_ids)]

    signals = detect_convergence(numeric_history, full_step=full_step)
    approaching = any(signal.kind == "stall_approaching" for signal in signals)
    established = any(signal.kind == "stall_established" for signal in signals)

    # An established stall stops the loop before any instruction is requested:
    # spending more rounds on another dramatic change is exactly what the state
    # forbids. The decision belongs to the operator now.
    if established:
        return OptimizeResult(
            complete=False,
            next_plan=None,
            errors=(
                OptimizeError(
                    STALL_ESTABLISHED,
                    "the loop has stalled; stop and ask the user whether the current "
                    "state is acceptable before any further round",
                ),
            ),
            carried_forward=tuple(carried),
            rework=tuple(rework_ids),
            blocked=tuple(rework_ids),
            signals=signals,
        )

    errors: list[OptimizeError] = []

    unexpected = sorted(instructed & (known - set(rework_ids)))
    if unexpected:
        errors.append(
            OptimizeError(
                UNEXPECTED_INSTRUCTION,
                f"instructions were given for items that already passed: {', '.join(unexpected)}",
            )
        )

    ambiguous = sorted(set(rewrites) & retry_unchanged)
    if ambiguous:
        errors.append(
            OptimizeError(
                AMBIGUOUS_INSTRUCTION,
                f"both a rewrite and a retry-unchanged were given for: {', '.join(ambiguous)}",
            )
        )

    blank = sorted(item_id for item_id, text in rewrites.items() if not str(text).strip())
    if blank:
        errors.append(
            OptimizeError(EMPTY_REWRITE, f"a rewrite was empty for: {', '.join(blank)}")
        )

    silent = [item_id for item_id in rework_ids if item_id not in instructed]
    if silent:
        errors.append(
            OptimizeError(
                NEEDS_WORK_WITHOUT_INSTRUCTION,
                "each item that needs rework must be given a rewrite or an explicit "
                f"retry-unchanged: {', '.join(silent)}",
            )
        )

    # While a stall is approaching, keeping the same prompt is the definition of
    # the small tweak the state forbids: a rework item must get an actual rewrite.
    stalling = sorted(set(retry_unchanged) & set(rework_ids)) if approaching else []
    if stalling:
        errors.append(
            OptimizeError(
                STALL_REQUIRES_REWRITE,
                "a stall is approaching, so each rework item needs a structural rewrite "
                f"rather than a retry-unchanged: {', '.join(stalling)}",
            )
        )

    if errors:
        return OptimizeResult(
            complete=False,
            next_plan=None,
            errors=tuple(errors),
            carried_forward=tuple(carried),
            rework=tuple(rework_ids),
            signals=signals,
        )

    limits = current_plan.get("limits") or {}
    max_rounds = limits.get("max_rounds", DEFAULT_MAX_ROUNDS)
    current_round = current_plan.get("round", 1)
    if current_round + 1 > max_rounds:
        return OptimizeResult(
            complete=False,
            next_plan=None,
            errors=(
                OptimizeError(
                    ROUND_CAP_REACHED,
                    f"round {current_round + 1} would exceed the cap of {max_rounds}; "
                    "the remaining items are left for a human decision",
                ),
            ),
            carried_forward=tuple(carried),
            rework=tuple(rework_ids),
            blocked=tuple(rework_ids),
            signals=signals,
        )

    if not rework_ids:
        return OptimizeResult(
            complete=True,
            next_plan=None,
            errors=(),
            carried_forward=tuple(carried),
            signals=signals,
        )

    rework_set = set(rework_ids)
    rework_story_transitions = _materialize_rework_story_transitions(
        current_plan,
        rows,
        rework_set,
    )
    items = []
    for row in rows:
        if row["id"] not in rework_set:
            continue
        replacement = copy.deepcopy(row)
        if row["id"] in rework_story_transitions:
            replacement["state_transitions"] = rework_story_transitions[row["id"]]
        if row["id"] in rewrites:
            replacement["prompt"] = str(rewrites[row["id"]]).strip()
        items.append(replacement)

    next_plan: dict = {
        "schema_version": current_plan.get("schema_version", "1.0.0"),
        "batch_id": current_plan["batch_id"],
        "round": current_round + 1,
        "items": items,
    }
    if "goal" in current_plan:
        next_plan["goal"] = current_plan["goal"]
    if "limits" in current_plan:
        next_plan["limits"] = copy.deepcopy(current_plan["limits"])
    if "judge_policy" in current_plan:
        next_plan["judge_policy"] = copy.deepcopy(current_plan["judge_policy"])
    if "consistency_profile" in current_plan:
        next_plan["consistency_profile"] = copy.deepcopy(current_plan["consistency_profile"])
    next_plan = contract_migrations.migrate_image_batch(next_plan).document

    return OptimizeResult(
        complete=False,
        next_plan=next_plan,
        errors=(),
        carried_forward=tuple(carried),
        rework=tuple(rework_ids),
        signals=signals,
    )
