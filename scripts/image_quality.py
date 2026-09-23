#!/usr/bin/env python3
"""File-derived quality measurements safe to use as deterministic gates."""

from __future__ import annotations

import math
from pathlib import Path

import png_pixels


HASH_SIZE = 8
HASH_BITS = HASH_SIZE * HASH_SIZE
MULTI_HASH_VERSION = "multi-hash-v1"
ALGORITHM_VERSIONS = {
    "ahash": "average-hash-8x8-luma-v1",
    "dhash": "difference-hash-9x8-luma-v1",
    "phash": "dct-phash-32x32-luma-v1",
}


def _sample(width: int, height: int, pixels: bytearray, cols: int, rows: int) -> list[float]:
    values: list[float] = []
    for cell_y in range(rows):
        y0 = cell_y * height // rows
        y1 = max(y0 + 1, (cell_y + 1) * height // rows)
        for cell_x in range(cols):
            x0 = cell_x * width // cols
            x1 = max(x0 + 1, (cell_x + 1) * width // cols)
            total = 0.0
            count = 0
            for y in range(y0, min(y1, height)):
                for x in range(x0, min(x1, width)):
                    r, g, b = png_pixels.rgb_at(width, pixels, x, y)
                    total += 0.2126 * r + 0.7152 * g + 0.0722 * b
                    count += 1
            values.append(total / count)
    return values


def _hex_bits(flags: list[bool]) -> str:
    bits = 0
    for flag in flags:
        bits = (bits << 1) | int(flag)
    return f"{bits:016x}"


def average_hash(path: Path) -> str:
    """Return a fixed 64-bit average hash for a supported PNG.

    Each output cell averages the luminance of the source pixels that map to it.
    The algorithm and dimensions are intentionally fixed so evidence remains
    comparable across runs and hosts.
    """
    width, height, pixels = png_pixels.decode_png(Path(path))
    values = _sample(width, height, pixels, HASH_SIZE, HASH_SIZE)
    mean = sum(values) / len(values)
    return _hex_bits([value >= mean for value in values])


def multi_hash(path: Path) -> dict[str, str]:
    """Return versioned 64-bit composition hashes; these are not identity signals."""
    width, height, pixels = png_pixels.decode_png(Path(path))
    if width <= 0 or height <= 0:
        raise ValueError("PNG dimensions must be positive")
    ahash_samples = _sample(width, height, pixels, 8, 8)
    ahash_mean = sum(ahash_samples) / 64
    dhash_samples = _sample(width, height, pixels, 9, 8)
    dhash_flags = [
        dhash_samples[y * 9 + x] > dhash_samples[y * 9 + x + 1]
        for y in range(8) for x in range(8)
    ]
    samples = _sample(width, height, pixels, 32, 32)
    cosine = [[math.cos(math.pi * (2 * x + 1) * u / 64) for x in range(32)] for u in range(8)]
    horizontal = [
        [sum(samples[y * 32 + x] * cosine[u][x] for x in range(32)) for u in range(8)]
        for y in range(32)
    ]
    coefficients = [
        sum(horizontal[y][u] * cosine[v][y] for y in range(32))
        for v in range(8) for u in range(8)
    ]
    non_dc = sorted(coefficients[1:])
    median = non_dc[len(non_dc) // 2]
    return {
        "ahash": _hex_bits([value >= ahash_mean for value in ahash_samples]),
        "dhash": _hex_bits(dhash_flags),
        "phash": _hex_bits([value > median for value in coefficients]),
    }


def multi_hash_distances(left: dict[str, str], right: dict[str, str]) -> dict[str, int]:
    """Keep all per-algorithm distances for reproducible policy decisions."""
    return {name: hamming_distance(left[name], right[name]) for name in ALGORITHM_VERSIONS}


def hamming_distance(left: str, right: str) -> int:
    """Count differing bits between two fixed-length hexadecimal hashes."""
    if len(left) != 16 or len(right) != 16:
        raise ValueError("average hashes must contain exactly 16 hexadecimal characters")
    return (int(left, 16) ^ int(right, 16)).bit_count()
