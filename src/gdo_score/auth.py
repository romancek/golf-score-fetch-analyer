"""認証処理モジュール

GDOサイトへのログイン処理を提供する。
"""

import logging

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .browser import save_html, save_screenshot
from .config import Settings
from .selectors import LOGIN

logger = logging.getLogger(__name__)


class LoginError(Exception):
    """ログイン失敗時の例外"""

    pass


def login(page: Page, settings: Settings) -> bool:
    """GDOサイトにログインする

    Args:
        page: Playwrightページ
        settings: アプリケーション設定

    Returns:
        bool: ログイン成功時True

    Raises:
        LoginError: ログインに失敗した場合
    """
    logger.info("GDOサイトにアクセスします: %s", settings.gdo_base_url)
    page.goto(settings.gdo_base_url)

    # モーダルが表示された場合は閉じる
    _close_modal_if_exists(page, settings)

    # ログインボタンをクリック
    logger.info("ログインボタンをクリックします")
    _click_login_button(page, settings)

    # 認証情報を入力
    logger.info("認証情報を入力します")
    _fill_credentials(page, settings)

    # ログインボタンをクリック
    logger.info("ログインフォームを送信します")
    _submit_login_form(page, settings)

    # ログイン成功を確認
    if _verify_login(page):
        logger.info("ログインに成功しました")
        return True
    else:
        if settings.debug:
            save_screenshot(page, settings.debug_dir, "login_failed")
            save_html(page, settings.debug_dir, "login_failed")
        raise LoginError("ログインに失敗しました")


def _close_modal_if_exists(page: Page, _settings: Settings) -> None:
    """モーダルダイアログを閉じる(存在する場合)

    Args:
        page: Playwrightページ
        _settings: アプリケーション設定(将来の拡張用)
    """
    try:
        modal_button = page.locator(LOGIN.MODAL_CLOSE_BUTTON)
        if modal_button.is_visible(timeout=2000):
            modal_button.click()
            logger.info("モーダルダイアログを閉じました")
    except PlaywrightTimeoutError:
        logger.debug("モーダルダイアログは表示されていません")


@retry(
    retry=retry_if_exception_type(PlaywrightTimeoutError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
)
def _click_login_button(page: Page, settings: Settings) -> None:
    """ログインボタンをクリックする

    Args:
        page: Playwrightページ
        settings: アプリケーション設定

    Raises:
        LoginError: ログインボタンが見つからない場合
    """
    try:
        page.click(LOGIN.LOGIN_BUTTON, timeout=settings.timeout)
    except PlaywrightTimeoutError:
        if settings.debug:
            save_screenshot(page, settings.debug_dir, "login_button_not_found")
            save_html(page, settings.debug_dir, "login_button_not_found")
        raise LoginError("ログインボタンが見つかりません") from None


def _fill_credentials(page: Page, settings: Settings) -> None:
    """認証情報を入力する

    Args:
        page: Playwrightページ
        settings: アプリケーション設定

    Raises:
        LoginError: 入力フィールドが見つからない場合
    """
    try:
        page.fill(LOGIN.USERNAME_INPUT, settings.gdo_login_id)
        page.fill(LOGIN.PASSWORD_INPUT, settings.gdo_password.get_secret_value())
    except PlaywrightTimeoutError:
        if settings.debug:
            save_screenshot(page, settings.debug_dir, "credential_fields_not_found")
            save_html(page, settings.debug_dir, "credential_fields_not_found")
        raise LoginError("認証情報入力フィールドが見つかりません") from None


def _submit_login_form(page: Page, settings: Settings) -> None:
    """ログインフォームを送信する

    Args:
        page: Playwrightページ
        settings: アプリケーション設定

    Raises:
        LoginError: 送信ボタンが見つからない場合
    """
    try:
        page.click(LOGIN.SUBMIT_BUTTON)
        page.wait_for_load_state("networkidle")
    except PlaywrightTimeoutError:
        if settings.debug:
            save_screenshot(page, settings.debug_dir, "submit_button_not_found")
            save_html(page, settings.debug_dir, "submit_button_not_found")
        raise LoginError("ログイン送信ボタンが見つかりません") from None


def _verify_login(page: Page) -> bool:
    """ログイン成功を確認する

    Args:
        page: Playwrightページ

    Returns:
        bool: ログイン成功時True
    """
    # ログイン後、スコアサイトのトップページに戻る
    # ログインリンクが消えていればログイン成功
    try:
        login_button = page.locator(LOGIN.LOGIN_BUTTON)
        # ログインボタンが見えなくなっていればログイン成功
        return not login_button.is_visible(timeout=5000)
    except PlaywrightTimeoutError:
        # タイムアウトした場合は見えない = ログイン成功
        return True
