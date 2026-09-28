"""ドックパネル: ライブラリの一覧と、よく使う受け渡しだけ。色を作る作業はウィンドウで行う。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from .dialogs import strip_icon
from .library import KIND_LABELS, LibraryError
from .output import HandOff
from .studio_window import load_library, open_studio


class LibraryPanel(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.library, error = load_library(ctx)
        layout = QVBoxLayout(self)
        open_button = QPushButton("カラースタジオを開く", self)
        open_button.clicked.connect(lambda: open_studio(self.ctx))
        layout.addWidget(open_button)

        self.list = QListWidget(self)
        self.list.itemDoubleClicked.connect(lambda _item: self._open())
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.edit_button = QPushButton("開く", self)
        self.edit_button.setToolTip("選んだ配色をカラースタジオで開いて編集します")
        self.edit_button.clicked.connect(self._open)
        self.apply_button = QPushButton("選択中に適用", self)
        self.apply_button.setToolTip("Graphica で選択中のデータセットに、表示順で色を順に割り当てます(元に戻す可)")
        self.apply_button.clicked.connect(lambda: self._with_entry(lambda e: self.handoff.apply(e["colors"])))
        self.palette_button = QPushButton("配色パレットに登録...", self)
        self.palette_button.setToolTip("系列に順に割り当てる色の並びとして、本体の配色パレットに登録します")
        self.palette_button.clicked.connect(
            lambda: self._with_entry(lambda e: self.handoff.register_palette(e["colors"], e["name"])))
        for b in (self.edit_button, self.apply_button, self.palette_button):
            row.addWidget(b)
        layout.addLayout(row)

        self.status = QLabel(self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.handoff = HandOff(self, ctx, self.library, self.status.setText, self.status.setText)

        if self.library is None:
            self.status.setText(f"ライブラリを使えません: {error}")
            for b in (self.edit_button, self.apply_button, self.palette_button):
                b.setEnabled(False)
            return
        self.library.add_listener(self.reload)
        self.reload()

    def reload(self):
        current = self._selected_id()
        self.list.clear()
        entries = self.library.entries()
        for e in entries:
            item = QListWidgetItem(strip_icon(e["colors"], 64, 14), e["name"])
            item.setToolTip(f"{KIND_LABELS[e['kind']]} · {len(e['colors'])}色\n" + ", ".join(e["colors"]))
            item.setData(Qt.ItemDataRole.UserRole, e["id"])
            self.list.addItem(item)
            if e["id"] == current:
                self.list.setCurrentItem(item)
        if not entries:
            self.status.setText("ライブラリは空です。「カラースタジオを開く」で配色を作って保存してください。")

    def _selected_id(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _with_entry(self, fn):
        entry_id = self._selected_id()
        if entry_id is None:
            self.status.setText("一覧で配色を選んでください。")
            return
        try:
            entry = self.library.get(entry_id)
        except LibraryError as e:
            self.status.setText(str(e))
            return
        fn(entry)

    def _open(self):
        self._with_entry(lambda e: open_studio(self.ctx, e))
