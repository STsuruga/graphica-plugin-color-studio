import os
import sys
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from color_studio import colors as C  # noqa: E402
from color_studio.extract import dominant_colors  # noqa: E402
from color_studio.gradient import SPACES, Gradient, Stop, interpolate  # noqa: E402
from color_studio.harmony import (  # noqa: E402
    RULES, Harmony, hex_to_wheel, rgb_to_ryb_hue, ryb_to_rgb_hue, wheel_to_hex,
)


def G(*pairs, space="oklab", count=5):
    return Gradient(stops=tuple(Stop(p, c) for p, c in pairs), space=space, count=count)


# ---------------------------------------------------------------- gradient

@pytest.mark.parametrize("space", SPACES)
def test_samples_start_and_end_on_the_stops(space):
    g = G((0.0, "#0d47a1"), (1.0, "#f4e06a"), space=space, count=9)
    s = g.sample()
    assert len(s) == 9
    assert s[0] == "#0d47a1" and s[-1] == "#f4e06a"


def test_count_two_and_thirty_two():
    g = G((0, "#000000"), (1, "#ffffff"))
    assert g.sample(2) == ["#000000", "#ffffff"]
    assert len(g.sample(32)) == 32


@pytest.mark.parametrize("count", [1, 33])
def test_count_out_of_range_is_rejected(count):
    with pytest.raises(C.ColorError):
        G((0, "#000000"), (1, "#ffffff"), count=count)


def test_needs_two_stops():
    with pytest.raises(C.ColorError):
        Gradient(stops=(Stop(0, "#000000"),))


def test_oklab_midpoint_is_less_muddy_than_rgb():
    # 青→黄の中間は、RGB では灰色に近づき、OKLab では彩度が残る
    mid_rgb = interpolate("#0000ff", "#ffff00", 0.5, "rgb")
    mid_oklab = interpolate("#0000ff", "#ffff00", 0.5, "oklab")
    assert C.hex_to_oklch(mid_oklab)[1] > C.hex_to_oklch(mid_rgb)[1] - 1e-9
    assert mid_rgb == "#808080"


def test_black_to_white_in_oklab_is_perceptually_even():
    s = G((0, "#000000"), (1, "#ffffff"), count=5).sample()
    lightness = [C.hex_to_oklab(h)[0] for h in s]
    np.testing.assert_allclose(np.diff(lightness), 0.25, atol=0.01)


def test_hue_takes_the_short_arc():
    # 赤(29°付近)→ 赤紫(330°付近)は 0° をまたぐ短い弧を通り、緑を経由しない
    for space in ("oklch", "hsv"):
        mid = interpolate("#ff0000", "#ff00aa", 0.5, space)
        r, g, b = C.hex_to_rgb(mid)
        assert r > 0.9 and g < 0.1, (space, mid)


def test_gray_endpoint_keeps_the_other_hue():
    mid = interpolate("#808080", "#ff0000", 0.5, "oklch")
    r, g, b = C.hex_to_rgb(mid)
    assert r > g and r > b


def test_stops_are_sorted_for_sampling_but_order_is_kept():
    g = G((1.0, "#ffffff"), (0.0, "#000000"))
    assert g.sample(2) == ["#000000", "#ffffff"]
    assert g.stops[0].color == "#ffffff"
    assert [s.color for s in g.with_stops_sorted().stops] == ["#000000", "#ffffff"]


def test_three_stops_pass_through_the_middle_one():
    g = G((0, "#ff0000"), (0.5, "#00ff00"), (1, "#0000ff"), count=3)
    assert g.sample() == ["#ff0000", "#00ff00", "#0000ff"]


def test_equal_positions_make_a_hard_edge():
    g = G((0, "#000000"), (0.5, "#000000"), (0.5, "#ffffff"), (1, "#ffffff"))
    assert g.color_at(0.49) == "#000000"
    assert g.color_at(0.5) == "#ffffff"


def test_reverse():
    g = G((0, "#ff0000"), (0.25, "#00ff00"), (1, "#0000ff"), count=6)
    assert g.reversed().sample() == list(reversed(g.sample()))


def test_add_remove_and_even_spacing():
    g = G((0, "#000000"), (1, "#ffffff"))
    g2 = g.with_stop_added()
    assert len(g2.stops) == 3
    assert g2.stops[-1].position == 0.5
    # 途中の色で足すので見た目は変わらない(足した点の HEX への丸めの分だけずれる)
    for a, b in zip(g2.sample(5), g.sample(5)):
        assert C.delta_e_hex(a, b) < 0.5
    assert len(g2.with_stop_removed(2).stops) == 2
    with pytest.raises(C.ColorError):
        g.with_stop_removed(0)
    g3 = G((0, "#000000"), (0.1, "#ff0000"), (0.2, "#ffffff"), (1, "#0000ff")).with_stops_evenly_spaced()
    assert [s.position for s in g3.stops] == pytest.approx([0, 1 / 3, 2 / 3, 1])


def test_positions_are_clamped_and_colors_normalized():
    g = G((-0.5, "#ABC"), (1.5, "fff"))
    assert g.stops == (Stop(0.0, "#aabbcc"), Stop(1.0, "#ffffff"))


def test_dict_round_trip():
    g = G((0, "#123456"), (0.3, "#abcdef"), (1, "#fedcba"), space="hsv", count=11)
    assert Gradient.from_dict(g.to_dict()) == g
    with pytest.raises(C.ColorError):
        Gradient.from_dict({"stops": [{"position": 0}]})


# ---------------------------------------------------------------- harmony

def test_ryb_mapping_is_monotone_and_invertible():
    angles = np.linspace(0, 359.9, 500)
    hues = [ryb_to_rgb_hue(a) for a in angles]
    assert all(np.diff(hues) > 0)
    for a in angles:
        assert rgb_to_ryb_hue(ryb_to_rgb_hue(a)) == pytest.approx(a, abs=1e-9)


def test_ryb_complement_of_red_is_green():
    red = hex_to_wheel("#ff0000", "ryb")
    comp = wheel_to_hex(((red[0] + 180) % 360, 1.0, 1.0), "ryb")
    h, s, v = C.rgb_to_hsv(C.hex_to_rgb(comp))
    assert 80 < h < 140  # 緑
    comp_rgb = wheel_to_hex(((hex_to_wheel("#ff0000", "rgb")[0] + 180) % 360, 1.0, 1.0), "rgb")
    assert comp_rgb == "#00ffff"  # RGB の色相環ではシアン


@pytest.mark.parametrize("rule", RULES)
@pytest.mark.parametrize("count", [3, 5, 10])
def test_every_rule_gives_count_distinct_colors(rule, count):
    h = Harmony(rule="analogous", count=count, base=(10, 0.8, 0.85)).with_rule(rule)
    cols = h.colors()
    assert len(cols) == count
    assert len(set(cols)) == count, (rule, cols)
    assert 0 <= h.base_index() < count


@pytest.mark.parametrize("rule, offsets", [
    ("complementary", [0, 180, 0]),
    ("triad", [0, 120, 240]),
    ("split_complementary", [0, 150, 210]),
    ("square", [0, 90, 180, 270]),
])
def test_rule_angles(rule, offsets):
    h = Harmony(rule=rule, count=len(offsets), base=(40, 0.8, 0.9))
    assert [round(p[0]) for p in h.points()] == [(40 + o) % 360 for o in offsets]


def test_analogous_is_centered_on_the_base():
    h = Harmony(rule="analogous", count=5, base=(100, 0.8, 0.9))
    assert [p[0] for p in h.points()] == [40, 70, 100, 130, 160]
    assert h.base_index() == 2


def test_shades_keep_hue_and_saturation_and_darken():
    pts = Harmony(rule="shades", count=5, base=(200, 0.7, 1.0)).points()
    assert {(a, s) for a, s, _ in pts} == {(200, 0.7)}
    vs = [v for *_, v in pts]
    assert vs == sorted(vs, reverse=True) and vs[-1] == pytest.approx(0.2)


def test_dragging_one_point_rotates_all():
    h = Harmony(rule="triad", count=3, base=(0, 0.8, 0.9))
    moved = h.move_point(1, 150, 0.8)  # 120° の点を 150° へ
    assert [round(p[0]) for p in moved.points()] == [30, 150, 270]


def test_dragging_outward_changes_every_saturation():
    h = Harmony(rule="complementary", count=3, base=(0, 0.5, 0.9))
    moved = h.move_point(1, 180, 0.9)
    assert [p[1] for p in moved.points()] == pytest.approx([0.9, 0.9, 0.45])  # 3色目は2周目で彩度 0.5 倍


def test_custom_moves_only_that_point():
    h = Harmony(rule="triad", count=3, base=(0, 0.8, 0.9)).with_rule("custom")
    moved = h.move_point(1, 200, 0.3)
    assert moved.points()[0] == h.points()[0]
    assert moved.points()[1][:2] == (200, 0.3)


def test_switching_wheel_keeps_the_base_color():
    # ルールの角度はホイールの角度で測るので、基準以外の色はホイールによって変わる(RYB の補色 ≠ RGB の補色)
    for rule in RULES:
        h = Harmony(rule="analogous", count=5, base=(77, 0.6, 0.8)).with_rule(rule)
        assert h.with_wheel("rgb").base_color() == h.base_color()
        assert h.with_wheel("rgb").with_wheel("ryb").colors() == h.colors()


def test_switching_wheel_keeps_every_custom_color():
    h = Harmony(rule="triad", count=5, base=(77, 0.6, 0.8)).with_rule("custom")
    assert h.with_wheel("rgb").colors() == h.colors()


def test_base_color_and_brightness():
    h = Harmony(rule="complementary", count=4).with_base_color("#e8622a")
    assert h.base_color() == "#e8622a"
    dimmed = h.with_brightness(0.5)
    assert dimmed.points()[dimmed.base_index()][2] == pytest.approx(0.5)
    assert dimmed.points()[dimmed.base_index()][:2] == h.points()[h.base_index()][:2]


def test_count_change_for_custom_extends_and_truncates():
    h = Harmony(rule="triad", count=3).with_rule("custom")
    assert len(h.with_count(6).points()) == 6
    assert h.with_count(6).with_count(3).points() == h.points()


def test_with_colors_makes_a_custom_palette_of_those_colors():
    cols = ["#264653", "#2a9d8f", "#e9c46a", "#f4a261", "#e76f51"]
    h = Harmony().with_colors(cols)
    assert h.rule == "custom" and h.colors() == cols


def test_random_is_reproducible_with_a_seed():
    h = Harmony(rule="triad", count=5)
    a = h.randomized(np.random.default_rng(1)).colors()
    b = h.randomized(np.random.default_rng(1)).colors()
    assert a == b and a != h.colors()


def test_harmony_dict_round_trip():
    h = Harmony(rule="compound", count=7, base=(12.5, 0.4, 0.7), wheel="rgb")
    assert Harmony.from_dict(h.to_dict()) == h
    c = h.with_rule("custom")
    assert Harmony.from_dict(c.to_dict()) == c


# ---------------------------------------------------------------- extract

def _blocks(colors, size=40):
    rows = [np.tile(np.array(C.hex_to_rgb(c)) * 255, (size * (i + 1), size, 1)) for i, c in enumerate(colors)]
    width = size
    return np.concatenate([r.reshape(-1, width, 3) for r in rows], axis=0).astype(np.uint8)


def test_recovers_block_colors_largest_first():
    img = _blocks(["#264653", "#e9c46a", "#e76f51"])  # 面積は 1:2:3
    rng = np.random.default_rng(0)
    noisy = np.clip(img.astype(int) + rng.integers(-4, 5, img.shape), 0, 255).astype(np.uint8)
    got = dominant_colors(noisy, 3)
    for g, want in zip(got, ["#e76f51", "#e9c46a", "#264653"]):
        assert C.delta_e_hex(g, want) < 2.0


def test_fewer_distinct_colors_than_k():
    img = _blocks(["#000000", "#ffffff"])
    assert sorted(dominant_colors(img, 6)) == ["#000000", "#ffffff"]


def test_same_seed_same_result_and_float_input():
    rng = np.random.default_rng(3)
    img = rng.random((80, 80, 3))
    assert dominant_colors(img, 5, seed=7) == dominant_colors(img, 5, seed=7)


def test_transparent_pixels_are_ignored():
    img = _blocks(["#ff0000", "#0000ff"])
    alpha = np.full(img.shape[:2], 255)
    alpha[: img.shape[0] // 3] = 0  # 赤の帯(上1/3)を透明に
    assert dominant_colors(img, 2, alpha=alpha) == ["#0000ff"]
    with pytest.raises(C.ColorError):
        dominant_colors(img, 2, alpha=np.zeros(img.shape[:2]))


def test_large_image_is_fast_enough_for_the_gui_thread():
    rng = np.random.default_rng(0)
    img = (rng.random((256, 256, 3)) * 255).astype(np.uint8)
    t0 = time.perf_counter()
    dominant_colors(img, 10)
    elapsed = time.perf_counter() - t0
    print(f"k-means 256x256, k=10: {elapsed:.3f}s")
    assert elapsed < 2.0


def test_kmeans_separates_well_spread_clusters():
    from color_studio.extract import kmeans
    rng = np.random.default_rng(0)
    centers = np.array([[0.2, 0.0, 0.0], [0.5, 0.1, 0.1], [0.8, -0.1, 0.05]])
    data = np.concatenate([c + rng.normal(0, 0.01, (200, 3)) for c in centers])
    got, labels = kmeans(data, 3, np.random.default_rng(1))
    assert sorted(np.bincount(labels).tolist()) == [200, 200, 200]
    for c in centers:
        assert np.min(np.linalg.norm(got - c, axis=1)) < 0.01


def test_plugin_code_does_not_import_scipy():
    # Graphica v2.0.0 の exe には scipy.cluster が入っていない(本体の exe で確かめた)。使うと exe でだけ
    # ウィンドウが開かなくなる。scipy のほかの部分も exe では本体が使う範囲しか入らないので、scipy 自体を使わない。
    import pathlib
    import re
    pattern = re.compile(r"^\s*(from|import)\s+scipy(\.cluster)?\b", re.MULTILINE)
    root = pathlib.Path(__file__).resolve().parent.parent / "color_studio"
    offenders = [p.name for p in root.glob("*.py") if pattern.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
