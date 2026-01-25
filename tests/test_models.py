"""models.pyのテスト"""

import pytest
from pydantic import ValidationError

from gdo_score.models import ScoreData


class TestScoreData:
    """ScoreDataモデルのテスト"""

    def test_create_score_data_with_required_fields(self):
        """必須フィールドのみでScoreDataを作成できること"""
        score = ScoreData(
            year="2025",
            month="04",
            day="28",
            golf_place_name="テストゴルフ場",
            course_former_half="OUT",
            course_latter_half="IN",
        )

        assert score.year == "2025"
        assert score.month == "04"
        assert score.day == "28"
        assert score.golf_place_name == "テストゴルフ場"
        assert score.course_former_half == "OUT"
        assert score.course_latter_half == "IN"

    def test_create_score_data_with_all_fields(self, sample_score_data: ScoreData):
        """全フィールドでScoreDataを作成できること"""
        assert sample_score_data.year == "2025"
        assert sample_score_data.weather == "曇り"
        assert len(sample_score_data.hall_scores) == 18
        assert len(sample_score_data.accompany_member_names) == 3

    def test_default_values(self, sample_score_data_minimal: ScoreData):
        """デフォルト値が正しく設定されること"""
        assert sample_score_data_minimal.prefecture == ""
        assert sample_score_data_minimal.weather == ""
        assert sample_score_data_minimal.wind == ""
        assert sample_score_data_minimal.green == ""
        assert sample_score_data_minimal.tee == ""
        assert sample_score_data_minimal.hall_scores == []
        assert sample_score_data_minimal.putt_scores == []
        assert sample_score_data_minimal.accompany_member_names == []

    def test_missing_required_field_raises_error(self):
        """必須フィールドが欠けている場合はエラーになること"""
        with pytest.raises(ValidationError):
            ScoreData(
                year="2025",
                month="04",
                # day is missing
                golf_place_name="テストゴルフ場",
                course_former_half="OUT",
                course_latter_half="IN",
            )

    def test_to_dict(self, sample_score_data: ScoreData):
        """to_dict()が正しく辞書を返すこと"""
        result = sample_score_data.to_dict()

        assert isinstance(result, dict)
        assert result["year"] == "2025"
        assert result["month"] == "04"
        assert result["golf_place_name"] == "箱根くらかけゴルフ場"
        assert len(result["hall_scores"]) == 18

    def test_to_dict_json_compatible(self, sample_score_data: ScoreData):
        """to_dict()の結果がJSON互換であること"""
        import json

        result = sample_score_data.to_dict()
        # JSONシリアライズできることを確認
        json_str = json.dumps(result, ensure_ascii=False)
        # JSONデシリアライズできることを確認
        restored = json.loads(json_str)

        assert restored["year"] == sample_score_data.year
        assert restored["golf_place_name"] == sample_score_data.golf_place_name

    def test_from_dict(self, sample_score_data: ScoreData):
        """辞書からScoreDataを作成できること"""
        data = sample_score_data.to_dict()
        restored = ScoreData(**data)

        assert restored.year == sample_score_data.year
        assert restored.golf_place_name == sample_score_data.golf_place_name
        assert restored.hall_scores == sample_score_data.hall_scores
