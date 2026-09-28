import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from color_studio import colors as C  # noqa: E402


@pytest.mark.parametrize("text, expected", [
    ("#abc", "#aabbcc"), ("ABC", "#aabbcc"), ("#AaBbCc", "#aabbcc"), (" #102030 ", "#102030"),
])
def test_normalize_hex(text, expected):
    assert C.normalize_hex(text) == expected


@pytest.mark.parametrize("bad", ["", "#12", "#12345g", "red", None, 0x123456])
def test_normalize_hex_rejects(bad):
    with pytest.raises(C.ColorError):
        C.normalize_hex(bad)


def test_hex_round_trip_through_every_space():
    for h in ["#000000", "#ffffff", "#ff0000", "#00ff00", "#0000ff", "#1f77b4", "#7f7f7f", "#e8622a"]:
        assert C.rgb_to_hex(C.hex_to_rgb(h)) == h
        assert C.oklab_to_hex(C.hex_to_oklab(h)) == h
        assert C.oklch_to_hex(C.hex_to_oklch(h)) == h
        assert C.rgb_to_hex(C.hsv_to_rgb(C.rgb_to_hsv(C.hex_to_rgb(h)))) == h


def test_oklab_reference_values():
    # Ottosson の定義による既知の値
    np.testing.assert_allclose(C.hex_to_oklab("#ffffff"), [1.0, 0.0, 0.0], atol=1e-4)
    np.testing.assert_allclose(C.hex_to_oklab("#000000"), [0.0, 0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(C.hex_to_oklab("#ff0000"), [0.62796, 0.22486, 0.12585], atol=1e-4)
    np.testing.assert_allclose(C.hex_to_oklab("#0000ff"), [0.45201, -0.03246, -0.31153], atol=1e-4)


def test_oklab_accepts_arrays():
    rgb = np.array([[[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]])
    lab = C.rgb_to_oklab(rgb)
    assert lab.shape == (1, 2, 3)
    np.testing.assert_allclose(C.oklab_to_rgb(lab), rgb, atol=1e-6)


def test_gray_has_zero_chroma():
    lch = C.hex_to_oklch("#808080")
    assert lch[1] == pytest.approx(0.0, abs=1e-6)


def test_out_of_gamut_is_brought_in_keeping_hue():
    # 明るくて非常に鮮やかな青緑は sRGB の外
    lch = np.array([0.8, 0.35, 190.0])
    assert not C.in_gamut(C.oklab_to_rgb(C.oklch_to_oklab(lch)))
    rgb = C.oklab_to_rgb_in_gamut(C.oklch_to_oklab(lch))
    assert C.in_gamut(rgb)
    back = C.oklab_to_oklch(C.rgb_to_oklab(rgb))
    assert back[0] == pytest.approx(0.8, abs=0.01)
    assert back[2] == pytest.approx(190.0, abs=2.0)
    assert back[1] < 0.35
