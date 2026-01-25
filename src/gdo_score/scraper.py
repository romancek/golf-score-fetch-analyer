"""スクレイピングモジュール

GDOスコアページからスコアデータを抽出する。
"""

import logging
import re

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from .browser import save_html, save_screenshot
from .config import Settings
from .models import ScoreData
from .selectors import SCORE_DETAIL

logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """スクレイピング失敗時の例外"""

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

    def scrape_all_scores(self) -> list[ScoreData]:
        """すべてのスコアを取得する

        Returns:
            list[ScoreData]: スコアデータのリスト
        """
        scores: list[ScoreData] = []
        page_num = 1

        while True:
            logger.info("スコア一覧ページ %d を取得中...", page_num)
            url = self.SCORE_LIST_URL.format(page=page_num)
            self.page.goto(url)

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

                try:
                    score = self._scrape_score_detail(link)
                    scores.append(score)
                    logger.info(
                        "スコア取得完了: %s/%s/%s %s",
                        score.year,
                        score.month,
                        score.day,
                        score.golf_place_name,
                    )
                except ScraperError as e:
                    logger.warning("スコア取得失敗: %s - %s", link, e)
                    if self.settings.debug:
                        save_screenshot(
                            self.page, self.settings.debug_dir, "scrape_error"
                        )
                        save_html(self.page, self.settings.debug_dir, "scrape_error")

            page_num += 1

        logger.info("全 %d 件のスコアを取得しました", len(scores))
        return scores

    def _scrape_score_detail(self, url: str) -> ScoreData:
        """スコア詳細ページからデータを抽出する

        Args:
            url: スコア詳細ページのURL

        Returns:
            ScoreData: スコアデータ
        """
        self.page.goto(url)
        self.page.wait_for_load_state("networkidle")

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
        if "(" in text:
            parts = text.split("(")
            golf_place_name = parts[0]
            prefecture = parts[1].rstrip(")")
            return golf_place_name, prefecture
        return text, ""

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

        # 各同伴者のスコアを取得
        for i in range(len(names)):
            member_scores: list[str] = []

            # 前半スコア
            try:
                former_cells = self.page.locator(
                    f"{SCORE_DETAIL.BASE} {SCORE_DETAIL.MEMBER_ROW_FORMER}:nth-child({i + 1}) {SCORE_DETAIL.SCORE_CELLS}"
                ).all()
                for cell in former_cells:
                    member_scores.append(cell.inner_text())
            except PlaywrightTimeoutError:
                pass

            # 後半スコア
            try:
                latter_cells = self.page.locator(
                    f"{SCORE_DETAIL.BASE} {SCORE_DETAIL.MEMBER_ROW_LATTER}:nth-child({i + 1}) {SCORE_DETAIL.SCORE_CELLS}"
                ).all()
                for cell in latter_cells:
                    member_scores.append(cell.inner_text())
            except PlaywrightTimeoutError:
                pass

            scores.append(member_scores)

        return names, scores
