"""Crosshair share-code encoding and pixel-exact local rendering."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageChops

from src.services.crosshair import profile_to_code
from src.services.crosshair_render import (
    CrosshairCodeError,
    render_crosshair,
    render_png,
)

GOLDEN = Path(__file__).parent / "fixtures" / "crosshair"


def colour(r: int, g: int, b: int, a: int = 255) -> dict[str, int]:
    """Build one RGBA colour mapping."""
    return {"r": r, "g": g, "b": b, "a": a}


WHITE = colour(255, 255, 255)
RED = colour(255, 0, 0)


def lines(
    thickness: int,
    length: int,
    vertical: int,
    offset: int,
    shown: bool,
    opacity: float,
    movement: bool = False,
    shooting: bool = False,
) -> dict[str, object]:
    """Build one inner or outer line group."""
    return {
        "lineThickness": thickness,
        "lineLength": length,
        "lineLengthVertical": vertical,
        "lineOffset": offset,
        "bAllowVertScaling": False,
        "bShowMovementError": movement,
        "bShowShootingError": shooting,
        "bShowMinError": True,
        "opacity": opacity,
        "bShowLines": shown,
        "firingErrorScale": 1,
        "movementErrorScale": 1,
    }


def profile(
    color,
    custom,
    outline,
    dot,
    fade,
    inner,
    outer,
    sniper,
    advanced,
) -> dict[str, object]:
    """Build one saved crosshair profile."""
    return {
        "bUseAdvancedOptions": advanced,
        "bUsePrimaryCrosshairForADS": True,
        "aDS": None,
        "primary": {
            "color": color,
            "colorCustom": custom,
            "bUseCustomColor": False,
            "bHasOutline": outline[0],
            "outlineThickness": outline[1],
            "outlineOpacity": outline[2],
            "bDisplayCenterDot": dot[0],
            "centerDotSize": dot[1],
            "centerDotOpacity": dot[2],
            "bFadeCrosshairWithFiringError": fade,
            "bShowSpectatedPlayerCrosshair": True,
            "bHideCrosshair": False,
            "bFixMinErrorAcrossWeapons": False,
            "innerLines": inner,
            "outerLines": outer,
        },
        "sniper": {
            "centerDotColor": sniper[0],
            "centerDotColorCustom": WHITE,
            "centerDotSize": sniper[1],
            "centerDotOpacity": sniper[2],
            "bDisplayCenterDot": True,
            "bUseCustomCenterDotColor": False,
        },
    }


OFF_OUT = lines(1, 1, 2, 0, False, 0.3501844108104706)
OFF = lines(2, 2, 2, 10, False, 0.35, movement=True, shooting=True)

ENCODED = [
    (
        "nats",
        profile(
            colour(223, 255, 0),
            colour(0, 0, 0),
            (False, 1, 1),
            (False, 1, 0),
            True,
            lines(1, 2, 6, 1, True, 1),
            lines(0, 0, 2, 9, False, 0),
            (WHITE, 1, 1),
            True,
        ),
        "0;s;1;P;c;3;u;000000FF;h;0;0t;1;0l;2;0o;1;0a;1;0f;0;1b;0;S;c;0;o;1",
    ),
    (
        "blur 1",
        profile(
            RED,
            WHITE,
            (False, 2, 1),
            (True, 3, 1),
            False,
            lines(1, 2, 2, 2, True, 1),
            OFF_OUT,
            (RED, 1.0003890991210938, 0.7500972747802734),
            True,
        ),
        "0;s;1;P;c;7;h;0;d;1;z;3;f;0;0t;1;0l;2;0v;2;0o;2;0a;1;0f;0;1b;0;S;s;1.0",
    ),
    (
        "blur 2",
        profile(
            colour(0, 255, 255),
            WHITE,
            (False, 2, 0.5000709295272827),
            (True, 3, 1),
            False,
            lines(4, 1, 1, 0, False, 1),
            OFF_OUT,
            (WHITE, 1.000162124633789, 0.7500405311584473),
            True,
        ),
        "0;s;1;P;c;5;h;0;d;1;z;3;f;0;0b;0;1b;0;S;c;0;s;1.0",
    ),
    (
        "dot",
        profile(
            colour(0, 255, 255),
            colour(0, 0, 0),
            (False, 2, 0.336004376411438),
            (True, 3, 1),
            False,
            lines(10, 0, 0, 20, True, 1),
            lines(0, 0, 0, 0, False, 1),
            (WHITE, 1.0000324249267578, 0.7500081062316895),
            True,
        ),
        "0;s;1;P;c;5;u;000000FF;h;0;d;1;z;3;f;0;0t;10;0l;0;0v;0;0o;20;0a;1;0f;0;1b;0;S;c;0;s;1.0",
    ),
    (
        "gay",
        profile(
            colour(223, 255, 0),
            colour(0, 0, 0),
            (False, 2, 0.5000709295272827),
            (True, 3, 1),
            False,
            lines(1, 2, 2, 1, False, 1),
            OFF_OUT,
            (WHITE, 1.000162124633789, 1),
            True,
        ),
        "0;s;1;P;c;3;u;000000FF;h;0;d;1;z;3;f;0;0b;0;1b;0;S;c;0;s;1.0;o;1",
    ),
    (
        "gay 2",
        profile(
            colour(0, 255, 255),
            WHITE,
            (False, 2, 1),
            (True, 3, 1),
            False,
            lines(4, 0, 0, 5, False, 1),
            lines(1, 3, 3, 0, False, 0),
            (WHITE, 1.3489999771118164, 1),
            True,
        ),
        "0;s;1;P;c;5;h;0;d;1;z;3;f;0;0b;0;1b;0;S;c;0;s;1.349;o;1",
    ),
    (
        "imported 1",
        profile(
            RED,
            WHITE,
            (False, 2, 1),
            (True, 3, 1),
            False,
            lines(1, 3, 0, 2, False, 1),
            lines(0, 0, 3, 0, False, 0),
            (WHITE, 1.3489999771118164, 1),
            True,
        ),
        "0;s;1;P;c;7;h;0;d;1;z;3;f;0;0b;0;1b;0;S;c;0;s;1.349;o;1",
    ),
    (
        "imported 2",
        profile(
            WHITE,
            WHITE,
            (True, 1, 0.5),
            (True, 2, 1),
            False,
            lines(4, 1, 1, 0, True, 1),
            OFF,
            (RED, 1, 0.75),
            False,
        ),
        "0;P;d;1;f;0;0t;4;0l;1;0v;1;0o;0;0a;1;0f;0;1b;0",
    ),
    (
        "imported xh",
        profile(
            RED,
            WHITE,
            (True, 1, 1),
            (False, 2, 1),
            False,
            lines(1, 2, 2, 2, True, 1),
            OFF,
            (RED, 1, 0.75),
            False,
        ),
        "0;P;c;7;o;1;f;0;0t;1;0l;2;0v;2;0o;2;0a;1;0f;0;1b;0",
    ),
]

GOLDEN_CODES = [
    ("sample1_t1_inner", "0;P;c;1;o;1;f;0;0t;1;0l;2;0o;2;0a;1;0f;0;1b;0"),
    (
        "code_a_preset_no_outline",
        "0;s;1;P;c;3;u;000000FF;h;0;0t;1;0l;2;0o;1;0a;1;0f;0;1b;0;S;c;0;o;1",
    ),
    ("code_b_dot_outline", "0;s;1;P;c;1;o;1;d;1;z;1;f;0;0b;0;1b;0;S;c;0;s;1.349;o;1"),
    ("probe1_t2", "0;P;c;1;h;0;0t;2;0l;4;0o;3;0a;1;0f;0;1b;0"),
    ("probe2_t3", "0;P;c;1;h;0;0t;3;0l;4;0o;3;0a;1;0f;0;1b;0"),
    ("probe3_t4_off0", "0;P;c;1;h;0;0t;4;0l;4;0o;0;0a;1;0f;0;1b;0"),
    ("probe4_dot2", "0;P;c;1;h;0;d;1;z;2;0b;0;1b;0"),
    ("probe5_dot3", "0;P;c;1;h;0;d;1;z;3;0b;0;1b;0"),
    ("probe6_outer", "0;P;c;1;h;0;0b;0;1t;2;1l;4;1o;6;1a;1"),
    ("outer_off5_len3", "0;P;c;1;h;0;0b;0;1t;2;1l;3;1o;5;1a;1"),
    ("outer_off12_len3", "0;P;c;1;h;0;0b;0;1t;2;1l;3;1o;12;1a;1"),
    ("outer_t1_off5", "0;P;c;1;h;0;0b;0;1t;1;1l;3;1o;5;1a;1"),
    ("outer_t3_off5", "0;P;c;1;h;0;0b;0;1t;3;1l;3;1o;5;1a;1"),
    (
        "inner_and_outer_firing_on",
        "0;P;c;1;h;0;0t;2;0l;4;0o;3;0a;1;1t;2;1l;3;1o;5;1a;1",
    ),
    (
        "outer_inner_values_while_off",
        "0;P;c;1;h;0;0b;0;0t;1;0l;1;0o;1;1t;2;1l;3;1o;5;1a;1",
    ),
    ("outer_all_defaults", "0;P;c;1;h;0;0b;0"),
]


@pytest.mark.parametrize(
    "name, saved, expected", ENCODED, ids=[case[0] for case in ENCODED]
)
def test_profile_encodes_to_the_games_code(name, saved, expected):
    """Each real saved profile must produce its known share code."""
    code, _warnings = profile_to_code(saved)
    assert code == expected


@pytest.mark.parametrize(
    "name, code", GOLDEN_CODES, ids=[case[0] for case in GOLDEN_CODES]
)
def test_render_matches_api_images(name, code):
    """Rendered primary crosshairs must match the API images pixel for pixel."""
    api = Image.open(GOLDEN / f"{name}.png")
    transparent = api.mode == "RGBA"
    rendered = render_crosshair(code, transparent=transparent)
    difference = ImageChops.difference(api.convert("RGBA"), rendered.convert("RGBA"))
    assert difference.getbbox() is None


def test_render_png_returns_a_png_and_rejects_bad_scale():
    """PNG output must have a PNG signature and a bounded scale."""
    payload = render_png("0;P;c;1;h;0;0b;0;1b;0")
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(CrosshairCodeError):
        render_png("0;P;c;1", scale=5)


@pytest.mark.parametrize(
    "code",
    ["", "1;P;c;1", "0;P;c;9", "0;P;c", "0;P;c;1;c;2", "0;X;c;1"],
)
def test_invalid_codes_are_rejected(code):
    """Malformed share codes must fail instead of drawing a misleading preview."""
    with pytest.raises(CrosshairCodeError):
        render_crosshair(code)
