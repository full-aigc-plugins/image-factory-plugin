#!/usr/bin/env python3
"""Validate an image batch plan before anything is allowed to spend usage.

Validation is split in two stages on purpose. Structural validation runs first
against the published JSON Schema and returns immediately if it fails, so a plan
that asks for something the platform cannot do (a size, a quality tier, a model)
is rejected as a contract violation rather than quietly ignored. Only a
structurally valid plan reaches the semantic stage, which hashes reference
images, rejects duplicate work, and applies the spend caps.

Every batch item carries an idempotency key derived from its content, so a
resumed run can skip an item that has already been produced instead of paying
for it twice.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import contract_migrations
import declared_checks as declared_checks_module
import schema_lite

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "image_batch.schema.json"

# These mirror the published schema and are asserted against it in tests, so the
# document and the code cannot drift apart unnoticed.
DEFAULT_MAX_IMAGES = 200
DEFAULT_MAX_ROUNDS = 20
MAX_REFERENCE_IMAGES = 5

HASH_CHUNK = 64 * 1024


@dataclass(frozen=True)
class PlanError:
    code: str
    message: str
    item_id: str | None = None


@dataclass(frozen=True)
class ReferenceBinding:
    path: str
    role: str
    entity_id: str | None
    sha256: str


@dataclass(frozen=True)
class PlanItem:
    id: str
    prompt: str
    round: int
    reference_images: tuple[str, ...]
    reference_sha256: tuple[str, ...]
    idempotency_key: str
    # Declared evaluation criteria. Deliberately excluded from the idempotency
    # key: they judge the artifact, they are not a generation input.
    pixel_checks: tuple[dict, ...] = ()
    effective_prompt: str = ""
    effective_prompt_sha256: str = ""
    reference_bindings: tuple[ReferenceBinding, ...] = ()
    entity_ids: tuple[str, ...] = ()
    allowed_variations: tuple[str, ...] = ()
    aspect_ratio_range: tuple[float, float] | None = None
    series_mode: bool = False


@dataclass(frozen=True)
class PlanResult:
    ok: bool
    batch_id: str
    round: int
    errors: tuple[PlanError, ...]
    items: tuple[PlanItem, ...]
    require_approval_before_run: bool
    max_images: int
    max_rounds: int
    pass_threshold: float
    min_dimension: int
    reject_duplicates: bool
    advisory_enabled: bool
    plan_sha256: str
    require_human_labels: bool
    migration_notes: tuple[str, ...]
    consistency_profile_sha256: str | None = None
    near_duplicate_hamming_distance: int | None = None


def file_sha256(target: Path) -> str:
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        while True:
            block = handle.read(HASH_CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def compute_idempotency_key(
    *,
    batch_id: str,
    item_id: str,
    round_number: int,
    prompt: str,
    reference_sha256: tuple[str, ...],
    reference_bindings: tuple[ReferenceBinding, ...] = (),
) -> str:
    """Hash what would actually be sent, so identical work maps to one key.

    Reference order is preserved because an edit treats the first reference as the
    identity source; reordering them is a different request.
    """
    identity = {
        "batch_id": batch_id,
        "item_id": item_id,
        "round": round_number,
        "prompt": prompt,
        "reference_sha256": list(reference_sha256),
    }
    if reference_bindings:
        identity["reference_bindings"] = [
            {
                "role": binding.role,
                "entity_id": binding.entity_id,
                "sha256": binding.sha256,
            }
            for binding in reference_bindings
        ]
    payload = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _compile_effective_prompt(
    *,
    prompt: str,
    profile: dict | None,
    entities: tuple[dict, ...],
    allowed_variations: tuple[str, ...],
    bindings: tuple[ReferenceBinding, ...],
    structured_references: bool,
) -> str:
    if profile is None and not structured_references:
        return prompt

    lines = ["[SERIES CONSISTENCY CONTRACT]"]
    if profile is not None:
        lines.append(f"Style bible: {profile['style_bible'].strip()}")
        negative = tuple(str(value).strip() for value in profile.get("negative_constraints", ()))
        if negative:
            lines.append(f"Global negative constraints: {'; '.join(negative)}")
        if entities:
            lines.append("Entities that must remain visually consistent:")
            for entity in entities:
                traits = "; ".join(str(value).strip() for value in entity["fixed_traits"])
                lines.append(
                    f"- {entity['id']} ({entity['kind']}): {entity['description'].strip()}. "
                    f"Fixed traits: {traits}"
                )
    if allowed_variations:
        lines.append(f"Allowed variations: {'; '.join(allowed_variations)}")
    else:
        lines.append("Allowed variations: none declared; preserve all fixed traits.")
    if bindings:
        lines.append("Attached reference order and roles:")
        for index, binding in enumerate(bindings, start=1):
            suffix = f", entity={binding.entity_id}" if binding.entity_id else ""
            lines.append(f"{index}. role={binding.role}{suffix}")
    lines.extend(("[SCENE REQUEST]", prompt))
    return "\n".join(lines)


def canonical_plan_sha256(result_fields: dict) -> str:
    """Return the SHA-256 of a canonical, semantic plan representation."""
    encoded = json.dumps(
        result_fields,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _coerce(plan: object) -> tuple[dict | None, PlanError | None]:
    if isinstance(plan, dict):
        return plan, None
    if isinstance(plan, (str, bytes)):
        try:
            loaded = json.loads(plan)
        except (ValueError, UnicodeDecodeError) as error:
            return None, PlanError("plan_unparseable", f"plan is not valid JSON: {error}")
        if not isinstance(loaded, dict):
            return None, PlanError("plan_unparseable", "plan must be a JSON object")
        return loaded, None
    return None, PlanError("plan_unparseable", f"unsupported plan type: {type(plan).__name__}")


def validate_plan(
    plan: object,
    *,
    base_dir: Path,
    schema: dict | None = None,
) -> PlanResult:
    document = schema if schema is not None else _load_schema()
    empty = PlanResult(
        ok=False,
        batch_id="",
        round=0,
        errors=(),
        items=(),
        require_approval_before_run=True,
        max_images=DEFAULT_MAX_IMAGES,
        max_rounds=DEFAULT_MAX_ROUNDS,
        pass_threshold=0.0,
        min_dimension=0,
        reject_duplicates=True,
        advisory_enabled=False,
        plan_sha256="",
        require_human_labels=True,
        migration_notes=(),
    )

    instance, coercion_error = _coerce(plan)
    if instance is None:
        assert coercion_error is not None
        return PlanResult(**{**empty.__dict__, "errors": (coercion_error,)})

    try:
        migration = contract_migrations.migrate_image_batch(instance)
    except ValueError as error:
        return PlanResult(
            **{**empty.__dict__, "errors": (PlanError("plan_schema_invalid", str(error)),)}
        )
    instance = migration.document
    empty = PlanResult(**{**empty.__dict__, "migration_notes": migration.notes})
    structural = schema_lite.validate(instance, document)
    if structural:
        errors = tuple(PlanError("plan_schema_invalid", message) for message in structural)
        return PlanResult(**{**empty.__dict__, "errors": errors})

    batch_id = instance["batch_id"]
    round_number = instance["round"]
    limits = instance.get("limits") or {}
    policy = instance.get("judge_policy") or {}

    max_images = limits.get("max_images", DEFAULT_MAX_IMAGES)
    max_rounds = limits.get("max_rounds", DEFAULT_MAX_ROUNDS)
    require_approval = limits.get("require_approval_before_run", True)

    errors: list[PlanError] = []
    rows = instance["items"]
    profile = instance.get("consistency_profile")
    profile_sha256 = _canonical_sha256(profile) if profile is not None else None
    entities_by_id: dict[str, dict] = {}
    if profile is not None:
        for entity in profile.get("entities", ()):
            entity_id = entity["id"]
            if entity_id in entities_by_id:
                errors.append(
                    PlanError(
                        "plan_duplicate_entity_id",
                        f"duplicate consistency entity id {entity_id!r}",
                    )
                )
                continue
            entities_by_id[entity_id] = entity

    if len(rows) > max_images:
        errors.append(
            PlanError(
                "plan_exceeds_max_images",
                f"plan declares {len(rows)} items but its cap is {max_images}",
            )
        )
    if round_number > max_rounds:
        errors.append(
            PlanError(
                "plan_exceeds_max_rounds",
                f"round {round_number} exceeds the cap of {max_rounds}",
            )
        )

    seen: set[str] = set()
    items: list[PlanItem] = []
    for row in rows:
        item_id = row["id"]
        prompt = row["prompt"].strip()
        if not prompt:
            errors.append(PlanError("plan_empty_prompt", "prompt is empty after trimming", item_id))
            continue
        if item_id in seen:
            errors.append(PlanError("plan_duplicate_item_id", f"duplicate item id {item_id!r}", item_id))
            continue
        seen.add(item_id)

        entity_ids = tuple(row.get("entity_ids") or ())
        if len(entity_ids) != len(set(entity_ids)):
            errors.append(
                PlanError(
                    "plan_duplicate_entity_id",
                    f"item {item_id!r} repeats an entity id",
                    item_id,
                )
            )
            continue
        if entity_ids and profile is None:
            errors.append(
                PlanError(
                    "plan_consistency_profile_required",
                    f"item {item_id!r} declares entities without a consistency profile",
                    item_id,
                )
            )
            continue
        unknown_entities = tuple(entity_id for entity_id in entity_ids if entity_id not in entities_by_id)
        if unknown_entities:
            errors.append(
                PlanError(
                    "plan_unknown_entity",
                    f"item {item_id!r} names unknown consistency entities: {', '.join(unknown_entities)}",
                    item_id,
                )
            )
            continue

        binding_specs: list[tuple[str, str, str | None]] = []
        if profile is not None:
            binding_specs.extend(
                (path, "style", None)
                for path in (profile.get("style_reference_images") or ())
            )
            for entity_id in entity_ids:
                entity = entities_by_id[entity_id]
                role = "identity" if entity["kind"] == "character" else "prop"
                binding_specs.extend(
                    (path, role, entity_id)
                    for path in (entity.get("reference_images") or ())
                )
        invalid_reference_entity = False
        for reference in row.get("references") or ():
            reference_entity = reference.get("entity_id")
            if reference_entity is not None and reference_entity not in entities_by_id:
                errors.append(
                    PlanError(
                        "plan_unknown_entity",
                        f"item {item_id!r} reference names unknown entity {reference_entity!r}",
                        item_id,
                    )
                )
                invalid_reference_entity = True
                continue
            binding_specs.append((reference["path"], reference["role"], reference_entity))
        if invalid_reference_entity:
            continue
        binding_specs.extend(
            (reference, "generic", None)
            for reference in (row.get("reference_images") or ())
        )
        if len(binding_specs) > MAX_REFERENCE_IMAGES:
            errors.append(
                PlanError(
                    "plan_too_many_effective_references",
                    f"item {item_id!r} resolves to {len(binding_specs)} reference images; "
                    f"the platform accepts {MAX_REFERENCE_IMAGES}",
                    item_id,
                )
            )
            continue

        bindings: list[ReferenceBinding] = []
        missing = False
        for reference, role, reference_entity in binding_specs:
            target = Path(reference)
            if not target.is_absolute():
                target = base_dir / target
            if not target.is_file():
                errors.append(
                    PlanError(
                        "plan_missing_reference_image",
                        f"reference image not found: {reference}",
                        item_id,
                    )
                )
                missing = True
                continue
            bindings.append(
                ReferenceBinding(
                    path=reference,
                    role=role,
                    entity_id=reference_entity,
                    sha256=file_sha256(target),
                )
            )
        if missing:
            continue

        reference_bindings = tuple(bindings)
        references = tuple(binding.path for binding in reference_bindings)
        reference_hashes = tuple(binding.sha256 for binding in reference_bindings)
        selected_entities = tuple(entities_by_id[entity_id] for entity_id in entity_ids)
        allowed_variations = tuple(
            str(value).strip() for value in (row.get("allowed_variations") or ())
        )
        effective_prompt = _compile_effective_prompt(
            prompt=prompt,
            profile=profile,
            entities=selected_entities,
            allowed_variations=allowed_variations,
            bindings=reference_bindings,
            structured_references=bool(row.get("references")),
        )
        effective_prompt_sha256 = _sha256_text(effective_prompt)
        declared_checks = tuple(row.get("pixel_checks") or ())
        check_errors = False
        for check in declared_checks:
            message = declared_checks_module.validate_check(check)
            if message is not None:
                errors.append(
                    PlanError("plan_pixel_check_invalid", message, item_id)
                )
                check_errors = True
        if check_errors:
            continue
        ratio_declaration = row.get("aspect_ratio_range")
        aspect_ratio_range = None
        if ratio_declaration is not None:
            ratio_min = float(ratio_declaration["min"])
            ratio_max = float(ratio_declaration["max"])
            if ratio_min > ratio_max:
                errors.append(
                    PlanError(
                        "plan_aspect_ratio_range_invalid",
                        "aspect_ratio_range min must not exceed max",
                        item_id,
                    )
                )
                continue
            aspect_ratio_range = (ratio_min, ratio_max)
        items.append(
            PlanItem(
                id=item_id,
                prompt=prompt,
                round=round_number,
                reference_images=references,
                reference_sha256=reference_hashes,
                idempotency_key=compute_idempotency_key(
                    batch_id=batch_id,
                    item_id=item_id,
                    round_number=round_number,
                    prompt=effective_prompt,
                    reference_sha256=reference_hashes,
                    reference_bindings=(
                        reference_bindings
                        if profile is not None or bool(row.get("references"))
                        else ()
                    ),
                ),
                pixel_checks=declared_checks,
                effective_prompt=effective_prompt,
                effective_prompt_sha256=effective_prompt_sha256,
                reference_bindings=reference_bindings,
                entity_ids=entity_ids,
                allowed_variations=allowed_variations,
                aspect_ratio_range=aspect_ratio_range,
                series_mode=profile is not None,
            )
        )

    require_human_labels = policy.get("require_human_labels", True)
    pass_threshold = policy.get("pass_threshold", 0.8)
    min_dimension = policy.get("min_dimension", 256)
    reject_duplicates = policy.get("reject_duplicates", True)
    advisory_enabled = policy.get("advisory_enabled", False)
    near_duplicate_hamming_distance = policy.get("near_duplicate_hamming_distance")
    plan_sha256 = ""
    if not errors:
        plan_sha256 = canonical_plan_sha256(
            {
                "batch_id": batch_id,
                "round": round_number,
                "limits": {
                    "max_images": max_images,
                    "max_rounds": max_rounds,
                    "require_approval_before_run": require_approval,
                },
                "judge_policy": {
                    "min_dimension": min_dimension,
                    "reject_duplicates": reject_duplicates,
                    "pass_threshold": pass_threshold,
                    "advisory_enabled": advisory_enabled,
                    "require_human_labels": require_human_labels,
                    "near_duplicate_hamming_distance": near_duplicate_hamming_distance,
                },
                "consistency_profile_sha256": profile_sha256,
                "items": [
                    {
                        "id": item.id,
                        "prompt": item.prompt,
                        "effective_prompt_sha256": item.effective_prompt_sha256,
                        "reference_sha256": list(item.reference_sha256),
                        "reference_bindings": [
                            {
                                "role": binding.role,
                                "entity_id": binding.entity_id,
                                "sha256": binding.sha256,
                            }
                            for binding in item.reference_bindings
                        ],
                        "idempotency_key": item.idempotency_key,
                        "aspect_ratio_range": (
                            None
                            if item.aspect_ratio_range is None
                            else {
                                "min": item.aspect_ratio_range[0],
                                "max": item.aspect_ratio_range[1],
                            }
                        ),
                    }
                    for item in items
                ],
            }
        )

    return PlanResult(
        ok=not errors,
        batch_id=batch_id,
        round=round_number,
        errors=tuple(errors),
        items=tuple(items),
        require_approval_before_run=require_approval,
        max_images=max_images,
        max_rounds=max_rounds,
        pass_threshold=pass_threshold,
        min_dimension=min_dimension,
        reject_duplicates=reject_duplicates,
        advisory_enabled=advisory_enabled,
        plan_sha256=plan_sha256,
        require_human_labels=require_human_labels,
        migration_notes=migration.notes,
        consistency_profile_sha256=profile_sha256,
        near_duplicate_hamming_distance=near_duplicate_hamming_distance,
    )
