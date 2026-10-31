"""Render a VALORANT crosshair share code to a PNG without network access."""

from __future__ import annotations

import io
import math
import re

from PIL import Image, ImageDraw

PALETTE = (
    "FFFFFF",
    "00FF00",
    "7FFF00",
    "DFFF00",
    "FFFF00",
    "00FFFF",
    "FF00FF",
    "FF0000",
)
# Lines whose firing-error flag is on are drawn this many grid px further out.
FIRING_ERROR_EXTRA_OFFSET = 4
# Per-shape compositing in this order keeps every golden API image pixel-exact.
ARM_ORDER = "BLRT"
INNER_DEFAULTS = {"length": 6, "thickness": 2, "offset": 3, "alpha": 0.8}
OUTER_DEFAULTS = {"length": 2, "thickness": 2, "offset": 10, "alpha": 0.35}


class CrosshairCodeError(ValueError):
    """Raised when a share code cannot be parsed or drawn."""


def parse_code(code: str) -> dict[str, str]:
    """Parse a share code and return the primary (``P``) section's settings."""
    if len(code) > 2048:
        raise CrosshairCodeError("Crosshair code is too long")
    tokens = code.strip().rstrip(";").split(";")
    if not tokens or tokens[0] != "0":
        raise CrosshairCodeError("Expected a version-0 VALORANT crosshair code")
    sections: dict[str, dict[str, str]] = {"general": {}}
    section = "general"
    index = 1
    while index < len(tokens):
        key = tokens[index]
        if key in {"P", "A", "S"}:
            if key in sections:
                raise CrosshairCodeError(f"Duplicate section: {key}")
            section = key
            sections[section] = {}
            index += 1
            continue
        if not re.fullmatch(r"[a-z]|[01][a-z]", key):
            raise CrosshairCodeError(f"Invalid setting key: {key!r}")
        if index + 1 >= len(tokens) or tokens[index + 1] in {"", "P", "A", "S"}:
            raise CrosshairCodeError(f"Missing value for {key}")
        if key in sections[section]:
            raise CrosshairCodeError(f"Duplicate setting: {key}")
        sections[section][key] = tokens[index + 1]
        index += 2
    if "P" not in sections:
        raise CrosshairCodeError("Code has no primary (P) crosshair section")
    return sections["P"]


def _number(
    settings: dict[str, str],
    key: str,
    default: float,
    maximum: float,
    *,
    minimum: float = 0.0,
) -> float:
    """Read one finite, in-range setting value."""
    try:
        value = float(settings.get(key, default))
    except ValueError as error:
        raise CrosshairCodeError(f"Invalid number for {key}") from error
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise CrosshairCodeError(f"{key} must be between {minimum} and {maximum}")
    return value


def _integer(settings: dict[str, str], key: str, default: float, maximum: float) -> int:
    """Read one setting that the game stores as a whole number."""
    value = _number(settings, key, default, maximum)
    if not value.is_integer():
        raise CrosshairCodeError(f"{key} must be an integer")
    return int(value)


def _composite(
    image: Image.Image, box: tuple[int, int, int, int], fill: tuple[int, int, int, int]
) -> Image.Image:
    """Draw one rectangle on its own layer and composite it onto the canvas."""
    layer = Image.new("RGBA", image.size)
    ImageDraw.Draw(layer).rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill=fill)
    return Image.alpha_composite(image, layer)


def render_crosshair(code: str, *, transparent: bool = True) -> Image.Image:
    """Render the primary crosshair of a share code to a 256x256 image."""
    settings = parse_code(code)
    color_index = _integer(settings, "c", 0, 8)
    if color_index == 8:
        color_hex = settings.get("u", "FFFFFFFF")
        if not re.fullmatch(r"[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", color_hex):
            raise CrosshairCodeError("u must contain 6 or 8 hexadecimal digits")
    else:
        color_hex = PALETTE[color_index]
    color = (
        int(color_hex[0:2], 16),
        int(color_hex[2:4], 16),
        int(color_hex[4:6], 16),
    )
    color_alpha = int(color_hex[6:8], 16) if len(color_hex) == 8 else 255
    outline = _integer(settings, "h", 1, 1)
    outline_width = _integer(settings, "t", 1, 6) or 1
    outline_alpha = round(_number(settings, "o", 0.5, 1) * 255)

    shapes: list[tuple[tuple[int, int, int, int], int]] = []
    for group, defaults in (("0", INNER_DEFAULTS), ("1", OUTER_DEFAULTS)):
        length = _integer(settings, group + "l", defaults["length"], 20)
        thickness = _integer(settings, group + "t", defaults["thickness"], 10)
        offset = _integer(settings, group + "o", defaults["offset"], 40)
        alpha = round(
            _number(settings, group + "a", defaults["alpha"], 1) * color_alpha
        )
        vertical = _integer(settings, group + "v", defaults["length"], 20)
        if not _integer(settings, group + "g", 0, 1):
            vertical = length
        if not _integer(settings, group + "b", 1, 1) or not thickness:
            continue
        if _integer(settings, group + "f", 1, 1):
            offset += FIRING_ERROR_EXTRA_OFFSET
        band_low = 64 - (thickness + 1) // 2
        band_high = band_low + thickness
        near_low = 64 - offset - thickness % 2
        near_high = 64 + offset
        arms = {
            "L": (near_low - length, band_low, near_low, band_high) if length else None,
            "R": (near_high, band_low, near_high + length, band_high)
            if length
            else None,
            "T": (band_low, near_low - vertical, band_high, near_low)
            if vertical
            else None,
            "B": (band_low, near_high, band_high, near_high + vertical)
            if vertical
            else None,
        }
        for tag in ARM_ORDER:
            arm = arms[tag]
            if arm is not None:
                shapes.append((arm, alpha))

    if _integer(settings, "d", 0, 1):
        size = _integer(settings, "z", 2, 6) or 1
        low = 64 - (size + 1) // 2
        alpha = round(_number(settings, "a", 1, 1) * color_alpha)
        shapes.append(((low, low, low + size, low + size), alpha))

    background = (0, 0, 0, 0) if transparent else (0, 0, 0, 255)
    image = Image.new("RGBA", (128, 128), background)
    for box, alpha in shapes:
        if outline:
            expanded = (
                box[0] - outline_width,
                box[1] - outline_width,
                box[2] + outline_width,
                box[3] + outline_width,
            )
            image = _composite(image, expanded, (0, 0, 0, outline_alpha))
        image = _composite(image, box, (*color, alpha))
    return image.resize((256, 256), Image.Resampling.NEAREST)


def render_png(code: str, *, transparent: bool = True, scale: int = 2) -> bytes:
    """Render a share code to PNG bytes, optionally upscaled 1-4 times."""
    if not 1 <= scale <= 4:
        raise CrosshairCodeError("scale must be between 1 and 4")
    image = render_crosshair(code, transparent=transparent)
    if scale != 1:
        image = image.resize(
            (image.width * scale, image.height * scale), Image.Resampling.NEAREST
        )
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()
