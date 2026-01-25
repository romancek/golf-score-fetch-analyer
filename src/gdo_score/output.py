"""出力処理モジュール

スコアデータをJSON形式でファイルに出力する。
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from .models import ScoreData

logger = logging.getLogger(__name__)


def save_scores_to_json(
    scores: list[ScoreData],
    output_dir: Path,
    filename: str | None = None,
) -> Path:
    """スコアデータをJSONファイルに保存する

    Args:
        scores: スコアデータのリスト
        output_dir: 出力ディレクトリ
        filename: ファイル名(省略時は自動生成)

    Returns:
        Path: 保存したファイルのパス
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"scores_{timestamp}.json"

    output_path = output_dir / filename

    # ScoreDataをdictに変換
    scores_dict = [score.to_dict() for score in scores]

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(scores_dict, f, ensure_ascii=False, indent=2)

    logger.info("スコアデータを保存しました: %s (%d件)", output_path, len(scores))
    return output_path


def load_scores_from_json(file_path: Path) -> list[ScoreData]:
    """JSONファイルからスコアデータを読み込む

    Args:
        file_path: JSONファイルのパス

    Returns:
        list[ScoreData]: スコアデータのリスト
    """
    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    scores = [ScoreData(**item) for item in data]
    logger.info("スコアデータを読み込みました: %s (%d件)", file_path, len(scores))
    return scores
