# CLAUDE.md

Graphica(https://github.com/STsuruga/Graphica)用プラグイン P-901 カラースタジオ(グラデーション作成・配色パレット生成)のリポジトリ。

## 最初に読むもの
- 開発ハブ(Artifact): https://claude.ai/artifact/GZ3LTLJjbxj1LQsAhZFg2o
  Artifact ツールの action: "read" で読む。共通ルール・API 早見表・この項目の仕様と状態がある。
- 開発計画(Artifact): https://claude.ai/artifact/LdRqogvd3bf6H7E3sujLTc
  決まった仕様、モジュール構成、テスト方針、工程 M0〜M7、リスク。
- 本体の CLAUDE.md「Plugin API」節と docs/plugin_development.md(本体リポジトリ)

## 作業の範囲
- このリポジトリ専用。ほかのプラグインのリポジトリと Graphica 本体は変更しない
  (本体への書き込みは docs/dev/PLUGIN_DEVELOPMENT_PROGRESS.md の表への1行だけ)。
- 新しいプラグインを始めるときは、新しいチャットでハブの引継ぎプロンプトから始める。

## このプラグイン
- 項目: P-901。使うフック: register_menu_action(独立ウィンドウ)、register_panel(ライブラリの一覧)
- v1.0 の範囲(ユーザーと決めた内容):
  - グラデーション: ストップ2個以上、位置 0〜1、等間隔に N 色を抽出。補間は OKLab が既定で、RGB / OKLCH / HSV に切替可。
  - 配色パレット: 基準色・画像(k-means)・カラーホイールの3つの作り方、配色ルール9種、点の連動、ランダム、Undo/Redo。
    ホイールは RYB が既定で、RGB 色相環に切替可。
  - ライブラリ: ctx.data_dir の library.json。保存・一覧・複製・削除、JSON の書き出し / 読み込み。
  - 本体へ: 登録色(名前 → 1色)、配色パレット(色のリスト)、選択中のデータセットへ直接適用(Undo 付き)。
- 見送ったこと・次の版に回したこと: 色覚の見え方の切り替え(P/D/T 型)と見分けにくい色の警告は、実機で試したユーザーの判断で外した(2026-09-28。いったん実装したが不要とされた)。colormap としての登録(窓口なし)、画像のスポイト、英語 UI。
- 本体への要望(2026-09-28 に作成): exe に scipy.cluster を同梱(STsuruga/Graphica#77)、複数データセットの変更を1回の Undo にまとめる窓口と、配色パレットを有効にする窓口(STsuruga/Graphica#78)。

## 構成
- color_studio/ の計算モジュール(colors / gradient / harmony / extract / library)は Qt にも本体にも依存させない。
- 本体とのやりとりは bridge.py に集め、ctx のメソッドだけを使う。
- Qt は qt_image.py / widgets/ / studio_window.py / panel.py だけ。

## コマンド
python -m venv .venv                  # 初回だけ。Python 3.11 以上
.venv\Scripts\activate               # macOS / Linux は source .venv/bin/activate
pip install "graphica-plot>=2.0,<3"   # 本体の未リリースの変更で試すときは pip install -e <PlotterApp>/Graphica_project
pip install -r requirements-dev.txt
pytest
graphica                               # 本体を起動(zip は 編集 ▸ 環境設定 ▸ プラグイン から入れる)
python scripts/build_zip.py --all      # dist/color_studio-<version>.zip

## ルール
- Graphica 本体のコードは変更しない。足りない拡張点は本体の Issue(ユーザーの了承を得て作成)とハブの note に記録する。
- 依存は本体同梱のパッケージのみ(PySide6 6.11 / matplotlib 3.11 / numpy / pandas / scipy / openpyxl / xlrd)。
  ただし exe には「本体が import するサブパッケージ」しか入らない。v2.0.0 の exe には scipy.cluster が無い
  (exe で import を試すプローブで確認)。このプラグインは scipy を使わず、k-means は numpy で自前に持つ。
  仮想環境の pip 版は配布版より新しいことがある(2026-09 時点で numpy 2.5 / scipy 1.18、配布版は 2.3 / 1.16)。両方にある API だけ使う。
- matplotlib の色は組で返ることがあるので、Qt に渡す前に matplotlib.colors.to_hex で #rrggbb にする。
- プラグイン内は相対 import。他プラグインは import できない。
- 受け取った Dataset は書き換えない。新しい Dataset は name / df / x_col_name / y_col_name 必須。
- 本体から import するのは graphica.plugin / graphica.plugin.testing だけ。本体の操作は窓口 ctx(PluginContext)で行う。
- リリースしたら plugin.json の version とタグを揃え、ハブの db(collection "plugins", doc_id "P-901")を更新する。

## exe で import できるかの確かめ方
pip 版で通るテストでは、exe にサブパッケージが無いことに気づけない。Releases の Graphica-windows.zip(ポータブル版)を
展開し、一時フォルダを LOCALAPPDATA にして、register() の中で import を試してファイルに書くだけの使い捨てプラグインを置いて起動する。
- 環境変数: LOCALAPPDATA=<一時フォルダ>(プラグインは <一時フォルダ>\Graphica\plugins に置く)、QT_QPA_PLATFORM=offscreen(画面を出さない)
- exe は QSettings をレジストリ(HKCU\Software\Graphica)に書くので、先に reg export で退避し、終わったら reg delete → reg import で戻す。
- 結果のファイルができたらプロセスを終了する。

## 現状
- v1.0.0 をリリース(2026-09-28): https://github.com/STsuruga/graphica-plugin-color-studio/releases/tag/v1.0.0
  - pip 版(仮想環境の graphica)と Releases の exe(v2.0.0)の両方で動作を確認し、ユーザーも実機で確認した。テスト 142 件。
  - 計画からの変更: ホイールは QConicalGradient ではなく numpy で画素ごとに描く(RYB の色相対応を正確に出すため)。
  - 実機確認のあと、色覚の見え方の切り替えと見分けにくい色の警告を外した(ユーザー判断)。
  - 計測: k-means(256×256 のノイズ画像、k=10、numpy 版)0.12 秒、ホイール描画(480px)0.5 秒未満。
  - exe に scipy.cluster が無い → k-means を numpy で自前に持ち、scipy の import を禁じるテストを置いた(Graphica#77)。
  - 画面の Qt レイアウトの罠: 右の列を QLayout のまま置くと行の高さの上限になり、余りが下の色見本に回った(QWidget に包んで解決)。
- 次の版の候補: Graphica#78 が入ったら「選択中に適用」を1回の Undo にまとめ、「配色パレットに登録」で有効にもする(API 2.1)。
