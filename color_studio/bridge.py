"""Graphica 本体への受け渡し。窓口 ctx(PluginContext)のメソッドだけを使う。

登録色と配色パレットは本体でも別物:
    登録色     = 名前と1色の対応(同じ物質にいつも同じ色)。ctx.named_colors / set_named_colors
    配色パレット = 系列に順に割り当てる色のリスト。ctx.color_palettes / set_color_palettes
どちらも本体が検証し、不正なら ValueError(の子)を出す。メッセージはそのまま利用者に見せられる。
"""
from . import colors as C
from .library import unique_name

UNDO_TEXT = "[カラースタジオ] 色の適用"
NAMED_COLOR_MAX_NAME_LENGTH = 60

ADD, OVERWRITE, RENAME, SKIP = "add", "overwrite", "rename", "skip"


class PaletteExistsError(ValueError):
    pass


def plan_named_colors(ctx, items):
    """
    登録色へ追加する前の確認用。

    Args:
        items: [(名前, '#rrggbb'), ...]
    Returns:
        list[dict]: {"name", "color", "existing": 既存の同名の色 or None}
    """
    existing = {e["name"]: e["color"] for e in ctx.named_colors()}
    return [{"name": name, "color": C.normalize_hex(color), "existing": existing.get(name)} for name, color in items]


def add_named_colors(ctx, items, conflict=RENAME):
    """
    登録色の末尾に足す。同名が既にあるときの扱いは conflict で決める
    (OVERWRITE はその位置のまま色を変える、RENAME は「名前 (2)」で足す、SKIP は足さない)。
    conflict は1つの値か、名前 → 値の dict。

    Returns:
        dict: {"added": [...], "overwritten": [...], "skipped": [...]}(名前のリスト)
    Raises:
        ValueError: 名前や色が本体の検証を通らない(何も書かない)。
    """
    entries = [dict(e) for e in ctx.named_colors()]
    index = {e["name"]: i for i, e in enumerate(entries)}
    result = {"added": [], "overwritten": [], "skipped": []}
    for name, color in items:
        name = " ".join(str(name).split())
        color = C.normalize_hex(color)
        policy = conflict.get(name, RENAME) if isinstance(conflict, dict) else conflict
        if name in index and policy == OVERWRITE:
            entries[index[name]]["color"] = color
            result["overwritten"].append(name)
            continue
        if name in index and policy == SKIP:
            result["skipped"].append(name)
            continue
        if name in index:
            name = unique_name(name, index)
        entries.append({"name": name, "color": color})
        index[name] = len(entries) - 1
        result["added"].append(name)
    ctx.set_named_colors(entries)
    return result


def register_palette(ctx, name, colors, overwrite=False):
    """
    本体の配色パレットとして登録する。

    Raises:
        PaletteExistsError: 同名の利用者パレットがあり、overwrite でない。
        ValueError: 組み込みのパレットと同じ名前、色コードが不正など(本体の検証)。
    """
    name = " ".join(str(name).split())
    if not name:
        raise ValueError("パレット名を入力してください。")
    palettes = ctx.color_palettes()
    if name in palettes and not overwrite:
        raise PaletteExistsError(f"配色パレット「{name}」は既にあります。")
    palettes[name] = [C.normalize_hex(c) for c in colors]
    ctx.set_color_palettes(palettes)


def target_datasets(ctx):
    """選択中のデータセットを表示順に。色を持たない 2D マップは除く。"""
    selected = {id(d) for d in ctx.selected_datasets()}
    return [d for d in ctx.datasets() if id(d) in selected and getattr(d, "data_kind", "1d") != "2d_grid"]


def apply_to_selected(ctx, colors):
    """
    選択中のデータセットに、表示順で色を順に割り当てる。色が足りなければ先頭に戻る。
    本体の窓口ではデータセットごとに1回の Undo になる。

    Returns:
        tuple[int, int]: (色を変えた数, 対象の数)。既に同じ色のものは変えない(Undo を積まない)。
    """
    colors = [C.normalize_hex(c) for c in colors]
    if not colors:
        raise ValueError("適用する色がありません。")
    targets = target_datasets(ctx)
    changed = 0
    for i, ds in enumerate(targets):
        color = colors[i % len(colors)]
        if str(getattr(ds, "color", "")).lower() == color:
            continue
        ctx.set_dataset_properties(ds, {"color": color}, UNDO_TEXT)
        changed += 1
    return changed, len(targets)
