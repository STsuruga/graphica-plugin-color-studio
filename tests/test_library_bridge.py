import json
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import GRAPHICA_AVAILABLE, requires_graphica  # noqa: E402

from color_studio import bridge  # noqa: E402
from color_studio.library import (  # noqa: E402
    FILENAME, Library, LibraryError, NewerLibraryError, get_library, unique_name,
)

if GRAPHICA_AVAILABLE:
    from graphica.plugin import Dataset
    from graphica.plugin.testing import FakePluginContext

PALETTE = ["#264653", "#2a9d8f", "#e9c46a", "#f4a261", "#e76f51"]


# ---------------------------------------------------------------- library

@pytest.fixture
def lib(tmp_path):
    return Library(str(tmp_path / FILENAME))


def test_empty_when_no_file(lib):
    assert lib.entries() == []


def test_add_persists_and_reloads(lib, tmp_path):
    e = lib.add("palette", "  試料  A〜E ", PALETTE, {"rule": "custom"})
    assert e["name"] == "試料 A〜E"
    again = Library(str(tmp_path / FILENAME))
    assert again.entries() == [e]
    data = json.loads((tmp_path / FILENAME).read_text(encoding="utf-8"))
    assert data["format"] == "graphica-color-studio" and data["version"] == 1


def test_duplicate_name_is_refused_unless_replacing(lib):
    first = lib.add("palette", "A", PALETTE)
    with pytest.raises(LibraryError):
        lib.add("gradient", "A", PALETTE)
    replaced = lib.add("palette", "A", ["#000000", "#ffffff"], replace_id=first["id"])
    assert replaced["id"] == first["id"] and replaced["created"] == first["created"]
    assert [e["colors"] for e in lib.entries()] == [["#000000", "#ffffff"]]


@pytest.mark.parametrize("name, colors", [("", PALETTE), ("x" * 61, PALETTE), ("A", []), ("A", ["nope"])])
def test_invalid_entries_are_refused(lib, name, colors):
    with pytest.raises(ValueError):
        lib.add("palette", name, colors)
    assert lib.entries() == []


def test_rename_duplicate_delete_move(lib):
    a = lib.add("palette", "A", PALETTE)
    b = lib.add("gradient", "B", PALETTE[:2])
    lib.rename(a["id"], "A2")
    with pytest.raises(LibraryError):
        lib.rename(a["id"], "B")
    c = lib.duplicate(a["id"])
    assert c["name"] == "A2 のコピー" and c["id"] != a["id"]
    assert lib.duplicate(a["id"])["name"] == "A2 のコピー (2)"
    lib.move(c["id"], -10)
    assert lib.names()[0] == "A2 のコピー"
    lib.delete(b["id"])
    assert "B" not in lib.names()
    with pytest.raises(LibraryError):
        lib.delete(b["id"])
    assert [e["name"] for e in lib.entries("gradient")] == []


def test_corrupt_file_is_moved_aside(tmp_path):
    path = tmp_path / FILENAME
    path.write_text("{ not json", encoding="utf-8")
    lib = Library(str(path))
    assert lib.entries() == []
    assert lib.recovered_to and os.path.exists(lib.recovered_to)
    assert not path.exists()


def test_bad_entries_are_dropped_one_by_one(tmp_path):
    path = tmp_path / FILENAME
    path.write_text(json.dumps({"format": "graphica-color-studio", "version": 1, "entries": [
        {"kind": "palette", "name": "ok", "colors": ["#000000"]},
        {"kind": "palette", "name": "bad", "colors": ["zzz"]},
        {"kind": "mystery", "name": "bad2", "colors": ["#000000"]},
    ]}), encoding="utf-8")
    lib = Library(str(path))
    assert lib.names() == ["ok"] and lib.dropped_count == 2


def test_newer_version_is_not_touched(tmp_path):
    path = tmp_path / FILENAME
    path.write_text(json.dumps({"format": "graphica-color-studio", "version": 99, "entries": []}), encoding="utf-8")
    with pytest.raises(NewerLibraryError):
        Library(str(path))
    assert path.exists()


def test_failed_write_keeps_the_old_file(lib, tmp_path, monkeypatch):
    lib.add("palette", "A", PALETTE)
    before = (tmp_path / FILENAME).read_text(encoding="utf-8")

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        lib.add("palette", "B", PALETTE)
    assert (tmp_path / FILENAME).read_text(encoding="utf-8") == before
    assert [p.name for p in tmp_path.iterdir()] == [FILENAME]


def test_changes_by_another_process_are_picked_up(lib, tmp_path):
    lib.add("palette", "A", PALETTE)
    other = Library(str(tmp_path / FILENAME))
    other.add("palette", "B", PALETTE)
    os.utime(tmp_path / FILENAME, ns=(1, 1))  # 更新時刻の粒度が粗い環境でも変化として見えるように
    assert lib.names() == ["A", "B"]


def test_export_and_import_with_name_conflicts(lib, tmp_path):
    a = lib.add("palette", "A", PALETTE)
    lib.add("gradient", "G", PALETTE[:2], {"space": "oklab"})
    out = tmp_path / "share.json"
    assert lib.export([a["id"]], str(out)) == 1
    added, dropped = lib.import_file(str(out))
    assert [e["name"] for e in added] == ["A (2)"] and dropped == 0
    assert added[0]["id"] != a["id"]
    with pytest.raises(LibraryError):
        lib.export([], str(out))
    (tmp_path / "junk.json").write_text("[]", encoding="utf-8")
    with pytest.raises(LibraryError):
        lib.import_file(str(tmp_path / "junk.json"))


def test_listeners_are_called_and_dead_ones_dropped(lib):
    calls = []

    class Widget:
        def refresh(self):
            calls.append("w")

    w = Widget()
    lib.add_listener(w.refresh)
    lib.add_listener(lambda: calls.append("f"))
    lib.add("palette", "A", PALETTE)
    assert calls == ["w", "f"]
    del w
    lib.add("palette", "B", PALETTE)
    assert calls == ["w", "f", "f"]


def test_get_library_is_shared_per_folder(tmp_path):
    assert get_library(str(tmp_path)) is get_library(str(tmp_path) + os.sep)


def test_unique_name():
    assert unique_name("A", {"B"}) == "A"
    assert unique_name("A", {"A", "A (2)"}) == "A (3)"


# ---------------------------------------------------------------- bridge

def _ds(name, color="#1f77b4", kind="1d"):
    return Dataset(name=name, df=pd.DataFrame({"x": [0, 1], "y": [0, 1]}), x_col_name="x", y_col_name="y",
                   color=color, data_kind=kind)


@requires_graphica
def test_named_colors_are_appended_in_order():
    ctx = FakePluginContext(named_colors=[{"name": "水", "color": "#1f77b4"}])
    result = bridge.add_named_colors(ctx, [("エタノール", "#E76F51"), ("酢酸", "#2a9d8f")])
    assert result["added"] == ["エタノール", "酢酸"]
    assert ctx.named_colors() == [
        {"name": "水", "color": "#1f77b4"},
        {"name": "エタノール", "color": "#e76f51"},
        {"name": "酢酸", "color": "#2a9d8f"},
    ]


@requires_graphica
@pytest.mark.parametrize("policy, expected", [
    (bridge.OVERWRITE, [{"name": "水", "color": "#e76f51"}]),
    (bridge.SKIP, [{"name": "水", "color": "#1f77b4"}]),
    (bridge.RENAME, [{"name": "水", "color": "#1f77b4"}, {"name": "水 (2)", "color": "#e76f51"}]),
])
def test_named_color_conflicts(policy, expected):
    ctx = FakePluginContext(named_colors=[{"name": "水", "color": "#1f77b4"}])
    plan = bridge.plan_named_colors(ctx, [("水", "#e76f51")])
    assert plan == [{"name": "水", "color": "#e76f51", "existing": "#1f77b4"}]
    bridge.add_named_colors(ctx, [("水", "#e76f51")], conflict=policy)
    assert ctx.named_colors() == expected


@requires_graphica
def test_invalid_named_color_writes_nothing():
    ctx = FakePluginContext(named_colors=[{"name": "水", "color": "#1f77b4"}])
    with pytest.raises(ValueError):
        bridge.add_named_colors(ctx, [("", "#000000")])
    assert ctx.named_colors() == [{"name": "水", "color": "#1f77b4"}]


@requires_graphica
def test_register_palette_and_conflicts():
    ctx = FakePluginContext(color_palettes={"既存": ["#000000"]})
    bridge.register_palette(ctx, "試料 A〜E", PALETTE)
    assert ctx.color_palettes()["試料 A〜E"] == PALETTE
    assert ctx.color_palettes()["既存"] == ["#000000"]
    with pytest.raises(bridge.PaletteExistsError):
        bridge.register_palette(ctx, "既存", PALETTE)
    bridge.register_palette(ctx, "既存", PALETTE, overwrite=True)
    assert ctx.color_palettes()["既存"] == PALETTE


@requires_graphica
def test_builtin_palette_name_is_refused_by_graphica():
    ctx = FakePluginContext()
    with pytest.raises(ValueError, match="組み込み"):
        bridge.register_palette(ctx, "Okabe-Ito(色覚多様性対応)", PALETTE)


@requires_graphica
def test_apply_to_selected_in_display_order_with_cycling():
    a, b, c, d, m = _ds("a"), _ds("b"), _ds("c"), _ds("d"), _ds("map", kind="2d_grid")
    ctx = FakePluginContext(datasets=[a, b, c, d, m], selected=[d, a, m, c])
    changed, total = bridge.apply_to_selected(ctx, ["#ff0000", "#00ff00"])
    assert (changed, total) == (3, 3)
    assert [x.color for x in (a, b, c, d)] == ["#ff0000", "#1f77b4", "#00ff00", "#ff0000"]
    assert ctx.undo_descriptions == [bridge.UNDO_TEXT] * 3


@requires_graphica
def test_apply_skips_datasets_that_already_have_the_color():
    a = _ds("a", color="#FF0000")
    ctx = FakePluginContext(datasets=[a], selected=[a])
    assert bridge.apply_to_selected(ctx, ["#ff0000"]) == (0, 1)
    assert ctx.undo_descriptions == []


@requires_graphica
def test_apply_with_nothing_selected():
    ctx = FakePluginContext(datasets=[_ds("a")])
    assert bridge.apply_to_selected(ctx, PALETTE) == (0, 0)
    with pytest.raises(ValueError):
        bridge.apply_to_selected(ctx, [])
