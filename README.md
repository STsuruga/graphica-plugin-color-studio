# graphica-plugin-color-studio

[Graphica](https://github.com/STsuruga/Graphica) 用のプラグイン。複数のデータを重ねて描くときの
**色選び**を手伝います(バックログ上の項目番号は **P-901**)。

> 開発中です(v1.0.0 未リリース)。

## できること(v1.0 の予定)

- **グラデーション作成**: 2色以上のストップからグラデーションを作り、端から端まで等間隔に N 色を抜き出す。
  補間は OKLab(既定)/ OKLCH / RGB / HSV。
- **配色パレット生成**: 基準色・画像・カラーホイールから、配色ルール(類似色、モノクロマティック、トライアド、
  補色、スプリットコンプリメンタリー、スクエア、コンパウンド、シェード、カスタム)に沿って作る。
- **色覚への配慮**: P型・D型・T型の見え方に切り替え、隣り合う色が見分けにくい組を警告する。
- **ライブラリ**: 作った配色に名前を付けて保存し、JSON で書き出し / 読み込みできる。
- **Graphica への受け渡し**: 登録色(名前 → 1色)として追加、配色パレット(系列に順に割り当てる色のリスト)
  として登録、選択中のデータセットへ直接適用(Undo 可)。

## インストール(利用者向け)

1. [Releases](https://github.com/STsuruga/graphica-plugin-color-studio/releases) から
   `color_studio-<version>.zip` をダウンロード
2. Graphica を起動し、**編集 ▸ 環境設定 ▸「プラグイン」タブ ▸ プラグインをインストール...** から zip を選ぶ
3. Graphica を再起動すると、「プラグイン」メニューに「カラースタジオを開く...」が出ます

## 開発環境

```bash
python -m venv .venv                   # Python 3.11 以上
.venv\Scripts\activate                 # macOS / Linux は source .venv/bin/activate
pip install "graphica-plot>=2.0,<3"
pip install -r requirements-dev.txt
pytest
```

仮想環境はこのリポジトリ専用にします(ふだんの Python の Graphica 開発環境とぶつからないように)。
Graphica 本体が入っていない環境では、本体を必要とするテストは理由付きで skip されます。

## 配布用 zip のビルド

```bash
python scripts/build_zip.py --all      # dist/color_studio-1.0.0.zip
```

`dist/` はコミットせず、zip は Releases に添付します。

## 構成

```
color_studio/        ← プラグイン本体(このフォルダ名がインストール先のフォルダ名)
  __init__.py        ← register(api)
  plugin.json        ← name / version / api_version
tests/               ← pytest
scripts/build_zip.py ← 配布用 zip のビルド
```

## ライセンス

MIT
