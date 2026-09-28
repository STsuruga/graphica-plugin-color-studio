"""カラーホイールのウィジェット。

円は numpy で画素ごとに計算して QImage にする(RYB の色相対応は非線形で、QConicalGradient の補間では
正確に出ないため)。角度は上が 0 度で時計回り、半径が彩度。
"""
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .harmony import ryb_to_rgb_hues, wheel_to_hex

_HIT_RADIUS = 14
_POINT_RADIUS = 8
_BASE_POINT_RADIUS = 11
_KEY_ANGLE_STEP = 2.0
_KEY_SATURATION_STEP = 0.02


def _hsv_to_rgb_array(h, s, v):
    """h 度・s・v の配列から (..., 3) の RGB(0〜1)。"""
    h = (h % 360.0) / 60.0
    c = v * s
    x = c * (1 - np.abs(h % 2 - 1))
    zero = np.zeros_like(h)
    sector = np.floor(h).astype(int) % 6
    r = np.choose(sector, [c, x, zero, zero, x, c])
    g = np.choose(sector, [x, c, c, x, zero, zero])
    b = np.choose(sector, [zero, zero, x, c, c, x])
    m = v - c
    return np.stack([r + m, g + m, b + m], axis=-1)


def render_wheel_rgba(size, wheel="ryb", brightness=1.0):
    """直径 size の円を (size, size, 4) の uint8 RGBA で返す。円の外は透明。"""
    coords = (np.arange(size) + 0.5 - size / 2) / (size / 2)
    x, y = np.meshgrid(coords, coords)
    radius = np.hypot(x, y)
    angle = np.degrees(np.arctan2(x, -y)) % 360.0
    hue = ryb_to_rgb_hues(angle) if wheel == "ryb" else angle
    rgb = _hsv_to_rgb_array(hue, np.clip(radius, 0, 1), np.full_like(radius, float(brightness)))
    # 縁を1画素ぶん滑らかにする
    alpha = np.clip((1.0 - radius) * size / 2 + 0.5, 0.0, 1.0)
    rgba = np.concatenate([rgb, alpha[..., None]], axis=-1)
    return np.ascontiguousarray((rgba * 255 + 0.5).astype(np.uint8))


class ColorWheel(QWidget):
    """
    点をドラッグして配色を作るホイール。モデル(Harmony)は持たず、点の表示と操作の通知だけを担う。

    Signals:
        pointMoved(int, float, float): 点の番号、角度、彩度。ドラッグ中に繰り返し出る。
        interactionFinished(): ドラッグやキー操作が1回分終わった(履歴に積む合図)。
    """

    pointMoved = Signal(int, float, float)
    interactionFinished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("カラーホイール")
        self._wheel = "ryb"
        self._brightness = 1.0
        self._points = []
        self._base_index = 0
        self._selected = 0
        self._dragging = None
        self._cache_key = None
        self._cache_image = None

    # --- 外から設定 ---

    def set_wheel(self, wheel):
        self._wheel = wheel
        self.update()

    def set_brightness(self, v):
        self._brightness = float(v)
        self.update()

    def set_points(self, points, base_index=0):
        self._points = [tuple(p) for p in points]
        self._base_index = base_index
        if self._selected >= len(self._points):
            self._selected = base_index
        self.update()

    def selected_index(self):
        return self._selected

    # --- 幾何 ---

    def _geometry(self):
        side = min(self.width(), self.height()) - 2 * _BASE_POINT_RADIUS - 4
        side = max(side, 20)
        center = QPointF(self.width() / 2, self.height() / 2)
        return center, side / 2

    def point_position(self, point):
        center, radius = self._geometry()
        angle, s, _ = point
        rad = np.radians(angle)
        return QPointF(center.x() + radius * s * np.sin(rad), center.y() - radius * s * np.cos(rad))

    def position_to_polar(self, pos):
        center, radius = self._geometry()
        dx, dy = pos.x() - center.x(), pos.y() - center.y()
        angle = float(np.degrees(np.arctan2(dx, -dy)) % 360.0)
        saturation = float(min(np.hypot(dx, dy) / radius, 1.0))
        return angle, saturation

    def _hit(self, pos):
        best, best_d = None, _HIT_RADIUS
        for i, p in enumerate(self._points):
            q = self.point_position(p)
            d = float(np.hypot(q.x() - pos.x(), q.y() - pos.y()))
            if d <= best_d:
                best, best_d = i, d
        return best

    # --- 描画 ---

    def _wheel_image(self, diameter):
        key = (diameter, self._wheel, round(self._brightness, 3))
        if key != self._cache_key:
            rgba = render_wheel_rgba(diameter, self._wheel, self._brightness)
            self._cache_image = QImage(rgba.data, diameter, diameter, 4 * diameter,
                                       QImage.Format.Format_RGBA8888).copy()
            self._cache_key = key
        return self._cache_image

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center, radius = self._geometry()
        diameter = int(2 * radius)
        if diameter > 0:
            painter.drawImage(QRectF(center.x() - radius, center.y() - radius, diameter, diameter),
                              self._wheel_image(diameter))
        line_pen = QPen(QColor(255, 255, 255, 200), 1.5)
        for p in self._points:
            painter.setPen(line_pen)
            painter.drawLine(center, self.point_position(p))
        order = [i for i in range(len(self._points)) if i != self._base_index] + [self._base_index]
        for i in order:
            if i >= len(self._points):
                continue
            p = self._points[i]
            pos = self.point_position(p)
            r = _BASE_POINT_RADIUS if i == self._base_index else _POINT_RADIUS
            painter.setPen(QPen(QColor(0, 0, 0, 150), 1))
            painter.setBrush(QColor(wheel_to_hex(p, self._wheel)))
            painter.drawEllipse(pos, r + 1.5, r + 1.5)
            painter.setPen(QPen(QColor("white"), 3 if i == self._base_index else 2))
            painter.drawEllipse(pos, r, r)
            if i == self._selected and self.hasFocus():
                painter.setPen(QPen(self.palette().highlight().color(), 2, Qt.PenStyle.DotLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(pos, r + 5, r + 5)
        painter.end()

    # --- 操作 ---

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._points:
            return super().mousePressEvent(event)
        pos = event.position()
        hit = self._hit(pos)
        if hit is None:
            # 何も無いところを押したら基準の点をそこへ動かす
            hit = self._base_index
            self._emit_move(hit, *self.position_to_polar(pos))
        self._dragging = hit
        self._selected = hit
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._dragging is not None:
            self._emit_move(self._dragging, *self.position_to_polar(pos))
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor if self._hit(pos) is not None
                           else Qt.CursorShape.CrossCursor)

    def mouseReleaseEvent(self, event):
        if self._dragging is not None and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = None
            self.interactionFinished.emit()

    def keyPressEvent(self, event):
        if not self._points:
            return super().keyPressEvent(event)
        key = event.key()
        angle, s, _ = self._points[self._selected]
        if key == Qt.Key.Key_Tab or key == Qt.Key.Key_Backtab:
            return super().keyPressEvent(event)
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            angle += _KEY_ANGLE_STEP * (1 if key == Qt.Key.Key_Right else -1)
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            s = min(max(s + _KEY_SATURATION_STEP * (1 if key == Qt.Key.Key_Up else -1), 0.0), 1.0)
        elif key == Qt.Key.Key_Space:
            self._selected = (self._selected + 1) % len(self._points)
            self.update()
            return None
        else:
            return super().keyPressEvent(event)
        self._emit_move(self._selected, angle % 360.0, s)
        self.interactionFinished.emit()
        return None

    def _emit_move(self, index, angle, saturation):
        self.pointMoved.emit(index, float(angle), float(saturation))
