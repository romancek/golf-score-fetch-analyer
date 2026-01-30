"""データモデルモジュール

スコアデータの型定義とバリデーションを提供する。
既存のJSONフォーマットとの完全互換性を維持。
"""

from pydantic import BaseModel, Field


class ScoreData(BaseModel):
    """1ラウンドのスコアデータ

    GDOスコアサイトから取得した1ラウンド分のスコア情報を保持する。
    既存のJSONフォーマットと互換性を維持するため、フィールド名は変更不可。
    """

    # 日付情報
    year: str = Field(..., description="年(YYYY形式)")
    month: str = Field(..., description="月(MM形式)")
    day: str = Field(..., description="日(DD形式)")

    # ゴルフ場情報
    golf_place_name: str = Field(..., description="ゴルフ場名")
    course_former_half: str = Field(..., description="前半コース名")
    course_latter_half: str = Field(..., description="後半コース名")
    prefecture: str = Field(default="", description="都道府県")

    # コンディション
    weather: str = Field(default="", description="天気")
    wind: str = Field(default="", description="風")
    green: str = Field(default="", description="グリーン状態")
    tee: str = Field(default="", description="ティー")

    # スコア情報(18ホール分)
    hall_scores: list[str] = Field(default_factory=list, description="各ホールのスコア")
    putt_scores: list[str] = Field(
        default_factory=list, description="各ホールのパット数"
    )

    # ショット情報
    teeshots: list[str] = Field(
        default_factory=list, description="ティーショット使用クラブ"
    )
    fairway_keeps: list[str] = Field(
        default_factory=list, description="フェアウェイキープ状況"
    )
    oneons: list[str] = Field(default_factory=list, description="パーオン状況")

    # ペナルティ情報
    obs: list[str] = Field(default_factory=list, description="OB数")
    bunkers: list[str] = Field(default_factory=list, description="バンカー数")
    penaltys: list[str] = Field(default_factory=list, description="ペナルティ数")

    # ホール情報
    par_scores: list[str] = Field(
        default_factory=list, description="各ホールのパー数(18ホール分)"
    )
    yard_scores: list[str] = Field(
        default_factory=list, description="各ホールのヤード数(18ホール分)"
    )

    # 同伴者情報
    accompany_member_names: list[str] = Field(
        default_factory=list, description="同伴者名"
    )
    accompany_member_scores: list[list[str]] = Field(
        default_factory=list, description="同伴者のスコア"
    )

    def to_dict(self) -> dict:
        """辞書形式に変換(JSON出力用)

        Returns:
            dict: スコアデータの辞書表現
        """
        return self.model_dump()
