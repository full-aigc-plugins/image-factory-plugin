#!/usr/bin/env python3
"""Resolve structured story state for a linear image sequence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoryStateError:
    code: str
    message: str


@dataclass(frozen=True)
class StoryStateModel:
    permanent: tuple[tuple[str, str], ...]
    scenes: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
    variables: tuple[tuple[str, str], ...]

    def scene_map(self) -> dict[str, tuple[tuple[str, str], ...]]:
        return dict(self.scenes)

    def initial_variables(self) -> dict[str, str]:
        return dict(self.variables)


@dataclass(frozen=True)
class ResolvedFrameState:
    scene_id: str | None
    bindings: tuple[tuple[str, str], ...]
    transitions: tuple[tuple[str, str, str], ...]


def _unique_bindings(
    rows: list[dict], *, scope: str
) -> tuple[dict[str, str], list[StoryStateError]]:
    bindings: dict[str, str] = {}
    errors: list[StoryStateError] = []
    for row in rows:
        path = row["path"]
        if path in bindings:
            errors.append(
                StoryStateError(
                    "plan_story_state_duplicate_path",
                    f"story state path {path!r} is duplicated in {scope}",
                )
            )
            continue
        bindings[path] = row["value"]
    return bindings, errors


def build_model(profile: dict | None) -> tuple[StoryStateModel | None, tuple[StoryStateError, ...]]:
    """Build the immutable state model declared by a consistency profile."""
    if profile is None or profile.get("story_state") is None:
        return None, ()
    declaration = profile["story_state"]
    permanent, errors = _unique_bindings(
        list(declaration.get("permanent_locks") or ()), scope="permanent_locks"
    )

    scenes: dict[str, tuple[tuple[str, str], ...]] = {}
    scene_locked_paths: set[str] = set()
    for scene in declaration.get("scenes") or ():
        scene_id = scene["id"]
        if scene_id in scenes:
            errors.append(
                StoryStateError(
                    "plan_story_state_duplicate_scene",
                    f"story state scene {scene_id!r} is duplicated",
                )
            )
            continue
        locks, scene_errors = _unique_bindings(
            list(scene.get("locks") or ()), scope=f"scene {scene_id!r}"
        )
        errors.extend(scene_errors)
        overlap = sorted(set(locks) & set(permanent))
        if overlap:
            errors.append(
                StoryStateError(
                    "plan_story_state_path_conflict",
                    "story state paths cannot be both permanent and scene locked: "
                    + ", ".join(overlap),
                )
            )
        scene_locked_paths.update(locks)
        scenes[scene_id] = tuple(sorted(locks.items()))

    variables: dict[str, str] = {}
    for row in declaration.get("variables") or ():
        path = row["path"]
        if path in variables:
            errors.append(
                StoryStateError(
                    "plan_story_state_duplicate_path",
                    f"story state variable path {path!r} is duplicated",
                )
            )
            continue
        variables[path] = row["initial_value"]
    conflicts = sorted(set(variables) & (set(permanent) | scene_locked_paths))
    if conflicts:
        errors.append(
            StoryStateError(
                "plan_story_state_path_conflict",
                "story state paths cannot be both locked and variable: "
                + ", ".join(conflicts),
            )
        )

    model = StoryStateModel(
        permanent=tuple(sorted(permanent.items())),
        scenes=tuple(sorted(scenes.items())),
        variables=tuple(sorted(variables.items())),
    )
    return model, tuple(errors)


def resolve_frame(
    model: StoryStateModel,
    row: dict,
    current_variables: dict[str, str],
) -> tuple[ResolvedFrameState | None, dict[str, str], tuple[StoryStateError, ...]]:
    """Resolve one frame against inherited variable state."""
    scene_id = row.get("scene_id")
    scene_map = model.scene_map()
    errors: list[StoryStateError] = []
    if scene_map and scene_id is None:
        errors.append(
            StoryStateError(
                "plan_story_state_scene_required",
                "an item using structured story state must declare scene_id",
            )
        )
    elif scene_id is not None and scene_id not in scene_map:
        errors.append(
            StoryStateError(
                "plan_story_state_unknown_scene",
                f"story state scene {scene_id!r} is not declared",
            )
        )

    next_variables = dict(current_variables)
    seen_paths: set[str] = set()
    transitions: list[tuple[str, str, str]] = []
    allowed = set(dict(model.variables))
    for transition in row.get("state_transitions") or ():
        path = transition["path"]
        before = transition["from"]
        after = transition["to"]
        if path in seen_paths:
            errors.append(
                StoryStateError(
                    "plan_story_state_duplicate_transition",
                    f"story state transition path {path!r} is duplicated in one frame",
                )
            )
            continue
        seen_paths.add(path)
        if path not in allowed:
            errors.append(
                StoryStateError(
                    "plan_story_state_locked_transition",
                    f"story state path {path!r} is not a declared variable",
                )
            )
            continue
        inherited = next_variables[path]
        if inherited != before:
            errors.append(
                StoryStateError(
                    "plan_story_state_transition_mismatch",
                    f"story state transition {path!r} expects {before!r} but inherited {inherited!r}",
                )
            )
            continue
        next_variables[path] = after
        transitions.append((path, before, after))

    if errors:
        return None, current_variables, tuple(errors)
    resolved = dict(model.permanent)
    if scene_id is not None:
        resolved.update(scene_map[scene_id])
    resolved.update(next_variables)
    return (
        ResolvedFrameState(
            scene_id=scene_id,
            bindings=tuple(sorted(resolved.items())),
            transitions=tuple(sorted(transitions)),
        ),
        next_variables,
        (),
    )
