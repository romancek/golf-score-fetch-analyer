# デバッグ・トラブルシューティングガイド

このドキュメントでは、GDOスコア取得ツールのデバッグ方法と、よくある問題の解決方法を説明します。

## 1. Playwrightデバッグ機能

### 1.1 Codegen（セレクタ自動生成）

ページ構造が変更された際に、新しいセレクタを特定するのに便利です。

```bash
# ブラウザを起動してGDOサイトにアクセス
uv run playwright codegen https://score.golfdigest.co.jp/

# ログイン後のページをターゲットにする場合
uv run playwright codegen --save-storage=auth.json https://score.golfdigest.co.jp/
```

**使い方**:

1. コマンドを実行するとブラウザと「Playwright Inspector」が開く
2. ブラウザ上で要素をクリックすると、最適なセレクタが自動生成される
3. 生成されたコードを `selectors.py` に反映する

### 1.2 Inspector（ステップ実行）

スクリプトをステップごとに実行し、各操作の結果を確認できます。

```bash
# デバッグモードでスクリプトを実行
PWDEBUG=1 uv run python -m gdo_score

# または、コード内で pause() を使用
# await page.pause()  # このポイントで一時停止
```

### 1.3 トレース（操作履歴の記録）

エラー発生時の操作履歴を記録し、後から再現・分析できます。

```bash
# デバッグモードで実行するとトレースが自動記録される
uv run python -m gdo_score --debug

# トレースファイルの確認
uv run playwright show-trace debug/traces/trace.zip
```

**トレースビューアでできること**:

- 各操作のスクリーンショット確認
- ネットワークリクエストの確認
- コンソールログの確認
- DOM スナップショットの確認

## 2. デバッグモードの使い方

### 2.1 デバッグモードの有効化

```bash
# コマンドラインオプション
uv run python -m gdo_score --debug

# または環境変数
DEBUG_MODE=true uv run python -m gdo_score
```

### 2.2 デバッグモードで収集される情報

```text
debug/
├── screenshots/          # スクリーンショット
│   ├── login_failed_20250125_123456.png
│   └── selector_not_found_date_20250125_123457.png
├── traces/               # Playwrightトレース
│   └── trace.zip
└── html/                 # ページHTML
    ├── login_page_20250125_123456.html
    └── score_page_20250125_123457.html
```

## 3. よくある問題と解決方法

### 3.1 ログインできない

**症状**: `LoginError: ログインに失敗しました`

**確認手順**:

1. 認証情報の確認

   ```bash
   # .envファイルの内容を確認
   cat .env
   ```

2. ブラウザを表示して確認

   ```bash
   uv run python -m gdo_score --no-headless --debug
   ```

3. モーダルが邪魔している可能性

   - スクリーンショットを確認
   - キャンペーンモーダルなどが表示されていないか確認

**解決策**:

- `.env` の認証情報を確認・更新
- モーダルを閉じる処理を `auth.py` に追加

### 3.2 セレクタが見つからない

**症状**: `SelectorNotFoundError: セレクタ '.score__detail__place__info > p' が見つかりません`

**確認手順**:

1. デバッグモードで実行してHTMLを保存

   ```bash
   uv run python -m gdo_score --debug
   ```

2. 保存されたHTMLを確認

   ```bash
   cat debug/html/score_page_*.html | grep -A5 "score__detail"
   ```

3. Codegenで新しいセレクタを特定

   ```bash
   uv run playwright codegen https://score.golfdigest.co.jp/member/score_detail.asp
   ```

**解決策**:

- `selectors.py` のセレクタを更新
- フォールバックセレクタを追加

### 3.3 データが一部取得できない

**症状**: スコアの一部が空になる

**確認手順**:

1. 該当ページのHTMLを確認
2. データ構造が想定と異なる可能性を検討

**解決策**:

- スクレイピング処理にオプショナルな取得ロジックを追加
- デフォルト値を設定

## 4. セレクタ修正ワークフロー

### 4.1 修正手順

1. **問題の特定**

   ```bash
   # デバッグモードで実行
   uv run python -m gdo_score --debug --no-headless
   ```

2. **新しいセレクタの特定**

   ```bash
   # Codegenを使用
   uv run playwright codegen https://score.golfdigest.co.jp/
   ```

3. **セレクタの更新**

   [selectors.py](../src/gdo_score/selectors.py) を編集:

   ```python
   # 古いセレクタ
   DATE: str = ".score__detail__place__info > p"
   
   # 新しいセレクタ（変更があった場合）
   DATE: str = ".play-date-info > span"
   ```

4. **テスト実行**

   ```bash
   uv run pytest tests/ -v
   uv run python -m gdo_score --debug
   ```

### 4.2 フォールバックセレクタの追加

複数のセレクタパターンを定義して、ページ変更に柔軟に対応:

```python
# selectors.py
SELECTOR_FALLBACKS = {
    "date": [
        ".score__detail__place__info > p",      # 現在のパターン
        "[data-testid='play-date']",            # data属性パターン
        ".play-date",                           # シンプルなクラス
    ],
}
```

## 5. ログの活用

### 5.1 ログレベルの設定

```bash
# 詳細ログを表示
LOG_LEVEL=DEBUG uv run python -m gdo_score

# エラーのみ表示
LOG_LEVEL=ERROR uv run python -m gdo_score
```

### 5.2 ログ出力例

```text
2025-01-25 12:34:56 INFO     ログイン処理を開始します
2025-01-25 12:34:57 DEBUG    セレクタ '.button--login' をクリック
2025-01-25 12:34:58 DEBUG    ユーザー名を入力
2025-01-25 12:34:59 INFO     ログイン成功
2025-01-25 12:35:00 INFO     スコアページ 1 を取得中...
2025-01-25 12:35:01 DEBUG    日付を抽出: 2025/04/28
```

## 6. CI/CD でのデバッグ

### 6.1 GitHub Actions でのアーティファクト保存

```yaml
- name: Run tests
  run: uv run pytest --trace=debug/traces

- name: Upload debug artifacts
  if: failure()
  uses: actions/upload-artifact@v4
  with:
    name: debug-artifacts
    path: debug/
```

### 6.2 ローカルでの再現

```bash
# CIで失敗したトレースをダウンロードして確認
unzip debug-artifacts.zip
uv run playwright show-trace debug/traces/trace.zip
```

## 7. パフォーマンス問題

### 7.1 処理が遅い場合

**確認項目**:

- ネットワーク状況
- タイムアウト設定
- 不要な待機処理

**解決策**:

```python
# 明示的な待機を最小限に
page.wait_for_load_state("domcontentloaded")  # networkidleより速い

# 並列処理の検討（複数ページを同時取得）
```

### 7.2 メモリ使用量が多い場合

```python
# 定期的にブラウザコンテキストをリセット
if page_count % 50 == 0:
    context.close()
    context = browser.new_context()
    page = context.new_page()
```

## 8. 連絡先

問題が解決しない場合は、以下の情報とともに Issue を作成してください：

1. 実行環境（OS、Pythonバージョン）
2. エラーメッセージの全文
3. `debug/` フォルダの内容（スクリーンショット、HTML）
4. トレースファイル（`debug/traces/trace.zip`）
