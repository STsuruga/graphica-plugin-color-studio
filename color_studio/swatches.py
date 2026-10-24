"""色見本の列(クリックで HEX をコピーする合図を出す)と、今の色を見せる色のボタン。"""
from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QPushButton, QSizePolicy, QWidget

from .theme import theme_qcolor


_GAP = 4
_SWATCH_HEIGHT = 44
_LABEL_HEIGHT = 18
_MIN_WIDTH_FOR_HEX = 58


class SwatchStrip(QWidget):
    """
    Signals:
        swatchClicked(int): 左クリックした色の番号。
        swatchMenuRequested(int, QPoint): 右クリック(画面座標)。
    """

    swatchClicked = Signal(int)
    swatchMenuRequested = Signal(int, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(_SWATCH_HEIGHT + _LABEL_HEIGHT + 2)
        self.setMouseTracking(True)
        self.setAccessibleName("色見本")
        self._colors = []
        self._base_index = None

    def sizeHint(self):
        size = super().sizeHint()
        size.setHeight(self.minimumHeight())
        return size

    def set_colors(self, colors, base_index=None):
        self._colors = list(colors)
        self._base_index = base_index
        self.setAccessibleDescription(" ".join(self._colors))
        self.update()

    def colors(self):
        return list(self._colors)

    def _cell(self, i):
        n = max(len(self._colors), 1)
        w = (self.width() - _GAP * (n - 1)) / n
        return QRectF(i * (w + _GAP), 0, w, _SWATCH_HEIGHT)

    def index_at(self, pos):
        for i in range(len(self._colors)):
            if self._cell(i).adjusted(0, 0, _GAP, _LABEL_HEIGHT).contains(pos):
                return i
        return None

    def paintEvent(self, event):
        if not self._colors:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text_color = theme_qcolor(self, "text_primary")
        outline = theme_qcolor(self, "border_strong")
        fm = QFontMetrics(self.font())
        for i, color in enumerate(self._colors):
            cell = self._cell(i)
            painter.setPen(QPen(outline, 1))
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(cell, 4, 4)
            if i == self._base_index:
                painter.setPen(QPen(QColor("white"), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(cell.center(), 5, 5)
            label = f"{i + 1}  {color}" if cell.width() >= _MIN_WIDTH_FOR_HEX + 20 else (
                color if cell.width() >= _MIN_WIDTH_FOR_HEX else str(i + 1))
            label = fm.elidedText(label, Qt.TextElideMode.ElideRight, int(cell.width()))
            painter.setPen(text_color)
            painter.drawText(QRectF(cell.left(), cell.bottom() + 2, cell.width(), _LABEL_HEIGHT),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, label)
        painter.end()

    def mouseMoveEvent(self, event):
        i = self.index_at(event.position())
        self.setToolTip("" if i is None else f"{i + 1}: {self._colors[i]}(クリックでコピー、右クリックでメニュー)")
        self.setCursor(Qt.CursorShape.PointingHandCursor if i is not None else Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event):
        i = self.index_at(event.position())
        if i is None:
            return super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.swatchClicked.emit(i)
        elif event.button() == Qt.MouseButton.RightButton:
            self.swatchMenuRequested.emit(i, event.globalPosition().toPoint())
        return None


class ColorButton(QPushButton):
    """押すと色を選ぶボタン。本体のボタンの形の上に今の色を描く(色を直書きした QSS は使わない)。"""

    def __init__(self, tooltip, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 24)
        self.setToolTip(tooltip)
        self._color = None

    def color(self):
        return self._color

    def set_color(self, color):
        self._color = color
        self.setAccessibleName(color)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._color:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(theme_qcolor(self, "border_strong"), 1))
        painter.setBrush(QColor(self._color))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(4.5, 4.5, -4.5, -4.5), 3, 3)
        painter.end()
