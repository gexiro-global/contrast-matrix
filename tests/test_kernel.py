import math

import pytest

from contrast_matrix import ColorError, contrast_ratio, mix, over, parse_color, relative_luminance


def test_published_wcag_extremes_and_examples():
    assert contrast_ratio((0, 0, 0), (255, 255, 255)) == 21
    assert contrast_ratio((255, 255, 255), (0, 0, 0)) == 21
    # W3C WCAG technique G18 examples: #767676 on white is 4.54:1;
    # #777777 on white is 4.48:1 and misses the 4.5 normal-text boundary.
    assert contrast_ratio((118, 118, 118), (255, 255, 255)) == pytest.approx(4.5422, rel=1e-4)
    assert contrast_ratio((119, 119, 119), (255, 255, 255)) == pytest.approx(4.4781, rel=1e-4)
    assert contrast_ratio((89, 89, 89), (255, 255, 255)) == pytest.approx(7.0047, rel=1e-4)
    assert contrast_ratio((90, 90, 90), (255, 255, 255)) < 7


@pytest.mark.parametrize("text, expected", [
    ("#abc", (170, 187, 204, 1)),
    ("#abcd", (170, 187, 204, 221 / 255)),
    ("#112233", (17, 34, 51, 1)),
    ("#11223380", (17, 34, 51, 128 / 255)),
    ("rgb(255, 0, 127)", (255, 0, 127, 1)),
    ("rgb(100%, 0%, 50%)", (255, 0, 127.5, 1)),
    ("rgba(1, 2, 3, .25)", (1, 2, 3, .25)),
    ("rgba(1, 2, 3, 25%)", (1, 2, 3, .25)),
])
def test_color_forms(text, expected):
    assert parse_color(text) == pytest.approx(expected)


def test_hsl_forms():
    assert parse_color("hsl(0, 100%, 50%)") == pytest.approx((255, 0, 0, 1))
    assert parse_color("hsl(120, 100%, 50%)") == pytest.approx((0, 255, 0, 1))
    assert parse_color("hsla(240deg, 100%, 50%, 0.5)") == pytest.approx((0, 0, 255, .5))
    assert parse_color("hsl(360, 100%, 50%)") == pytest.approx((255, 0, 0, 1))


@pytest.mark.parametrize("text", [
    "", "none", "red", "#12", "#12345", "#ggg", "#ff ff ff", "rgb(0,0)",
    "rgb(0,0,0,0)", "rgba(0,0,0)", "rgb(256,0,0)", "rgb(-1,0,0)",
    "rgb(0%,0,0)",
    "rgba(0,0,0,2)", "rgba(0,0,0,-.1)", "hsl(0,2,3)",
    "hsl(0,101%,50%)", "hsl(0,-1%,50%)", "hsl(0,50%,50%,1)",
])
def test_invalid_colors_are_rejected(text):
    with pytest.raises(ColorError):
        parse_color(text)


def test_alpha_compositing_and_zero_alpha():
    assert over((255, 255, 255, .5), (0, 0, 0)) == pytest.approx((127.5, 127.5, 127.5))
    assert over((9, 8, 7, 0), (1, 2, 3)) == (1, 2, 3)
    assert over((9, 8, 7, 1), (1, 2, 3)) == (9, 8, 7)


def test_mix_and_luminance():
    assert mix((0, 0, 0, 1), (255, 255, 255, .5), .5) == (127.5, 127.5, 127.5, .75)
    assert relative_luminance((0, 0, 0)) == 0
    assert relative_luminance((255, 255, 255)) == 1
    with pytest.raises(ColorError):
        mix((0, 0, 0, 1), (1, 1, 1, 1), 1.1)


def test_uppercase_float_and_range_forms():
    assert parse_color(" RGB(1.5, 2.5, 3.5) ") == (1.5, 2.5, 3.5, 1)
    assert parse_color("HSLA(-120DEG, 100%, 50%, 100%)") == pytest.approx((0, 0, 255, 1))
    with pytest.raises(ColorError):
        relative_luminance((-1, 0, 0))
    with pytest.raises(ColorError):
        relative_luminance((math.nan, 0, 0))
