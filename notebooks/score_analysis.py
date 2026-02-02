# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo",
#     "polars",
#     "altair",
#     "vega_datasets",
# ]
# ///
"""GDOゴルフスコア分析ノートブック.

このノートブックでは、GDOから取得したゴルフスコアデータを
分析・可視化します。
"""

import marimo

__generated_with = "0.19.6"
app = marimo.App(width="medium")


@app.cell
def _():
    # ノーマライザーのインポート
    import sys
    from pathlib import Path

    import altair as alt
    import marimo as mo
    import polars as pl

    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from gdo_score.normalizer import DataNormalizer

    return DataNormalizer, Path, alt, mo, pl


@app.cell
def _(mo):
    mo.md("""
    # GDOゴルフスコア分析

    GDOスコアサイトから取得したゴルフスコアデータを分析・可視化します。
    """)
    return


@app.cell
def _(Path, mo):
    # data/ディレクトリのJSONファイル一覧を取得
    _DATA_DIR = Path(__file__).parent.parent / "data"
    json_files = sorted([f.name for f in _DATA_DIR.glob("*.json")])

    if not json_files:
        mo.stop(True, mo.md("⚠️ data/ディレクトリにJSONファイルが見つかりません"))

    # デフォルトでscores_で始まる最新のファイルを選択
    default_files = [
        f for f in json_files if f.startswith("scores_") and not f.endswith(".bak")
    ]
    if not default_files:
        default_files = json_files[:1]  # なければ最初のファイル

    file_selector = mo.ui.multiselect(
        options=json_files,
        value=default_files,
        label="データファイルを選択（複数選択可）",
    )

    mo.md(f"""
    ## データファイル選択

    {file_selector}
    """)
    return (file_selector,)


@app.cell
def _(Path, file_selector, mo, pl):
    # 選択されたファイルを読み込み
    if not file_selector.value:
        mo.stop(True, mo.md("⚠️ データファイルを選択してください"))

    _DATA_DIR = Path(__file__).parent.parent / "data"

    # 複数ファイルを読み込んで結合
    dfs = []
    for filename in file_selector.value:
        file_path = _DATA_DIR / filename
        try:
            df_temp = pl.read_json(file_path)
            dfs.append(df_temp)
        except Exception as e:
            mo.output.append(mo.md(f"⚠️ {filename}の読み込みに失敗: {e}"))

    if not dfs:
        mo.stop(True, mo.md("⚠️ 有効なデータファイルがありません"))

    # 複数のDataFrameを結合
    if len(dfs) == 1:
        df_raw = dfs[0]
    else:
        df_raw = pl.concat(dfs, how="vertical_relaxed")
        # 重複を削除（同じ日付・ゴルフ場のラウンドは1つに）
        df_raw = df_raw.unique(
            subset=["year", "month", "day", "golf_place_name"], keep="first"
        )

    mo.md(f"""
    ### 読み込み完了

    - **選択ファイル数**: {len(file_selector.value)}
    - **総レコード数**: {len(df_raw)}
    """)
    return (df_raw,)


@app.cell
def _(DataNormalizer, df_raw, pl):
    # パーオン率・ボギーオン率・ワンオン率計算関数
    def calculate_green_on_rates(row: dict) -> dict:
        """パーオン率、ボギーオン率、ワンオン率を計算する

        Args:
            row: hall_scores, putt_scores, par_scores を含む辞書

        Returns:
            dict: {
                "par_on_rate": float | None,  # パー-2打でグリーンオン
                "bogey_on_rate": float | None,  # パー打でグリーンオン
                "one_on_rate": float | None  # パー3で1打でグリーンオン
            }
        """
        hall_scores = row.get("hall_scores", [])
        putt_scores = row.get("putt_scores", [])
        par_scores = row.get("par_scores", [])

        # パー数が存在しない場合はNoneを返す
        if not par_scores or len(par_scores) == 0:
            return {"par_on_rate": None, "bogey_on_rate": None, "one_on_rate": None}

        par_on_count = 0
        bogey_on_count = 0
        one_on_count = 0
        valid_holes = 0
        par3_holes = 0

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

                # パーオン判定: パー - 2打でグリーンに乗せる
                if shots_to_green <= (par - 2):
                    par_on_count += 1

                # ボギーオン判定: パー打でグリーンに乗せる
                if shots_to_green <= par:
                    bogey_on_count += 1

                # ワンオン判定: パー3で1打でグリーンに乗せる
                if par == 3:
                    par3_holes += 1
                    if shots_to_green == 1:
                        one_on_count += 1

            except (ValueError, TypeError):
                continue

        if valid_holes == 0:
            return {"par_on_rate": None, "bogey_on_rate": None, "one_on_rate": None}

        one_on_rate = one_on_count / par3_holes if par3_holes > 0 else None

        return {
            "par_on_rate": par_on_count / valid_holes,
            "bogey_on_rate": bogey_on_count / valid_holes,
            "one_on_rate": one_on_rate,
        }

    # 条件付きスコア率計算関数
    def calculate_conditional_score_rates(row: dict) -> dict:
        """OB・ペナルティー・バンカー時のスコア率を計算

        Returns:
            dict: {
                "ob_par_rate", "ob_bogey_rate", "ob_double_bogey_rate",
                "penalty_par_rate", "penalty_bogey_rate", "penalty_double_bogey_rate",
                "bunker_par_rate", "bunker_bogey_rate", "bunker_double_bogey_rate"
            }
        """
        hall_scores = row.get("hall_scores", [])
        par_scores = row.get("par_scores", [])
        obs = row.get("obs", [])
        penaltys = row.get("penaltys", [])
        bunkers = row.get("bunkers", [])

        result = {}

        # 各条件の集計
        for condition_name, condition_data in [
            ("ob", obs),
            ("penalty", penaltys),
            ("bunker", bunkers),
        ]:
            par_count = 0
            bogey_count = 0
            double_bogey_count = 0
            total_count = 0

            for i in range(min(len(hall_scores), len(par_scores), len(condition_data))):
                score_str = hall_scores[i]
                par_str = par_scores[i]
                cond_str = condition_data[i]

                # 条件が発生していない、または欠損値の場合はスキップ
                if not cond_str or cond_str == "" or cond_str == "ー":
                    continue

                try:
                    cond_value = int(cond_str)
                    if cond_value == 0:
                        continue
                except (ValueError, TypeError):
                    continue

                # スコアとパーが有効な場合のみカウント
                if score_str == "ー" or par_str == "ー":
                    continue

                try:
                    score = int(score_str)
                    par = int(par_str)

                    total_count += 1
                    diff = score - par

                    if diff == 0:
                        par_count += 1
                    elif diff == 1:
                        bogey_count += 1
                    elif diff == 2:
                        double_bogey_count += 1

                except (ValueError, TypeError):
                    continue

            # 率を計算
            if total_count > 0:
                result[f"{condition_name}_par_rate"] = par_count / total_count
                result[f"{condition_name}_bogey_rate"] = bogey_count / total_count
                result[f"{condition_name}_double_bogey_rate"] = (
                    double_bogey_count / total_count
                )
            else:
                result[f"{condition_name}_par_rate"] = None
                result[f"{condition_name}_bogey_rate"] = None
                result[f"{condition_name}_double_bogey_rate"] = None

        return result

    # ノーマライザーのインスタンス作成
    normalizer = DataNormalizer()

    # データ前処理
    df = (
        df_raw
        # データ正規化（ゴルフ場名、都道府県、コース名）
        .with_columns(
            [
                pl.col("golf_place_name")
                .map_elements(
                    normalizer.normalize_golf_place_name, return_dtype=pl.String
                )
                .alias("golf_place_name"),
                pl.col("prefecture")
                .map_elements(normalizer.normalize_prefecture, return_dtype=pl.String)
                .alias("prefecture"),
                pl.col("course_former_half")
                .map_elements(normalizer.clean_course_name, return_dtype=pl.String)
                .alias("course_former_half"),
                pl.col("course_latter_half")
                .map_elements(normalizer.clean_course_name, return_dtype=pl.String)
                .alias("course_latter_half"),
            ]
        )
        # 日付列を追加
        .with_columns(
            [
                pl.concat_str(
                    [
                        pl.col("year"),
                        pl.lit("-"),
                        pl.col("month").str.zfill(2),
                        pl.lit("-"),
                        pl.col("day").str.zfill(2),
                    ]
                ).alias("date_str"),
            ]
        )
        .with_columns(
            [
                pl.col("date_str").str.to_date("%Y-%m-%d").alias("date"),
                pl.col("year").cast(pl.Int32).alias("year_int"),
            ]
        )
        # スコア合計を計算("ー"は欠損値として扱う)
        .with_columns(
            [
                pl.col("hall_scores")
                .list.eval(
                    pl.element().replace("ー", None).cast(pl.Int32, strict=False)
                )
                .list.sum()
                .alias("total_score"),
                pl.col("putt_scores")
                .list.eval(
                    pl.element().replace("ー", None).cast(pl.Int32, strict=False)
                )
                .list.sum()
                .alias("total_putt"),
                # ペナルティ集計
                pl.col("obs")
                .list.eval(
                    pl.element()
                    .replace("ー", "0")
                    .replace("", "0")
                    .cast(pl.Int32, strict=False)
                )
                .list.sum()
                .alias("total_ob"),
                pl.col("bunkers")
                .list.eval(
                    pl.element()
                    .replace("ー", "0")
                    .replace("", "0")
                    .cast(pl.Int32, strict=False)
                )
                .list.sum()
                .alias("total_bunker"),
                pl.col("penaltys")
                .list.eval(
                    pl.element()
                    .replace("ー", "0")
                    .replace("", "0")
                    .cast(pl.Int32, strict=False)
                )
                .list.sum()
                .alias("total_penalty"),
            ]
        )
        # グリーンオン率を計算
        .with_columns(
            [
                pl.struct(["hall_scores", "putt_scores", "par_scores"])
                .map_elements(
                    calculate_green_on_rates,
                    return_dtype=pl.Struct(
                        {
                            "par_on_rate": pl.Float64,
                            "bogey_on_rate": pl.Float64,
                            "one_on_rate": pl.Float64,
                        }
                    ),
                )
                .alias("green_on_rates")
            ]
        )
        .unnest("green_on_rates")
        # 条件付きスコア率を計算
        .with_columns(
            [
                pl.struct(["hall_scores", "par_scores", "obs", "penaltys", "bunkers"])
                .map_elements(
                    calculate_conditional_score_rates,
                    return_dtype=pl.Struct(
                        {
                            "ob_par_rate": pl.Float64,
                            "ob_bogey_rate": pl.Float64,
                            "ob_double_bogey_rate": pl.Float64,
                            "penalty_par_rate": pl.Float64,
                            "penalty_bogey_rate": pl.Float64,
                            "penalty_double_bogey_rate": pl.Float64,
                            "bunker_par_rate": pl.Float64,
                            "bunker_bogey_rate": pl.Float64,
                            "bunker_double_bogey_rate": pl.Float64,
                        }
                    ),
                )
                .alias("conditional_rates")
            ]
        )
        .unnest("conditional_rates")
        # 日付順にソート
        .sort("date")
    )
    df
    return (calculate_conditional_score_rates, calculate_green_on_rates, df)


@app.cell
def _(df, mo, pl):
    # フィルタ用のオプションを取得
    years = sorted(df.select("year_int").unique().to_series().to_list())
    golf_places = sorted(df.select("golf_place_name").unique().to_series().to_list())
    prefectures = sorted(
        [p for p in df.select("prefecture").unique().to_series().to_list() if p]
    )

    # 期間の範囲
    min_date = df.select(pl.col("date").min()).item()
    max_date = df.select(pl.col("date").max()).item()

    mo.md(f"""
    ## データ概要

    - **データ期間**: {min_date} 〜 {max_date}
    - **総ラウンド数**: {len(df)}
    - **ゴルフ場数**: {len(golf_places)}
    - **都道府県数**: {len(prefectures)}
    """)
    return golf_places, max_date, min_date, years


@app.cell
def _(golf_places, max_date, min_date, mo, years):
    # フィルタUI
    year_selector = mo.ui.multiselect(
        options=[str(y) for y in years],
        value=[str(y) for y in years],
        label="年を選択",
    )

    place_selector = mo.ui.dropdown(
        options={"全て": None} | {p: p for p in golf_places},
        value=None,
        label="ゴルフ場",
    )

    date_range = mo.ui.date_range(
        start=min_date,
        stop=max_date,
        value=(min_date, max_date),
        label="期間",
    )

    mo.md(f"""
    ## フィルタ設定

    {mo.hstack([year_selector, place_selector], justify="start", gap=2)}

    {date_range}
    """)
    return date_range, place_selector, year_selector


@app.cell
def _(date_range, df, pl, place_selector, year_selector):
    # フィルタを適用
    selected_years = (
        [int(y) for y in year_selector.value] if year_selector.value else []
    )
    start_date, end_date = date_range.value if date_range.value else (None, None)

    df_filtered = df.filter(
        pl.col("year_int").is_in(selected_years) if selected_years else pl.lit(True)
    )

    if start_date and end_date:
        df_filtered = df_filtered.filter(
            (pl.col("date") >= start_date) & (pl.col("date") <= end_date)
        )

    if place_selector.value:
        df_filtered = df_filtered.filter(
            pl.col("golf_place_name") == place_selector.value
        )

    df_filtered
    return (df_filtered,)


@app.cell
def _(df_filtered, mo, pl):
    # 基本統計情報
    if len(df_filtered) == 0:
        mo.stop(True, mo.md("⚠️ 選択条件に該当するデータがありません"))

    stats = df_filtered.select(
        [
            pl.col("total_score").count().alias("ラウンド数"),
            pl.col("total_score").mean().round(1).alias("平均スコア"),
            pl.col("total_score").std().round(1).alias("標準偏差"),
            pl.col("total_score").min().alias("ベストスコア"),
            pl.col("total_score").max().alias("ワーストスコア"),
            pl.col("total_putt").mean().round(1).alias("平均パット"),
        ]
    )

    mo.md(f"""
    ## 基本統計情報

    {mo.ui.table(stats)}
    """)
    return


@app.cell
def _(alt, df_filtered, mo):
    # スコア推移グラフ
    score_chart = (
        alt.Chart(df_filtered)
        .mark_line(point=True)
        .encode(
            x=alt.X("date:T", title="日付"),
            y=alt.Y("total_score:Q", title="スコア", scale=alt.Scale(zero=False)),
            tooltip=["date:T", "total_score:Q", "golf_place_name:N", "prefecture:N"],
        )
        .properties(title="スコア推移", width=700, height=300)
        .interactive()
    )

    # 平均線を追加
    mean_score = df_filtered.select("total_score").mean().item()
    mean_line = (
        alt.Chart(df_filtered)
        .mark_rule(color="red", strokeDash=[5, 5])
        .encode(y=alt.datum(mean_score))
    )

    mo.md(f"""
    ## スコア推移

    平均スコア: **{mean_score:.1f}** (赤点線)
    """)
    return mean_line, score_chart


@app.cell
def _(mean_line, mo, score_chart):
    mo.ui.altair_chart(score_chart + mean_line)
    return


@app.cell
def _(alt, df_filtered, mo, pl):
    # パット推移グラフ（0パットは除外）
    df_putt = df_filtered.filter(pl.col("total_putt") > 0)

    putt_chart = (
        alt.Chart(df_putt)
        .mark_line(point=True, color="green")
        .encode(
            x=alt.X("date:T", title="日付"),
            y=alt.Y("total_putt:Q", title="パット数", scale=alt.Scale(zero=False)),
            tooltip=["date:T", "total_putt:Q", "golf_place_name:N"],
        )
        .properties(title="パット数推移", width=700, height=300)
        .interactive()
    )

    mean_putt = df_putt.select("total_putt").mean().item()

    mo.md(f"""
    ## パット数推移

    平均パット: **{mean_putt:.1f}**
    """)
    return (putt_chart,)


@app.cell
def _(mo, putt_chart):
    mo.ui.altair_chart(putt_chart)
    return


@app.cell
def _(alt, df_filtered, mo, pl):
    # 年別箱ひげ図 + ラウンド数表示
    boxplot = (
        alt.Chart(df_filtered)
        .mark_boxplot()
        .encode(
            x=alt.X("year:O", title="年", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("total_score:Q", title="スコア", scale=alt.Scale(zero=False)),
            color=alt.Color("year:O", legend=None),
        )
        .properties(title="年別スコア分布", width=700, height=300)
    )

    # 年別ラウンド数を計算
    yearly_rounds = (
        df_filtered.group_by("year_int")
        .agg(pl.col("total_score").count().alias("rounds"))
        .sort("year_int")
    )

    mo.md("""
    ## 年別スコア分布
    """)
    return boxplot, yearly_rounds


@app.cell
def _(boxplot, mo):
    mo.ui.altair_chart(boxplot)
    return


@app.cell
def _(mo, yearly_rounds):
    mo.md(f"""
    ### 年間ラウンド数

    {mo.ui.table(yearly_rounds.rename({"year_int": "年", "rounds": "ラウンド数"}))}
    """)
    return


@app.cell
def _(alt, df_filtered, mo, pl):
    # スコア範囲別の年別棒グラフ
    score_ranges = (
        df_filtered.with_columns(
            [
                pl.when(pl.col("total_score") < 70)
                .then(pl.lit("~69"))
                .when(pl.col("total_score") < 80)
                .then(pl.lit("70-79"))
                .when(pl.col("total_score") < 90)
                .then(pl.lit("80-89"))
                .when(pl.col("total_score") < 100)
                .then(pl.lit("90-99"))
                .when(pl.col("total_score") < 110)
                .then(pl.lit("100-109"))
                .when(pl.col("total_score") < 120)
                .then(pl.lit("110-119"))
                .otherwise(pl.lit("120~"))
                .alias("score_range")
            ]
        )
        .group_by("year_int", "score_range")
        .agg(pl.col("total_score").count().alias("count"))
        .sort("year_int")
    )

    # スコア範囲の順序を定義
    score_range_order = ["~69", "70-79", "80-89", "90-99", "100-109", "110-119", "120~"]

    score_range_chart = (
        alt.Chart(score_ranges)
        .mark_bar()
        .encode(
            x=alt.X("year_int:O", title="年", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("count:Q", title="ラウンド数"),
            color=alt.Color(
                "score_range:N",
                title="スコア範囲",
                sort=score_range_order,
                scale=alt.Scale(
                    domain=score_range_order,
                    range=[
                        "#1f77b4",
                        "#2ca02c",
                        "#98df8a",
                        "#ffbb78",
                        "#ff7f0e",
                        "#d62728",
                        "#8b0000",
                    ],
                ),
            ),
            tooltip=["year_int:O", "score_range:N", "count:Q"],
        )
        .properties(title="年別スコア分布(範囲別)", width=700, height=300)
    )

    mo.md("""
    ### 年別スコア割合(棒グラフ)
    """)
    return (score_range_chart,)


@app.cell
def _(mo, score_range_chart):
    mo.ui.altair_chart(score_range_chart)
    return


@app.cell
def _(alt, df_filtered, mo, pl):
    # 月別スコア分布(箱ひげ図)
    # monthを整数に変換してソート用カラムを追加
    df_monthly = df_filtered.with_columns(
        pl.col("month").cast(pl.Int32).alias("month_int")
    ).sort("month_int")

    monthly_boxplot = (
        alt.Chart(df_monthly)
        .mark_boxplot()
        .encode(
            x=alt.X("month_int:O", title="月", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("total_score:Q", title="スコア", scale=alt.Scale(zero=False)),
            color=alt.Color(
                "month_int:O",
                legend=None,
                scale=alt.Scale(scheme="tableau20"),
            ),
        )
        .properties(title="月別スコア分布", width=700, height=300)
    )

    # 月別ラウンド数を計算
    monthly_rounds = (
        df_monthly.group_by("month_int")
        .agg(pl.col("total_score").count().alias("rounds"))
        .sort("month_int")
    )

    mo.md("""
    ## 月別スコア分布
    """)
    return monthly_boxplot, monthly_rounds


@app.cell
def _(mo, monthly_boxplot):
    mo.ui.altair_chart(monthly_boxplot)
    return


@app.cell
def _(mo, monthly_rounds):
    mo.md(f"""
    ### 月別ラウンド数

    {mo.ui.table(monthly_rounds.rename({"month_int": "月", "rounds": "ラウンド数"}))}
    """)
    return


@app.cell
def _(alt, df_filtered, mo):
    # スコア分布ヒストグラム
    histogram = (
        alt.Chart(df_filtered)
        .mark_bar()
        .encode(
            x=alt.X("total_score:Q", bin=alt.Bin(maxbins=30), title="スコア"),
            y=alt.Y("count()", title="頻度"),
            tooltip=["count()"],
        )
        .properties(title="スコア分布", width=700, height=300)
    )

    mo.md("""
    ## スコア分布
    """)
    return (histogram,)


@app.cell
def _(histogram, mo):
    mo.ui.altair_chart(histogram)
    return


@app.cell
def _(df_filtered, mo, pl):
    # ゴルフ場別集計
    place_stats = (
        df_filtered.group_by("golf_place_name", "prefecture")
        .agg(
            [
                pl.col("total_score").count().alias("ラウンド数"),
                pl.col("total_score").mean().round(1).alias("平均スコア"),
                pl.col("total_score").min().alias("ベスト"),
                pl.col("total_putt").mean().round(1).alias("平均パット"),
            ]
        )
        .sort("ラウンド数", descending=True)
    )

    mo.md(f"""
    ## ゴルフ場別集計

    {mo.ui.table(place_stats, selection=None)}
    """)
    return


@app.cell
def _(df_filtered, mo, pl):
    # 都道府県別集計
    pref_stats = (
        df_filtered.filter(pl.col("prefecture") != "")
        .group_by("prefecture")
        .agg(
            [
                pl.col("total_score").count().alias("ラウンド数"),
                pl.col("total_score").mean().round(1).alias("平均スコア"),
                pl.col("golf_place_name").n_unique().alias("ゴルフ場数"),
            ]
        )
        .sort("ラウンド数", descending=True)
    )

    mo.md(f"""
    ## 都道府県別集計

    {mo.ui.table(pref_stats, selection=None)}
    """)
    return


@app.cell
def _(Path, pl):
    # ゴルフ場位置情報を読み込み
    POSITION_FILE = (
        Path(__file__).parent.parent / "data" / "golf_place_position_lat_lon.csv"
    )
    df_positions = pl.read_csv(POSITION_FILE).with_columns(
        [
            pl.col("lat").str.strip_chars().cast(pl.Float64),
        ]
    )
    return (df_positions,)


@app.cell
def _(mo):
    # 地図表示のズームレベル選択UI
    map_region = mo.ui.dropdown(
        options={
            "日本全国": "japan",
            "関東": "kanto",
            "東海": "tokai",
            "関西": "kansai",
            "九州": "kyushu",
            "北海道": "hokkaido",
            "神奈川・静岡": "kanagawa",
        },
        value="関東",
        label="地図範囲",
    )

    mo.md(f"""
    ## ゴルフ場マップ

    {map_region}
    """)
    return (map_region,)


@app.cell
def _(alt, df_filtered, df_positions, map_region, pl):
    # 地図の表示範囲とスケールを定義
    region_config = {
        "japan": {
            "lon": [129, 146],
            "lat": [30, 46],
            "scale": 1200,
            "center": [137, 38],
        },
        "kanto": {
            "lon": [138.5, 141],
            "lat": [34.8, 37],
            "scale": 10000,
            "center": [139.8, 35.9],
        },
        "tokai": {
            "lon": [136, 139],
            "lat": [34, 36],
            "scale": 12000,
            "center": [137, 35.3],
        },
        "kansai": {
            "lon": [134, 137],
            "lat": [33.5, 36],
            "scale": 10000,
            "center": [135.5, 34.8],
        },
        "kyushu": {
            "lon": [129, 132],
            "lat": [31, 34],
            "scale": 10000,
            "center": [130.5, 32.5],
        },
        "hokkaido": {
            "lon": [139, 146],
            "lat": [41, 46],
            "scale": 5000,
            "center": [142.5, 43.5],
        },
        "kanagawa": {
            "lon": [138.8, 139.8],
            "lat": [34.9, 35.8],
            "scale": 25000,
            "center": [139.3, 35.35],
        },
    }

    selected_region = map_region.value
    config = region_config[selected_region]
    bounds = {"lon": config["lon"], "lat": config["lat"]}

    # ゴルフ場別集計データと位置情報を結合
    place_stats_with_pos = (
        df_filtered.group_by("golf_place_name")
        .agg(
            [
                pl.col("total_score").count().alias("rounds"),
                pl.col("total_score").mean().round(1).alias("avg_score"),
                pl.col("total_score").min().alias("best_score"),
            ]
        )
        .join(df_positions, on="golf_place_name", how="left")
        .filter(pl.col("lat").is_not_null())
        .filter(
            (pl.col("lon") >= bounds["lon"][0])
            & (pl.col("lon") <= bounds["lon"][1])
            & (pl.col("lat") >= bounds["lat"][0])
            & (pl.col("lat") <= bounds["lat"][1])
        )
        .with_columns(
            [
                pl.when(pl.col("avg_score") >= 110)
                .then(pl.lit("110+"))
                .when(pl.col("avg_score") >= 100)
                .then(pl.lit("100-109"))
                .when(pl.col("avg_score") >= 90)
                .then(pl.lit("90-99"))
                .otherwise(pl.lit("~89"))
                .alias("score_category")
            ]
        )
    )

    # 日本地図の背景 (TopoJSON)
    japan_topo = (
        "https://raw.githubusercontent.com/dataofjapan/land/master/japan.topojson"
    )

    background = (
        alt.Chart(alt.topo_feature(japan_topo, "japan"))
        .mark_geoshape(fill="lightgray", stroke="white", strokeWidth=0.5)
        .project(
            type="mercator",
            scale=config["scale"],
            center=config["center"],
        )
        .properties(width=700, height=500)
    )

    # スコアカテゴリの色定義
    score_color_scale = alt.Scale(
        domain=["~89", "90-99", "100-109", "110+"],
        range=["#2ca02c", "#98df8a", "#ff7f0e", "#d62728"],
    )

    # ゴルフ場のポイント
    points = (
        alt.Chart(place_stats_with_pos)
        .mark_circle()
        .encode(
            longitude="lon:Q",
            latitude="lat:Q",
            size=alt.Size(
                "rounds:Q", scale=alt.Scale(range=[50, 500]), title="ラウンド数"
            ),
            color=alt.Color(
                "score_category:N", scale=score_color_scale, title="平均スコア"
            ),
            tooltip=[
                alt.Tooltip("golf_place_name:N", title="ゴルフ場"),
                alt.Tooltip("rounds:Q", title="ラウンド数"),
                alt.Tooltip("avg_score:Q", title="平均スコア"),
                alt.Tooltip("best_score:Q", title="ベスト"),
            ],
        )
        .project(
            type="mercator",
            scale=config["scale"],
            center=config["center"],
        )
    )

    golf_map = (background + points).properties(
        title=f"ゴルフ場マップ - {map_region.value}",
        width=700,
        height=500,
    )

    golf_map
    return


@app.cell
def _(mo):
    mo.md("""
    ## ゴルフ場マップ(自由操作)

    地図範囲はドロップダウンではなく、中心位置(緯度・経度)とスケールを
    スライダーで調整して移動・拡大縮小します。
    """)

    center_lon = mo.ui.slider(
        start=120.0,
        stop=150.0,
        step=0.05,
        value=139.05,
        label="中心経度(lon)",
    )
    center_lat = mo.ui.slider(
        start=20.0,
        stop=50.0,
        step=0.05,
        value=35.15,
        label="中心緯度(lat)",
    )
    map_scale = mo.ui.slider(
        start=1000,
        stop=100000,
        step=1000,
        value=32000,
        label="スケール(mercator)",
    )

    mo.md(
        f"""
        {mo.hstack([center_lon, center_lat, map_scale], justify="start", gap=2)}
        """
    )
    return center_lat, center_lon, map_scale


@app.cell(hide_code=True)
def _(alt, center_lat, center_lon, df_filtered, df_positions, map_scale, pl):
    # ゴルフ場別集計データと位置情報を結合（自由操作マップ用：範囲フィルタなし）
    place_stats_with_pos_all = (
        df_filtered.group_by("golf_place_name")
        .agg(
            [
                pl.col("total_score").count().alias("rounds"),
                pl.col("total_score").mean().round(1).alias("avg_score"),
                pl.col("total_score").min().alias("best_score"),
            ]
        )
        .join(df_positions, on="golf_place_name", how="left")
        .filter(pl.col("lat").is_not_null())
        .with_columns(
            [
                pl.when(pl.col("avg_score") >= 110)
                .then(pl.lit("110+"))
                .when(pl.col("avg_score") >= 100)
                .then(pl.lit("100-109"))
                .when(pl.col("avg_score") >= 90)
                .then(pl.lit("90-99"))
                .otherwise(pl.lit("~89"))
                .alias("score_category")
            ]
        )
    )

    # 日本地図の背景 (TopoJSON)
    _japan_topo_free = (
        "https://raw.githubusercontent.com/dataofjapan/land/master/japan.topojson"
    )

    center = [center_lon.value, center_lat.value]
    scale = map_scale.value

    background_free = (
        alt.Chart(alt.topo_feature(_japan_topo_free, "japan"))
        .mark_geoshape(fill="lightgray", stroke="white", strokeWidth=0.5)
        .project(
            type="mercator",
            scale=scale,
            center=center,
        )
        .properties(width=700, height=500)
    )

    _score_color_scale_free = alt.Scale(
        domain=["~89", "90-99", "100-109", "110+"],
        range=["#2ca02c", "#98df8a", "#ff7f0e", "#d62728"],
    )

    points_free = (
        alt.Chart(place_stats_with_pos_all)
        .mark_circle()
        .encode(
            longitude="lon:Q",
            latitude="lat:Q",
            size=alt.Size(
                "rounds:Q", scale=alt.Scale(range=[50, 500]), title="ラウンド数"
            ),
            color=alt.Color(
                "score_category:N",
                scale=_score_color_scale_free,
                title="平均スコア",
            ),
            tooltip=[
                alt.Tooltip("golf_place_name:N", title="ゴルフ場"),
                alt.Tooltip("rounds:Q", title="ラウンド数"),
                alt.Tooltip("avg_score:Q", title="平均スコア"),
                alt.Tooltip("best_score:Q", title="ベスト"),
            ],
        )
        .project(
            type="mercator",
            scale=scale,
            center=center,
        )
    )

    golf_map_free = (background_free + points_free).properties(
        title=(
            f"ゴルフ場マップ(自由操作) - center(lat,lon)=({center_lat.value:.1f},"
            f"{center_lon.value:.1f}), scale={scale}"
        ),
        width=700,
        height=500,
    )

    golf_map_free
    return


# ============================================================
# 追加分析セクション
# ============================================================


@app.cell
def _(mo):
    mo.md("""
    ---
    # 追加分析

    天気・風・フェアウェイキープ率・パーオン率・前半後半比較・同伴者比較・曜日別の分析を行います。
    """)
    return


# ------------------------------------------------------------
# 1. 天気別スコア分析
# ------------------------------------------------------------
@app.cell
def _(alt, df_filtered, mo, pl):
    # 天気別スコア分布
    df_weather = df_filtered.filter(
        pl.col("weather").is_not_null() & (pl.col("weather") != "")
    )

    weather_order = ["晴れ", "曇り", "雨", "雪"]

    weather_boxplot = (
        alt.Chart(df_weather)
        .mark_boxplot()
        .encode(
            x=alt.X(
                "weather:N",
                title="天気",
                sort=weather_order,
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y("total_score:Q", title="スコア", scale=alt.Scale(zero=False)),
            color=alt.Color(
                "weather:N",
                legend=None,
                sort=weather_order,
                scale=alt.Scale(
                    domain=weather_order,
                    range=["#FFD700", "#A9A9A9", "#4169E1", "#E0FFFF"],
                ),
            ),
        )
        .properties(title="天気別スコア分布", width=500, height=300)
    )

    weather_stats = (
        df_weather.group_by("weather")
        .agg(
            [
                pl.col("total_score").count().alias("ラウンド数"),
                pl.col("total_score").mean().round(1).alias("平均スコア"),
                pl.col("total_score").std().round(1).alias("標準偏差"),
            ]
        )
        .sort("平均スコア")
    )

    mo.md("""
    ## 1. 天気別スコア分析
    """)
    return weather_boxplot, weather_stats


@app.cell
def _(mo, weather_boxplot):
    mo.ui.altair_chart(weather_boxplot)
    return


@app.cell
def _(mo, weather_stats):
    mo.md(f"""
    ### 天気別統計

    {mo.ui.table(weather_stats)}
    """)
    return


# ------------------------------------------------------------
# 2. 風の強さとスコアの関係
# ------------------------------------------------------------
@app.cell
def _(alt, df_filtered, mo, pl):
    df_wind = df_filtered.filter(pl.col("wind").is_not_null() & (pl.col("wind") != ""))

    wind_order = ["微風", "弱", "中", "強"]

    wind_boxplot = (
        alt.Chart(df_wind)
        .mark_boxplot()
        .encode(
            x=alt.X("wind:N", title="風", sort=wind_order, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("total_score:Q", title="スコア", scale=alt.Scale(zero=False)),
            color=alt.Color(
                "wind:N",
                legend=None,
                sort=wind_order,
                scale=alt.Scale(
                    domain=wind_order,
                    range=["#98FB98", "#87CEEB", "#FFA500", "#DC143C"],
                ),
            ),
        )
        .properties(title="風の強さ別スコア分布", width=500, height=300)
    )

    wind_stats = (
        df_wind.group_by("wind")
        .agg(
            [
                pl.col("total_score").count().alias("ラウンド数"),
                pl.col("total_score").mean().round(1).alias("平均スコア"),
                pl.col("total_score").std().round(1).alias("標準偏差"),
            ]
        )
        .sort("平均スコア")
    )

    mo.md("""
    ## 2. 風の強さとスコアの関係
    """)
    return wind_boxplot, wind_stats


@app.cell
def _(mo, wind_boxplot):
    mo.ui.altair_chart(wind_boxplot)
    return


@app.cell
def _(mo, wind_stats):
    mo.md(f"""
    ### 風の強さ別統計

    {mo.ui.table(wind_stats)}
    """)
    return


# ------------------------------------------------------------
# 3. フェアウェイキープ率とスコア相関
# ------------------------------------------------------------
@app.cell
def _(alt, df_filtered, mo, pl):
    # フェアウェイキープ率を計算(Par3を除くホールでis-keepの割合)
    df_fwk = (
        df_filtered.with_columns(
            [
                pl.col("fairway_keeps")
                .list.eval(pl.element().eq("is-keep").cast(pl.Int32))
                .list.sum()
                .alias("fwk_count"),
                pl.col("fairway_keeps")
                .list.eval((pl.element() != "-").cast(pl.Int32))
                .list.sum()
                .alias("fwk_total"),
            ]
        )
        .with_columns(
            [
                (pl.col("fwk_count") / pl.col("fwk_total") * 100)
                .round(1)
                .alias("fwk_rate")
            ]
        )
        .filter(pl.col("fwk_total") > 0)
    )

    fwk_scatter = (
        alt.Chart(df_fwk)
        .mark_circle(size=80, opacity=0.6)
        .encode(
            x=alt.X("fwk_rate:Q", title="フェアウェイキープ率(%)"),
            y=alt.Y("total_score:Q", title="スコア", scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("date:T", title="日付"),
                alt.Tooltip("golf_place_name:N", title="ゴルフ場"),
                alt.Tooltip("fwk_rate:Q", title="FWK率(%)"),
                alt.Tooltip("total_score:Q", title="スコア"),
            ],
            color=alt.value("#2E8B57"),
        )
        .properties(title="フェアウェイキープ率とスコアの関係", width=600, height=400)
        .interactive()
    )

    # 回帰線を追加
    fwk_regression = fwk_scatter + fwk_scatter.transform_regression(
        "fwk_rate", "total_score"
    ).mark_line(color="red", strokeDash=[5, 5])

    # 相関係数を計算
    fwk_corr = df_fwk.select(pl.corr("fwk_rate", "total_score")).item()

    mo.md(f"""
    ## 3. フェアウェイキープ率とスコア相関

    相関係数: **{fwk_corr:.3f}**
    """)
    return (fwk_regression,)


@app.cell
def _(fwk_regression):
    fwk_regression
    return


# ------------------------------------------------------------
# 4. ワンオン率とスコア相関
# ------------------------------------------------------------
@app.cell
def _(alt, df_filtered, mo, pl):
    # ワンオン率を計算(GDOのoneonsフィールドのis-ok割合)
    # GDOのoneonsはワンオンを示すフィールド
    df_oneon = (
        df_filtered.with_columns(
            [
                pl.col("oneons")
                .list.eval(pl.element().eq("is-ok").cast(pl.Int32))
                .list.sum()
                .alias("oneon_count"),
                pl.col("oneons")
                .list.eval((pl.element() != "-").cast(pl.Int32))
                .list.sum()
                .alias("oneon_total"),
            ]
        )
        .with_columns(
            [
                (pl.col("oneon_count") / pl.col("oneon_total") * 100)
                .round(1)
                .alias("oneon_rate")
            ]
        )
        .filter(pl.col("oneon_total") > 0)
    )

    oneon_scatter = (
        alt.Chart(df_oneon)
        .mark_circle(size=80, opacity=0.6)
        .encode(
            x=alt.X("oneon_rate:Q", title="ワンオン率(%)"),
            y=alt.Y("total_score:Q", title="スコア", scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("date:T", title="日付"),
                alt.Tooltip("golf_place_name:N", title="ゴルフ場"),
                alt.Tooltip("oneon_rate:Q", title="ワンオン率(%)"),
                alt.Tooltip("total_score:Q", title="スコア"),
            ],
            color=alt.value("#4169E1"),
        )
        .properties(title="ワンオン率とスコアの関係", width=600, height=400)
        .interactive()
    )

    oneon_regression = oneon_scatter + oneon_scatter.transform_regression(
        "oneon_rate", "total_score"
    ).mark_line(color="red", strokeDash=[5, 5])

    oneon_corr = df_oneon.select(pl.corr("oneon_rate", "total_score")).item()

    mo.md(f"""
    ## 4. ワンオン率とスコア相関

    相関係数: **{oneon_corr:.3f}**
    """)
    return (oneon_regression,)


@app.cell
def _(oneon_regression):
    oneon_regression
    return


# ------------------------------------------------------------
# 5. 前半/後半スコア比較
# ------------------------------------------------------------
@app.cell
def _(alt, df_filtered, mo, pl):
    # 前半(1-9)と後半(10-18)のスコアを計算
    df_half = (
        df_filtered.with_columns(
            [
                pl.col("hall_scores")
                .list.slice(0, 9)
                .list.eval(
                    pl.element().replace("ー", None).cast(pl.Int32, strict=False)
                )
                .list.sum()
                .alias("first_half"),
                pl.col("hall_scores")
                .list.slice(9, 9)
                .list.eval(
                    pl.element().replace("ー", None).cast(pl.Int32, strict=False)
                )
                .list.sum()
                .alias("second_half"),
            ]
        )
        .with_columns(
            [(pl.col("first_half") - pl.col("second_half")).alias("half_diff")]
        )
        .filter(
            pl.col("first_half").is_not_null() & pl.col("second_half").is_not_null()
        )
    )

    max_first = df_half.select(pl.col("first_half").max()).item()
    max_second = df_half.select(pl.col("second_half").max()).item()
    max_half = max(max_first or 0, max_second or 0)
    axis_max = max_half if max_half > 0 else 80

    # 前半 vs 後半 散布図
    half_scatter = (
        alt.Chart(df_half)
        .mark_circle(size=80, opacity=0.6)
        .encode(
            x=alt.X(
                "second_half:Q",
                title="後半スコア",
                scale=alt.Scale(domain=[30, axis_max]),
            ),
            y=alt.Y(
                "first_half:Q",
                title="前半スコア",
                scale=alt.Scale(domain=[30, axis_max]),
            ),
            color=alt.Color(
                "half_diff:Q",
                title="前半-後半",
                scale=alt.Scale(scheme="redblue", domainMid=0),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="日付"),
                alt.Tooltip("golf_place_name:N", title="ゴルフ場"),
                alt.Tooltip("first_half:Q", title="前半"),
                alt.Tooltip("second_half:Q", title="後半"),
                alt.Tooltip("half_diff:Q", title="差(前半-後半)"),
            ],
        )
        .properties(
            title="前半vs後半スコア(青:前半が良い、赤:後半が良い)",
            width=500,
            height=400,
        )
        .interactive()
    )

    # 対角線(前半=後半)を追加
    line_df = pl.DataFrame({"x": [30, 80], "y": [30, 80]})
    diagonal = (
        alt.Chart(line_df)
        .mark_line(color="gray", strokeDash=[5, 5], opacity=0.5)
        .encode(x="x:Q", y="y:Q")
    )

    half_chart = half_scatter + diagonal

    # 前半-後半の差分分布（マイナスは前半が良い）
    diff_hist = (
        alt.Chart(df_half)
        .mark_bar()
        .encode(
            x=alt.X(
                "half_diff:Q",
                bin=alt.Bin(step=2),
                title="前半-後半スコア差",
            ),
            y=alt.Y("count()", title="頻度"),
            color=alt.condition(
                alt.datum.half_diff < 0,
                alt.value("#1f77b4"),
                alt.value("#d62728"),
            ),
            tooltip=[
                alt.Tooltip("count()", title="件数"),
                alt.Tooltip("half_diff:Q", title="差(前半-後半)"),
            ],
        )
        .properties(title="前半-後半スコア差分布", width=500, height=250)
    )

    # 統計
    avg_first = df_half.select("first_half").mean().item()
    avg_second = df_half.select("second_half").mean().item()
    avg_diff = df_half.select("half_diff").mean().item()

    mo.md(f"""
    ## 5. 前半/後半スコア比較

    - 前半平均: **{avg_first:.1f}**
    - 後半平均: **{avg_second:.1f}**
    - 平均差(前半-後半): **{avg_diff:+.1f}** {"(後半が良い)" if avg_diff > 0 else "(前半が良い)"}
    """)
    return diff_hist, half_chart


@app.cell
def _(diff_hist, half_chart, mo):
    mo.vstack([half_chart, diff_hist])
    return


# ------------------------------------------------------------
# 6. 同伴者との比較
# ------------------------------------------------------------
@app.cell
def _(Path, df_filtered, mo, pl):
    # 同伴者名の表記ゆれマッピングを読み込み
    MAPPING_FILE = Path(__file__).parent.parent / "data" / "accompany_name_mapping.json"

    import json

    if MAPPING_FILE.exists():
        with MAPPING_FILE.open() as f:
            name_mapping = json.load(f)
    else:
        name_mapping = {}

    # 同伴者スコアを展開して比較
    def calc_accompany_scores(row):
        scores = row["accompany_member_scores"]
        names = row["accompany_member_names"]
        if not scores or not names:
            return []
        result = []
        for name, score_list in zip(names, scores, strict=False):
            try:
                total = sum(int(s) for s in score_list if s and s != "ー")
                if total > 0:
                    # 表記ゆれマッピングを適用
                    normalized_name = name_mapping.get(name, name)
                    if normalized_name:  # 空文字列は除外
                        result.append({"name": normalized_name, "score": total})
            except (ValueError, TypeError):
                pass
        return result

    # 同伴者との比較データを作成
    accompany_data = []
    for row in df_filtered.iter_rows(named=True):
        my_score = row["total_score"]
        if my_score is None:
            continue
        accompany = calc_accompany_scores(row)
        for a in accompany:
            accompany_data.append(
                {
                    "date": row["date"],
                    "golf_place_name": row["golf_place_name"],
                    "my_score": my_score,
                    "accompany_name": a["name"],
                    "accompany_score": a["score"],
                    "diff": my_score - a["score"],
                }
            )

    df_accompany = pl.DataFrame(accompany_data) if accompany_data else None

    if df_accompany is not None and len(df_accompany) > 0:
        # 同伴者別の勝敗と平均差
        accompany_stats = (
            df_accompany.group_by("accompany_name")
            .agg(
                [
                    pl.col("diff").count().alias("ラウンド数"),
                    (pl.col("diff") < 0).sum().alias("勝ち"),
                    (pl.col("diff") == 0).sum().alias("引分"),
                    (pl.col("diff") > 0).sum().alias("負け"),
                    pl.col("diff").mean().round(1).alias("平均スコア差"),
                ]
            )
            .filter(pl.col("ラウンド数") >= 3)
            .sort("平均スコア差")
        )

        # 同伴数ランキング
        accompany_ranking = (
            df_accompany.group_by("accompany_name")
            .agg(
                [
                    pl.col("diff").count().alias("同伴回数"),
                ]
            )
            .sort("同伴回数", descending=True)
        )
    else:
        accompany_stats = None
        accompany_ranking = None

    mo.md("""
    ## 6. 同伴者との比較
    """)
    return accompany_ranking, accompany_stats, df_accompany


@app.cell
def _(accompany_ranking, mo):
    if accompany_ranking is not None and len(accompany_ranking) > 0:
        _output = mo.md(f"""
        ### 同伴数ランキング

        {mo.ui.table(accompany_ranking)}
        """)
    else:
        _output = mo.md("")
    _output
    return


@app.cell
def _(accompany_stats, mo):
    if accompany_stats is not None and len(accompany_stats) > 0:
        _output = mo.md(f"""
        ### 同伴者別成績(3ラウンド以上)

        スコア差: 自分 - 同伴者(マイナスは自分が良い)

        {mo.ui.table(accompany_stats)}
        """)
    else:
        _output = mo.md("同伴者データが不足しています。")
    _output
    return


@app.cell
def _(alt, df_accompany, mo):
    if df_accompany is not None and len(df_accompany) > 0:
        accompany_hist = (
            alt.Chart(df_accompany)
            .mark_bar()
            .encode(
                x=alt.X("diff:Q", bin=alt.Bin(step=5), title="スコア差(自分-同伴者)"),
                y=alt.Y("count()", title="頻度"),
                color=alt.condition(
                    alt.datum.diff < 0,
                    alt.value("#2E8B57"),
                    alt.value("#DC143C"),
                ),
            )
            .properties(
                title="同伴者とのスコア差分布(緑:勝ち、赤:負け)", width=600, height=300
            )
        )
        _output = mo.ui.altair_chart(accompany_hist)
    else:
        _output = mo.md("")
    _output
    return


# ------------------------------------------------------------
# 7. 曜日別スコア分析
# ------------------------------------------------------------
@app.cell
def _(alt, df_filtered, mo, pl):
    # 曜日を追加
    df_weekday = (
        df_filtered.with_columns(
            [
                pl.col("date").dt.weekday().alias("weekday_num"),
            ]
        )
        .with_columns(
            [
                pl.when(pl.col("weekday_num") == 1)
                .then(pl.lit("月"))
                .when(pl.col("weekday_num") == 2)
                .then(pl.lit("火"))
                .when(pl.col("weekday_num") == 3)
                .then(pl.lit("水"))
                .when(pl.col("weekday_num") == 4)
                .then(pl.lit("木"))
                .when(pl.col("weekday_num") == 5)
                .then(pl.lit("金"))
                .when(pl.col("weekday_num") == 6)
                .then(pl.lit("土"))
                .when(pl.col("weekday_num") == 7)
                .then(pl.lit("日"))
                .alias("weekday"),
                pl.when(pl.col("weekday_num") >= 6)
                .then(pl.lit("週末"))
                .otherwise(pl.lit("平日"))
                .alias("day_type"),
            ]
        )
        .filter(pl.col("weekday").is_not_null() & (pl.col("weekday") != ""))
    )

    weekday_order = ["月", "火", "水", "木", "金", "土", "日"]

    weekday_boxplot = (
        alt.Chart(df_weekday)
        .mark_boxplot()
        .encode(
            x=alt.X(
                "weekday:N",
                title="曜日",
                sort=weekday_order,
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y("total_score:Q", title="スコア", scale=alt.Scale(zero=False)),
            color=alt.Color(
                "day_type:N",
                title="種別",
                scale=alt.Scale(domain=["平日", "週末"], range=["#4169E1", "#FF6347"]),
            ),
        )
        .properties(title="曜日別スコア分布", width=600, height=300)
    )

    weekday_stats = (
        df_weekday.group_by("weekday", "weekday_num")
        .agg(
            [
                pl.col("total_score").count().alias("ラウンド数"),
                pl.col("total_score").mean().round(1).alias("平均スコア"),
            ]
        )
        .sort("weekday_num")
        .drop("weekday_num")
    )

    daytype_stats = df_weekday.group_by("day_type").agg(
        [
            pl.col("total_score").count().alias("ラウンド数"),
            pl.col("total_score").mean().round(1).alias("平均スコア"),
            pl.col("total_score").std().round(1).alias("標準偏差"),
        ]
    )

    mo.md("""
    ## 7. 曜日別スコア分析
    """)
    return daytype_stats, weekday_boxplot, weekday_stats


@app.cell
def _(mo, weekday_boxplot):
    mo.ui.altair_chart(weekday_boxplot)
    return


@app.cell
def _(daytype_stats, mo, weekday_stats):
    mo.md(f"""
    ### 曜日別統計

    {mo.ui.table(weekday_stats)}

    ### 平日 vs 週末

    {mo.ui.table(daytype_stats)}
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## パーオン率分析

    パー数データがあるラウンドについて、パーオン率とボギーオン率を分析します。
    """)
    return


@app.cell
def _(df_filtered, pl):
    # パー数データが存在するラウンドのみフィルタ
    df_with_par = df_filtered.filter(pl.col("par_on_rate").is_not_null())
    return (df_with_par,)


@app.cell
def _(alt, df_with_par, pl):
    # パーオン率の推移
    chart_par_on = (
        alt.Chart(df_with_par)
        .mark_line(point=True)
        .encode(
            x=alt.X("date:T", title="日付"),
            y=alt.Y(
                "par_on_rate:Q",
                title="パーオン率",
                scale=alt.Scale(domain=[0, 1]),
                axis=alt.Axis(format="%"),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="日付"),
                alt.Tooltip("par_on_rate:Q", format=".1%", title="パーオン率"),
                alt.Tooltip("total_score:Q", title="スコア"),
                alt.Tooltip("golf_place_name:N", title="ゴルフ場"),
            ],
        )
        .properties(
            width=800, height=300, title="パーオン率の推移(パー-2打でグリーンオン)"
        )
        .interactive()
    )

    # ボギーオン率の推移
    chart_bogey_on = (
        alt.Chart(df_with_par)
        .mark_line(point=True, color="orange")
        .encode(
            x=alt.X("date:T", title="日付"),
            y=alt.Y(
                "bogey_on_rate:Q",
                title="ボギーオン率",
                scale=alt.Scale(domain=[0, 1]),
                axis=alt.Axis(format="%"),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="日付"),
                alt.Tooltip("bogey_on_rate:Q", format=".1%", title="ボギーオン率"),
                alt.Tooltip("total_score:Q", title="スコア"),
                alt.Tooltip("golf_place_name:N", title="ゴルフ場"),
            ],
        )
        .properties(
            width=800, height=300, title="ボギーオン率の推移(パー打でグリーンオン)"
        )
        .interactive()
    )

    # ワンオン率の推移(パー3のみ)
    df_with_one_on = df_with_par.filter(pl.col("one_on_rate").is_not_null())

    chart_one_on = (
        alt.Chart(df_with_one_on)
        .mark_line(point=True, color="green")
        .encode(
            x=alt.X("date:T", title="日付"),
            y=alt.Y(
                "one_on_rate:Q",
                title="ワンオン率",
                scale=alt.Scale(domain=[0, 1]),
                axis=alt.Axis(format="%"),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="日付"),
                alt.Tooltip("one_on_rate:Q", format=".1%", title="ワンオン率"),
                alt.Tooltip("total_score:Q", title="スコア"),
                alt.Tooltip("golf_place_name:N", title="ゴルフ場"),
            ],
        )
        .properties(
            width=800, height=300, title="ワンオン率の推移(パー3で1打でグリーンオン)"
        )
        .interactive()
    )

    chart_par_on, chart_bogey_on, chart_one_on
    return chart_bogey_on, chart_one_on, chart_par_on, df_with_one_on


@app.cell
def _(mo):
    mo.md("""
    ## ペナルティ発生率の推移

    OB、バンカー、ペナルティの発生率（ホールあたり）を表示します。
    """)
    return


@app.cell
def _(df_filtered, pl):
    # ペナルティ率を計算（ホールあたりの発生率）
    penalty_df = df_filtered.select(
        [
            "date",
            "golf_place_name",
            "total_ob",
            "total_bunker",
            "total_penalty",
        ]
    ).with_columns(
        [
            (pl.col("total_ob") / 18).alias("ob_rate"),
            (pl.col("total_bunker") / 18).alias("bunker_rate"),
            (pl.col("total_penalty") / 18).alias("penalty_rate"),
        ]
    )

    # ロングフォーマットに変換
    penalty_long = (
        penalty_df.select(
            ["date", "golf_place_name", "ob_rate", "bunker_rate", "penalty_rate"]
        )
        .unpivot(
            index=["date", "golf_place_name"],
            on=["ob_rate", "bunker_rate", "penalty_rate"],
            variable_name="penalty_type",
            value_name="rate",
        )
        .with_columns(
            [
                pl.col("penalty_type")
                .replace(
                    {
                        "ob_rate": "OB",
                        "bunker_rate": "バンカー",
                        "penalty_rate": "ペナルティ",
                    }
                )
                .alias("penalty_type")
            ]
        )
    )

    penalty_df, penalty_long
    return penalty_df, penalty_long


@app.cell
def _(alt, penalty_long):
    # ペナルティ発生率の推移グラフ
    chart_penalty = (
        alt.Chart(penalty_long)
        .mark_line(point=True)
        .encode(
            x=alt.X("date:T", title="日付"),
            y=alt.Y("rate:Q", title="発生率（ホールあたり）"),
            color=alt.Color("penalty_type:N", title="種別"),
            tooltip=[
                alt.Tooltip("date:T", title="日付"),
                alt.Tooltip("penalty_type:N", title="種別"),
                alt.Tooltip("rate:Q", format=".2f", title="発生率"),
            ],
        )
        .properties(width=800, height=400, title="ペナルティ発生率の推移")
        .interactive()
    )

    chart_penalty
    return (chart_penalty,)


@app.cell
def _(mo):
    mo.md("""
    ## 条件付きスコア率分析

    OB・ペナルティー・バンカーが発生した場合のパー・ボギー・ダブルボギー率を分析します。
    """)
    return


@app.cell
def _(df_with_par, pl):
    # 条件付きスコア率の集計
    conditional_stats = []

    for condition_name, condition_label in [
        ("ob", "OB"),
        ("penalty", "ペナルティー"),
        ("bunker", "バンカー"),
    ]:
        # データが存在するラウンドのみ
        valid_df = df_with_par.filter(
            pl.col(f"{condition_name}_par_rate").is_not_null()
        )

        if len(valid_df) > 0:
            par_rate = valid_df.select(f"{condition_name}_par_rate").mean().item()
            bogey_rate = valid_df.select(f"{condition_name}_bogey_rate").mean().item()
            double_bogey_rate = (
                valid_df.select(f"{condition_name}_double_bogey_rate").mean().item()
            )

            conditional_stats.append(
                {
                    "条件": condition_label,
                    "パー率": f"{par_rate:.1%}" if par_rate is not None else "-",
                    "ボギー率": (
                        f"{bogey_rate:.1%}" if bogey_rate is not None else "-"
                    ),
                    "ダブルボギー率": (
                        f"{double_bogey_rate:.1%}"
                        if double_bogey_rate is not None
                        else "-"
                    ),
                    "集計ラウンド数": len(valid_df),
                }
            )

    df_conditional_stats = (
        pl.DataFrame(conditional_stats) if conditional_stats else None
    )
    df_conditional_stats
    return (conditional_stats, df_conditional_stats)


@app.cell
def _(df_conditional_stats, mo):
    if df_conditional_stats is not None and len(df_conditional_stats) > 0:
        _output = mo.md(f"""
        ### 条件付きスコア率（平均）

        {mo.ui.table(df_conditional_stats)}

        ※ 各条件が発生したホールのみを対象に集計しています。
        """)
    else:
        _output = mo.md(
            "パー数データが不足しているため、条件付きスコア率を計算できません。"
        )
    _output
    return


if __name__ == "__main__":
    app.run()
