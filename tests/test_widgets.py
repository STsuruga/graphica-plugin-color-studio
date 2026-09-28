import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import requires_qt  # noqa: E402

pytestmark = requires_qt

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from color_studio import colors as C  # noqa: E402
from color_studio.gradient import Gradient, Stop  # noqa: E402
from color_studio.gradient_bar import GradientBar  # noqa: E402
from color_studio.harmony import Harmony  # noqa: E402
from color_studio.swatches import SwatchStrip  # noqa: E402
from color_studio.wheel import ColorWheel, render_wheel_rgba  # noqa: E402


def _hue_at(rgba, y, x):
    return C.rgb_to_hsv(rgba[y, x, :3] / 255.0)[0]


def test_wheel_image_layout():
    size = 201
    ryb = render_wheel_rgba(size, "ryb")
    rgb = render_wheel_rgba(size, "rgb")
    assert ryb.shape == (size, size, 4)
    assert ryb[0, 0, 3] == 0  # 円の外は透明
    assert tuple(ryb[100, 100, :3]) == (255, 255, 255)  # 中心は彩度 0
    assert _hue_at(ryb, 2, 100) == pytest.approx(0, abs=4)      # 上は赤
    assert _hue_at(rgb, 100, 198) == pytest.approx(90, abs=4)   # RGB の右(90°)は黄緑
    assert _hue_at(ryb, 100, 198) == pytest.approx(47, abs=4)   # RYB の右(90°)は山吹
    assert _hue_at(ryb, 198, 100) == pytest.approx(95, abs=4)   # RYB の下(180°)は緑 = 赤の補色


def test_wheel_image_respects_cvd_and_brightness():
    normal = render_wheel_rgba(51, "ryb")
    deut = render_wheel_rgba(51, "ryb", cvd_type="deuteranopia")
    dark = render_wheel_rgba(51, "ryb", brightness=0.5)
    assert not np.array_equal(normal, deut)
    assert dark[25, 25, :3].max() == 128


def _show(widget, w=320, h=320):
    widget.resize(w, h)
    widget.show()
    QTest.qWaitForWindowExposed(widget)
    return widget


def test_dragging_a_wheel_point_reports_polar_coordinates():
    wheel = _show(ColorWheel())
    h = Harmony(rule="triad", count=3, base=(0, 0.8, 0.9))
    wheel.set_points(h.points(), h.base_index())
    moves, done = [], []
    wheel.pointMoved.connect(lambda i, a, s: moves.append((i, a, s)))
    wheel.interactionFinished.connect(lambda: done.append(True))
    start = wheel.point_position(h.points()[1]).toPoint()
    target = wheel.point_position((200.0, 0.5, 0.9)).toPoint()
    QTest.mousePress(wheel, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(wheel, target)
    QTest.mouseRelease(wheel, Qt.MouseButton.LeftButton, pos=target)
    i, angle, sat = moves[-1]
    assert i == 1
    assert angle == pytest.approx(200, abs=2) and sat == pytest.approx(0.5, abs=0.02)
    assert done == [True]
    wheel.grab()  # paintEvent が例外なく走る


def test_pressing_empty_wheel_area_moves_the_base_point():
    wheel = _show(ColorWheel())
    h = Harmony(rule="analogous", count=5, base=(0, 0.3, 0.9))
    wheel.set_points(h.points(), h.base_index())
    moves = []
    wheel.pointMoved.connect(lambda i, a, s: moves.append(i))
    QTest.mousePress(wheel, Qt.MouseButton.LeftButton, pos=wheel.point_position((180.0, 0.9, 0.9)).toPoint())
    assert moves == [h.base_index()]


def test_wheel_keyboard_rotates_selected_point():
    wheel = _show(ColorWheel())
    wheel.set_points([(10.0, 0.5, 0.9)], 0)
    moves = []
    wheel.pointMoved.connect(lambda i, a, s: moves.append((a, s)))
    QTest.keyClick(wheel, Qt.Key.Key_Right)
    QTest.keyClick(wheel, Qt.Key.Key_Up)
    assert moves == [(12.0, 0.5), (10.0, pytest.approx(0.52))]


def test_gradient_bar_drag_add_and_delete():
    bar = _show(GradientBar(), 420, 90)
    g = Gradient(stops=(Stop(0, "#000000"), Stop(1, "#ffffff")), count=5)
    bar.set_gradient(g)
    changes, done = [], []
    bar.gradientChanged.connect(changes.append)
    bar.interactionFinished.connect(lambda: done.append(True))

    rect = bar._bar_rect()
    handle = QPoint(int(bar._x_of(1.0)), int(rect.bottom() + 12))
    to = QPoint(int(bar._x_of(0.75)), int(rect.bottom() + 12))
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=handle)
    QTest.mouseMove(bar, to)
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=to)
    assert changes[-1].stops[1].position == pytest.approx(0.75, abs=0.01)
    assert done == [True]

    QTest.mouseDClick(bar, Qt.MouseButton.LeftButton, pos=QPoint(int(bar._x_of(0.4)), int(rect.center().y())))
    assert len(changes[-1].stops) == 3 and bar.selected_index() == 2
    bar.setFocus()
    QTest.keyClick(bar, Qt.Key.Key_Delete)
    assert len(changes[-1].stops) == 2
    QTest.keyClick(bar, Qt.Key.Key_Delete)  # 2個より減らせない
    assert len(changes[-1].stops) == 2
    bar.grab()


def test_gradient_bar_double_click_handle_requests_color():
    bar = _show(GradientBar(), 420, 90)
    bar.set_gradient(Gradient())
    asked = []
    bar.stopColorRequested.connect(asked.append)
    QTest.mouseDClick(bar, Qt.MouseButton.LeftButton, pos=QPoint(int(bar._x_of(0.0)), int(bar._bar_rect().bottom() + 12)))
    assert asked == [0]


def test_swatch_click_and_warning_marks():
    strip = _show(SwatchStrip(), 500, 80)
    strip.set_colors(["#c0504d", "#9bbb59", "#1f77b4"], base_index=0)
    strip.set_warnings([(0, 1, 7.8), (0, 2, 5.0)])
    assert strip._warn_pairs == {(0, 1)}
    clicked = []
    strip.swatchClicked.connect(clicked.append)
    QTest.mouseClick(strip, Qt.MouseButton.LeftButton, pos=strip._cell(2).center().toPoint())
    assert clicked == [2]
    assert strip.index_at(QPointF(-5, 5)) is None
    strip.set_cvd("tritanopia")
    strip.grab()
