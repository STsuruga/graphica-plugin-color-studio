"""グラデーションの帯と、ストップのつまみ。モデル(Gradient)を受け取り、変更は新しい Gradient で通知する。"""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .colors import ColorError

_MARGIN = 10
_BAR_HEIGHT = 36
_HANDLE_HEIGHT = 22
_HANDLE_HALF_WIDTH = 8
_PREVIEW_SAMPLES = 256
_KEY_STEP = 0.01


class GradientBar(QWidget):
    """
    Signals:
        gradientChanged(object): 新しい Gradient。ドラッグ中は繰り返し出る。
        interactionFinished(): 1回分の操作が終わった(履歴に積む合図)。
        stopSelected(int): 選んだストップの番号(gradient.stops の添字)。
        stopColorRequested(int): ストップをダブルクリックした(色を選ばせる合図)。
    """

    gradientChanged = Signal(object)
    interactionFinished = Signal()
    stopSelected = Signal(int)
    stopColorRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(_BAR_HEIGHT + _HANDLE_HEIGHT + 2 * _MARGIN)
        self.setMinimumWidth(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("グラデーションの帯")
        self.setToolTip("つまみをドラッグして位置を変更、帯をダブルクリックで色の点を追加、"
                        "つまみをダブルクリックで色を変更、Delete で削除")
        self._gradient = None
        self._selected = 0
        self._dragging = False
        self._preview_key = None
        self._preview = None

    def sizeHint(self):
        size = super().sizeHint()
        size.setHeight(self.minimumHeight())
        return size

    def set_gradient(self, gradient):
        self._gradient = gradient
        if self._selected >= len(gradient.stops):
            self._selected = 0
        self.update()

    def selected_index(self):
        return self._selected

    def select(self, index):
        self._selected = index
        self.update()
        self.stopSelected.emit(index)

    # --- 幾何 ---

    def _bar_rect(self):
        return QRectF(_MARGIN, _MARGIN, max(self.width() - 2 * _MARGIN, 1), _BAR_HEIGHT)

    def _x_of(self, position):
        bar = self._bar_rect()
        return bar.left() + position * bar.width()

    def _position_of(self, x):
        bar = self._bar_rect()
        return min(max((x - bar.left()) / bar.width(), 0.0), 1.0)

    def _hit_handle(self, pos):
        if self._gradient is None:
            return None
        bar = self._bar_rect()
        if not bar.bottom() - 4 <= pos.y() <= bar.bottom() + _HANDLE_HEIGHT + 4:
            return None
        best, best_d = None, _HANDLE_HALF_WIDTH + 3
        # 重なったつまみは、選択中のものを優先して掴めるようにする
        for i in [self._selected] + list(range(len(self._gradient.stops))):
            d = abs(self._x_of(self._gradient.stops[i].position) - pos.x())
            if d < best_d:
                best, best_d = i, d
        return best

    # --- 描画 ---

    def _preview_image(self):
        if self._gradient != self._preview_key:
            image = QImage(_PREVIEW_SAMPLES, 1, QImage.Format.Format_RGB32)
            for i in range(_PREVIEW_SAMPLES):
                color = self._gradient.color_at(i / (_PREVIEW_SAMPLES - 1))
                image.setPixelColor(i, 0, QColor(color))
            self._preview, self._preview_key = image, self._gradient
        return self._preview

    def paintEvent(self, event):
        if self._gradient is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar = self._bar_rect()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(bar, self._preview_image())
        painter.setPen(QPen(self.palette().mid().color(), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(bar)

        # 抽出する位置の目印
        n = self._gradient.count
        painter.setPen(QPen(QColor(255, 255, 255, 220), 1.5))
        for k in range(n):
            x = self._x_of(k / (n - 1))
            painter.drawLine(QPointF(x, bar.top() + 4), QPointF(x, bar.top() + 10))
            painter.drawLine(QPointF(x, bar.bottom() - 10), QPointF(x, bar.bottom() - 4))

        order = [i for i in range(len(self._gradient.stops)) if i != self._selected] + [self._selected]
        for i in order:
            stop = self._gradient.stops[i]
            x = self._x_of(stop.position)
            top = bar.bottom() + 2
            path = QPainterPath()
            path.moveTo(x, top)
            path.lineTo(x + _HANDLE_HALF_WIDTH, top + 7)
            path.lineTo(x + _HANDLE_HALF_WIDTH, top + _HANDLE_HEIGHT - 2)
            path.lineTo(x - _HANDLE_HALF_WIDTH, top + _HANDLE_HEIGHT - 2)
            path.lineTo(x - _HANDLE_HALF_WIDTH, top + 7)
            path.closeSubpath()
            selected = i == self._selected
            pen_color = self.palette().highlight().color() if selected else self.palette().text().color()
            painter.setPen(QPen(pen_color, 2.5 if selected else 1))
            painter.setBrush(QColor(stop.color))
            painter.drawPath(path)
        painter.end()

    # --- 操作 ---

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._gradient is None:
            return super().mousePressEvent(event)
        hit = self._hit_handle(event.position())
        if hit is not None:
            self._dragging = True
            self.select(hit)
        return None

    def mouseMoveEvent(self, event):
        if self._dragging and self._gradient is not None:
            p = round(self._position_of(event.position().x()), 4)
            self._gradient = self._gradient.with_stop(self._selected, position=p)
            self.update()
            self.gradientChanged.emit(self._gradient)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self.interactionFinished.emit()

    def mouseDoubleClickEvent(self, event):
        if self._gradient is None:
            return
        hit = self._hit_handle(event.position())
        if hit is not None:
            self.stopColorRequested.emit(hit)
            return
        if self._bar_rect().contains(event.position()):
            p = round(self._position_of(event.position().x()), 4)
            self._gradient = self._gradient.with_stop_added(p)
            self._selected = len(self._gradient.stops) - 1
            self.update()
            self.gradientChanged.emit(self._gradient)
            self.interactionFinished.emit()
            self.stopSelected.emit(self._selected)

    def keyPressEvent(self, event):
        if self._gradient is None:
            return super().keyPressEvent(event)
        key = event.key()
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            try:
                g = self._gradient.with_stop_removed(self._selected)
            except ColorError:
                return None
            self._selected = min(self._selected, len(g.stops) - 1)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            stop = self._gradient.stops[self._selected]
            step = _KEY_STEP * (1 if key == Qt.Key.Key_Right else -1)
            g = self._gradient.with_stop(self._selected, position=round(min(max(stop.position + step, 0.0), 1.0), 4))
        elif key == Qt.Key.Key_Space:
            self.select((self._selected + 1) % len(self._gradient.stops))
            return None
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.stopColorRequested.emit(self._selected)
            return None
        else:
            return super().keyPressEvent(event)
        self._gradient = g
        self.update()
        self.gradientChanged.emit(g)
        self.interactionFinished.emit()
        return None
