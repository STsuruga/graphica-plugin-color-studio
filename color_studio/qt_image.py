"""画像を読み、代表色の計算に渡せる numpy の配列にする。"""
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader

from .colors import ColorError

MAX_SIDE = 256


def image_file_filter():
    formats = sorted({bytes(f).decode("ascii").lower() for f in QImageReader.supportedImageFormats()})
    patterns = " ".join(f"*.{f}" for f in formats)
    return f"画像 ({patterns});;すべてのファイル (*)"


def load_image(path, max_side=MAX_SIDE):
    """
    Returns:
        tuple[QImage, np.ndarray, np.ndarray]: 縮小した画像、RGB(uint8, 形 (h, w, 3))、不透明度(形 (h, w))。
            長辺を max_side 以下に縮めるのは、GUI スレッドで動く k-means の計算量を抑えるため。
    """
    image = QImage(path)
    if image.isNull():
        raise ColorError("画像を読めません。対応している形式か確認してください。")
    if max(image.width(), image.height()) > max_side:
        image = image.scaled(max_side, max_side, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h, bpl = image.width(), image.height(), image.bytesPerLine()
    raw = np.frombuffer(image.constBits(), dtype=np.uint8, count=h * bpl).reshape(h, bpl)
    rgba = raw[:, : w * 4].reshape(h, w, 4).copy()
    return image, rgba[..., :3], rgba[..., 3]
