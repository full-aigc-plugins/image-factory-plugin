#!/usr/bin/env python3
"""File-derived quality measurements safe to use as deterministic gates."""

from __future__ import annotations

from pathlib import Path

import png_pixels


HASH_SIZE = 8
HASH_BITS = HASH_SIZE * HASH_SIZE


def average_hash(path: Path) -> str:
    """Return a fixed 64-bit average hash for a supported PNG.

    Each output cell averages the luminance of the source pixels that map to it.
    The algorithm and dimensions are intentionally fixed so evidence remains
    comparable across runs and hosts.
    """
    width, height, pixels = png_pixels.decode_png(Path(path))
    values: list[float] = []
    for cell_y in range(HASH_SIZE):
        y0 = cell_y * height // HASH_SIZE
        y1 = max(y0 + 1, (cell_y + 1) * height // HASH_SIZE)
        for cell_x in range(HASH_SIZE):
            x0 = cell_x * width // HASH_SIZE
            x1 = max(x0 + 1, (cell_x + 1) * width // HASH_SIZE)
            total = 0.0
            count = 0
            for y in range(y0, min(y1, height)):
                for x in range(x0, min(x1, width)):
                    r, g, b = png_pixels.rgb_at(width, pixels, x, y)
                    total += 0.2126 * r + 0.7152 * g + 0.0722 * b
                    count += 1
            values.append(total / count)
    mean = sum(values) / len(values)
    bits = 0
    for value in values:
        bits = (bits << 1) | int(value >= mean)
    return f"{bits:016x}"


def hamming_distance(left: str, right: str) -> int:
    """Count differing bits between two fixed-length hexadecimal hashes."""
    if len(left) != 16 or len(right) != 16:
        raise ValueError("average hashes must contain exactly 16 hexadecimal characters")
    return (int(left, 16) ^ int(right, 16)).bit_count()
