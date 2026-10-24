"""カラースタジオの独立ウィンドウ(グラデーション / 配色パレット / ライブラリの3タブ)。

タブ(PlotterApp)ごとに1つ。親をそのタブにするので、タブを閉じると一緒に破棄される。
閉じるボタンでは隠すだけにして、次に開いたときに作業の続きから始められるようにする。
"""
from graphica.plugin import ui  # このモジュールはウィンドウ・パネルを作るときにだけ読み込まれる
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSizePolicy, QSlider, QSpinBox, QTabWidget,
    QVBoxLayout, QWidget,
)

from . import colors as C
from . import gradient, harmony
from .dialogs import ask_name, strip_icon
from .extract import dominant_colors
from .gradient import Gradient, Stop
from .gradient_bar import GradientBar
from .harmony import Harmony
from .library import KIND_LABELS, LibraryError, get_library
from .output import ColorOutput, History
from .qt_image import image_file_filter, load_image
from .swatches import ColorButton
from .theme import theme_qcolor
from .wheel import ColorWheel

WINDOW_TITLE = "カラースタジオ"
_THUMB_SIDE = 96


def _segmented(items, parent):
    """選択肢の少ない欄。items は (説明つきの名前, 値)。ボタンには括弧の前の短い名前を出し、全体はツールチップに。"""
    control = ui.SegmentedControl(parent)
    for label, value in items:
        control.addItem(label.split("(")[0], value, label)
    return control


def _left(*widgets):
    """フォームの欄を左に寄せて並べる(数値の欄などを横いっぱいに伸ばさない)。"""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        row.addWidget(w)
    row.addStretch(1)
    return box


class _ImageThumb(QLabel):
    """画像の縮小表示。画像が無い間は点線の枠(テーマの色)を描く。"""

    def paintEvent(self, event):
        super().paintEvent(event)
        pixmap = self.pixmap()
        if pixmap is not None and not pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setPen(QPen(theme_qcolor(self, "border_strong"), 1, Qt.PenStyle.DashLine))
        painter.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        painter.end()


def _pick_color(parent, initial, title):
    color = QColorDialog.getColor(QColor(initial), parent, title)
    return color.name() if color.isValid() else None


def load_library(ctx):
    """(Library か None, 使えない理由)。"""
    try:
        return get_library(ctx.data_dir), ""
    except LibraryError as e:
        return None, str(e)


class GradientTab(QWidget):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio = studio
        self.history = History(Gradient())
        self._state = self.history.current

        layout = QVBoxLayout(self)
        intro = QLabel("色の点(ストップ)を2個以上置き、端から端まで等間隔に色を抜き出します。"
                       "帯をダブルクリックで点を追加、点をドラッグで位置を変更、点をダブルクリックで色を変更します。")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.bar = GradientBar(self)
        self.bar.gradientChanged.connect(self._preview)
        self.bar.interactionFinished.connect(self._commit_current)
        self.bar.stopSelected.connect(lambda _i: self._sync_stop_editor())
        self.bar.stopColorRequested.connect(self._pick_stop_color)
        layout.addWidget(self.bar)

        # 抽出の設定と、選んでいる色の点は、本体のインスペクタと同じ節にして左右に並べる
        sections = QHBoxLayout()
        extract_box, extract_form = ui.section("抽出")
        self.space_control = _segmented(
            [(gradient.SPACE_LABELS[key], key) for key in gradient.SPACES], self)
        self.space_control.currentIndexChanged.connect(
            lambda _i: self._commit(Gradient(self._state.stops, self.space_control.currentData(), self._state.count)))
        self.count_spin = QSpinBox(self)
        self.count_spin.setRange(gradient.MIN_COUNT, gradient.MAX_COUNT)
        self.count_spin.setKeyboardTracking(False)
        self.count_spin.valueChanged.connect(
            lambda n: self._commit(Gradient(self._state.stops, self._state.space, n)))
        extract_form.addRow("補間", self.space_control)
        extract_form.addRow("色の数", _left(self.count_spin))
        sections.addWidget(extract_box, 1)

        stop_box, stop_form = ui.section("選んでいる色の点")
        self.position_spin = QDoubleSpinBox(self)
        self.position_spin.setRange(0.0, 1.0)
        self.position_spin.setDecimals(3)
        self.position_spin.setSingleStep(0.01)
        self.position_spin.setKeyboardTracking(False)
        self.position_spin.valueChanged.connect(self._position_edited)
        self.stop_color_button = ColorButton("クリックで色を選ぶ", self)
        self.stop_color_button.clicked.connect(lambda: self._pick_stop_color(self.bar.selected_index()))
        self.stop_hex = QLineEdit(self)
        self.stop_hex.setMaximumWidth(100)
        self.stop_hex.setPlaceholderText("#rrggbb")
        self.stop_hex.editingFinished.connect(self._hex_edited)
        stop_form.addRow("位置 (0〜1)", _left(self.position_spin))
        stop_form.addRow("色", _left(self.stop_color_button, self.stop_hex))
        sections.addWidget(stop_box, 1)
        layout.addLayout(sections)

        row = QHBoxLayout()
        for text, handler, tip in (
            ("反転", lambda: self._commit(self._state.reversed()), "グラデーションの向きを逆にします"),
            ("点を追加", lambda: self._add_stop(), "いちばん広い隙間の中央に点を足します"),
            ("点を削除", self._remove_stop, "選んでいる点を削除します(2個より減らせません)"),
            ("等間隔に並べる", lambda: self._commit(self._state.with_stops_evenly_spaced()), "点を位置の順に等間隔にします"),
        ):
            b = QPushButton(text, self)
            b.setToolTip(tip)
            b.clicked.connect(handler)
            row.addWidget(b)
        row.addStretch(1)
        self.undo_button = QPushButton("元に戻す", self)
        self.redo_button = QPushButton("やり直し", self)
        self.undo_button.clicked.connect(self.undo)
        self.redo_button.clicked.connect(self.redo)
        row.addWidget(self.undo_button)
        row.addWidget(self.redo_button)
        layout.addLayout(row)

        layout.addWidget(QLabel("抜き出した色(クリックで HEX をコピー):"))
        self.output = ColorOutput(studio, "gradient", self._source, self)
        layout.addWidget(self.output)
        layout.addStretch(1)
        self._show(self._state)

    # --- 状態 ---

    def state(self):
        return self._state

    def _source(self):
        return f"グラデーション {len(self._state.stops)}点・{self._state.count}色", self._state.to_dict()

    def _show(self, g):
        self._state = g
        self.bar.set_gradient(g)
        self.space_control.blockSignals(True)
        self.space_control.setCurrentIndex(self.space_control.findData(g.space))
        self.space_control.blockSignals(False)
        self.count_spin.blockSignals(True)
        self.count_spin.setValue(g.count)
        self.count_spin.blockSignals(False)
        self._sync_stop_editor()
        self.output.set_colors(g.sample())
        self.undo_button.setEnabled(self.history.can_undo())
        self.redo_button.setEnabled(self.history.can_redo())

    def _preview(self, g):
        """ドラッグ中。履歴には積まない。"""
        self._state = g
        self._sync_stop_editor()
        self.output.set_colors(g.sample())

    def _commit(self, g):
        self.history.push(g)
        self._show(g)

    def _commit_current(self):
        self._commit(self._state)

    def load(self, g):
        self._commit(g)

    def undo(self):
        self._show(self.history.undo())

    def redo(self):
        self._show(self.history.redo())

    # --- 色の点 ---

    def _sync_stop_editor(self):
        i = self.bar.selected_index()
        if i >= len(self._state.stops):
            return
        stop = self._state.stops[i]
        self.position_spin.blockSignals(True)
        self.position_spin.setValue(stop.position)
        self.position_spin.blockSignals(False)
        self.stop_color_button.set_color(stop.color)
        self.stop_hex.setText(stop.color)

    def _position_edited(self, value):
        self._commit(self._state.with_stop(self.bar.selected_index(), position=value))

    def _hex_edited(self):
        text = self.stop_hex.text()
        i = self.bar.selected_index()
        if text == self._state.stops[i].color:
            return
        try:
            self._commit(self._state.with_stop(i, color=C.normalize_hex(text)))
        except C.ColorError as e:
            self.studio.show_error(str(e))
            self._sync_stop_editor()

    def _pick_stop_color(self, i):
        color = _pick_color(self, self._state.stops[i].color, "色の点の色")
        if color:
            self._commit(self._state.with_stop(i, color=color))

    def _add_stop(self):
        g = self._state.with_stop_added()
        self._commit(g)
        self.bar.select(len(g.stops) - 1)

    def _remove_stop(self):
        try:
            self._commit(self._state.with_stop_removed(self.bar.selected_index()))
        except C.ColorError as e:
            self.studio.show_error(str(e))


class PaletteTab(QWidget):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio = studio
        self.history = History(Harmony())
        self._state = self.history.current
        self._image_pixels = None  # 画像から作った直後だけ保持し、色数を変えたら取り直す

        outer = QVBoxLayout(self)
        top = QHBoxLayout()
        self.wheel = ColorWheel(self)
        self.wheel.pointMoved.connect(self._point_moved)
        self.wheel.interactionFinished.connect(self._commit_current)
        top.addWidget(self.wheel, 3)

        # 右の列は QWidget に包む。レイアウトのままだと行の高さの上限になり、余った高さが下の色見本に回る。
        side_widget = QWidget(self)
        side = QVBoxLayout(side_widget)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(0)
        rule_box, rule_form = ui.section("配色")
        self.rule_combo = QComboBox(self)
        for key in harmony.RULES:
            self.rule_combo.addItem(harmony.RULE_LABELS[key], key)
        self.rule_combo.currentIndexChanged.connect(
            lambda _i: self._commit(self._state.with_rule(self.rule_combo.currentData()), keep_image=False))
        self.count_spin = QSpinBox(self)
        self.count_spin.setRange(harmony.MIN_COUNT, harmony.MAX_COUNT)
        self.count_spin.setKeyboardTracking(False)
        self.count_spin.valueChanged.connect(self._count_changed)
        self.wheel_control = _segmented([(harmony.WHEEL_LABELS[key], key) for key in harmony.WHEELS], self)
        self.wheel_control.currentIndexChanged.connect(
            lambda _i: self._commit(self._state.with_wheel(self.wheel_control.currentData())))
        self.brightness = QSlider(Qt.Orientation.Horizontal, self)
        self.brightness.setRange(5, 100)
        self.brightness.setAccessibleName("明るさ")
        self.brightness.valueChanged.connect(
            lambda v: self._preview(self._state.with_brightness(v / 100)))
        self.brightness.sliderReleased.connect(self._commit_current)
        rule_form.addRow("配色ルール", self.rule_combo)
        rule_form.addRow("色数", _left(self.count_spin))
        rule_form.addRow("色相環", self.wheel_control)
        rule_form.addRow("明るさ", self.brightness)
        side.addWidget(rule_box)

        base_box, base_form = ui.section("基準色から")
        self.base_button = ColorButton("クリックで基準色を選ぶ", self)
        self.base_button.clicked.connect(self._pick_base)
        self.base_hex = QLineEdit(self)
        self.base_hex.setPlaceholderText("#rrggbb")
        self.base_hex.setMaximumWidth(100)
        self.base_hex.editingFinished.connect(self._base_hex_edited)
        base_form.addRow("基準色", _left(self.base_button, self.base_hex))
        side.addWidget(base_box)

        image_box, image_form = ui.section("画像から")
        self.thumb = _ImageThumb(self)
        self.thumb.setFixedSize(_THUMB_SIDE, _THUMB_SIDE)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setText("画像なし")
        open_image = QPushButton("画像を開く...", self)
        open_image.setToolTip("画像の色を k-means で代表色に絞り、パレットにします(色数の分だけ)。")
        open_image.clicked.connect(self._open_image)
        image_row = _left(self.thumb, open_image)
        image_row.layout().setAlignment(open_image, Qt.AlignmentFlag.AlignTop)
        image_form.addRow(image_row)
        side.addWidget(image_box)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 8, 0, 0)
        random_button = QPushButton("ランダム", self)
        random_button.setToolTip("配色ルールはそのままに、基準色を無作為に選び直します")
        random_button.clicked.connect(lambda: self._commit(self._state.randomized(), keep_image=False))
        self.undo_button = QPushButton("元に戻す", self)
        self.redo_button = QPushButton("やり直し", self)
        self.undo_button.clicked.connect(self.undo)
        self.redo_button.clicked.connect(self.redo)
        for b in (random_button, self.undo_button, self.redo_button):
            buttons.addWidget(b)
        buttons.addStretch(1)
        side.addLayout(buttons)
        side.addStretch(1)
        top.addWidget(side_widget, 2)
        outer.addLayout(top, 1)

        outer.addWidget(QLabel("配色パレット(クリックで HEX をコピー、白い丸が基準色):"))
        self.output = ColorOutput(studio, "palette", self._source, self)
        self.output.swatchMenuRequested.connect(self._extend_swatch_menu)
        outer.addWidget(self.output)
        self._show(self._state)

    def state(self):
        return self._state

    def _source(self):
        return f"{harmony.RULE_LABELS[self._state.rule]} {self._state.count}色", self._state.to_dict()

    def _show(self, h):
        self._state = h
        self.wheel.set_wheel(h.wheel)
        self.wheel.set_points(h.points(), h.base_index())
        base_point = h.points()[h.base_index()]
        self.wheel.set_brightness(base_point[2])
        for w, setter in ((self.rule_combo, lambda: self.rule_combo.setCurrentIndex(self.rule_combo.findData(h.rule))),
                          (self.count_spin, lambda: self.count_spin.setValue(h.count)),
                          (self.wheel_control, lambda: self.wheel_control.setCurrentIndex(self.wheel_control.findData(h.wheel))),
                          (self.brightness, lambda: self.brightness.setValue(round(base_point[2] * 100)))):
            w.blockSignals(True)
            setter()
            w.blockSignals(False)
        base = h.base_color()
        self.base_button.set_color(base)
        self.base_hex.setText(base)
        self.output.set_colors(h.colors(), h.base_index())
        self.undo_button.setEnabled(self.history.can_undo())
        self.redo_button.setEnabled(self.history.can_redo())

    def _preview(self, h):
        self._state = h
        self.wheel.set_points(h.points(), h.base_index())
        self.wheel.set_brightness(h.points()[h.base_index()][2])
        self.output.set_colors(h.colors(), h.base_index())

    def _commit(self, h, keep_image=True):
        if not keep_image:
            self._image_pixels = None
        self.history.push(h)
        self._show(h)

    def _commit_current(self):
        self._commit(self._state)

    def load(self, h):
        self._image_pixels = None
        self._commit(h)

    def undo(self):
        self._image_pixels = None
        self._show(self.history.undo())

    def redo(self):
        self._image_pixels = None
        self._show(self.history.redo())

    def _point_moved(self, index, angle, saturation):
        self._image_pixels = None
        self._preview(self._state.move_point(index, angle, saturation))

    def _count_changed(self, n):
        if self._image_pixels is not None:
            rgb, alpha = self._image_pixels
            try:
                self._commit(self._state.with_colors(dominant_colors(rgb, n, alpha=alpha)))
            except C.ColorError as e:
                self.studio.show_error(str(e))
                self._show(self._state)
        else:
            self._commit(self._state.with_count(n))

    def _pick_base(self):
        color = _pick_color(self, self._state.base_color(), "基準色")
        if color:
            self._commit(self._state.with_base_color(color), keep_image=False)

    def _base_hex_edited(self):
        text = self.base_hex.text()
        if text == self._state.base_color():
            return
        try:
            self._commit(self._state.with_base_color(C.normalize_hex(text)), keep_image=False)
        except C.ColorError as e:
            self.studio.show_error(str(e))
            self.base_hex.setText(self._state.base_color())

    def _open_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "画像を開く", "", image_file_filter())
        if path:
            self.load_image_file(path)

    def load_image_file(self, path):
        try:
            image, rgb, alpha = load_image(path)
            colors = dominant_colors(rgb, self._state.count, alpha=alpha)
            state = self._state.with_colors(colors)
        except C.ColorError as e:
            self.studio.show_error(str(e))
            return
        self.thumb.setPixmap(QPixmap.fromImage(image).scaled(
            _THUMB_SIDE, _THUMB_SIDE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.thumb.setToolTip(path)
        self._image_pixels = (rgb, alpha)
        self.history.push(state)
        self._show(state)
        if len(colors) < self._state.count:
            self.studio.show_status(f"画像の色が少ないため、{len(colors)} 色になりました。")
        else:
            self.studio.show_status("画像の代表色からパレットを作りました(配色ルールはカスタム)。")

    def _extend_swatch_menu(self, menu, i):
        color = self.output.colors()[i]
        menu.addAction("この色を基準色にする", lambda: self._commit(self._state.with_base_color(color), keep_image=False))


class LibraryTab(QWidget):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio = studio
        self.library = studio.library
        layout = QVBoxLayout(self)
        if self.library is None:
            msg = QLabel(f"ライブラリを使えません: {studio.library_error}")
            msg.setWordWrap(True)
            layout.addWidget(msg)
            layout.addStretch(1)
            return
        hint = QLabel(f"保存先: {self.library.path}")
        hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        body = QHBoxLayout()
        self.list = QListWidget(self)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setIconSize(QSize(96, 16))
        self.list.itemSelectionChanged.connect(self._selection_changed)
        self.list.itemDoubleClicked.connect(lambda _item: self.open_selected())
        body.addWidget(self.list, 1)
        buttons = QVBoxLayout()
        for text, handler in (("開いて編集", self.open_selected), ("名前の変更...", self._rename),
                              ("複製", self._duplicate), ("削除", self._delete), ("上へ", lambda: self._move(-1)),
                              ("下へ", lambda: self._move(1)), ("書き出し (JSON)...", self._export),
                              ("読み込み (JSON)...", self._import)):
            b = QPushButton(text, self)
            b.clicked.connect(handler)
            buttons.addWidget(b)
        buttons.addStretch(1)
        body.addLayout(buttons)
        layout.addLayout(body, 1)
        self.output = ColorOutput(studio, None, None, self)
        layout.addWidget(self.output)
        self.library.add_listener(self.reload)
        self.reload()

    def reload(self):
        selected = set(self.selected_ids())
        self.list.blockSignals(True)
        self.list.clear()
        for e in self.library.entries():
            item = QListWidgetItem(strip_icon(e["colors"], 96, 16),
                                   f"{e['name']}   ·  {KIND_LABELS[e['kind']]} · {len(e['colors'])}色")
            item.setData(Qt.ItemDataRole.UserRole, e["id"])
            self.list.addItem(item)
            item.setSelected(e["id"] in selected)
        self.list.blockSignals(False)
        self._selection_changed()

    def selected_ids(self):
        return [item.data(Qt.ItemDataRole.UserRole) for item in self.list.selectedItems()]

    def select_id(self, entry_id):
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole) == entry_id)

    def _current(self):
        ids = self.selected_ids()
        if not ids:
            self.studio.show_status("ライブラリの一覧で項目を選んでください。")
            return None
        try:
            return self.library.get(ids[0])
        except LibraryError as e:
            self.studio.show_error(str(e))
            return None

    def _selection_changed(self):
        ids = self.selected_ids()
        entry = None
        if ids:
            try:
                entry = self.library.get(ids[0])
            except LibraryError:
                entry = None
        if entry:
            self.output.set_colors(entry["colors"], name_hint=entry["name"])
        else:
            self.output.set_colors([])

    def open_selected(self):
        entry = self._current()
        if entry:
            self.studio.open_entry(entry)

    def _rename(self):
        entry = self._current()
        if not entry:
            return
        name = ask_name(self, "名前の変更", "新しい名前:", entry["name"])
        if name:
            self._guard(self.library.rename, entry["id"], name)

    def _duplicate(self):
        entry = self._current()
        if entry:
            copy = self._guard(self.library.duplicate, entry["id"])
            if copy:
                self.select_id(copy["id"])

    def _delete(self):
        ids = self.selected_ids()
        if not ids:
            return
        answer = QMessageBox.question(self, "削除", f"選んだ {len(ids)} 件をライブラリから削除しますか?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        for entry_id in ids:
            self._guard(self.library.delete, entry_id)

    def _move(self, offset):
        ids = self.selected_ids()
        if ids:
            self._guard(self.library.move, ids[0], offset)
            self.select_id(ids[0])

    def _export(self):
        ids = self.selected_ids() or [e["id"] for e in self.library.entries()]
        if not ids:
            self.studio.show_status("書き出す項目がありません。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "ライブラリを書き出す", "color_studio_library.json", "JSON (*.json)")
        if path:
            n = self._guard(self.library.export, ids, path)
            if n:
                self.studio.show_done(f"{n} 件を書き出しました。", path)

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "ライブラリを読み込む", "", "JSON (*.json);;すべてのファイル (*)")
        if not path:
            return
        result = self._guard(self.library.import_file, path)
        if result:
            added, dropped = result
            note = f"読めなかった {dropped} 件は飛ばしました。" if dropped else ""
            self.studio.show_done(f"{len(added)} 件を読み込みました。", note)

    def _guard(self, fn, *args):
        try:
            return fn(*args)
        except (LibraryError, OSError) as e:
            self.studio.show_error(str(e))
            return None


class StudioWindow(QWidget):
    def __init__(self, ctx):
        super().__init__(ctx.parent_widget, Qt.WindowType.Window)
        self.ctx = ctx
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1040, 720)
        self.library, self.library_error = load_library(ctx)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        self.gradient_tab = GradientTab(self)
        self.palette_tab = PaletteTab(self)
        self.library_tab = LibraryTab(self)
        self.tabs.addTab(self.gradient_tab, "グラデーション")
        self.tabs.addTab(self.palette_tab, "配色パレット")
        self.tabs.addTab(self.library_tab, "ライブラリ")
        layout.addWidget(self.tabs, 1)

        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.status.setAccessibleName("状態")
        layout.addWidget(self.status)

        # 独立ウィンドウなので、本体のメニューの Ctrl+Z(本体の Undo)とはぶつからない
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=lambda: self._history("undo"))
        QShortcut(QKeySequence.StandardKey.Redo, self, activated=lambda: self._history("redo"))
        self._report_library_recovery()

    def _history(self, action):
        tab = self.tabs.currentWidget()
        if hasattr(tab, action):
            getattr(tab, action)()

    def show_status(self, text):
        self.status.setText(text)

    def show_done(self, text, detail=""):
        """済んだ操作。状態の行に加えて、本体と同じ知らせをウィンドウの右下に出す。"""
        self.status.setText(text + detail)
        ui.show_toast(self, text)

    def show_error(self, text):
        self.status.setText(text)
        QMessageBox.warning(self, WINDOW_TITLE, text)

    def _report_library_recovery(self):
        lib = self.library
        if lib is None or getattr(lib, "recovery_reported", False):
            return
        if lib.recovered_to:
            self.show_status(f"ライブラリのファイルが壊れていたため、{lib.recovered_to} に退避して空のライブラリで始めました。")
        elif lib.dropped_count:
            self.show_status(f"ライブラリの {lib.dropped_count} 件が読めなかったため、表示していません。")
        lib.recovery_reported = True

    def open_entry(self, entry):
        """ライブラリの項目を、作り方のデータから編集できる状態で開く。"""
        source = entry.get("source") or {}
        try:
            if entry["kind"] == "gradient":
                if source.get("stops"):
                    g = Gradient.from_dict(source)
                else:
                    n = len(entry["colors"])
                    g = Gradient(stops=tuple(Stop(i / max(n - 1, 1), c) for i, c in enumerate(entry["colors"])),
                                 count=max(n, gradient.MIN_COUNT))
                self.gradient_tab.load(g)
                self.tabs.setCurrentWidget(self.gradient_tab)
            else:
                if source.get("rule"):
                    h = Harmony.from_dict(source)
                else:
                    h = Harmony().with_colors(entry["colors"][:harmony.MAX_COUNT])
                self.palette_tab.load(h)
                self.tabs.setCurrentWidget(self.palette_tab)
        except (C.ColorError, ValueError) as e:
            self.show_error(f"「{entry['name']}」を開けません: {e}")
            return
        self.show_status(f"「{entry['name']}」を開きました。")


_WINDOWS = {}


def open_studio(ctx, entry=None):
    """そのタブのウィンドウを開く(既にあれば前に出す)。"""
    key = id(ctx)
    window = _WINDOWS.get(key)
    if window is not None:
        try:
            alive = window.ctx is ctx
            window.isVisible()
        except RuntimeError:
            alive = False
        if not alive:
            window = None
    if window is None:
        window = StudioWindow(ctx)
        _WINDOWS[key] = window
        window.destroyed.connect(lambda *_args, k=key: _WINDOWS.pop(k, None))
    if entry is not None:
        window.open_entry(entry)
    window.show()
    window.raise_()
    window.activateWindow()
    return window
