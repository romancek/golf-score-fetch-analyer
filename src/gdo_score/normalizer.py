"""データ正規化モジュール

ゴルフ場名、県名、コース名などのデータを正規化する。
"""

import json
import re
from pathlib import Path

import yaml


class DataNormalizer:
    """データ正規化クラス"""

    def __init__(self, project_root: Path | None = None):
        """初期化

        Args:
            project_root: プロジェクトルートパス（省略時は自動検出）
        """
        if project_root is None:
            # このファイルの位置から project_root を推測
            project_root = Path(__file__).parent.parent.parent

        self.project_root = project_root
        self._load_mappings()

    def _load_mappings(self) -> None:
        """マッピングファイルを読み込む"""
        # ゴルフ場名マッピング
        golf_place_file = self.project_root / "data" / "golf_place_name_mapping.json"
        if golf_place_file.exists():
            with golf_place_file.open(encoding="utf-8") as f:
                self.golf_place_mapping: dict[str, str] = json.load(f)
        else:
            self.golf_place_mapping = {}

        # 県名マッピング
        prefecture_file = self.project_root / "data" / "prefecture_mapping.yaml"
        if prefecture_file.exists():
            with prefecture_file.open(encoding="utf-8") as f:
                self.prefecture_mapping: dict[str, str] = yaml.safe_load(f) or {}
        else:
            self.prefecture_mapping = {}

    def normalize_golf_place_name(self, name: str) -> str:
        """ゴルフ場名を正規化する

        Args:
            name: 元のゴルフ場名

        Returns:
            str: 正規化されたゴルフ場名
        """
        return self.golf_place_mapping.get(name, name)

    def normalize_prefecture(self, prefecture: str) -> str:
        """県名を正規化する

        Args:
            prefecture: 元の県名

        Returns:
            str: 正規化された県名
        """
        return self.prefecture_mapping.get(prefecture, prefecture)

    def clean_course_name(self, course_name: str) -> str:
        """コース名から【】を除去する

        Args:
            course_name: 元のコース名（例: "IN 【REGULARティー】"）

        Returns:
            str: クリーンなコース名（例: "IN"）

        Examples:
            >>> normalizer = DataNormalizer()
            >>> normalizer.clean_course_name("IN 【REGULARティー】")
            'IN'
            >>> normalizer.clean_course_name("桜OUT 【BACKティー】")
            '桜OUT'
            >>> normalizer.clean_course_name("箱根(OUT)")
            '箱根(OUT)'
        """
        # 【】とその中身、および前後の空白を削除
        cleaned = re.sub(r"\s*【[^】]*】\s*", "", course_name)
        return cleaned.strip()
