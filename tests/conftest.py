# tests/conftest.py
"""
テスト共通のフィクスチャ。

Graphica本体(graphica.plugin.testing)は仮想環境に `pip install "graphica-plot>=2.0,<3"` で
入れておく。入っていない環境では、本体に依存しない純粋な計算のテストだけが走り、
配線・読み込み・画面のテストは skip される(README の「開発環境」参照)。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover - PySide6が無い環境
    QApplication = None

try:
    import graphica.plugin.testing  # noqa: F401
    GRAPHICA_AVAILABLE = True
except ImportError:
    GRAPHICA_AVAILABLE = False


requires_graphica = pytest.mark.skipif(
    not GRAPHICA_AVAILABLE,
    reason='Graphica本体が未インストールです(pip install "graphica-plot>=2.0,<3")',
)

requires_qt = pytest.mark.skipif(QApplication is None, reason="PySide6 が未インストールです")


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Graphica本体と同じく、セッション全体で1つだけ QApplication を用意する。"""
    if QApplication is None:
        yield None
        return
    app = QApplication.instance() or QApplication([])
    yield app
