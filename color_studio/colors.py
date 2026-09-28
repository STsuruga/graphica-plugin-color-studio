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
_XYZ_FROM_LINEAR = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
])
_D65_WHITE = np.array([0.95047, 1.0, 1.08883])

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


def rgb_to_cielab(rgb):
    """CIE L*a*b*(D65)。CIEDE2000 の入力に使う。"""
    xyz = srgb_to_linear(rgb) @ _XYZ_FROM_LINEAR.T / _D65_WHITE
    delta = 6 / 29
    f = np.where(xyz > delta ** 3, np.cbrt(xyz), xyz / (3 * delta ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def delta_e_2000(lab1, lab2):
    """CIEDE2000(kL = kC = kH = 1)。Sharma, Wu, Dalal (2005) の式。"""
    L1, a1, b1 = (float(v) for v in lab1)
    L2, a2, b2 = (float(v) for v in lab2)
    c_bar = (np.hypot(a1, b1) + np.hypot(a2, b2)) / 2
    g = 0.5 * (1 - np.sqrt(c_bar ** 7 / (c_bar ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0 if c1p else 0.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0 if c2p else 0.0

    dL = L2 - L1
    dC = c2p - c1p
    if c1p * c2p == 0:
        dh = 0.0
    elif abs(h2p - h1p) <= 180:
        dh = h2p - h1p
    elif h2p - h1p > 180:
        dh = h2p - h1p - 360
    else:
        dh = h2p - h1p + 360
    dH = 2 * np.sqrt(c1p * c2p) * np.sin(np.radians(dh / 2))

    L_bar = (L1 + L2) / 2
    c_bar_p = (c1p + c2p) / 2
    if c1p * c2p == 0:
        h_bar = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        h_bar = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        h_bar = (h1p + h2p + 360) / 2
    else:
        h_bar = (h1p + h2p - 360) / 2

    t = (1 - 0.17 * np.cos(np.radians(h_bar - 30)) + 0.24 * np.cos(np.radians(2 * h_bar))
         + 0.32 * np.cos(np.radians(3 * h_bar + 6)) - 0.20 * np.cos(np.radians(4 * h_bar - 63)))
    d_theta = 30 * np.exp(-(((h_bar - 275) / 25) ** 2))
    r_c = 2 * np.sqrt(c_bar_p ** 7 / (c_bar_p ** 7 + 25.0 ** 7))
    s_l = 1 + 0.015 * (L_bar - 50) ** 2 / np.sqrt(20 + (L_bar - 50) ** 2)
    s_c = 1 + 0.045 * c_bar_p
    s_h = 1 + 0.015 * c_bar_p * t
    r_t = -np.sin(np.radians(2 * d_theta)) * r_c
    return float(np.sqrt((dL / s_l) ** 2 + (dC / s_c) ** 2 + (dH / s_h) ** 2
                         + r_t * (dC / s_c) * (dH / s_h)))


def delta_e_hex(hex1, hex2):
    return delta_e_2000(rgb_to_cielab(hex_to_rgb(hex1)), rgb_to_cielab(hex_to_rgb(hex2)))
