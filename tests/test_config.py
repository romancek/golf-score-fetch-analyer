"""config.pyのテスト"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from gdo_score.config import Settings, get_settings


class TestSettings:
    """Settingsクラスのテスト"""

    def test_create_settings_from_env(self, monkeypatch):
        """環境変数から設定を作成できること"""
        monkeypatch.setenv("GDO_LOGIN_ID", "test@example.com")
        monkeypatch.setenv("GDO_PASSWORD", "test_password")

        settings = Settings()

        assert settings.gdo_login_id == "test@example.com"
        assert settings.gdo_password.get_secret_value() == "test_password"

    def test_default_values(self, monkeypatch):
        """デフォルト値が正しく設定されること"""
        monkeypatch.setenv("GDO_LOGIN_ID", "test@example.com")
        monkeypatch.setenv("GDO_PASSWORD", "test_password")

        settings = Settings()

        assert settings.headless is True
        assert settings.timeout == 30000
        assert settings.debug is False
        assert settings.output_dir == Path("output")
        assert settings.debug_dir == Path("debug")

    def test_override_default_values(self, monkeypatch):
        """デフォルト値を上書きできること"""
        monkeypatch.setenv("GDO_LOGIN_ID", "test@example.com")
        monkeypatch.setenv("GDO_PASSWORD", "test_password")
        monkeypatch.setenv("HEADLESS", "false")
        monkeypatch.setenv("TIMEOUT", "60000")
        monkeypatch.setenv("DEBUG", "true")

        settings = Settings()

        assert settings.headless is False
        assert settings.timeout == 60000
        assert settings.debug is True

    def test_missing_required_field_raises_error(self, monkeypatch):
        """必須フィールドが欠けている場合はエラーになること"""
        # 環境変数をクリア
        monkeypatch.delenv("GDO_LOGIN_ID", raising=False)
        monkeypatch.delenv("GDO_PASSWORD", raising=False)

        with pytest.raises(ValidationError):
            Settings()

    def test_password_is_secret(self, monkeypatch):
        """パスワードがSecretStr型であること"""
        monkeypatch.setenv("GDO_LOGIN_ID", "test@example.com")
        monkeypatch.setenv("GDO_PASSWORD", "test_password")

        settings = Settings()

        # strとして直接アクセスできない
        assert str(settings.gdo_password) == "**********"
        # get_secret_value()で取得できる
        assert settings.gdo_password.get_secret_value() == "test_password"

    def test_output_dir_as_path(self, monkeypatch):
        """出力ディレクトリがPath型に変換されること"""
        monkeypatch.setenv("GDO_LOGIN_ID", "test@example.com")
        monkeypatch.setenv("GDO_PASSWORD", "test_password")
        monkeypatch.setenv("OUTPUT_DIR", "/custom/output")

        settings = Settings()

        assert isinstance(settings.output_dir, Path)
        assert settings.output_dir == Path("/custom/output")


class TestGetSettings:
    """get_settings関数のテスト"""

    def test_get_settings(self, monkeypatch):
        """設定を取得できること"""
        monkeypatch.setenv("GDO_LOGIN_ID", "test@example.com")
        monkeypatch.setenv("GDO_PASSWORD", "test_password")

        settings = get_settings()

        assert isinstance(settings, Settings)
        assert settings.gdo_login_id == "test@example.com"
