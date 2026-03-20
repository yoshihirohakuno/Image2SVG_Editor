"""
font_mapper.py - フォント分類・マッピングモジュール
テキストの文字種からフォントグループを推定し、代替フォントを返す
"""

from __future__ import annotations
import re


# フォントグループ → SVG用フォントファミリ
FONT_MAP: dict[str, str] = {
    "gothic":      "Noto Sans JP, Noto Sans, sans-serif",
    "mincho":      "Noto Serif JP, Noto Serif, serif",
    "maru_gothic": "Zen Maru Gothic, Noto Sans JP, sans-serif",
    "bold_gothic": "Noto Sans JP, sans-serif",
    "latin":       "Inter, Helvetica Neue, Arial, sans-serif",
}

# フォントグループ → SVG font-weight
FONT_WEIGHT_MAP: dict[str, str] = {
    "gothic":      "400",
    "mincho":      "400",
    "maru_gothic": "400",
    "bold_gothic": "700",
    "latin":       "400",
}

# 役職 → 太字ゴシックにする
_BOLD_ROLES = {"company", "name"}

# 漢字・ひらがな・カタカナ検出
_CJK_RE = re.compile(
    r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u3400-\u4DBF]"
)


def detect_font_group(text: str, role: str = "other") -> str:
    """
    テキストとロールからフォントグループを推定する

    Parameters
    ----------
    text : str
        対象テキスト
    role : str
        分類済みテキスト役割

    Returns
    -------
    str
        フォントグループキー
    """
    has_cjk = bool(_CJK_RE.search(text))

    if role in _BOLD_ROLES:
        return "bold_gothic" if has_cjk else "latin"

    if has_cjk:
        # 初期フェーズ: CJK文字はゴシック優先
        # 明朝の手がかりとなる特別なキーワードがある場合のみ明朝
        mincho_keywords = ["株式会社", "有限会社", "合同会社"]
        if any(kw in text for kw in mincho_keywords):
            return "gothic"  # 会社名はゴシックが多い
        return "gothic"
    else:
        return "latin"


def get_font_family(font_group: str) -> str:
    """フォントグループからCSS font-familyを返す"""
    return FONT_MAP.get(font_group, FONT_MAP["gothic"])


def get_font_weight(font_group: str) -> str:
    """フォントグループからfont-weightを返す"""
    return FONT_WEIGHT_MAP.get(font_group, "400")
