"""画像の画素から代表色を求める(k-means)。Qt にも Graphica 本体にも依存しない。

画像の読み込みと縮小は qt_image.py が行い、ここには numpy の配列だけが来る。
k-means は numpy で自前に持つ。Graphica v2.0.0 の exe は scipy.cluster を同梱していない
(本体が使わないため PyInstaller が入れない)ので、scipy.cluster.vq は exe で import できない。
"""
import numpy as np

from . import colors as C

MAX_PIXELS = 65536
# 中心を求めるのはこの数までの標本で行い、画素の数え上げだけ全体で行う(GUI スレッドで待たせないため)。
_FIT_SAMPLES = 16384
_MAX_ITERATIONS = 50
_CONVERGED = 1e-7
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
        fit = lab if len(lab) <= _FIT_SAMPLES else lab[rng.choice(len(lab), size=_FIT_SAMPLES, replace=False)]
        centroids, _ = kmeans(fit, k, rng)
        labels = _nearest(lab, centroids)
    counts = np.bincount(labels, minlength=len(centroids))
    order = [i for i in np.argsort(-counts, kind="stable") if counts[i] > 0]
    return [C.oklab_to_hex(centroids[i]) for i in order]


def kmeans(data, k, rng):
    """k-means++ で初期値を選び、Lloyd 法で更新する。空になったクラスタは前の中心のまま残す。"""
    n = len(data)
    centers = [data[rng.integers(n)]]
    d2 = ((data - centers[0]) ** 2).sum(axis=1)
    for _ in range(1, k):
        total = d2.sum()
        if total <= 0:
            break
        pick = data[rng.choice(n, p=d2 / total)]
        centers.append(pick)
        d2 = np.minimum(d2, ((data - pick) ** 2).sum(axis=1))
    centers = np.array(centers)
    m = len(centers)
    for _ in range(_MAX_ITERATIONS):
        labels = _nearest(data, centers)
        counts = np.bincount(labels, minlength=m)
        sums = np.stack([np.bincount(labels, weights=data[:, c], minlength=m) for c in range(data.shape[1])], axis=1)
        updated = np.where(counts[:, None] > 0, sums / np.maximum(counts, 1)[:, None], centers)
        if np.allclose(updated, centers, atol=_CONVERGED):
            break
        centers = updated
    return centers, _nearest(data, centers)


def _nearest(points, centers):
    # |p - c|^2 = |p|^2 - 2 p·c + |c|^2。|p|^2 は比較に効かないので省く。
    d = (centers ** 2).sum(axis=1)[None, :] - 2.0 * points @ centers.T
    return d.argmin(axis=1)
