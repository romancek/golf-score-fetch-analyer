"""output.pyのテスト"""

import json
from pathlib import Path

import pytest

from gdo_score.models import ScoreData
from gdo_score.output import load_scores_from_json, save_scores_to_json


class TestSaveScoresToJson:
    """save_scores_to_json関数のテスト"""

    def test_save_single_score(self, tmp_path: Path, sample_score_data: ScoreData):
        """1件のスコアを保存できること"""
        output_path = save_scores_to_json(
            [sample_score_data],
            tmp_path,
            "test_scores.json",
        )

        assert output_path.exists()
        assert output_path.name == "test_scores.json"

        # ファイル内容を確認
        with output_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 1
        assert data[0]["year"] == "2025"
        assert data[0]["golf_place_name"] == "箱根くらかけゴルフ場"

    def test_save_multiple_scores(
        self,
        tmp_path: Path,
        sample_score_data: ScoreData,
        sample_score_data_minimal: ScoreData,
    ):
        """複数のスコアを保存できること"""
        output_path = save_scores_to_json(
            [sample_score_data, sample_score_data_minimal],
            tmp_path,
            "test_scores.json",
        )

        with output_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 2

    def test_save_empty_list(self, tmp_path: Path):
        """空のリストを保存できること"""
        output_path = save_scores_to_json([], tmp_path, "empty.json")

        with output_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert data == []

    def test_auto_generate_filename(self, tmp_path: Path, sample_score_data: ScoreData):
        """ファイル名を自動生成できること"""
        output_path = save_scores_to_json(
            [sample_score_data],
            tmp_path,
        )

        assert output_path.exists()
        assert output_path.name.startswith("scores_")
        assert output_path.suffix == ".json"

    def test_create_output_directory(
        self, tmp_path: Path, sample_score_data: ScoreData
    ):
        """出力ディレクトリが存在しない場合は作成すること"""
        nested_path = tmp_path / "nested" / "output"
        output_path = save_scores_to_json(
            [sample_score_data],
            nested_path,
            "test.json",
        )

        assert nested_path.exists()
        assert output_path.exists()

    def test_japanese_characters_preserved(
        self, tmp_path: Path, sample_score_data: ScoreData
    ):
        """日本語が正しく保存されること"""
        output_path = save_scores_to_json(
            [sample_score_data],
            tmp_path,
            "test.json",
        )

        with output_path.open("r", encoding="utf-8") as f:
            content = f.read()

        # 日本語がエスケープされていないこと
        assert "箱根くらかけゴルフ場" in content
        assert "神奈川県" in content


class TestLoadScoresFromJson:
    """load_scores_from_json関数のテスト"""

    def test_load_scores(self, tmp_path: Path, sample_score_data: ScoreData):
        """スコアを読み込めること"""
        # まず保存
        output_path = save_scores_to_json(
            [sample_score_data],
            tmp_path,
            "test.json",
        )

        # 読み込み
        scores = load_scores_from_json(output_path)

        assert len(scores) == 1
        assert scores[0].year == sample_score_data.year
        assert scores[0].golf_place_name == sample_score_data.golf_place_name
        assert scores[0].hall_scores == sample_score_data.hall_scores

    def test_load_multiple_scores(
        self,
        tmp_path: Path,
        sample_score_data: ScoreData,
        sample_score_data_minimal: ScoreData,
    ):
        """複数のスコアを読み込めること"""
        output_path = save_scores_to_json(
            [sample_score_data, sample_score_data_minimal],
            tmp_path,
            "test.json",
        )

        scores = load_scores_from_json(output_path)

        assert len(scores) == 2
        assert isinstance(scores[0], ScoreData)
        assert isinstance(scores[1], ScoreData)

    def test_load_empty_list(self, tmp_path: Path):
        """空のリストを読み込めること"""
        output_path = save_scores_to_json([], tmp_path, "empty.json")

        scores = load_scores_from_json(output_path)

        assert scores == []

    def test_file_not_found(self, tmp_path: Path):
        """存在しないファイルを読み込むとエラーになること"""
        with pytest.raises(FileNotFoundError):
            load_scores_from_json(tmp_path / "nonexistent.json")
