"""色空間の変換と色差。Qt にも Graphica 本体にも依存しない。

RGB は 0〜1 の sRGB(ガンマ補正済み)。配列を受ける関数は形 (..., 3) を受け、同じ形で返す。
OKLab / OKLCH は Björn Ottosson の定義、OKLCH と HSV の色相は度(0〜360)。
"""
import colorsys
import re

import numpy as np

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

_LMS_FROM_LINEAR = np.array([
    [0.4122214708, 0.5363325363, 0.0514459929],
    [0.2119034982, 0.6806995451, 0.1073969566],
    [0.0883024619, 0.2817188376, 0.6299787005],
])
_OKLAB_FROM_LMS = np.array([
    [0.2104542553, 0.7936177850, -0.0040720468],
    [1.9779984951, -2.4285922050, 0.4505937099],
    [0.0259040371, 0.7827717662, -0.8086757660],
])
_LMS_FROM_OKLAB = np.array([
    [1.0, 0.3963377774, 0.2158037573],
    [1.0, -0.1055613458, -0.0638541728],
    [1.0, -0.0894841775, -1.2914855480],
])
_LINEAR_FROM_LMS = np.array([
    [4.0767416621, -3.3077115913, 0.2309699292],
    [-1.2684380046, 2.6097574011, -0.3413193965],
    [-0.0041960863, -0.7034186147, 1.7076147010],
])

# 色域の判定の許容幅。変換の丸めで 1.0000001 などになるのを色域外と見なさない。
_GAMUT_EPS = 1e-6
# これ以内のはみ出しは計算誤差とみなして切り詰める(彩度を下げると色相がわずかに動くため)。
_CLIP_TOLERANCE = 2e-3


class ColorError(ValueError):
    """メッセージはそのまま利用者に表示する。"""


def normalize_hex(text):
    """'#abc' / 'ABC' / '#AaBbCc' などを小文字の '#rrggbb' にする。"""
    if not isinstance(text, str):
        raise ColorError(f"色コードは文字列で指定してください: {text!r}")
    m = _HEX_RE.match(text.strip())
    if not m:
        raise ColorError(f"色コードの形が正しくありません: {text!r}(#rrggbb の形で指定してください)")
    digits = m.group(1)
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return "#" + digits.lower()


def hex_to_rgb(text):
    digits = normalize_hex(text)[1:]
    return np.array([int(digits[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def rgb_to_hex(rgb):
    values = np.clip(np.asarray(rgb, dtype=float), 0.0, 1.0)
    return "#" + "".join(f"{int(round(v * 255)):02x}" for v in values)


def srgb_to_linear(rgb):
    c = np.asarray(rgb, dtype=float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(linear):
    c = np.asarray(linear, dtype=float)
    # 負の値は色域外。べき乗の前に符号を分けて NaN を避ける。
    a = np.abs(c)
    encoded = np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - 0.055)
    return np.sign(c) * encoded


def linear_to_oklab(linear):
    lms = np.asarray(linear, dtype=float) @ _LMS_FROM_LINEAR.T
    return np.cbrt(lms) @ _OKLAB_FROM_LMS.T


def oklab_to_linear(lab):
    lms = (np.asarray(lab, dtype=float) @ _LMS_FROM_OKLAB.T) ** 3
    return lms @ _LINEAR_FROM_LMS.T


def rgb_to_oklab(rgb):
    return linear_to_oklab(srgb_to_linear(rgb))


def oklab_to_rgb(lab):
    """色域の外は丸めない(in_gamut で判定、oklab_to_rgb_in_gamut で色域に収める)。"""
    return linear_to_srgb(oklab_to_linear(lab))


def oklab_to_oklch(lab):
    lab = np.asarray(lab, dtype=float)
    chroma = np.hypot(lab[..., 1], lab[..., 2])
    hue = np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360.0
    return np.stack([lab[..., 0], chroma, hue], axis=-1)


def oklch_to_oklab(lch):
    lch = np.asarray(lch, dtype=float)
    h = np.radians(lch[..., 2])
    return np.stack([lch[..., 0], lch[..., 1] * np.cos(h), lch[..., 1] * np.sin(h)], axis=-1)


def rgb_to_hsv(rgb):
    """(h 度, s 0〜1, v 0〜1)。"""
    h, s, v = colorsys.rgb_to_hsv(*np.clip(np.asarray(rgb, dtype=float), 0.0, 1.0))
    return np.array([h * 360.0, s, v])


def hsv_to_rgb(hsv):
    h, s, v = (float(x) for x in hsv)
    return np.array(colorsys.hsv_to_rgb((h % 360.0) / 360.0, min(max(s, 0.0), 1.0), min(max(v, 0.0), 1.0)))


def in_gamut(rgb):
    c = np.asarray(rgb, dtype=float)
    return bool(np.all((c >= -_GAMUT_EPS) & (c <= 1.0 + _GAMUT_EPS)))


def oklab_to_rgb_in_gamut(lab):
    """sRGB の外にある色は、明度と色相を保ったまま彩度を下げて収める(単色)。"""
    lab = np.asarray(lab, dtype=float)
    rgb = oklab_to_rgb(lab)
    if np.all((rgb >= -_CLIP_TOLERANCE) & (rgb <= 1.0 + _CLIP_TOLERANCE)):
        return np.clip(rgb, 0.0, 1.0)
    lightness = min(max(float(lab[0]), 0.0), 1.0)
    _, chroma, hue = oklab_to_oklch(lab)
    lo, hi = 0.0, float(chroma)
    for _ in range(30):
        mid = (lo + hi) / 2
        if in_gamut(oklab_to_rgb(oklch_to_oklab([lightness, mid, hue]))):
            lo = mid
        else:
            hi = mid
    return np.clip(oklab_to_rgb(oklch_to_oklab([lightness, lo, hue])), 0.0, 1.0)


def hex_to_oklab(text):
    return rgb_to_oklab(hex_to_rgb(text))


def oklab_to_hex(lab):
    return rgb_to_hex(oklab_to_rgb_in_gamut(lab))


def hex_to_oklch(text):
    return oklab_to_oklch(hex_to_oklab(text))


def oklch_to_hex(lch):
    return oklab_to_hex(oklch_to_oklab(lch))


