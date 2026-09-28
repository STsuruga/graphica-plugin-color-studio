import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from color_studio import colors as C  # noqa: E402
from color_studio import cvd  # noqa: E402


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


# Sharma, Wu, Dalal (2005) の CIEDE2000 検証データから
@pytest.mark.parametrize("lab1, lab2, expected", [
    ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
    ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
    ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
    ((50.0, 2.49, -0.001), (50.0, -2.49, 0.0009), 7.1792),
    ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
])
def test_delta_e_2000_matches_reference(lab1, lab2, expected):
    assert C.delta_e_2000(lab1, lab2) == pytest.approx(expected, abs=1e-4)
    assert C.delta_e_2000(lab2, lab1) == pytest.approx(expected, abs=1e-4)


def test_cielab_of_white_and_red():
    np.testing.assert_allclose(C.rgb_to_cielab(C.hex_to_rgb("#ffffff")), [100.0, 0.0, 0.0], atol=0.01)
    np.testing.assert_allclose(C.rgb_to_cielab(C.hex_to_rgb("#ff0000")), [53.24, 80.09, 67.20], atol=0.05)


def test_cvd_matrices_keep_grays():
    for m in cvd.CVD_MATRICES.values():
        np.testing.assert_allclose(m.sum(axis=1), 1.0, atol=1e-9)
    for t in cvd.CVD_MATRICES:
        for g in ["#000000", "#808080", "#ffffff"]:
            assert cvd.simulate_hex(g, t) == g


def test_simulate_hex_normal_returns_normalized():
    assert cvd.simulate_hex("#ABC", None) == "#aabbcc"
    with pytest.raises(ValueError):
        cvd.simulate_hex("#ffffff", "achromatopsia")


def test_red_and_green_are_confusable_for_red_green_types_only():
    colors = ["#c0504d", "#9bbb59"]
    assert cvd.confusable_pairs(colors, None) == []
    assert cvd.confusable_pairs(colors, "tritanopia") == []
    for t in ("protanopia", "deuteranopia"):
        assert [(i, j) for i, j, _ in cvd.confusable_pairs(colors, t)] == [(0, 1)]
    pairs = cvd.confusable_pairs(colors, "deuteranopia")
    assert cvd.describe_pairs(pairs, "deuteranopia")[0].startswith("D型(2型): 1 と 2 が見分けにくい")


def test_adjacent_only_skips_distant_pairs():
    colors = ["#c0504d", "#1f77b4", "#9bbb59"]
    assert cvd.confusable_pairs(colors, "deuteranopia", adjacent_only=True) == []
    assert [(i, j) for i, j, _ in cvd.confusable_pairs(colors, "deuteranopia", adjacent_only=False)] == [(0, 2)]


def test_confusion_report_covers_every_mode():
    report = cvd.confusion_report(["#000000", "#ffffff"])
    assert set(report) == {None, "protanopia", "deuteranopia", "tritanopia"}
    assert all(v == [] for v in report.values())
