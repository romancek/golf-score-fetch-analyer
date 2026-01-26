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
    from pathlib import Path

    import altair as alt
    import marimo as mo
    import polars as pl

    return Path, alt, mo, pl


@app.cell
def _(mo):
    mo.md("""
    # GDOゴルフスコア分析

    GDOスコアサイトから取得したゴルフスコアデータを分析・可視化します。
    """)
    return


@app.cell
def _(Path, pl):
    # データファイルのパス
    DATA_FILE = Path(__file__).parent.parent / "data" / "scores_20160312-20251214.json"

    # JSONデータを読み込み
    df_raw = pl.read_json(DATA_FILE)
    df_raw
    return (df_raw,)


@app.cell
def _(df_raw, pl):
    # データ前処理
    df = (
        df_raw
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
            ]
        )
        # 日付順にソート
        .sort("date")
    )
    df
    return (df,)


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
def _(alt, df_filtered, mo):
    # パット推移グラフ
    putt_chart = (
        alt.Chart(df_filtered)
        .mark_line(point=True, color="green")
        .encode(
            x=alt.X("date:T", title="日付"),
            y=alt.Y("total_putt:Q", title="パット数", scale=alt.Scale(zero=False)),
            tooltip=["date:T", "total_putt:Q", "golf_place_name:N"],
        )
        .properties(title="パット数推移", width=700, height=300)
        .interactive()
    )

    mean_putt = df_filtered.select("total_putt").mean().item()

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
            x=alt.X("year:O", title="年"),
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
            x=alt.X("year_int:O", title="年"),
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
        step=0.1,
        value=139.8,
        label="中心経度(lon)",
    )
    center_lat = mo.ui.slider(
        start=20.0,
        stop=50.0,
        step=0.1,
        value=35.9,
        label="中心緯度(lat)",
    )
    map_scale = mo.ui.slider(
        start=1000,
        stop=40000,
        step=1000,
        value=10000,
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


if __name__ == "__main__":
    app.run()
