# ワンオン率・ペナルティ率グラフ機能追加 設計書

## 1. 概要

GDOスコアデータに以下の機能を追加します：

1. **パー数・ヤード数の取得**: スクレイピング時に各ホールのパー数とヤード数を取得
2. **ワンオン率の算出**: パー数、スコア、パット数からワンオン判定を行い率を計算
3. **ペナルティ率のグラフ化**: バンカー率・OB率・ペナルティー率をラウンドごとに可視化

### 1.1 ワンオン判定ロジック

**定義**: パー数以下の打数でグリーンに乗せること

| パー | ワンオン条件 |
|------|--------------|
| Par 3 | 1打でグリーンに乗せる（スコア - パット数 ≤ 1） |
| Par 4 | 2打でグリーンに乗せる（スコア - パット数 ≤ 2） |
| Par 5 | 3打でグリーンに乗せる（スコア - パット数 ≤ 3） |

計算式: `グリーンオンまでの打数 = スコア - パット数`

---

## 2. データモデルの変更

### 2.1 ScoreDataモデルの拡張

**ファイル**: `src/gdo_score/models.py`

```python
class ScoreData(BaseModel):
    """1ラウンドのスコアデータ"""

    # ... 既存フィールド ...

    # 【新規追加】各ホールのパー数
    par_scores: list[str] = Field(
        default_factory=list,
        description="各ホールのパー数(18ホール分)"
    )

    # 【新規追加】各ホールのヤード数
    yard_scores: list[str] = Field(
        default_factory=list,
        description="各ホールのヤード数(18ホール分)"
    )

    # 既存フィールドはそのまま維持
    hall_scores: list[str] = Field(...)
    putt_scores: list[str] = Field(...)
    obs: list[str] = Field(...)
    bunkers: list[str] = Field(...)
    penaltys: list[str] = Field(...)
```

**互換性の保証**:

- `default_factory=list` により、既存データ(パー数・ヤード数なし)との後方互換性を維持
- 既存のJSONデータ読み込み時は空リストとして扱われる

---

## 3. スクレイピング処理の変更

### 3.1 セレクタの追加

**ファイル**: `src/gdo_score/selectors.py`

```python
@dataclass(frozen=True)
class ScoreDetailSelectors:
    """スコア詳細ページのセレクター"""

    # ... 既存セレクタ ...

    # 【新規追加】パー行のセレクタ
    PAR_ROW_FORMER: str = "table:nth-child(4) > tbody > tr.is-par"
    PAR_ROW_LATTER: str = "table:nth-child(6) > tbody > tr.is-par"

    # 【新規追加】ヤード行のセレクタ
    YARD_ROW_FORMER: str = "table:nth-child(4) > tbody > tr.is-yard"
    YARD_ROW_LATTER: str = "table:nth-child(6) > tbody > tr.is-yard"
```

**確認済み**: GDOサイトのHTML構造を確認し、以下のクラス名を使用することを確定

- パー行: `tr.is-par`
- ヤード行: `tr.is-yard`

### 3.2 スクレイパーの修正

**ファイル**: `src/gdo_score/scraper.py`

```python
def _scrape_score_detail(self, url: str) -> ScoreData:
    """スコア詳細ページからデータを抽出する"""

    # ... 既存処理 ...

    # 【新規追加】パー情報の取得
    par_scores = self._get_scores_from_rows(
        SCORE_DETAIL.PAR_ROW_FORMER,
        SCORE_DETAIL.PAR_ROW_LATTER
    )

    # 【新規追加】ヤード情報の取得
    yard_scores = self._get_scores_from_rows(
        SCORE_DETAIL.YARD_ROW_FORMER,
        SCORE_DETAIL.YARD_ROW_LATTER
    )

    return ScoreData(
        # ... 既存フィールド ...
        par_scores=par_scores,   # 新規追加
        yard_scores=yard_scores,  # 新規追加
        # ...
    )
```

**実装のポイント**:

- 既存の `_get_scores_from_rows()` メソッドをそのまま流用可能
- パー行・ヤード行が存在しない場合は空リストを返す(既存データとの互換性)

---

## 4. 分析ノートブックの変更

### 4.1 データ前処理の追加

**ファイル**: `notebooks/score_analysis.py`

```python
# データ前処理
df = (
    df_raw
    # ... 既存の処理 ...
    .with_columns([
        # 【新規追加】ワンオン率の計算
        pl.struct(["hall_scores", "putt_scores", "par_scores"])
          .map_elements(calculate_oneon_rate, return_dtype=pl.Float64)
          .alias("oneon_rate"),

        # 【新規追加】バンカー率の計算
        pl.col("bunkers")
          .list.eval(
              pl.element().replace("ー", "0").cast(pl.Int32, strict=False)
          )
          .list.sum()
          .alias("total_bunker"),

        # 【新規追加】OB率の計算
        pl.col("obs")
          .list.eval(
              pl.element().replace("ー", "0").cast(pl.Int32, strict=False)
          )
          .list.sum()
          .alias("total_ob"),

        # 【新規追加】ペナルティー率の計算
        pl.col("penaltys")
          .list.eval(
              pl.element().replace("ー", "0").cast(pl.Int32, strict=False)
          )
          .list.sum()
          .alias("total_penalty"),
    ])
)
```

### 4.2 ワンオン率計算関数

```python
def calculate_oneon_rate(row_struct: dict) -> float:
    """ワンオン率を計算する

    Args:
        row_struct: {
            "hall_scores": ["5", "4", ...],
            "putt_scores": ["2", "2", ...],
            "par_scores": ["4", "3", ...]
        }

    Returns:
        float: ワンオン率(0.0〜1.0、または None)
    """
    hall_scores = row_struct.get("hall_scores", [])
    putt_scores = row_struct.get("putt_scores", [])
    par_scores = row_struct.get("par_scores", [])

    # パー数が存在しない場合はNoneを返す(古いデータ対応)
    if not par_scores or len(par_scores) == 0:
        return None

    oneon_count = 0
    valid_holes = 0

    for i in range(min(len(hall_scores), len(putt_scores), len(par_scores))):
        score_str = hall_scores[i]
        putt_str = putt_scores[i]
        par_str = par_scores[i]

        # 欠損値チェック
        if score_str == "ー" or putt_str == "ー" or par_str == "ー":
            continue

        try:
            score = int(score_str)
            putt = int(putt_str)
            par = int(par_str)

            valid_holes += 1

            # グリーンオンまでの打数 = スコア - パット数
            shots_to_green = score - putt

            # ワンオン判定: パー - 1打以内でグリーンに乗せる
            # Par3なら1打、Par4なら2打、Par5なら3打
            if shots_to_green <= (par - 1):
                oneon_count += 1

        except (ValueError, TypeError):
            continue

    if valid_holes == 0:
        return None

    return oneon_count / valid_holes
```

**注意**: Polarsの `map_elements` は処理が遅いため、大量データの場合は
Polarsネイティブの式で実装することを検討してください。

### 4.3 ペナルティ率グラフの追加

```python
@app.cell
def _(df, alt, mo):
    mo.md("## ペナルティ率の推移")
    return

@app.cell
def _(df, alt):
    # ラウンドごとのペナルティ率を計算
    penalty_df = df.select([
        "date",
        "total_bunker",
        "total_ob",
        "total_penalty",
    ]).with_columns([
        (pl.col("total_bunker") / 18 * 100).alias("bunker_rate"),
        (pl.col("total_ob") / 18 * 100).alias("ob_rate"),
        (pl.col("total_penalty") / 18 * 100).alias("penalty_rate"),
    ])

    # ロングフォーマットに変換
    penalty_long = penalty_df.melt(
        id_vars=["date"],
        value_vars=["bunker_rate", "ob_rate", "penalty_rate"],
        variable_name="penalty_type",
        value_name="rate"
    ).with_columns([
        pl.col("penalty_type").replace({
            "bunker_rate": "バンカー率",
            "ob_rate": "OB率",
            "penalty_rate": "ペナルティ率"
        })
    ])

    # グラフ作成
    chart = alt.Chart(penalty_long).mark_line(point=True).encode(
        x=alt.X("date:T", title="日付"),
        y=alt.Y("rate:Q", title="発生率(%)", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color("penalty_type:N", title="種別"),
        tooltip=["date:T", "penalty_type:N", "rate:Q"]
    ).properties(
        width=800,
        height=400,
        title="ペナルティ発生率の推移(ホールあたり)"
    )

    chart
    return penalty_df, penalty_long, chart

@app.cell
def _(df, alt, mo):
    mo.md("## ワンオン率の推移")
    return

@app.cell
def _(df, alt):
    # ワンオン率の推移グラフ
    # パー数データが存在するラウンドのみフィルタ
    oneon_df = df.filter(pl.col("oneon_rate").is_not_null())

    chart_oneon = alt.Chart(oneon_df).mark_line(point=True).encode(
        x=alt.X("date:T", title="日付"),
        y=alt.Y(
            "oneon_rate:Q",
            title="ワンオン率",
            scale=alt.Scale(domain=[0, 1]),
            axis=alt.Axis(format="%")
        ),
        tooltip=[
            "date:T",
            alt.Tooltip("oneon_rate:Q", format=".1%", title="ワンオン率")
        ]
    ).properties(
        width=800,
        height=400,
        title="ワンオン率の推移"
    )

    chart_oneon
    return oneon_df, chart_oneon
```

---

## 5. 実装手順

### Phase 1: パー数・ヤード数取得機能の実装

1. ✅ **GDOサイトのHTML構造確認**
   - 実際のスコア詳細ページでパー行・ヤード行のセレクタを特定
   - ブラウザの開発者ツールで要素を検査
   - 確認済み: `tr.is-par`, `tr.is-yard`

2. ⬜ **セレクタ追加**
   - `src/gdo_score/selectors.py` に `PAR_ROW_FORMER/LATTER` を追加
   - `src/gdo_score/selectors.py` に `YARD_ROW_FORMER/LATTER` を追加

3. ⬜ **モデル拡張**
   - `src/gdo_score/models.py` に `par_scores` フィールド追加
   - `src/gdo_score/models.py` に `yard_scores` フィールド追加

4. ⬜ **スクレイパー修正**
   - `src/gdo_score/scraper.py` の `_scrape_score_detail()` でパー・ヤード取得処理追加

5. ⬜ **テスト実行**
   - 実際にスクレイピングを実行してパー数・ヤード数が取得できることを確認
   - 既存データとの互換性確認(エラーが出ないこと)

### Phase 2: ワンオン率計算機能の実装

6. ⬜ **計算関数の実装**
   - `notebooks/score_analysis.py` に `calculate_oneon_rate()` 関数追加

7. ⬜ **データ前処理の追加**
   - ワンオン率の計算列を追加

8. ⬜ **グラフの追加**
   - ワンオン率推移グラフのセルを追加

### Phase 3: ペナルティ率グラフの実装

9. ⬜ **既存データの活用**
   - 既に取得済みの `obs`, `bunkers`, `penaltys` を集計

10. ⬜ **グラフの追加**
    - ペナルティ率推移グラフのセルを追加

11. ⬜ **動作確認**
    - 各グラフが正しく表示されることを確認

---

## 6. データ移行戦略

### 6.1 既存データとの互換性

- **古いJSONデータ**: `par_scores`, `yard_scores` フィールドが存在しない
  - `default_factory=list` により空リストとして扱われる
  - ワンオン率は `None` (計算不可)として処理
  - ヤード数を使った分析は実施不可

- **新しいJSONデータ**: `par_scores`, `yard_scores` フィールドが存在する
  - ワンオン率が正しく計算される
  - ヤード数を使った分析が可能(飛距離分析など)

### 6.2 データ再取得の推奨

機能追加後、以下の手順でデータを再取得することを推奨します：

```bash
# 1. 既存データのバックアップ
cp data/scores_20160312-20251214.json data/scores_20160312-20251214.json.backup

# 2. スクレイピング実行
uv run gdo-score

# 3. ノートブックで確認
uv run marimo run notebooks/score_analysis.py
```

---

## 7. 注意事項

### 7.1 GDOサイトのHTML構造

- **セレクタ確認済み**: `tr.is-par`, `tr.is-yard`
- パー行・ヤード行が存在しないページがある可能性を考慮（古いデータなど）

### 7.2 パフォーマンス

- `map_elements` は処理が遅い
  - 大量データの場合、Polarsネイティブの式での実装を検討
  - 例: `pl.when()`, `pl.struct()` の組み合わせ

### 7.3 データの信頼性

- ユーザーが手入力したデータはパー数が正確でない可能性
- 欠損値 `"ー"` の適切な処理

---

## 8. テストケース

### 8.1 スクレイピングのテスト

```python
def test_scrape_par_scores():
    """パー数が正しく取得されることを確認"""
    # Given: スコア詳細ページ
    # When: スクレイピング実行
    # Then: par_scores が 18個の要素を持つリスト
    assert len(score_data.par_scores) == 18
    assert all(p in ["3", "4", "5"] for p in score_data.par_scores if p != "ー")

def test_scrape_yard_scores():
    """ヤード数が正しく取得されることを確認"""
    # Given: スコア詳細ページ
    # When: スクレイピング実行
    # Then: yard_scores が 18個の要素を持つリスト
    assert len(score_data.yard_scores) == 18
    # ヤード数は数値文字列または"ー"
    for yard in score_data.yard_scores:
        if yard != "ー":
            assert yard.isdigit()
```

### 8.2 ワンオン率計算のテスト

```python
def test_calculate_oneon_rate():
    """ワンオン率の計算ロジックが正しいことを確認"""
    # Par 4で2打でグリーンオン(スコア5、パット3)
    row = {
        "hall_scores": ["5"],
        "putt_scores": ["3"],
        "par_scores": ["4"]
    }
    assert calculate_oneon_rate(row) == 1.0  # ワンオン成功

    # Par 4で3打でグリーンオン(スコア5、パット2)
    row = {
        "hall_scores": ["5"],
        "putt_scores": ["2"],
        "par_scores": ["4"]
    }
    assert calculate_oneon_rate(row) == 0.0  # ワンオン失敗
```

---

## 9. 参考資料

- **既存設計書**: `docs/DESIGN.md`
- **Polarsドキュメント**: <https://docs.pola.rs/>
- **Altairドキュメント**: <https://altair-viz.github.io/>
- **marimoドキュメント**: <https://docs.marimo.io/>
