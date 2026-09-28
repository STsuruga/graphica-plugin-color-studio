"""画像の画素から代表色を求める(k-means)。Qt にも Graphica 本体にも依存しない。

画像の読み込みと縮小は qt_image.py が行い、ここには numpy の配列だけが来る。
"""
import warnings

import numpy as np
from scipy.cluster.vq import kmeans2

from . import colors as C

MAX_PIXELS = 65536
# 半透明より透明な画素は背景とみなして数えない。
_ALPHA_CUTOFF = 128


def dominant_colors(pixels, k, *, alpha=None, max_pixels=MAX_PIXELS, seed=0):
    """
    Args:
        pixels: 形 (..., 3) の RGB。uint8(0〜255)か、0〜1 の実数。
        k (int): 求める色の数。異なる色がそれより少なければ、その数だけ返す。
        alpha: pixels と同じ並びの不透明度(0〜255)。省略時はすべて不透明。
        max_pixels (int): これより多ければ無作為に間引く(GUI スレッドで動くので計算量を抑える)。
        seed (int): 同じ画像から毎回同じ結果を出すための乱数の種。
    Returns:
        list[str]: '#rrggbb'。その色に属する画素が多い順。
    """
    rgb = np.asarray(pixels).reshape(-1, 3)
    if rgb.dtype.kind in "ui":
        rgb = rgb.astype(float) / 255.0
    else:
        rgb = np.clip(rgb.astype(float), 0.0, 1.0)
    if alpha is not None:
        rgb = rgb[np.asarray(alpha).reshape(-1) >= _ALPHA_CUTOFF]
    if len(rgb) == 0:
        raise C.ColorError("画像に不透明な画素がありません。")

    rng = np.random.default_rng(seed)
    if len(rgb) > max_pixels:
        rgb = rgb[rng.choice(len(rgb), size=max_pixels, replace=False)]

    lab = C.rgb_to_oklab(rgb)
    distinct = np.unique(np.round(lab, 4), axis=0)
    k = max(1, min(int(k), len(distinct)))
    if k == len(distinct):
        labels = _nearest(lab, distinct)
        centroids = np.array([lab[labels == i].mean(axis=0) for i in range(k)])
    else:
        with warnings.catch_warnings():
            # 空のクラスタは下で数を数えて捨てるので、警告は要らない。
            warnings.simplefilter("ignore")
            centroids, labels = kmeans2(lab, k, minit="++", rng=rng)
    counts = np.bincount(labels, minlength=len(centroids))
    order = [i for i in np.argsort(-counts, kind="stable") if counts[i] > 0]
    return [C.oklab_to_hex(centroids[i]) for i in order]


def _nearest(points, centers):
    d = ((points[:, None, :] - centers[None, :, :]) ** 2).sum(axis=-1)
    return d.argmin(axis=1)
