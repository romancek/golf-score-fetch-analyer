"""ブラウザ管理モジュール

Playwrightブラウザのライフサイクル管理を提供する。
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from .config import Settings

logger = logging.getLogger(__name__)


@contextmanager
def create_browser_context(
    settings: Settings,
) -> Generator[tuple[Browser, BrowserContext, Page]]:
    """ブラウザコンテキストを生成するコンテキストマネージャ

    Args:
        settings: アプリケーション設定

    Yields:
        tuple[Browser, BrowserContext, Page]: ブラウザ、コンテキスト、ページのタプル
    """
    with sync_playwright() as playwright:
        # ボット検出を回避するためのブラウザ起動オプション
        browser = playwright.chromium.launch(
            headless=settings.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        logger.info(
            "ブラウザを起動しました(headless=%s)",
            settings.headless,
        )

        # より実際のブラウザに近い設定でコンテキストを作成
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            extra_http_headers={
                "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            },
        )
        context.set_default_timeout(settings.timeout)

        # デバッグモードの場合はトレースを開始
        if settings.debug:
            context.tracing.start(screenshots=True, snapshots=True, sources=True)
            logger.info("トレース記録を開始しました")

        page = context.new_page()

        # navigator.webdriverをfalseに設定してボット検出を回避
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        try:
            yield browser, context, page
        finally:
            # デバッグモードの場合はトレースを保存
            if settings.debug:
                _save_trace(context, settings.debug_dir)

            context.close()
            browser.close()
            logger.info("ブラウザを終了しました")


def _save_trace(context: BrowserContext, debug_dir: Path) -> None:
    """トレースファイルを保存する

    Args:
        context: ブラウザコンテキスト
        debug_dir: デバッグファイル出力ディレクトリ
    """
    debug_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trace_path = debug_dir / f"trace_{timestamp}.zip"
    context.tracing.stop(path=str(trace_path))
    logger.info("トレースを保存しました: %s", trace_path)


def save_screenshot(page: Page, debug_dir: Path, name: str) -> Path:
    """スクリーンショットを保存する

    Args:
        page: Playwrightページ
        debug_dir: デバッグファイル出力ディレクトリ
        name: ファイル名(拡張子なし)

    Returns:
        Path: 保存したファイルのパス
    """
    debug_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = debug_dir / f"{name}_{timestamp}.png"
    page.screenshot(path=str(screenshot_path))
    logger.info("スクリーンショットを保存しました: %s", screenshot_path)
    return screenshot_path


def save_html(page: Page, debug_dir: Path, name: str) -> Path:
    """ページHTMLを保存する

    Args:
        page: Playwrightページ
        debug_dir: デバッグファイル出力ディレクトリ
        name: ファイル名(拡張子なし)

    Returns:
        Path: 保存したファイルのパス
    """
    debug_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = debug_dir / f"{name}_{timestamp}.html"
    html_path.write_text(page.content(), encoding="utf-8")
    logger.info("HTMLを保存しました: %s", html_path)
    return html_path
