"""CLIエントリーポイントモジュール

コマンドラインからスコア取得ツールを実行するためのインターフェース。
"""

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .auth import LoginError, login
from .browser import create_browser_context
from .config import Settings, get_settings
from .output import save_scores_to_json
from .scraper import ScoreScraper


def setup_logging(debug: bool = False) -> None:
    """ロギングを設定する

    Args:
        debug: デバッグモードの場合True
    """
    level = logging.DEBUG if debug else logging.INFO
    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def parse_args() -> argparse.Namespace:
    """コマンドライン引数をパースする

    Returns:
        argparse.Namespace: パース済み引数
    """
    parser = argparse.ArgumentParser(
        prog="gdo-score",
        description="GDOスコアサイトからスコア情報を取得するツール",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="出力ディレクトリ(デフォルト: 環境変数OUTPUT_DIRまたはoutput)",
    )

    parser.add_argument(
        "--headless",
        type=str,
        choices=["true", "false"],
        default=None,
        help="ヘッドレスモード(デフォルト: 環境変数HEADLESSまたはtrue)",
    )

    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="デバッグモードを有効にする",
    )

    parser.add_argument(
        "--filename",
        "-f",
        type=str,
        default=None,
        help="出力ファイル名(省略時は自動生成)",
    )

    parser.add_argument(
        "--year",
        "-y",
        type=str,
        default=None,
        help="取得する年を指定(例: 2024 または 2025,2024)。カンマ区切りで複数年指定可能。省略時は全年のデータを取得",
    )

    return parser.parse_args()


def main() -> int:
    """メインエントリーポイント

    Returns:
        int: 終了コード(0: 成功, 1: 失敗)
    """
    args = parse_args()

    # 設定を読み込み
    try:
        settings = get_settings()
    except Exception as e:
        print(f"設定の読み込みに失敗しました: {e}", file=sys.stderr)
        print("環境変数またはz.envファイルを確認してください。", file=sys.stderr)
        return 1

    # コマンドライン引数で設定を上書き
    if args.output is not None:
        settings = Settings(
            gdo_login_id=settings.gdo_login_id,
            gdo_password=settings.gdo_password,
            headless=settings.headless,
            timeout=settings.timeout,
            debug=args.debug or settings.debug,
            output_dir=args.output,
            debug_dir=settings.debug_dir,
            gdo_base_url=settings.gdo_base_url,
            gdo_score_detail_url=settings.gdo_score_detail_url,
        )

    if args.headless is not None:
        headless_value = args.headless.lower() == "true"
        settings = Settings(
            gdo_login_id=settings.gdo_login_id,
            gdo_password=settings.gdo_password,
            headless=headless_value,
            timeout=settings.timeout,
            debug=args.debug or settings.debug,
            output_dir=settings.output_dir,
            debug_dir=settings.debug_dir,
            gdo_base_url=settings.gdo_base_url,
            gdo_score_detail_url=settings.gdo_score_detail_url,
        )

    if args.debug:
        settings = Settings(
            gdo_login_id=settings.gdo_login_id,
            gdo_password=settings.gdo_password,
            headless=settings.headless,
            timeout=settings.timeout,
            debug=True,
            output_dir=settings.output_dir,
            debug_dir=settings.debug_dir,
            gdo_base_url=settings.gdo_base_url,
            gdo_score_detail_url=settings.gdo_score_detail_url,
        )

    # ロギング設定
    setup_logging(settings.debug)
    logger = logging.getLogger(__name__)

    logger.info("GDOスコア取得ツール v%s を開始します", __version__)

    try:
        with create_browser_context(settings) as (_browser, _context, page):
            # ログイン
            logger.info("GDOサイトにログインします...")
            login(page, settings)

            # スコア取得
            target_years = None
            if args.year:
                try:
                    target_years = [int(y.strip()) for y in args.year.split(",")]
                    logger.info(
                        "スコア情報を取得します(対象年: %s)...",
                        ", ".join(map(str, target_years)),
                    )
                except ValueError:
                    logger.error("年の指定が不正です: %s", args.year)
                    return 1
            else:
                logger.info("スコア情報を取得します...")
            scraper = ScoreScraper(page, settings)
            scores = scraper.scrape_all_scores(target_years=target_years)

            if not scores:
                logger.warning("取得できるスコアがありませんでした")
                return 0

            # 保存
            output_path = save_scores_to_json(
                scores,
                settings.output_dir,
                args.filename,
            )
            logger.info("完了: %s", output_path)

    except LoginError as e:
        logger.exception("ログインに失敗しました: %s", e)
        return 1
    except Exception as e:
        logger.exception("予期しないエラーが発生しました: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
