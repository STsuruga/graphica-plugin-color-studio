"""作った色の表示(色見本・HEX)と、ライブラリ・本体への受け渡しの操作。"""
from PySide6.QtCore import Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLineEdit, QMenu, QMessageBox, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from . import bridge
from .dialogs import NamedColorsDialog, ask_name
from .library import LibraryError
from .swatches import SwatchStrip

HISTORY_LIMIT = 200


class History:
    """プラグイン内の元に戻す / やり直し。状態は変更不可のオブジェクト(Gradient / Harmony)。"""

    def __init__(self, initial, limit=HISTORY_LIMIT):
        self._states = [initial]
        self._index = 0
        self._limit = limit

    @property
    def current(self):
        return self._states[self._index]

    def push(self, state):
        if state == self.current:
            return
        del self._states[self._index + 1:]
        self._states.append(state)
        if len(self._states) > self._limit:
            del self._states[0]
        self._index = len(self._states) - 1

    def can_undo(self):
        return self._index > 0

    def can_redo(self):
        return self._index < len(self._states) - 1

    def undo(self):
        if self.can_undo():
            self._index -= 1
        return self.current

    def redo(self):
        if self.can_redo():
            self._index += 1
        return self.current


class HandOff:
    """
    ライブラリへの保存と、本体(登録色・配色パレット・選択中のデータセット)への受け渡し。
    ウィンドウのタブとドックパネルの両方から使う。結果は status(text) / error(text) で知らせる。
    """

    def __init__(self, parent, ctx, library, status, error):
        self.parent = parent
        self.ctx = ctx
        self.library = library
        self.status = status
        self.error = error

    def _guard(self, fn, *args):
        try:
            return fn(*args)
        except (ValueError, LibraryError) as e:
            self.error(str(e))
        except Exception as e:  # noqa: BLE001 - タブが閉じられた後の窓口など。落とさずに知らせる
            self.error(f"処理できませんでした: {e}")
        return None

    def save(self, kind, colors, source, default_name):
        return self._guard(self._save, kind, colors, source, default_name)

    def _save(self, kind, colors, source, default_name):
        if self.library is None:
            raise LibraryError("ライブラリを使えません(ライブラリのタブの説明を参照)。")
        name = ask_name(self.parent, "ライブラリに保存", "名前:", default_name)
        if name is None:
            return None
        existing = self.library.find_by_name(name)
        replace_id = None
        if existing is not None:
            answer = QMessageBox.question(self.parent, "ライブラリに保存", f"「{name}」は既にあります。上書きしますか?")
            if answer != QMessageBox.StandardButton.Yes:
                return None
            replace_id = existing["id"]
        entry = self.library.add(kind, name, colors, source, replace_id=replace_id)
        self.status(f"ライブラリに「{entry['name']}」を保存しました。")
        return entry

    def register_palette(self, colors, default_name):
        return self._guard(self._register_palette, colors, default_name)

    def _register_palette(self, colors, default_name):
        name = ask_name(self.parent, "配色パレットに登録",
                        "配色パレットは、系列(データセット)に順に割り当てる色の並びです。\n"
                        "パレット名(本体の「パレット管理」に出る名前):", default_name)
        if name is None:
            return
        try:
            bridge.register_palette(self.ctx, name, colors)
        except bridge.PaletteExistsError:
            answer = QMessageBox.question(self.parent, "配色パレットに登録",
                                          f"配色パレット「{name}」は既にあります。上書きしますか?")
            if answer != QMessageBox.StandardButton.Yes:
                return
            bridge.register_palette(self.ctx, name, colors, overwrite=True)
        self.status(f"配色パレット「{name}」を登録しました。本体の「パレット管理」でこのパレットを選ぶと、"
                    "「自動配色」で系列に順に割り当てられます。")

    def add_named_colors(self, colors, name_hint=""):
        return self._guard(self._add_named_colors, colors, name_hint)

    def _add_named_colors(self, colors, name_hint):
        defaults = [f"{name_hint} {i + 1}" if name_hint else "" for i in range(len(colors))]
        if len(colors) == 1 and name_hint:
            defaults = [name_hint]
        plan = bridge.plan_named_colors(self.ctx, list(zip(defaults, colors)))
        dialog = NamedColorsDialog(plan, self.parent)
        dialog.set_existing({e["name"]: e["color"] for e in self.ctx.named_colors()})
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        items, conflict = dialog.items()
        if not items:
            self.status("名前を付けた色が無いので、登録色には何も追加しませんでした。")
            return
        result = bridge.add_named_colors(self.ctx, items, conflict)
        parts = []
        if result["added"]:
            parts.append(f"{len(result['added'])} 色を追加")
        if result["overwritten"]:
            parts.append(f"{len(result['overwritten'])} 色を置き換え")
        if result["skipped"]:
            parts.append(f"{len(result['skipped'])} 色は追加せず")
        self.status("登録色: " + "、".join(parts) + "。本体の色見本メニューの「登録色」に出ます。")

    def apply(self, colors):
        return self._guard(self._apply, colors)

    def _apply(self, colors):
        changed, total = bridge.apply_to_selected(self.ctx, colors)
        if total == 0:
            self.status("Graphica のデータセット一覧で、色を付けたいデータセットを選んでから押してください"
                        "(2D マップは対象外)。")
        elif changed == 0:
            self.status(f"選択中の {total} 件は、すでにこの色です。")
        else:
            self.status(f"選択中の {total} 件のうち {changed} 件に色を適用しました"
                        "(本体の「元に戻す」は1件ずつ戻ります)。")


class ColorOutput(QWidget):
    """
    色見本・HEX と、受け渡しのボタン。

    Signals:
        swatchMenuRequested(QMenu, int): 色見本の右クリックメニューを出す直前。タブが項目を足せる。
    """

    swatchMenuRequested = Signal(QMenu, int)

    def __init__(self, studio, kind=None, source_fn=None, parent=None):
        super().__init__(parent)
        self._studio = studio
        self._kind = kind
        self._source_fn = source_fn  # () -> (既定の名前, 作り方の dict)
        self._colors = []
        self._name_hint = ""
        self.handoff = HandOff(self, studio.ctx, studio.library, studio.show_status, studio.show_error)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.strip = SwatchStrip(self)
        self.strip.swatchClicked.connect(self._copy_one)
        self.strip.swatchMenuRequested.connect(self._swatch_menu)
        layout.addWidget(self.strip)

        hex_row = QHBoxLayout()
        self.hex_edit = QLineEdit(self)
        self.hex_edit.setReadOnly(True)
        self.hex_edit.setAccessibleName("HEX の一覧")
        copy_all = QPushButton("HEX をすべてコピー", self)
        copy_all.clicked.connect(self._copy_all)
        hex_row.addWidget(self.hex_edit, 1)
        hex_row.addWidget(copy_all)
        layout.addLayout(hex_row)

        actions = QHBoxLayout()
        self.save_button = QPushButton("ライブラリに保存...", self)
        self.save_button.clicked.connect(self._save)
        self.palette_button = QPushButton("配色パレットに登録...", self)
        self.palette_button.setToolTip("系列に順に割り当てる色の並びとして、本体の配色パレットに登録します。")
        self.palette_button.clicked.connect(lambda: self.handoff.register_palette(self._colors, self._default_name()))
        self.named_button = QPushButton("登録色に追加...", self)
        self.named_button.setToolTip("「名前 → 1色」の対応として、本体の登録色に追加します。")
        self.named_button.clicked.connect(lambda: self.handoff.add_named_colors(self._colors, self._name_hint))
        self.apply_button = QPushButton("選択中のデータセットに適用", self)
        self.apply_button.setToolTip("Graphica で選択中のデータセットに、表示順で色を順に割り当てます(元に戻す可)。")
        self.apply_button.clicked.connect(lambda: self.handoff.apply(self._colors))
        for b in (self.save_button, self.palette_button, self.named_button, self.apply_button):
            b.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            actions.addWidget(b)
        actions.addStretch(1)
        layout.addLayout(actions)
        if kind is None:
            self.save_button.hide()
        if studio.library is None:
            self.save_button.setEnabled(False)

    def colors(self):
        return list(self._colors)

    def set_colors(self, colors, base_index=None, name_hint=""):
        self._colors = list(colors)
        self._name_hint = name_hint
        self.strip.set_colors(self._colors, base_index)
        self.hex_edit.setText(", ".join(self._colors))
        enabled = bool(self._colors)
        for b in (self.palette_button, self.named_button, self.apply_button):
            b.setEnabled(enabled)

    def _default_name(self):
        return self._source_fn()[0] if self._source_fn else self._name_hint

    def _save(self):
        if self._source_fn is None:
            return
        name, source = self._source_fn()
        self.handoff.save(self._kind, self._colors, source, name)

    def _copy_all(self):
        QGuiApplication.clipboard().setText(", ".join(self._colors))
        self._studio.show_status(f"{len(self._colors)} 色の HEX をコピーしました。")

    def _copy_one(self, i):
        QGuiApplication.clipboard().setText(self._colors[i])
        self._studio.show_status(f"{i + 1} 番目の色 {self._colors[i]} をコピーしました。")

    def _swatch_menu(self, i, global_pos):
        menu = QMenu(self)
        color = self._colors[i]
        menu.addAction(f"{color} をコピー", lambda: self._copy_one(i))
        menu.addAction("この色を登録色に追加...", lambda: self.handoff.add_named_colors([color], ""))
        self.swatchMenuRequested.emit(menu, i)
        menu.exec(global_pos)
