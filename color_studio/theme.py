"""自前で描く部品に、本体のテーマの色を渡す(graphica.plugin.ui、プラグイン API 2.2)。

描くたびに読むので、明暗やテーマカラーを替えると次の描画から替わる。本体が無いとき(Qt だけの単体テスト)は
部品のパレットの近い色を使う。
"""
from PySide6.QtGui import QColor, QPalette

_FALLBACK_ROLES = {
    "accent": QPalette.ColorRole.Highlight,
    "border": QPalette.ColorRole.Midlight,
    "border_strong": QPalette.ColorRole.Mid,
    "text_primary": QPalette.ColorRole.Text,
    "text_secondary": QPalette.ColorRole.PlaceholderText,
}


def theme_qcolor(widget, name):
    """name は graphica.plugin.ui.THEME_COLOR_NAMES のうち、上の _FALLBACK_ROLES にあるもの。"""
    try:
        from graphica.plugin import ui
    except ImportError:
        return widget.palette().color(_FALLBACK_ROLES[name])
    return QColor(ui.theme_color(name))
