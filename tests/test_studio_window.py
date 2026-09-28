"""ウィンドウとパネルを FakePluginContext で動かす(モーダルな確認は差し替える)。"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import GRAPHICA_AVAILABLE, requires_graphica  # noqa: E402

pytestmark = requires_graphica

if GRAPHICA_AVAILABLE:
    from graphica.plugin import Dataset
    from graphica.plugin.testing import FakeGraphicaPluginAPI, FakePluginContext
    from PySide6.QtGui import QGuiApplication, QImage
    from PySide6.QtWidgets import QDialog, QMessageBox

    from color_studio import MENU_TEXT, PANEL_NAME, register
    from color_studio import output as output_module
    from color_studio import studio_window
    from color_studio.harmony import Harmony
    from color_studio.library import get_library
    from color_studio.panel import LibraryPanel


@pytest.fixture(autouse=True)
def close_windows():
    yield
    for w in list(studio_window._WINDOWS.values()):
        w.close()
        w.deleteLater()
    studio_window._WINDOWS.clear()


@pytest.fixture
def prompts(monkeypatch):
    """名前の入力・上書きの確認・エラー表示を差し替え、呼ばれた内容を記録する。"""
    rec = {"names": [], "questions": [], "warnings": [], "answer": QMessageBox.StandardButton.Yes}

    def fake_ask(parent, title, label, default=""):
        rec["names"].append((title, default))
        return rec.get("name", default)

    def fake_question(parent, title, text, *a, **k):
        rec["questions"].append(text)
        return rec["answer"]

    monkeypatch.setattr(output_module, "ask_name", fake_ask)
    monkeypatch.setattr(studio_window, "ask_name", fake_ask)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda p, t, text, *a, **k: rec["warnings"].append(text)))
    return rec


def _ds(name, color="#1f77b4"):
    return Dataset(name=name, df=pd.DataFrame({"x": [0, 1], "y": [0, 1]}), x_col_name="x", y_col_name="y", color=color)


def _ctx(tmp_path, **kw):
    return FakePluginContext(plugin_name="color_studio", data_dir=str(tmp_path / "data"), **kw)


def test_register_adds_menu_and_panel():
    api = FakeGraphicaPluginAPI(plugin_name="color_studio")
    register(api)
    assert [a.text for a in api.menu_actions] == [MENU_TEXT]
    assert list(api.panels) == [PANEL_NAME]


def test_menu_opens_one_window_per_tab(tmp_path):
    api = FakeGraphicaPluginAPI(plugin_name="color_studio")
    register(api)
    ctx, other = _ctx(tmp_path), _ctx(tmp_path)
    api.menu_actions[0].callback(ctx)
    first = studio_window._WINDOWS[id(ctx)]
    api.menu_actions[0].callback(ctx)
    assert studio_window._WINDOWS[id(ctx)] is first
    api.menu_actions[0].callback(other)
    assert studio_window._WINDOWS[id(other)] is not first
    first.grab()


def test_gradient_tab_count_space_and_undo(tmp_path):
    win = studio_window.open_studio(_ctx(tmp_path))
    tab = win.gradient_tab
    tab.count_spin.setValue(9)
    assert len(tab.output.colors()) == 9
    tab.space_combo.setCurrentIndex(tab.space_combo.findData("rgb"))
    assert tab.state().space == "rgb"
    tab.undo()
    assert tab.state().space == "oklab" and tab.state().count == 9
    tab.undo()
    assert tab.state().count == 7
    tab.redo()
    assert tab.state().count == 9
    tab.stop_hex.setText("#ff0000")
    tab.stop_hex.editingFinished.emit()
    assert tab.state().stops[0].color == "#ff0000"
    assert tab.output.colors()[0] == "#ff0000"


def test_gradient_tab_rejects_a_bad_hex(tmp_path, prompts):
    win = studio_window.open_studio(_ctx(tmp_path))
    tab = win.gradient_tab
    tab.stop_hex.setText("nope")
    tab.stop_hex.editingFinished.emit()
    assert prompts["warnings"] and tab.stop_hex.text() == tab.state().stops[0].color


def test_palette_tab_rule_drag_and_random(tmp_path):
    win = studio_window.open_studio(_ctx(tmp_path))
    tab = win.palette_tab
    tab.rule_combo.setCurrentIndex(tab.rule_combo.findData("triad"))
    assert tab.state().rule == "triad" and len(tab.output.colors()) == 5
    before = tab.state()
    tab._point_moved(1, 200.0, 0.5)
    tab._commit_current()
    assert tab.state() != before
    tab.undo()
    assert tab.state() == before
    tab.base_hex.setText("#e8622a")
    tab.base_hex.editingFinished.emit()
    assert tab.state().base_color() == "#e8622a"
    tab.count_spin.setValue(8)
    assert len(tab.output.colors()) == 8


def test_palette_from_image(tmp_path):
    img = QImage(60, 30, QImage.Format.Format_RGB32)
    for x in range(60):
        for y in range(30):
            img.setPixelColor(x, y, ["#264653", "#e9c46a", "#e76f51"][x // 20])
    path = str(tmp_path / "three.png")
    assert img.save(path)
    win = studio_window.open_studio(_ctx(tmp_path))
    tab = win.palette_tab
    tab.count_spin.setValue(3)
    tab.load_image_file(path)
    assert tab.state().rule == "custom"
    assert sorted(tab.output.colors()) == sorted(["#264653", "#e9c46a", "#e76f51"])
    assert tab.thumb.pixmap() is not None and not tab.thumb.pixmap().isNull()


def test_image_with_too_few_colors_shows_an_error(tmp_path, prompts):
    img = QImage(10, 10, QImage.Format.Format_RGB32)
    img.fill(0x336699)
    path = str(tmp_path / "flat.png")
    img.save(path)
    win = studio_window.open_studio(_ctx(tmp_path))
    before = win.palette_tab.state()
    win.palette_tab.load_image_file(path)
    assert prompts["warnings"] and win.palette_tab.state() == before
    win.palette_tab.load_image_file(str(tmp_path / "missing.png"))
    assert len(prompts["warnings"]) == 2


def test_save_to_library_and_overwrite(tmp_path, prompts):
    ctx = _ctx(tmp_path)
    win = studio_window.open_studio(ctx)
    prompts["name"] = "試料 A〜E"
    win.palette_tab.output._save()
    lib = get_library(ctx.data_dir)
    assert lib.names() == ["試料 A〜E"]
    assert lib.entries()[0]["source"]["rule"] == "analogous"
    win.palette_tab.rule_combo.setCurrentIndex(win.palette_tab.rule_combo.findData("shades"))
    win.palette_tab.output._save()
    assert prompts["questions"] and lib.entries()[0]["source"]["rule"] == "shades"
    assert win.library_tab.list.count() == 1  # リスナーで一覧が更新される


def test_register_palette_and_named_colors(tmp_path, prompts, monkeypatch):
    ctx = _ctx(tmp_path, color_palettes={"既存": ["#000000"]}, named_colors=[{"name": "水", "color": "#000000"}])
    win = studio_window.open_studio(ctx)
    out = win.palette_tab.output
    prompts["name"] = "既存"
    prompts["answer"] = QMessageBox.StandardButton.No
    out.handoff.register_palette(out.colors(), "x")
    assert ctx.color_palettes()["既存"] == ["#000000"]
    prompts["answer"] = QMessageBox.StandardButton.Yes
    out.handoff.register_palette(out.colors(), "x")
    assert ctx.color_palettes()["既存"] == out.colors()
    assert "パレット管理" in win.status.text()

    def accept(dialog):
        dialog._name_edits[0].setText("水")
        dialog._conflict_boxes[0].setCurrentIndex(dialog._conflict_boxes[0].findData("overwrite"))
        dialog._name_edits[1].setText("エタノール")
        for e in dialog._name_edits[2:]:
            e.setText("")
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(output_module.NamedColorsDialog, "exec", accept)
    out.handoff.add_named_colors(out.colors(), "")
    named = ctx.named_colors()
    assert [e["name"] for e in named] == ["水", "エタノール"]
    assert named[0]["color"] == out.colors()[0]


def test_apply_to_selected_datasets(tmp_path):
    a, b = _ds("a"), _ds("b")
    ctx = _ctx(tmp_path, datasets=[a, b], selected=[a, b])
    win = studio_window.open_studio(ctx)
    out = win.palette_tab.output
    out.apply_button.click()
    assert [a.color, b.color] == out.colors()[:2]
    assert len(ctx.undo_descriptions) == 2
    empty = _ctx(tmp_path)
    win2 = studio_window.open_studio(empty)
    win2.palette_tab.output.apply_button.click()
    assert "選んでから" in win2.status.text()


def test_copy_all_hex(tmp_path):
    win = studio_window.open_studio(_ctx(tmp_path))
    win.gradient_tab.output._copy_all()
    assert QGuiApplication.clipboard().text() == ", ".join(win.gradient_tab.output.colors())


def test_loaded_palette_is_shown_as_is(tmp_path):
    win = studio_window.open_studio(_ctx(tmp_path))
    tab = win.palette_tab
    tab.load(Harmony().with_colors(["#c0504d", "#9bbb59", "#1f77b4"]))
    assert tab.output.strip.colors() == ["#c0504d", "#9bbb59", "#1f77b4"]
    win.grab()


def test_library_tab_open_rename_duplicate_delete(tmp_path, prompts):
    ctx = _ctx(tmp_path)
    lib = get_library(ctx.data_dir)
    lib.add("gradient", "温度", ["#0d47a1", "#f4e06a"], {"stops": [
        {"position": 0, "color": "#0d47a1"}, {"position": 1, "color": "#f4e06a"}], "space": "oklch", "count": 9})
    lib.add("palette", "外から", ["#264653", "#2a9d8f", "#e9c46a"])  # 作り方のデータが無い
    win = studio_window.open_studio(ctx)
    lt = win.library_tab
    assert lt.list.count() == 2
    lt.select_id(lib.entries()[0]["id"])
    lt.open_selected()
    assert win.tabs.currentWidget() is win.gradient_tab
    assert win.gradient_tab.state().space == "oklch" and win.gradient_tab.state().count == 9
    lt.select_id(lib.entries()[1]["id"])
    assert lt.output.colors() == ["#264653", "#2a9d8f", "#e9c46a"]
    lt.open_selected()
    assert win.palette_tab.output.colors() == ["#264653", "#2a9d8f", "#e9c46a"]
    prompts["name"] = "外から2"
    lt._rename()
    lt._duplicate()
    assert lib.names() == ["温度", "外から2", "外から2 のコピー"]
    lt.select_id(lib.entries()[2]["id"])
    lt._delete()
    assert lib.names() == ["温度", "外から2"]


def test_library_export_import_round_trip(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    lib = get_library(ctx.data_dir)
    lib.add("palette", "P", ["#111111", "#222222", "#333333"])
    win = studio_window.open_studio(ctx)
    out = str(tmp_path / "share.json")
    monkeypatch.setattr(studio_window.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, "")))
    monkeypatch.setattr(studio_window.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (out, "")))
    win.library_tab._export()
    win.library_tab._import()
    assert lib.names() == ["P", "P (2)"]


def test_panel_lists_library_and_applies(tmp_path):
    a = _ds("a")
    ctx = _ctx(tmp_path, datasets=[a], selected=[a])
    panel = LibraryPanel(ctx)
    lib = get_library(ctx.data_dir)
    assert panel.list.count() == 0 and "空" in panel.status.text()
    lib.add("palette", "P", ["#123456", "#abcdef", "#fedcba"])
    assert panel.list.count() == 1
    panel.list.setCurrentRow(0)
    panel.apply_button.click()
    assert a.color == "#123456"
    panel.edit_button.click()
    win = studio_window._WINDOWS[id(ctx)]
    assert win.palette_tab.output.colors() == ["#123456", "#abcdef", "#fedcba"]
    panel.list.clearSelection()
    panel.list.setCurrentItem(None)
    panel.apply_button.click()
    assert "選んでください" in panel.status.text()
    panel.deleteLater()


def test_corrupt_library_is_reported_once(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "library.json").write_text("{", encoding="utf-8")
    win = studio_window.open_studio(_ctx(tmp_path))
    assert "退避" in win.status.text()


def test_newer_library_disables_saving(tmp_path):
    data = tmp_path / "newer"
    data.mkdir()
    (data / "library.json").write_text('{"format": "graphica-color-studio", "version": 99}', encoding="utf-8")
    ctx = FakePluginContext(plugin_name="color_studio", data_dir=str(data))
    win = studio_window.open_studio(ctx)
    assert win.library is None
    assert not win.palette_tab.output.save_button.isEnabled()
    panel = LibraryPanel(ctx)
    assert "新しい版" in panel.status.text()
    panel.deleteLater()


def test_wheel_render_is_cheap_enough():
    import time
    from color_studio.wheel import render_wheel_rgba
    t0 = time.perf_counter()
    render_wheel_rgba(480, "ryb", 0.9)
    assert time.perf_counter() - t0 < 0.5
    assert np.asarray(render_wheel_rgba(8)).dtype == np.uint8
