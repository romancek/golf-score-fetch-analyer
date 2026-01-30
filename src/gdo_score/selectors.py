"""CSSセレクター定義モジュール

GDOスコアサイトのCSSセレクターを一元管理する。
ページ構造の変更時はこのファイルのみ修正すれば対応可能。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LoginSelectors:
    """ログインページのセレクター"""

    # ログインボタン(トップページ)
    LOGIN_BUTTON: str = "a.button.button--login"

    # ログインフォーム
    USERNAME_INPUT: str = "input[name='username']"
    PASSWORD_INPUT: str = "input[name='password']"
    # 送信ボタン(複数のセレクタをカンマ区切りで試行)
    SUBMIT_BUTTON: str = (
        '.parts_submit_btn input[type="image"], '
        '.parts_submit_btn input[type="submit"], '
        'input[type="submit"], '
        'button[type="submit"]'
    )

    # モーダルダイアログ(キャンペーン等)
    MODAL_CLOSE_BUTTON: str = "#karte-5322018 button"


@dataclass(frozen=True)
class ScoreDetailSelectors:
    """スコア詳細ページのセレクター

    サンプルコードのセレクターを基に定義。
    ベースパス: #container > div.score > div.score__container > div.score__main > div.score__detail
    """

    # ベースパス
    BASE: str = (
        "#container > div.score > div.score__container > "
        "div.score__main > div.score__detail"
    )

    # 日付・ゴルフ場情報
    PLACE_INFO: str = ".score__detail__place > .score__detail__place__info"
    DATE: str = ".score__detail__place__info > p"
    GOLF_PLACE_NAME: str = ".score__detail__place__info > a"
    GOLF_PLACE_NAME_ALT: str = ".score__detail__place__info > div"
    GOLF_PLACE_NAME_BREADCRUMB: str = (
        "#container > div.score > div.score__breadcrumb > ul > li:nth-child(4) > span"
    )

    # コンディション情報
    WEATHER: str = ".score__detail__place__info__list__item.is-weather"
    WIND: str = ".score__detail__place__info__list__item.is-wind"
    GREEN: str = ".score__detail__place__info__list__item.is-green"
    TEE: str = ".score__detail__place__info__list__item.is-tee"

    # コース名(前半・後半)
    COURSE_FORMER_HALF: str = "table:nth-child(4) > caption"
    COURSE_LATTER_HALF: str = "table:nth-child(6) > caption"

    # スコアテーブル(前半: nth-child(4), 後半: nth-child(6))
    # スコア行
    SCORE_ROW_FORMER: str = "table:nth-child(4) > tbody > tr.is-myscore"
    SCORE_ROW_LATTER: str = "table:nth-child(6) > tbody > tr.is-myscore"
    SCORE_CELLS: str = "td:nth-child(-n+10)"

    # パット行
    PUTT_ROW_FORMER: str = "table:nth-child(4) > tbody > tr.is-putt"
    PUTT_ROW_LATTER: str = "table:nth-child(6) > tbody > tr.is-putt"

    # ティーショット行
    TEESHOT_ROW_FORMER: str = "table:nth-child(4) > tbody > tr.is-teeshot"
    TEESHOT_ROW_LATTER: str = "table:nth-child(6) > tbody > tr.is-teeshot"

    # フェアウェイキープ行
    FAIRWAY_KEEP_ROW_FORMER: str = "table:nth-child(4) > tbody > tr.is-fairway-keep"
    FAIRWAY_KEEP_ROW_LATTER: str = "table:nth-child(6) > tbody > tr.is-fairway-keep"

    # パーオン行
    ONEON_ROW_FORMER: str = "table:nth-child(4) > tbody > tr.is-oneon"
    ONEON_ROW_LATTER: str = "table:nth-child(6) > tbody > tr.is-oneon"

    # OB行
    OB_ROW_FORMER: str = "table:nth-child(4) > tbody > tr.is-ob"
    OB_ROW_LATTER: str = "table:nth-child(6) > tbody > tr.is-ob"

    # バンカー行
    BUNKER_ROW_FORMER: str = "table:nth-child(4) > tbody > tr.is-bunker"
    BUNKER_ROW_LATTER: str = "table:nth-child(6) > tbody > tr.is-bunker"

    # ペナルティ行
    PENALTY_ROW_FORMER: str = "table:nth-child(4) > tbody > tr.is-penalty"
    PENALTY_ROW_LATTER: str = "table:nth-child(6) > tbody > tr.is-penalty"

    # パー行
    PAR_ROW_FORMER: str = "table:nth-child(4) > tbody > tr.is-par"
    PAR_ROW_LATTER: str = "table:nth-child(6) > tbody > tr.is-par"

    # ヤード行
    YARD_ROW_FORMER: str = "table:nth-child(4) > tbody > tr.is-yard"
    YARD_ROW_LATTER: str = "table:nth-child(6) > tbody > tr.is-yard"

    # 同伴者行
    MEMBER_ROW_FORMER: str = "table:nth-child(4) > tbody > tr.is-member"
    MEMBER_ROW_LATTER: str = "table:nth-child(6) > tbody > tr.is-member"
    MEMBER_NAME: str = "th"


# シングルトンインスタンス
LOGIN = LoginSelectors()
SCORE_DETAIL = ScoreDetailSelectors()
