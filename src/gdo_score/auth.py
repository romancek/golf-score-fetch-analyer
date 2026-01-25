"""認証処理モジュール

GDOサイトへのログイン処理を提供する。
"""

import logging
import time

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


def _goto_with_retry(page: Page, url: str, settings: Settings) -> None:
    """リトライ付きでページ遷移する

    Args:
        page: Playwrightページ
        url: 遷移先URL
        settings: アプリケーション設定

    Raises:
        LoginError: 最大リトライ回数を超えた場合
    """
    last_error = None
    for attempt in range(1, settings.max_retries + 1):
        try:
            page.goto(
                url,
                timeout=settings.timeout,
                wait_until="domcontentloaded",
            )
            return
        except PlaywrightTimeoutError as e:
            last_error = e
            logger.warning(
                "ページ遷移がタイムアウトしました (試行 %d/%d): %s",
                attempt,
                settings.max_retries,
                url,
            )
            if attempt < settings.max_retries:
                import time

                wait_time = min(
                    settings.retry_min_wait * (2 ** (attempt - 1)),
                    settings.retry_max_wait,
                )
                logger.info("%.1f秒後にリトライします...", wait_time)
                time.sleep(wait_time)

    if settings.debug:
        save_screenshot(page, settings.debug_dir, "goto_failed")
        save_html(page, settings.debug_dir, "goto_failed")
    raise LoginError(f"ページ遷移に失敗しました: {url}") from last_error


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
    _goto_with_retry(page, settings.gdo_base_url, settings)

    # モーダルが表示された場合は閉じる
    _close_modal_if_exists(page, settings)

    # ログインボタンをクリック
    time.sleep(1)
    logger.info("ログインボタンをクリックします")

    # ログインリンクをクリックしてページ遷移を待つ
    login_link = page.get_by_role("link", name="ログイン", exact=True)
    login_link.click()

    # ページ遷移を待つ
    page.wait_for_load_state("domcontentloaded")
    time.sleep(2)  # JSによるリダイレクト完了を待つ

    # ログインフォームが表示されるか確認
    # 既にログイン済みの場合はフォームが表示されずにリダイレクトされる
    try:
        page.wait_for_selector(LOGIN.USERNAME_INPUT, timeout=10000)
        logger.info("ログインフォームが表示されました")

        if settings.debug:
            save_screenshot(page, settings.debug_dir, "login_page_loaded")
            save_html(page, settings.debug_dir, "login_page_loaded")

        # 認証情報を入力
        logger.info("認証情報を入力します")
        _fill_credentials(page, settings)

        # ログインボタンをクリック
        logger.info("ログインフォームを送信します")
        _submit_login_form(page, settings)

        # ページ遷移を待つ
        page.wait_for_load_state("domcontentloaded")
    except PlaywrightTimeoutError:
        # ログインフォームが表示されない場合は既にログイン済みの可能性
        logger.info("ログインフォームが表示されませんでした(既にログイン済みの可能性)")

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
    # 方法1: alt属性で画像ボタンを探す (GDOのログインボタンは input type="image" alt="ログイン")
    try:
        submit_button = page.get_by_role("button", name="ログイン")
        if submit_button.is_visible(timeout=3000):
            submit_button.click()
            page.wait_for_load_state("domcontentloaded")
            return
    except PlaywrightTimeoutError:
        logger.info("ボタン(role)が見つかりません")

    # 方法2: 画像のalt属性で探す
    try:
        submit_button = page.locator('input[type="image"][alt="ログイン"]')
        if submit_button.is_visible(timeout=3000):
            submit_button.click()
            page.wait_for_load_state("domcontentloaded")
            return
    except PlaywrightTimeoutError:
        logger.info("画像ボタンが見つかりません")

    # 方法3: CSSセレクタで探す
    try:
        submit_button = page.locator(LOGIN.SUBMIT_BUTTON).first
        if submit_button.is_visible(timeout=3000):
            submit_button.click()
            page.wait_for_load_state("domcontentloaded")
            return
    except PlaywrightTimeoutError:
        logger.info("送信ボタン(CSS)が見つかりません")

    # 方法4: フォームをJSで送信
    try:
        page.evaluate("""
            const form = document.querySelector('form');
            if (form) {
                form.submit();
            }
        """)
        page.wait_for_load_state("domcontentloaded")
        logger.info("JavaScriptでフォームを送信しました")
        return
    except Exception as e:
        logger.warning("フォームのJS送信に失敗: %s", e)

    if settings.debug:
        save_screenshot(page, settings.debug_dir, "submit_button_not_found")
        save_html(page, settings.debug_dir, "submit_button_not_found")
    raise LoginError("ログイン送信ボタンが見つかりません")


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
