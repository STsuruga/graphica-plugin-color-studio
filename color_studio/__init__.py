"""カラースタジオ(P-901)。本体は graphica_plugin_color_studio という名前で読み込むので、中は相対 import にする。

Qt の画面は使うときに import する(register を軽く保ち、計算モジュールのテストに Qt を要らなくする)。
"""

MENU_TEXT = "カラースタジオを開く..."
PANEL_NAME = "カラースタジオ"


def _open_studio(ctx):
    from .studio_window import open_studio
    open_studio(ctx)


def _create_panel(ctx):
    from .panel import LibraryPanel
    return LibraryPanel(ctx)


def register(api):
    api.register_menu_action(MENU_TEXT, _open_studio)
    api.register_panel(PANEL_NAME, _create_panel, area="right")
