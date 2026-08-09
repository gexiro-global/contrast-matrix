"""Color math for WCAG 2.x contrast calculations."""

from __future__ import annotations

import colorsys
import math
import re
from typing import Tuple

RGBA = Tuple[float, float, float, float]
RGB = Tuple[float, float, float]
WCAG_VERSION = "WCAG 2.x"


class ColorError(ValueError):
    """Raised when a CSS color cannot be parsed."""


def _number(text: str, label: str) -> float:
    try:
        value = float(text.strip())
    except ValueError as exc:
        raise ColorError("invalid {} value: {!r}".format(label, text)) from exc
    if not value == value or value in (float("inf"), float("-inf")):
        raise ColorError("{} must be finite".format(label))
    return value


def _channel(text: str) -> float:
    text = text.strip()
    if text.endswith("%"):
        value = _number(text[:-1], "channel percentage") * 255 / 100
    else:
        value = _number(text, "channel")
    if not 0 <= value <= 255:
        raise ColorError("RGB channel outside 0..255: {!r}".format(text))
    return value


def _alpha(text: str) -> float:
    text = text.strip()
    value = _number(text[:-1], "alpha percentage") / 100 if text.endswith("%") else _number(text, "alpha")
    if not 0 <= value <= 1:
        raise ColorError("alpha outside 0..1: {!r}".format(text))
    return value


def parse_color(value: str) -> RGBA:
    """Parse supported CSS hex, rgb[a](), and hsl[a]() color syntax."""
    if not isinstance(value, str):
        raise ColorError("color must be a string")
    text = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3,4}|#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?", text):
        digits = text[1:]
        if len(digits) in (3, 4):
            digits = "".join(char * 2 for char in digits)
        if len(digits) == 6:
            digits += "ff"
        return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4)) + (int(digits[6:8], 16) / 255.0,)  # type: ignore[return-value]

    match = re.fullmatch(r"(?i)(rgb|rgba|hsl|hsla)\((.*)\)", text)
    if not match:
        raise ColorError("unsupported or invalid CSS color: {!r}".format(value))
    function, body = match.groups()
    parts = [part.strip() for part in body.split(",")]
    expected = 4 if function.lower() in ("rgba", "hsla") else 3
    if len(parts) != expected or any(not part for part in parts):
        raise ColorError("{}() requires {} comma-separated values".format(function, expected))
    alpha = _alpha(parts[3]) if expected == 4 else 1.0
    if function.lower().startswith("rgb"):
        percentage_channels = [part.endswith("%") for part in parts[:3]]
        if any(percentage_channels) and not all(percentage_channels):
            raise ColorError("RGB channels must be either all numbers or all percentages")
        return (_channel(parts[0]), _channel(parts[1]), _channel(parts[2]), alpha)
    hue_text = parts[0][:-3] if parts[0].lower().endswith("deg") else parts[0]
    hue = _number(hue_text, "hue") % 360
    if not parts[1].endswith("%") or not parts[2].endswith("%"):
        raise ColorError("HSL saturation and lightness must be percentages")
    saturation = _number(parts[1][:-1], "saturation") / 100
    lightness = _number(parts[2][:-1], "lightness") / 100
    if not 0 <= saturation <= 1 or not 0 <= lightness <= 1:
        raise ColorError("HSL saturation and lightness must be within 0%..100%")
    red, green, blue = colorsys.hls_to_rgb(hue / 360, lightness, saturation)
    return (red * 255, green * 255, blue * 255, alpha)


def over(fg_rgba: RGBA, bg_rgb: RGB) -> RGB:
    """Composite an RGBA source over an opaque RGB backdrop."""
    alpha = fg_rgba[3]
    return tuple(fg_rgba[i] * alpha + bg_rgb[i] * (1 - alpha) for i in range(3))  # type: ignore[return-value]


def composite(foreground: RGBA, background: RGBA) -> RGBA:
    """Composite one RGBA color over another without discarding alpha."""
    alpha = foreground[3] + background[3] * (1 - foreground[3])
    if alpha == 0:
        return (0.0, 0.0, 0.0, 0.0)
    channels = tuple(
        (foreground[i] * foreground[3] + background[i] * background[3] * (1 - foreground[3])) / alpha
        for i in range(3)
    )
    return channels + (alpha,)  # type: ignore[return-value]


def mix(a: RGBA, b: RGBA, t: float) -> RGBA:
    """Linearly interpolate from color a (t=0) to b (t=1), including alpha."""
    if not 0 <= t <= 1:
        raise ColorError("mix amount must be within 0..1")
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(4))  # type: ignore[return-value]


def relative_luminance(rgb: RGB) -> float:
    """Return WCAG 2.x sRGB relative luminance."""
    if len(rgb) != 3 or any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 255 for value in rgb):
        raise ColorError("RGB channels must be finite numbers within 0..255")
    def linear(channel: float) -> float:
        channel /= 255
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
    return 0.2126 * linear(rgb[0]) + 0.7152 * linear(rgb[1]) + 0.0722 * linear(rgb[2])


def contrast_ratio(first: RGB, second: RGB) -> float:
    """Return the WCAG 2.x contrast ratio of two opaque colors."""
    light, dark = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)
