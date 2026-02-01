"""スクレイピングモジュール

GDOスコアページからスコアデータを抽出する。
"""

import logging
import re
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
from .models import ScoreData
from .selectors import SCORE_DETAIL

logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """スクレイピング失敗時の例外"""

    pass


class TooManyErrorsError(ScraperError):
    """連続エラー回数超過時の例外"""

    pass


class ScoreScraper:
    """スコアページからデータを抽出するクラス"""

    # スコア一覧ページURL
    SCORE_LIST_URL = (
        "https://score.golfdigest.co.jp/score/list?mode=0&page={page}&gc_id="
    )
    # スコア詳細ページのラウンドリンクセレクター
    ROUND_LINK_SELECTOR = (
        "#container > div.score > div.score__container > div.score__main > "
        "div > table > tbody > tr > td:nth-child(2) > div > "
        "a.score__all__table__gc_name_text"
    )

    def __init__(self, page: Page, settings: Settings):
        """初期化

        Args:
            page: Playwrightページ
            settings: アプリケーション設定
        """
        self.page = page
        self.settings = settings
        self._consecutive_errors = 0

    def _wait_between_requests(self) -> None:
        """リクエスト間の待機(DDoS対策)"""
        interval = self.settings.request_interval
        if interval > 0:
            logger.debug("リクエスト間隔: %.1f秒待機", interval)
            time.sleep(interval)

    def _check_consecutive_errors(self) -> None:
        """連続エラー回数をチェックし、上限超過時は例外を発生させる"""
        if self._consecutive_errors >= self.settings.max_consecutive_errors:
            raise TooManyErrorsError(
                f"連続エラーが{self.settings.max_consecutive_errors}回を超えました。"
                "サーバーに問題がある可能性があります。処理を中断します。"
            )

    def _reset_consecutive_errors(self) -> None:
        """連続エラーカウンタをリセット"""
        self._consecutive_errors = 0

    def _increment_consecutive_errors(self) -> None:
        """連続エラーカウンタをインクリメント"""
        self._consecutive_errors += 1
        logger.warning(
            "連続エラー: %d/%d",
            self._consecutive_errors,
            self.settings.max_consecutive_errors,
        )

    def scrape_all_scores(
        self, target_years: list[int] | None = None
    ) -> list[ScoreData]:
        """すべてのスコアを取得する

        Args:
            target_years: 取得対象の年のリスト。Noneの場合は全年のデータを取得

        Returns:
            list[ScoreData]: スコアデータのリスト

        Raises:
            TooManyErrorsError: 連続エラー回数が上限を超えた場合
        """
        scores: list[ScoreData] = []
        page_num = 1
        older_year_count = 0  # 対象年より古いスコアが連続で見つかった回数

        while True:
            logger.info("スコア一覧ページ %d を取得中...", page_num)

            try:
                url = self.SCORE_LIST_URL.format(page=page_num)
                self._goto_with_retry(url)
                self._reset_consecutive_errors()
            except ScraperError:
                self._increment_consecutive_errors()
                self._check_consecutive_errors()
                page_num += 1
                continue

            # ラウンドリンクを取得
            round_links = self.page.locator(self.ROUND_LINK_SELECTOR).all()

            if not round_links:
                logger.info("ページ %d にスコアがありません。取得完了。", page_num)
                break

            # 各ラウンドのリンクを取得
            links = [link.get_attribute("href") for link in round_links]
            logger.info("ページ %d: %d件のラウンドを発見", page_num, len(links))

            # 各リンクにアクセスしてスコアを取得
            for link in links:
                if link is None:
                    continue

                # プロトコル相対URLを絶対URLに変換
                if link.startswith("//"):
                    link = "https:" + link
                elif link.startswith("/"):
                    link = "https://score.golfdigest.co.jp" + link

                # リクエスト間の待機(DDoS対策)
                self._wait_between_requests()

                try:
                    score = self._scrape_score_detail(link)

                    # 年でフィルタリング
                    if target_years is not None:
                        score_year = int(score.year)
                        min_target_year = min(target_years)

                        if score_year not in target_years:
                            # 対象年より古い場合
                            if score_year < min_target_year:
                                older_year_count += 1
                                logger.debug(
                                    "対象年より古いスコアをスキップ: %s/%s/%s (対象年: %s)",
                                    score.year,
                                    score.month,
                                    score.day,
                                    ", ".join(map(str, target_years)),
                                )
                                # 連続して10件対象年より古いスコアが見つかったら終了
                                if older_year_count >= 10:
                                    logger.info(
                                        "対象年(%s)より古いスコアが連続して見つかったため終了します",
                                        ", ".join(map(str, target_years)),
                                    )
                                    break
                            else:
                                # 対象年より新しい場合はスキップするがカウントしない
                                logger.debug(
                                    "対象年外のスコアをスキップ: %s/%s/%s (対象年: %s)",
                                    score.year,
                                    score.month,
                                    score.day,
                                    ", ".join(map(str, target_years)),
                                )
                            continue
                        else:
                            older_year_count = 0  # 対象年のスコアが見つかったらリセット

                    scores.append(score)
                    self._reset_consecutive_errors()
                    logger.info(
                        "スコア取得完了: %s/%s/%s %s",
                        score.year,
                        score.month,
                        score.day,
                        score.golf_place_name,
                    )
                except ScraperError as e:
                    self._increment_consecutive_errors()
                    logger.warning("スコア取得失敗: %s - %s", link, e)
                    if self.settings.debug:
                        save_screenshot(
                            self.page, self.settings.debug_dir, "scrape_error"
                        )
                        save_html(self.page, self.settings.debug_dir, "scrape_error")

                    # 連続エラー回数チェック
                    self._check_consecutive_errors()

            # 年フィルタリング時に対象年より古いスコアが連続したらループ終了
            if target_years is not None and older_year_count >= 10:
                break

            page_num += 1

            # ページ間の待機(DDoS対策)
            self._wait_between_requests()

        logger.info("全 %d 件のスコアを取得しました", len(scores))
        return scores

    def _goto_with_retry(self, url: str) -> None:
        """リトライ付きでページ遷移する

        Args:
            url: 遷移先URL

        Raises:
            ScraperError: ページ遷移に失敗した場合
        """

        @retry(
            retry=retry_if_exception_type(PlaywrightTimeoutError),
            stop=stop_after_attempt(self.settings.max_retries),
            wait=wait_exponential(
                multiplier=1,
                min=self.settings.retry_min_wait,
                max=self.settings.retry_max_wait,
            ),
            before_sleep=lambda retry_state: logger.warning(
                "リトライ %d/%d: %s",
                retry_state.attempt_number,
                self.settings.max_retries,
                url,
            ),
        )
        def _goto() -> None:
            self.page.goto(url, wait_until="domcontentloaded")

        try:
            _goto()
        except PlaywrightTimeoutError as e:
            raise ScraperError(f"ページ遷移に失敗しました: {url}") from e

    def _scrape_score_detail(self, url: str) -> ScoreData:
        """スコア詳細ページからデータを抽出する

        Args:
            url: スコア詳細ページのURL

        Returns:
            ScoreData: スコアデータ
        """
        self._goto_with_retry(url)

        # 日付情報
        date_text = self._get_text(SCORE_DETAIL.DATE)
        year = date_text[:4]
        month = date_text[5:7]
        day = date_text[8:10]

        # ゴルフ場情報
        golf_place_name, prefecture = self._get_golf_place_info()

        # コンディション情報
        weather = self._get_text(SCORE_DETAIL.WEATHER)
        wind = self._get_text(SCORE_DETAIL.WIND)
        green = self._get_text(SCORE_DETAIL.GREEN)
        tee = self._get_text(SCORE_DETAIL.TEE)

        # コース名
        course_former_text = self._get_text(SCORE_DETAIL.COURSE_FORMER_HALF)
        course_latter_text = self._get_text(SCORE_DETAIL.COURSE_LATTER_HALF)
        course_former_half = self._extract_course_name(course_former_text)
        course_latter_half = self._extract_course_name(course_latter_text)

        # スコア情報
        hall_scores = self._get_scores_from_rows(
            SCORE_DETAIL.SCORE_ROW_FORMER, SCORE_DETAIL.SCORE_ROW_LATTER
        )
        putt_scores = self._get_scores_from_rows(
            SCORE_DETAIL.PUTT_ROW_FORMER, SCORE_DETAIL.PUTT_ROW_LATTER
        )

        # ショット情報
        teeshots = self._get_scores_from_rows(
            SCORE_DETAIL.TEESHOT_ROW_FORMER, SCORE_DETAIL.TEESHOT_ROW_LATTER
        )
        fairway_keeps = self._get_class_based_data(
            SCORE_DETAIL.FAIRWAY_KEEP_ROW_FORMER, SCORE_DETAIL.FAIRWAY_KEEP_ROW_LATTER
        )
        oneons = self._get_class_based_data(
            SCORE_DETAIL.ONEON_ROW_FORMER, SCORE_DETAIL.ONEON_ROW_LATTER
        )

        # ペナルティ情報
        obs = self._get_scores_from_rows(
            SCORE_DETAIL.OB_ROW_FORMER, SCORE_DETAIL.OB_ROW_LATTER
        )
        bunkers = self._get_scores_from_rows(
            SCORE_DETAIL.BUNKER_ROW_FORMER, SCORE_DETAIL.BUNKER_ROW_LATTER
        )
        penaltys = self._get_scores_from_rows(
            SCORE_DETAIL.PENALTY_ROW_FORMER, SCORE_DETAIL.PENALTY_ROW_LATTER
        )

        # ホール情報
        par_scores = self._get_scores_from_rows(
            SCORE_DETAIL.PAR_ROW_FORMER, SCORE_DETAIL.PAR_ROW_LATTER
        )
        yard_scores = self._get_scores_from_rows(
            SCORE_DETAIL.YARD_ROW_FORMER, SCORE_DETAIL.YARD_ROW_LATTER
        )

        # 同伴者情報
        accompany_member_names, accompany_member_scores = self._get_accompany_members()

        return ScoreData(
            year=year,
            month=month,
            day=day,
            golf_place_name=golf_place_name,
            course_former_half=course_former_half,
            course_latter_half=course_latter_half,
            prefecture=prefecture,
            weather=weather,
            wind=wind,
            green=green,
            tee=tee,
            hall_scores=hall_scores,
            putt_scores=putt_scores,
            teeshots=teeshots,
            fairway_keeps=fairway_keeps,
            oneons=oneons,
            obs=obs,
            bunkers=bunkers,
            penaltys=penaltys,
            par_scores=par_scores,
            yard_scores=yard_scores,
            accompany_member_names=accompany_member_names,
            accompany_member_scores=accompany_member_scores,
        )

    def _get_text(self, selector: str, timeout: int = 5000) -> str:
        """セレクタからテキストを取得する

        Args:
            selector: CSSセレクター
            timeout: タイムアウト(ミリ秒)

        Returns:
            str: 要素のテキスト
        """
        try:
            element = self.page.locator(f"{SCORE_DETAIL.BASE} {selector}").first
            return element.inner_text(timeout=timeout)
        except PlaywrightTimeoutError:
            logger.warning("要素が見つかりません: %s", selector)
            return ""

    def _get_golf_place_info(self) -> tuple[str, str]:
        """ゴルフ場名と都道府県を取得する

        Returns:
            tuple[str, str]: (ゴルフ場名, 都道府県)
        """
        # 通常はリンク要素から取得
        try:
            element = self.page.locator(
                f"{SCORE_DETAIL.BASE} {SCORE_DETAIL.GOLF_PLACE_NAME}"
            ).first
            text = element.inner_text(timeout=3000)
            if text:
                return self._parse_golf_place_text(text)
        except PlaywrightTimeoutError:
            pass

        # 手入力の場合はdiv要素から取得
        try:
            element = self.page.locator(
                f"{SCORE_DETAIL.BASE} {SCORE_DETAIL.GOLF_PLACE_NAME_ALT}"
            ).first
            text = element.inner_text(timeout=3000)
            if text:
                return self._parse_golf_place_text(text)
        except PlaywrightTimeoutError:
            pass

        # 特殊ケース: パンくずリストから取得
        try:
            element = self.page.locator(SCORE_DETAIL.GOLF_PLACE_NAME_BREADCRUMB).first
            text = element.inner_text(timeout=3000)
            if text:
                return text, ""
        except PlaywrightTimeoutError:
            pass

        logger.warning("ゴルフ場名が取得できませんでした")
        return "", ""

    def _parse_golf_place_text(self, text: str) -> tuple[str, str]:
        """ゴルフ場テキストをパースする

        Args:
            text: ゴルフ場テキスト(例: "ゴルフ場名(都道府県)")

        Returns:
            tuple[str, str]: (ゴルフ場名, 都道府県)
        """
        # 全角括弧で分割(GDOサイトは全角を使用)
        fullwidth_left = "\uff08"
        fullwidth_right = "\uff09"
        if fullwidth_left in text:
            parts = text.split(fullwidth_left)
            golf_place_name = parts[0].strip()
            prefecture = parts[1].rstrip(fullwidth_right).strip()
            return golf_place_name, prefecture
        # 半角括弧でも対応
        if "(" in text:
            parts = text.split("(")
            golf_place_name = parts[0].strip()
            prefecture = parts[1].rstrip(")").strip()
            return golf_place_name, prefecture
        return text.strip(), ""

    def _extract_course_name(self, text: str) -> str:
        """コース名を抽出する

        Args:
            text: コーステキスト(例: "OUTコース")

        Returns:
            str: コース名(例: "OUT")
        """
        match = re.findall(r"(.*)コース", text)
        if match:
            return match[0]
        return text

    def _get_scores_from_rows(
        self, former_selector: str, latter_selector: str
    ) -> list[str]:
        """前後半の行からスコアを取得する

        Args:
            former_selector: 前半のセレクター
            latter_selector: 後半のセレクター

        Returns:
            list[str]: スコアリスト(18ホール分)
        """
        scores: list[str] = []

        for selector in [former_selector, latter_selector]:
            try:
                cells = self.page.locator(
                    f"{SCORE_DETAIL.BASE} {selector} {SCORE_DETAIL.SCORE_CELLS}"
                ).all()
                for cell in cells:
                    scores.append(cell.inner_text())
            except PlaywrightTimeoutError:
                logger.warning("スコア行が見つかりません: %s", selector)

        return scores

    def _get_class_based_data(
        self, former_selector: str, latter_selector: str
    ) -> list[str]:
        """クラス名ベースのデータを取得する(フェアウェイキープ、パーオン)

        Args:
            former_selector: 前半のセレクター
            latter_selector: 後半のセレクター

        Returns:
            list[str]: データリスト(18ホール分)
        """
        data: list[str] = []

        for selector in [former_selector, latter_selector]:
            for i in range(2, 11):  # 2〜10番目のセル
                try:
                    cell = self.page.locator(
                        f"{SCORE_DETAIL.BASE} {selector} td:nth-child({i})"
                    ).first
                    class_attr = cell.get_attribute("class") or ""
                    if "is-void" in class_attr:
                        data.append("-")
                    else:
                        data.append(class_attr)
                except PlaywrightTimeoutError:
                    data.append("-")

        return data

    def _get_accompany_members(self) -> tuple[list[str], list[list[str]]]:
        """同伴者情報を取得する

        Returns:
            tuple[list[str], list[list[str]]]: (同伴者名リスト, 同伴者スコアリスト)
        """
        names: list[str] = []
        scores: list[list[str]] = []

        # 前半テーブルから同伴者名を取得
        try:
            name_elements = self.page.locator(
                f"{SCORE_DETAIL.BASE} {SCORE_DETAIL.MEMBER_ROW_FORMER} {SCORE_DETAIL.MEMBER_NAME}"
            ).all()
            names = [elem.inner_text() for elem in name_elements]
        except PlaywrightTimeoutError:
            logger.debug("同伴者情報がありません")
            return names, scores

        if not names:
            return names, scores

        # 前半スコアを全て取得
        former_score_elements = self.page.locator(
            f"{SCORE_DETAIL.BASE} {SCORE_DETAIL.MEMBER_ROW_FORMER} {SCORE_DETAIL.SCORE_CELLS}"
        ).all()

        # 後半スコアを全て取得
        latter_score_elements = self.page.locator(
            f"{SCORE_DETAIL.BASE} {SCORE_DETAIL.MEMBER_ROW_LATTER} {SCORE_DETAIL.SCORE_CELLS}"
        ).all()

        # 各同伴者のスコアを分割(1人あたり9ホール分)
        holes_per_half = 9
        for i in range(len(names)):
            member_scores: list[str] = []

            # 前半スコア(9ホール分)
            start_idx = i * holes_per_half
            end_idx = start_idx + holes_per_half
            for j in range(start_idx, min(end_idx, len(former_score_elements))):
                member_scores.append(former_score_elements[j].inner_text())

            # 後半スコア(9ホール分)
            for j in range(start_idx, min(end_idx, len(latter_score_elements))):
                member_scores.append(latter_score_elements[j].inner_text())

            scores.append(member_scores)

        return names, scores
