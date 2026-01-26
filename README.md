# GDO Score Scraper

GDOのスコアサイトからスコア情報を取得するツールです。

- **Playwright**を用いてブラウザを自動操作
- **JSON形式**で保存
- [アクセス先](https://score.golfdigest.co.jp/)

## 環境要件

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) パッケージマネージャー

## セットアップ

### 1. 依存関係のインストール

```bash
# uvで依存関係をインストール
uv sync

# Playwrightブラウザをインストール
uv run playwright install chromium

# Playwrightのシステム依存関係をインストール（Linux環境で必要）
# sudo権限が必要です
uv run playwright install-deps chromium
```

### 2. 環境変数の設定

```bash
# .env.exampleをコピー
cp .env.example .env

# .envを編集してGDO認証情報を設定
# GDO_LOGIN_ID=your_email@example.com
# GDO_PASSWORD=your_password
```

### 3. pre-commitの設定（開発者向け）

```bash
# pre-commitフックをインストール
uv run pre-commit install
```

## 使い方

```bash
# スコア情報を取得
uv run gdo-score

# オプション指定
uv run gdo-score --output ./my_output --headless false
```

## 分析（marimoノートブック）

取得したスコアJSONを、marimoノートブックで集計・可視化できます。

### 依存関係

分析用の追加依存関係はextrasで管理しています。

```bash
uv sync --extra analysis
```

### ノートブック実行

```bash
uv run marimo run notebooks/score_analysis.py
```

### 入力データ

ノートブックは以下を参照します。

- `data/scores_20160312-20251214.json`
- `data/golf_place_position_lat_lon.csv`

### できること

- フィルタ（年、ゴルフ場、期間）
- スコア/パット推移
- 年別スコア分布（箱ひげ）と年間ラウンド数
- スコア帯ごとの年別分布（棒グラフ）
- ゴルフ場マップ（地域選択）

### 既知の制約

- marimoの制約により、地図（geoshape）をズーム・パンするインタラクションは利用できません（地域選択で範囲を切り替えます）。

## 開発

### コードチェック

```bash
# フォーマット
uv run ruff format .

# リント
uv run ruff check . --fix

# 型チェック
uv run ty check src/

# テスト
uv run pytest
```

### デバッグ

```bash
# Playwright Codegen（セレクター取得）
uv run playwright codegen https://score.golfdigest.co.jp/

# ヘッドフルモードで実行
HEADLESS=false uv run gdo-score

# デバッグモードで実行
DEBUG=true uv run gdo-score
```

## プロジェクト構造

```text
get-gdo-score/
├── data/              # 分析用データ（.gitignore運用推奨）
├── src/gdo_score/      # メインソースコード
│   ├── __init__.py
│   ├── config.py       # 設定管理
│   ├── models.py       # データモデル
│   ├── selectors.py    # CSSセレクター定義
│   ├── browser.py      # ブラウザ管理
│   ├── auth.py         # 認証処理
│   ├── scraper.py      # スクレイピングロジック
│   ├── output.py       # 出力処理
│   └── cli.py          # CLIエントリーポイント
├── tests/              # テストコード
├── notebooks/          # marimoノートブック
├── docs/               # ドキュメント
├── output/             # 出力ファイル（.gitignore）
├── debug/              # デバッグファイル（.gitignore）
└── sample/             # 参考用の旧コード
```

## ライセンス

[MIT](LICENSE)
