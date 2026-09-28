"""グラデーションのモデルと、等間隔の色の抽出。Qt にも Graphica 本体にも依存しない。"""
import bisect
from dataclasses import dataclass, field, replace

import numpy as np

from . import colors as C

SPACES = ("oklab", "oklch", "rgb", "hsv")
SPACE_LABELS = {
    "oklab": "OKLab(知覚的に均一・推奨)",
    "oklch": "OKLCH(色相を回る)",
    "rgb": "RGB(単純・中間がくすむ)",
    "hsv": "HSV(色相を回る)",
}
MIN_COUNT, MAX_COUNT = 2, 32
MIN_STOPS = 2
# 彩度がこれ未満の色は色相が定まらないので、色相の補間では相手の色相を使う。
_ACHROMATIC_OKLCH = 1e-3
_ACHROMATIC_HSV = 1e-3


@dataclass(frozen=True)
class Stop:
    position: float
    color: str


@dataclass(frozen=True)
class Gradient:
    stops: tuple = field(default_factory=lambda: (Stop(0.0, "#0d47a1"), Stop(1.0, "#f4e06a")))
    space: str = "oklab"
    count: int = 7

    def __post_init__(self):
        if len(self.stops) < MIN_STOPS:
            raise C.ColorError(f"色の点(ストップ)は {MIN_STOPS} 個以上必要です。")
        if self.space not in SPACES:
            raise C.ColorError(f"未知の色空間です: {self.space}")
        if not MIN_COUNT <= int(self.count) <= MAX_COUNT:
            raise C.ColorError(f"抽出する色の数は {MIN_COUNT}〜{MAX_COUNT} で指定してください。")
        clean = tuple(Stop(min(max(float(s.position), 0.0), 1.0), C.normalize_hex(s.color)) for s in self.stops)
        object.__setattr__(self, "stops", clean)
        object.__setattr__(self, "count", int(self.count))

    def sorted_stops(self):
        # 同じ位置のストップは並び順を保つ(その位置で色がくっきり切り替わる)。
        return sorted(self.stops, key=lambda s: s.position)

    def color_at(self, t):
        stops = self.sorted_stops()
        positions = [s.position for s in stops]
        t = min(max(float(t), 0.0), 1.0)
        if t <= positions[0]:
            return stops[0].color
        if t >= positions[-1]:
            return stops[-1].color
        k = bisect.bisect_right(positions, t) - 1
        a, b = stops[k], stops[k + 1]
        span = b.position - a.position
        u = 0.0 if span <= 0 else (t - a.position) / span
        return interpolate(a.color, b.color, u, self.space)

    def sample(self, count=None):
        n = self.count if count is None else int(count)
        if n < 1:
            return []
        if n == 1:
            return [self.color_at(0.5)]
        return [self.color_at(i / (n - 1)) for i in range(n)]

    def reversed(self):
        return replace(self, stops=tuple(Stop(1.0 - s.position, s.color) for s in reversed(self.stops)))

    def with_stop(self, index, *, position=None, color=None):
        stops = list(self.stops)
        old = stops[index]
        stops[index] = Stop(old.position if position is None else position, old.color if color is None else color)
        return replace(self, stops=tuple(stops))

    def with_stop_added(self, position=None):
        """position の省略時は、いちばん広い隙間の中央に、その位置の色で足す。"""
        if position is None:
            ps = [s.position for s in self.sorted_stops()]
            gaps = [(ps[i + 1] - ps[i], i) for i in range(len(ps) - 1)]
            width, i = max(gaps)
            position = ps[i] + width / 2
        return replace(self, stops=self.stops + (Stop(position, self.color_at(position)),))

    def with_stop_removed(self, index):
        if len(self.stops) <= MIN_STOPS:
            raise C.ColorError(f"色の点(ストップ)は {MIN_STOPS} 個より少なくできません。")
        return replace(self, stops=tuple(s for i, s in enumerate(self.stops) if i != index))

    def with_stops_sorted(self):
        return replace(self, stops=tuple(self.sorted_stops()))

    def with_stops_evenly_spaced(self):
        stops = self.sorted_stops()
        n = len(stops)
        return replace(self, stops=tuple(Stop(i / (n - 1), s.color) for i, s in enumerate(stops)))

    def to_dict(self):
        return {"stops": [{"position": s.position, "color": s.color} for s in self.stops],
                "space": self.space, "count": self.count}

    @classmethod
    def from_dict(cls, data):
        try:
            stops = tuple(Stop(float(s["position"]), s["color"]) for s in data["stops"])
        except (KeyError, TypeError, ValueError) as e:
            raise C.ColorError("グラデーションのデータが読めません。") from e
        return cls(stops=stops, space=data.get("space", "oklab"), count=data.get("count", 7))


def _lerp(a, b, u):
    return a + (b - a) * u


def _lerp_hue(h1, h2, u):
    """短い方の弧で補間する。"""
    d = (h2 - h1 + 180.0) % 360.0 - 180.0
    return (h1 + d * u) % 360.0


def interpolate(hex1, hex2, u, space="oklab"):
    if space == "rgb":
        return C.rgb_to_hex(_lerp(C.hex_to_rgb(hex1), C.hex_to_rgb(hex2), u))
    if space == "oklab":
        return C.oklab_to_hex(_lerp(C.hex_to_oklab(hex1), C.hex_to_oklab(hex2), u))
    if space == "oklch":
        (l1, c1, h1), (l2, c2, h2) = C.hex_to_oklch(hex1), C.hex_to_oklch(hex2)
        if c1 < _ACHROMATIC_OKLCH:
            h1 = h2
        if c2 < _ACHROMATIC_OKLCH:
            h2 = h1
        return C.oklch_to_hex(np.array([_lerp(l1, l2, u), _lerp(c1, c2, u), _lerp_hue(h1, h2, u)]))
    if space == "hsv":
        (h1, s1, v1), (h2, s2, v2) = C.rgb_to_hsv(C.hex_to_rgb(hex1)), C.rgb_to_hsv(C.hex_to_rgb(hex2))
        if s1 < _ACHROMATIC_HSV or v1 == 0:
            h1 = h2
        if s2 < _ACHROMATIC_HSV or v2 == 0:
            h2 = h1
        return C.rgb_to_hex(C.hsv_to_rgb([_lerp_hue(h1, h2, u), _lerp(s1, s2, u), _lerp(v1, v2, u)]))
    raise C.ColorError(f"未知の色空間です: {space}")
