"""カラーホイールと配色ルール。Qt にも Graphica 本体にも依存しない。

ホイール上の点は (角度 度, 彩度 0〜1, 明度 0〜1)。角度の意味はホイールの種類で変わる:
RYB では絵の具の色相環の角度(赤 0・黄 120・青 240)、RGB では HSV の色相そのもの。
"""
from dataclasses import dataclass, field, replace

import numpy as np

from . import colors as C

WHEELS = ("ryb", "rgb")
WHEEL_LABELS = {"ryb": "RYB(絵の具の色相環)", "rgb": "RGB(光の色相環)"}

RULES = ("custom", "analogous", "monochromatic", "triad", "complementary",
         "split_complementary", "square", "compound", "shades")
RULE_LABELS = {
    "custom": "カスタム",
    "analogous": "類似色",
    "monochromatic": "モノクロマティック",
    "triad": "トライアド",
    "complementary": "補色",
    "split_complementary": "スプリットコンプリメンタリー",
    "square": "スクエア",
    "compound": "コンパウンド",
    "shades": "シェード",
}
MIN_COUNT, MAX_COUNT, DEFAULT_COUNT = 3, 10, 5

# RYB の角度 → RGB(HSV)の色相。Itten の12色相環でよく使われる色(赤 #fe2712 … 赤紫 #c21460)の色相に
# 合わせた区分線形の近似。RYB には標準の定義が無い。単調増加なので逆変換できる。
_RYB_ANCHORS = np.array([0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330, 360], dtype=float)
_RGB_ANCHORS = np.array([0, 22, 37, 47, 60, 83, 95, 197, 223, 250, 286, 333, 360], dtype=float)

_HUE_OFFSETS = {
    "triad": (0, 120, 240),
    "complementary": (0, 180),
    "split_complementary": (0, 150, 210),
    "square": (0, 90, 180, 270),
    "compound": (0, 30, 165, 195),
}
# 同じ色相を2周目以降に使うときの (彩度の倍率, 明度の倍率)。系列の色として隣と見分けやすいよう交互に明暗を振る。
_TONE_VARIANTS = ((1.0, 1.0), (0.5, 1.15), (1.0, 0.6), (0.3, 1.25), (0.8, 0.4))
_MONO_VARIANTS = ((1.0, 1.0), (0.5, 1.15), (1.0, 0.65), (0.25, 1.25), (0.8, 0.4),
                  (0.7, 0.85), (0.35, 0.75), (1.0, 0.3), (0.15, 1.3), (0.6, 0.55))
_ANALOGOUS_MAX_STEP = 30.0
_ANALOGOUS_SPAN = 120.0
_SHADES_DARKEST = 0.2


def ryb_to_rgb_hue(angle):
    return float(np.interp(float(angle) % 360.0, _RYB_ANCHORS, _RGB_ANCHORS))


def ryb_to_rgb_hues(angles):
    """配列版(ホイールの描画用)。"""
    return np.interp(np.asarray(angles, dtype=float) % 360.0, _RYB_ANCHORS, _RGB_ANCHORS)


def rgb_to_ryb_hue(hue):
    return float(np.interp(float(hue) % 360.0, _RGB_ANCHORS, _RYB_ANCHORS))


def wheel_to_hex(point, wheel="ryb"):
    angle, s, v = point
    hue = ryb_to_rgb_hue(angle) if wheel == "ryb" else float(angle) % 360.0
    return C.rgb_to_hex(C.hsv_to_rgb([hue, s, v]))


def hex_to_wheel(hex_color, wheel="ryb"):
    hue, s, v = C.rgb_to_hsv(C.hex_to_rgb(hex_color))
    angle = rgb_to_ryb_hue(hue) if wheel == "ryb" else float(hue)
    return (angle, float(s), float(v))


def _clamp01(x):
    return min(max(float(x), 0.0), 1.0)


def rule_points(rule, base, count):
    """
    Returns:
        tuple[list[tuple], int]: ホイール上の点の並びと、その中の基準の点の番号。
            並びは系列に割り当てる順。隣どうしが似すぎないよう、色相が巡回するように並べる。
    """
    angle, s, v = base
    n = int(count)
    if rule in _HUE_OFFSETS:
        offsets = _HUE_OFFSETS[rule]
        points = []
        for k in range(n):
            sm, vm = _TONE_VARIANTS[(k // len(offsets)) % len(_TONE_VARIANTS)]
            points.append(((angle + offsets[k % len(offsets)]) % 360.0, _clamp01(s * sm), _clamp01(v * vm)))
        return points, 0
    if rule == "analogous":
        step = min(_ANALOGOUS_MAX_STEP, _ANALOGOUS_SPAN / (n - 1))
        center = n // 2
        return [((angle + (k - center) * step) % 360.0, s, v) for k in range(n)], center
    if rule == "monochromatic":
        return [(angle, _clamp01(s * sm), _clamp01(v * vm)) for sm, vm in _MONO_VARIANTS[:n]], 0
    if rule == "shades":
        return [(angle, s, _clamp01(v * (1 - (1 - _SHADES_DARKEST) * k / (n - 1)))) for k in range(n)], 0
    raise ValueError(f"配色ルール {rule!r} は rule_points では扱いません。")


@dataclass(frozen=True)
class Harmony:
    """配色パレットの状態。変更はすべて新しい Harmony を返す(元に戻す / やり直しの履歴にそのまま積める)。"""
    rule: str = "analogous"
    count: int = DEFAULT_COUNT
    base: tuple = (0.0, 0.75, 0.9)
    wheel: str = "ryb"
    custom_points: tuple = field(default_factory=tuple)

    def __post_init__(self):
        if self.rule not in RULES:
            raise ValueError(f"未知の配色ルールです: {self.rule}")
        if self.wheel not in WHEELS:
            raise ValueError(f"未知のホイールです: {self.wheel}")
        if not MIN_COUNT <= int(self.count) <= MAX_COUNT:
            raise C.ColorError(f"色数は {MIN_COUNT}〜{MAX_COUNT} で指定してください。")
        object.__setattr__(self, "count", int(self.count))
        object.__setattr__(self, "base", _normalize_point(self.base))
        object.__setattr__(self, "custom_points", tuple(_normalize_point(p) for p in self.custom_points))
        if self.rule == "custom" and len(self.custom_points) != self.count:
            raise ValueError("カスタムでは点の数と色数が一致している必要があります。")

    def points(self):
        if self.rule == "custom":
            return list(self.custom_points)
        return rule_points(self.rule, self.base, self.count)[0]

    def base_index(self):
        return 0 if self.rule == "custom" else rule_points(self.rule, self.base, self.count)[1]

    def colors(self):
        return [wheel_to_hex(p, self.wheel) for p in self.points()]

    def base_color(self):
        return self.colors()[self.base_index()]

    def with_rule(self, rule):
        if rule == self.rule:
            return self
        if rule == "custom":
            return replace(self, rule=rule, custom_points=tuple(self.points()))
        base = self.custom_points[0] if self.rule == "custom" else self.base
        return replace(self, rule=rule, base=base, custom_points=())

    def with_count(self, count):
        count = int(count)
        if self.rule != "custom":
            return replace(self, count=count)
        pts = list(self.custom_points[:count])
        while len(pts) < count:
            a, s, v = pts[-1]
            pts.append(((a + 360.0 / count) % 360.0, s, v))
        return replace(self, count=count, custom_points=tuple(pts))

    def with_wheel(self, wheel):
        """ホイールを切り替えても色は変わらないよう、点の角度を変換する。"""
        if wheel == self.wheel:
            return self

        to_angle = rgb_to_ryb_hue if wheel == "ryb" else ryb_to_rgb_hue

        def convert(p):
            return (to_angle(p[0]),) + tuple(p[1:])
        return replace(self, wheel=wheel, base=convert(self.base),
                       custom_points=tuple(convert(p) for p in self.custom_points))

    def with_base_color(self, hex_color):
        point = hex_to_wheel(hex_color, self.wheel)
        if self.rule == "custom":
            pts = list(self.custom_points)
            pts[0] = point
            return replace(self, custom_points=tuple(pts))
        return replace(self, base=point)

    def with_brightness(self, v):
        """ホイールに無い明度の軸。全部の点を同じだけ動かす。"""
        if self.rule == "custom":
            return replace(self, custom_points=tuple((a, s, v) for a, s, _ in self.custom_points))
        a, s, _ = self.base
        return replace(self, base=(a, s, v))

    def with_colors(self, hex_colors):
        """画像から取った色などを、そのままカスタムの点にする。"""
        pts = tuple(hex_to_wheel(h, self.wheel) for h in hex_colors)
        return replace(self, rule="custom", count=len(pts), custom_points=pts)

    def move_point(self, index, angle, saturation):
        """
        ホイール上の点 index を (angle, saturation) に動かす。カスタムではその点だけ、
        それ以外のルールでは、動かした量だけ全部の点を回し、彩度も同じだけ変える。
        """
        points = self.points()
        a0, s0, v0 = points[index]
        if self.rule == "custom":
            pts = list(self.custom_points)
            pts[index] = (angle, saturation, v0)
            return replace(self, custom_points=tuple(pts))
        ba, bs, bv = self.base
        d_angle = float(angle) - a0
        # 彩度の倍率を掛けた点(トーンの変化形)を動かしても、基準の彩度へ同じ比で戻す。
        ratio = s0 / bs if bs > 0 else 1.0
        new_bs = saturation / ratio if ratio > 0 else saturation
        return replace(self, base=(ba + d_angle, _clamp01(new_bs), bv))

    def randomized(self, rng=None):
        rng = rng if rng is not None else np.random.default_rng()

        def random_point():
            return (float(rng.uniform(0, 360)), float(rng.uniform(0.45, 0.95)), float(rng.uniform(0.6, 0.97)))
        if self.rule == "custom":
            return replace(self, custom_points=tuple(random_point() for _ in range(self.count)))
        return replace(self, base=random_point())

    def to_dict(self):
        return {"rule": self.rule, "count": self.count, "base": list(self.base), "wheel": self.wheel,
                "custom_points": [list(p) for p in self.custom_points]}

    @classmethod
    def from_dict(cls, data):
        try:
            return cls(rule=data.get("rule", "analogous"), count=data.get("count", DEFAULT_COUNT),
                       base=tuple(data.get("base", (0.0, 0.75, 0.9))), wheel=data.get("wheel", "ryb"),
                       custom_points=tuple(tuple(p) for p in data.get("custom_points", ())))
        except (TypeError, ValueError) as e:
            raise C.ColorError("配色パレットのデータが読めません。") from e


def _normalize_point(p):
    a, s, v = (float(x) for x in p)
    return (a % 360.0, _clamp01(s), _clamp01(v))
