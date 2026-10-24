"""パネル: ライブラリの一覧と、よく使う受け渡しだけ。色を作る作業はウィンドウで行う。

本体の左端の帯の「プラグイン」ページ(幅 280px)に入るので、横に並べるのは2つまでにする。
"""
from graphica.plugin import ui  # このモジュールはパネルを作るときにだけ読み込まれる
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from .dialogs import strip_icon
from .library import KIND_LABELS, LibraryError
from .output import HandOff
from .studio_window import load_library, open_studio

# 本体のプラグインのページの選ぶ欄と同じ左右の余白
_MARGIN = 12


class LibraryPanel(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.library, error = load_library(ctx)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(_MARGIN, 0, _MARGIN, _MARGIN)
        open_button = QPushButton("カラースタジオを開く", self)
        open_button.clicked.connect(lambda: open_studio(self.ctx))
        layout.addWidget(open_button)

        self.list = QListWidget(self)
        self.list.setIconSize(QSize(64, 14))
        self.list.itemDoubleClicked.connect(lambda _item: self._open())
        layout.addWidget(self.list, 1)

        # 3つは横に入らないので2段にする(上に2つ、下に1つを横いっぱい)
        buttons = QGridLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        self.edit_button = QPushButton("開いて編集", self)
        self.edit_button.setToolTip("選んだ配色をカラースタジオで開いて編集します")
        self.edit_button.clicked.connect(self._open)
        self.apply_button = QPushButton("選択中に適用", self)
        self.apply_button.setToolTip("Graphica で選択中のデータセットに、表示順で色を順に割り当てます(元に戻す可)")
        self.apply_button.clicked.connect(lambda: self._with_entry(lambda e: self.handoff.apply(e["colors"])))
        self.palette_button = QPushButton("配色パレットに登録...", self)
        self.palette_button.setToolTip("系列に順に割り当てる色の並びとして、本体の配色パレットに登録します")
        self.palette_button.clicked.connect(
            lambda: self._with_entry(lambda e: self.handoff.register_palette(e["colors"], e["name"])))
        buttons.addWidget(self.edit_button, 0, 0)
        buttons.addWidget(self.apply_button, 0, 1)
        buttons.addWidget(self.palette_button, 1, 0, 1, 2)
        layout.addLayout(buttons)

        self.status = QLabel(self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.handoff = HandOff(self, ctx, self.library, self.status.setText, self.status.setText, self._done)

        if self.library is None:
            self.status.setText(f"ライブラリを使えません: {error}")
            for b in (self.edit_button, self.apply_button, self.palette_button):
                b.setEnabled(False)
            return
        self.library.add_listener(self.reload)
        self.reload()

    def _done(self, text, detail=""):
        self.status.setText(text + detail)
        ui.show_toast(self, text)

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
