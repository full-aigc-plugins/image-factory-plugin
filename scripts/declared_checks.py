#!/usr/bin/env python3
"""Evaluate the pixel checks a plan item declares against its artifact.

Three closed check kinds, each with exactly one true answer given the pixels
and the declared parameters:

* ``corner-colour`` - all four corners within a per-channel tolerance of an RGB
* ``min-margin``    - the ink bounding box keeps at least the declared free
                      fraction on every side
* ``ink-colour``    - the mean colour of non-background pixels within tolerance

Checks are declared by a person in the plan; this module never invents one and
never widens one. Any decode failure is a failed check with the reason
recorded - fail-closed, never a silent pass.
"""

from __future__ import annotations

from pathlib import Path

import png_pixels

CHECK_KINDS = ("corner-colour", "min-margin", "ink-colour")
MAX_CHECKS_PER_ITEM = 8

_KIND_FIELDS: dict[str, set[str]] = {
    "corner-colour": {"r", "g", "b", "tolerance"},
    "ink-colour": {"r", "g", "b", "tolerance"},
    "min-margin": {"min_ratio"},
}


def validate_check(check: object) -> str | None:
    """Return an error message for a malformed declaration, else None."""
    if not isinstance(check, dict):
        return "a pixel check must be an object"
    kind = check.get("kind")
    if kind not in CHECK_KINDS:
        return f"pixel check kind must be one of {CHECK_KINDS}"
    unknown = sorted(set(check) - _KIND_FIELDS[kind] - {"kind"})
    if unknown:
        return f"{kind} check has unknown fields: {', '.join(unknown)}"
    if kind in ("corner-colour", "ink-colour"):
        for field in ("r", "g", "b", "tolerance"):
            value = check.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255:
                return f"{kind} check requires integer {field} within 0-255"
    else:
        ratio = check.get("min_ratio")
        if (
            not isinstance(ratio, (int, float))
            or isinstance(ratio, bool)
            or not 0.0 < float(ratio) <= 0.45
        ):
            return "min-margin check requires min_ratio within (0, 0.45]"
    return None


def _channel_delta(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return max(abs(x - y) for x, y in zip(a, b))


def evaluate_checks(checks, artifact_path: Path) -> list[dict]:
    """Evaluate declared checks; decode at most once per artifact, fail closed."""
    rows: list[dict] = []
    decoded = None
    for check in checks:
        kind = check["kind"]
        try:
            if decoded is None:
                decoded = png_pixels.decode_png(artifact_path)
            width, height, pixels = decoded
            if kind == "corner-colour":
                declared = (check["r"], check["g"], check["b"])
                samples = png_pixels.corner_colours(width, height, pixels)
                worst = max(samples, key=lambda s: _channel_delta(s, declared))
                passed = all(_channel_delta(s, declared) <= check["tolerance"] for s in samples)
                rows.append(
                    {
                        "kind": kind,
                        "passed": passed,
                        "measured": f"worst corner RGB {worst}",
                        "expected": f"corners within tolerance {check['tolerance']} of RGB {declared}",
                    }
                )
            elif kind == "min-margin":
                margins = png_pixels.ink_margins(width, height, pixels)
                names = ("left", "right", "top", "bottom")
                worst_name, worst = min(zip(names, margins), key=lambda pair: pair[1])
                passed = worst >= float(check["min_ratio"])
                rows.append(
                    {
                        "kind": kind,
                        "passed": passed,
                        "measured": f"margins L {margins[0]:.1%} R {margins[1]:.1%} "
                        f"T {margins[2]:.1%} B {margins[3]:.1%}",
                        "expected": f"every side at least {float(check['min_ratio']):.1%} "
                        f"(narrowest: {worst_name})",
                    }
                )
            else:
                declared = (check["r"], check["g"], check["b"])
                _bbox, mean, count = png_pixels.ink_metrics(width, height, pixels)
                delta = _channel_delta(mean, declared)
                passed = delta <= check["tolerance"]
                rows.append(
                    {
                        "kind": kind,
                        "passed": passed,
                        "measured": f"mean ink RGB {mean} over {count} samples",
                        "expected": f"mean ink within tolerance {check['tolerance']} of RGB {declared}",
                    }
                )
        except png_pixels.UnsupportedPNGError as error:
            rows.append(
                {
                    "kind": kind,
                    "passed": False,
                    "measured": f"not measurable: {error}",
                    "expected": "a decodable PNG for the declared check",
                }
            )
    return rows
