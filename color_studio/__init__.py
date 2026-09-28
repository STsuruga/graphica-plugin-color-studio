"""カラースタジオ(P-901)。本体は graphica_plugin_color_studio という名前で読み込むので、中は相対 import にする。"""

MENU_TEXT = "カラースタジオを開く..."
PANEL_NAME = "カラースタジオ"


def _open_studio(ctx):
    ctx.show_message("カラースタジオは準備中です。")


def register(api):
    api.register_menu_action(MENU_TEXT, _open_studio)
