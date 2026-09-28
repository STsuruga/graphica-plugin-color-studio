"""色覚の見え方の近似と、見分けにくい色の組の判定。Qt にも Graphica 本体にも依存しない。

行列は Graphica 本体の色覚シミュレーションと同じもの(Brettel / Viénot を簡略化し、ガンマ補正済みの
sRGB に直接掛ける近似)。本体のプレビューと同じ見え方にするため、線形化せずにそのまま掛ける。
本体の内部は import できないので写しを持つ。
"""
import numpy as np

from .colors import delta_e_hex, hex_to_rgb, rgb_to_hex

CVD_MATRICES = {
    "protanopia": np.array([
        [0.567, 0.433, 0.000],
        [0.558, 0.442, 0.000],
        [0.000, 0.242, 0.758],
    ]),
    "deuteranopia": np.array([
        [0.625, 0.375, 0.000],
        [0.700, 0.300, 0.000],
        [0.000, 0.300, 0.700],
    ]),
    "tritanopia": np.array([
        [0.950, 0.050, 0.000],
        [0.000, 0.433, 0.567],
        [0.000, 0.475, 0.525],
    ]),
}

CVD_LABELS = {
    None: "通常",
    "protanopia": "P型(1型)",
    "deuteranopia": "D型(2型)",
    "tritanopia": "T型(3型)",
}

DEFAULT_DELTA_E_THRESHOLD = 10.0


def simulate_hex(hex_color, cvd_type):
    """cvd_type が None なら元の色を '#rrggbb' に整えて返す。"""
    rgb = hex_to_rgb(hex_color)
    if cvd_type is None:
        return rgb_to_hex(rgb)
    if cvd_type not in CVD_MATRICES:
        raise ValueError(f"未知の色覚タイプです: {cvd_type}")
    return rgb_to_hex(CVD_MATRICES[cvd_type] @ rgb)


def simulate_rgb_array(rgb, cvd_type):
    """形 (..., 3)、0〜1 の RGB 配列を変換する(ホイールの描画用)。"""
    rgb = np.asarray(rgb, dtype=float)
    if cvd_type is None:
        return rgb
    return np.clip(rgb @ CVD_MATRICES[cvd_type].T, 0.0, 1.0)


def confusable_pairs(colors, cvd_type=None, threshold=DEFAULT_DELTA_E_THRESHOLD, adjacent_only=True):
    """
    見分けにくい色の組を返す。

    Returns:
        list[tuple[int, int, float]]: (i, j, ΔE)。i < j、ΔE は cvd_type の見え方での CIEDE2000。
    """
    seen = [simulate_hex(c, cvd_type) for c in colors]
    pairs = ([(i, i + 1) for i in range(len(seen) - 1)] if adjacent_only
             else [(i, j) for i in range(len(seen)) for j in range(i + 1, len(seen))])
    result = []
    for i, j in pairs:
        de = delta_e_hex(seen[i], seen[j])
        if de < threshold:
            result.append((i, j, de))
    return result


def confusion_report(colors, threshold=DEFAULT_DELTA_E_THRESHOLD, adjacent_only=True):
    """通常と P / D / T 型のそれぞれで confusable_pairs を求める。{cvd_type: pairs}"""
    return {t: confusable_pairs(colors, t, threshold, adjacent_only) for t in CVD_LABELS}


def describe_pairs(pairs, cvd_type, threshold=DEFAULT_DELTA_E_THRESHOLD):
    """警告の文面。色の番号は 1 始まり。"""
    label = CVD_LABELS[cvd_type]
    return [f"{label}: {i + 1} と {j + 1} が見分けにくい(ΔE {de:.1f} < {threshold:g})" for i, j, de in pairs]
