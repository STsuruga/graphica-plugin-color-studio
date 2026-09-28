"""名前の入力と、登録色へ追加する前の確認の画面。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from . import bridge

_CONFLICT_CHOICES = (
    (bridge.RENAME, "別名で追加(名前 (2))"),
    (bridge.OVERWRITE, "既存の色を置き換える"),
    (bridge.SKIP, "追加しない"),
)


def swatch_icon(color, size=16):
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


def strip_icon(colors, width=64, height=16):
    """ライブラリの一覧に出す、色を横に並べた小さな見本。"""
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    n = max(len(colors), 1)
    for i, c in enumerate(colors):
        x0, x1 = round(i * width / n), round((i + 1) * width / n)
        painter.fillRect(x0, 0, x1 - x0, height, QColor(c))
    painter.end()
    return QIcon(pixmap)


def ask_name(parent, title, label, default=""):
    """キャンセルなら None。"""
    text, ok = QInputDialog.getText(parent, title, label, QLineEdit.EchoMode.Normal, default)
    if not ok:
        return None
    return text.strip() or None


class NamedColorsDialog(QDialog):
    """
    登録色(名前と1色の対応)へ追加する色に名前を付ける。同名が既にある行では扱いを選ばせる。
    名前が空の行は追加しない。
    """

    def __init__(self, plan, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登録色に追加")
        self.resize(560, 360)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "登録色は「名前 → 1色」の対応です。同じ物質や試料に、いつも同じ色を使うために登録します。"
            "本体の色見本メニューの「登録色」に、すぐに表示されます。名前を空にした色は追加しません。")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.table = QTableWidget(len(plan), 3, self)
        self.table.setHorizontalHeaderLabels(["色", "名前", "同じ名前があるとき"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._colors = []
        self._name_edits = []
        self._conflict_boxes = []
        for row, item in enumerate(plan):
            color_item = QTableWidgetItem(swatch_icon(item["color"]), item["color"])
            color_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, color_item)
            edit = QLineEdit(item["name"], self.table)
            edit.setMaxLength(bridge.NAMED_COLOR_MAX_NAME_LENGTH)
            edit.setPlaceholderText("名前(空なら追加しない)")
            self.table.setCellWidget(row, 1, edit)
            box = QComboBox(self.table)
            for value, label in _CONFLICT_CHOICES:
                box.addItem(label, value)
            self.table.setCellWidget(row, 2, box)
            self._colors.append(item["color"])
            self._name_edits.append(edit)
            self._conflict_boxes.append(box)
            edit.textChanged.connect(self._refresh_conflicts)
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("追加")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._existing = {}

    def set_existing(self, existing):
        """existing: 本体の登録色 {名前: 色}。同名の行だけ扱いを選べるようにする。"""
        self._existing = dict(existing)
        self._refresh_conflicts()

    def _refresh_conflicts(self):
        for edit, box in zip(self._name_edits, self._conflict_boxes):
            name = " ".join(edit.text().split())
            conflict = name in self._existing
            box.setEnabled(conflict)
            box.setToolTip(f"「{name}」は既に {self._existing[name]} で登録されています。" if conflict else "")

    def items(self):
        """[(名前, 色), ...] と {名前: 扱い}。"""
        items, conflict = [], {}
        for color, edit, box in zip(self._colors, self._name_edits, self._conflict_boxes):
            name = " ".join(edit.text().split())
            if not name:
                continue
            items.append((name, color))
            conflict[name] = box.currentData()
        return items, conflict
