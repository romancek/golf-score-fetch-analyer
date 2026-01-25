"""設定管理モジュール

環境変数から設定を読み込み、アプリケーション全体で使用する設定を提供する。
"""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """アプリケーション設定

    環境変数または.envファイルから設定を読み込む。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # GDO認証情報(必須)
    gdo_login_id: str = Field(
        ...,
        description="GDOログインID(メールアドレス)",
    )
    gdo_password: SecretStr = Field(
        ...,
        description="GDOパスワード",
    )

    # オプション設定
    headless: bool = Field(
        default=True,
        description="ヘッドレスモード(true: ブラウザ非表示)",
    )
    timeout: int = Field(
        default=30000,
        description="タイムアウト(ミリ秒)",
    )
    debug: bool = Field(
        default=False,
        description="デバッグモード(true: デバッグ情報出力)",
    )
    output_dir: Path = Field(
        default=Path("output"),
        description="出力ディレクトリ",
    )
    debug_dir: Path = Field(
        default=Path("debug"),
        description="デバッグファイル出力ディレクトリ",
    )

    # GDOサイトURL
    gdo_base_url: str = Field(
        default="https://score.golfdigest.co.jp/",
        description="GDOスコアサイトのベースURL",
    )
    gdo_score_detail_url: str = Field(
        default="https://score.golfdigest.co.jp/member/score_detail.asp",
        description="スコア詳細ページのベースURL",
    )

    # リトライ・レート制限設定(DDoS対策)
    max_retries: int = Field(
        default=3,
        description="最大リトライ回数",
    )
    retry_min_wait: float = Field(
        default=2.0,
        description="リトライ最小待機時間(秒)",
    )
    retry_max_wait: float = Field(
        default=10.0,
        description="リトライ最大待機時間(秒)",
    )
    request_interval: float = Field(
        default=1.0,
        description="リクエスト間の待機時間(秒)",
    )
    max_consecutive_errors: int = Field(
        default=5,
        description="連続エラー許容回数(超過時は処理中断)",
    )


def get_settings() -> Settings:
    """設定インスタンスを取得する

    Returns:
        Settings: アプリケーション設定
    """
    return Settings()
