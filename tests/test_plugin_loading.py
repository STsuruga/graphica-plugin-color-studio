"""register() の配線と、本体と同じ読み込み経路・zip のインストールの確認。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from conftest import GRAPHICA_AVAILABLE, requires_graphica  # noqa: E402

if GRAPHICA_AVAILABLE:
    from graphica.plugin.testing import (
        FakeGraphicaPluginAPI,
        install_zip_like_graphica,
        load_plugin_like_graphica,
    )

PLUGIN_DIR = os.path.join(ROOT, "color_studio")


@requires_graphica
def test_register_adds_the_menu_action():
    from color_studio import MENU_TEXT, register

    api = FakeGraphicaPluginAPI(plugin_name="color_studio")
    register(api)
    assert [a.text for a in api.menu_actions] == [MENU_TEXT]


@requires_graphica
def test_loads_like_graphica(tmp_path):
    api, record = load_plugin_like_graphica(PLUGIN_DIR, work_dir=str(tmp_path))
    assert record["error"] is None
    assert api.registration_errors == []
    assert record["info"]["version"] == "1.0.0"


@requires_graphica
def test_built_zip_installs_like_graphica(tmp_path):
    from build_zip import build_plugin_zip

    zip_path = build_plugin_zip("color_studio", out_dir=str(tmp_path / "dist"))
    target = tmp_path / "plugins"
    target.mkdir()
    name = install_zip_like_graphica(zip_path, str(target))
    assert name == "color_studio"
    assert (target / "color_studio" / "plugin.json").is_file()
