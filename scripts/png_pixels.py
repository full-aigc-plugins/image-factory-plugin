#!/usr/bin/env python3
"""Standard-library PNG decoding plus the pixel measurements the checks need.

The runtime stays standard-library-only, so this module decodes exactly the PNG
subset the generation path produces: 8-bit depth, non-interlaced, colour types
0 (grey), 2 (RGB), 3 (palette), 4 (grey+alpha) and 6 (RGBA). Anything else -
16-bit channels, interlaced frames, unknown filters - raises
UnsupportedPNGError, and callers must treat that as a failed check: "cannot be
measured" must never quietly become "measured fine".

Pixels are normalized to RGBA byte order so the measurement helpers never have
to reason about colour types.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


class UnsupportedPNGError(ValueError):
    """The PNG uses a feature this decoder deliberately does not support."""


_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_SAMPLE_STEP = 2
_INK_THRESHOLD = 60
_CORNER_INSET = 8


def decode_png(target: Path) -> tuple[int, int, bytearray]:
    """Return (width, height, RGBA-packed pixels) for a supported PNG."""
    data = Path(target).read_bytes()
    if data[:8] != _SIGNATURE:
        raise UnsupportedPNGError("not a PNG file")
    pos = 8
    width = height = bit_depth = colour_type = interlace = None
    palette = b""
    idat = bytearray()
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width, height, bit_depth, colour_type, _c, _f, interlace = struct.unpack(
                ">IIBBBBB", chunk
            )
        elif kind == b"PLTE":
            palette = chunk
        elif kind == b"IDAT":
            idat += chunk
        elif kind == b"IEND":
            break
        pos += 12 + length
    if width is None:
        raise UnsupportedPNGError("missing IHDR chunk")
    if bit_depth != 8:
        raise UnsupportedPNGError(f"unsupported bit depth {bit_depth}")
    if colour_type not in _CHANNELS:
        raise UnsupportedPNGError(f"unsupported colour type {colour_type}")
    if interlace != 0:
        raise UnsupportedPNGError("interlaced PNG is not supported")
    channels = _CHANNELS[colour_type]
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as error:
        raise UnsupportedPNGError(f"corrupt pixel data: {error}") from error
    stride = width * channels
    if len(raw) < (stride + 1) * height:
        raise UnsupportedPNGError("truncated pixel data")

    pixels = bytearray(width * height * 4)
    previous = bytearray(stride)
    pos = 0
    for y in range(height):
        filt = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if filt == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif filt == 2:
            for i in range(stride):
                line[i] = (line[i] + previous[i]) & 0xFF
        elif filt == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + previous[i]) >> 1)) & 0xFF
        elif filt == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = previous[i]
                c = previous[i - channels] if i >= channels else 0
                p = a + b - c
                pa = abs(p - a)
                pb = abs(p - b)
                pc = abs(p - c)
                predictor = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + predictor) & 0xFF
        elif filt != 0:
            raise UnsupportedPNGError(f"unsupported filter type {filt}")
        previous = line
        base = y * width * 4
        for x in range(width):
            src = x * channels
            dst = base + x * 4
            if colour_type == 6:
                pixels[dst:dst + 4] = line[src:src + 4]
            elif colour_type == 2:
                pixels[dst:dst + 3] = line[src:src + 3]
                pixels[dst + 3] = 255
            elif colour_type == 0:
                grey = line[src]
                pixels[dst] = pixels[dst + 1] = pixels[dst + 2] = grey
                pixels[dst + 3] = 255
            elif colour_type == 4:
                grey = line[src]
                pixels[dst] = pixels[dst + 1] = pixels[dst + 2] = grey
                pixels[dst + 3] = line[src + 1]
            else:
                index = line[src]
                if index * 3 + 3 > len(palette):
                    raise UnsupportedPNGError("palette index out of range")
                pixels[dst:dst + 3] = palette[index * 3:index * 3 + 3]
                pixels[dst + 3] = 255
    return width, height, pixels


def decode_png_from_bytes(data: bytes) -> tuple[int, int, bytearray]:
    """Decode an in-memory PNG; same contract and same fail-closed behaviour."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    try:
        return decode_png(temporary)
    finally:
        temporary.unlink(missing_ok=True)


def rgb_at(width: int, pixels: bytearray, x: int, y: int) -> tuple[int, int, int]:
    base = (y * width + x) * 4
    return (pixels[base], pixels[base + 1], pixels[base + 2])


def corner_colours(width: int, height: int, pixels: bytearray) -> list[tuple[int, int, int]]:
    """The four inset corner colours; tiny images fall back to the centre pixel."""
    inset = _CORNER_INSET
    if width <= inset * 2 or height <= inset * 2:
        return [rgb_at(width, pixels, width // 2, height // 2)]
    return [
        rgb_at(width, pixels, inset, inset),
        rgb_at(width, pixels, width - 1 - inset, inset),
        rgb_at(width, pixels, inset, height - 1 - inset),
        rgb_at(width, pixels, width - 1 - inset, height - 1 - inset),
    ]


def _differs(pixels: bytearray, index: int, background: tuple[int, int, int]) -> bool:
    return (
        abs(pixels[index] - background[0])
        + abs(pixels[index + 1] - background[1])
        + abs(pixels[index + 2] - background[2])
    ) > _INK_THRESHOLD


def _background(width: int, height: int, pixels: bytearray) -> tuple[int, int, int]:
    corners = corner_colours(width, height, pixels)
    return tuple(sum(c[i] for c in corners) // len(corners) for i in range(3))  # type: ignore[return-value]


def ink_metrics(
    width: int, height: int, pixels: bytearray
) -> tuple[tuple[int, int, int, int], tuple[int, int, int], int]:
    """Return (ink bbox, mean ink RGB, sample count) against the corner background.

    Samples every _SAMPLE_STEP-th pixel in both axes; margins derived from the
    bbox are therefore accurate to that step, far below any declared ratio a
    person would write.
    """
    background = _background(width, height, pixels)
    x0 = y0 = width * height
    x1 = y1 = -1
    samples = 0
    sums = [0, 0, 0]
    for y in range(0, height, _SAMPLE_STEP):
        row = y * width * 4
        for x in range(0, width, _SAMPLE_STEP):
            index = row + x * 4
            if _differs(pixels, index, background):
                samples += 1
                sums[0] += pixels[index]
                sums[1] += pixels[index + 1]
                sums[2] += pixels[index + 2]
                x0 = min(x0, x)
                x1 = max(x1, x)
                y0 = min(y0, y)
                y1 = max(y1, y)
    if samples == 0:
        return (0, 0, 0, 0), (0, 0, 0), 0
    mean = (sums[0] // samples, sums[1] // samples, sums[2] // samples)
    return (x0, y0, x1, y1), mean, samples


def ink_margins(width: int, height: int, pixels: bytearray) -> tuple[float, float, float, float]:
    """Free fractions (left, right, top, bottom) around the ink bounding box."""
    (x0, y0, x1, y1), _mean, _n = ink_metrics(width, height, pixels)
    if x1 < x0:
        return (1.0, 1.0, 1.0, 1.0)
    return (
        x0 / width,
        (width - 1 - x1) / width,
        y0 / height,
        (height - 1 - y1) / height,
    )
