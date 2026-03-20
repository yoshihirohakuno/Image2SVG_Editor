"""
classifier.py - テキストブロック役割分類モジュール
ルールベースでテキストブロックを氏名・会社名・役職・住所・連絡先に分類する
"""

from __future__ import annotations
import re


# 連絡先パターン
_TEL_RE = re.compile(r"(tel|fax|電話|携帯|mobile|phone|℡)\s*[:：]?\s*[\d\-\+\(\)]+", re.IGNORECASE)
_MAIL_RE = re.compile(r"[\w.\-+]+@[\w.\-]+\.\w+", re.IGNORECASE)
_URL_RE = re.compile(r"(https?://|www\.)[\w./\-?=&%]+", re.IGNORECASE)
_POSTAL_RE = re.compile(r"[〒\u3012]?\s*\d{3}[-ー]\d{4}")
_ADDRESS_KW = ["都", "道", "府", "県", "市", "区", "町", "村", "丁目", "番地", "号"]
_TITLE_KW = [
    "部長", "課長", "係長", "主任", "取締役", "代表", "社長", "副社長", "専務", "常務",
    "執行役員", "マネージャー", "ディレクター", "リーダー", "チーフ", "シニア",
    "エンジニア", "デザイナー", "プランナー", "コンサルタント",
    "Director", "Manager", "CEO", "CTO", "CFO", "COO", "President",
]


def classify_blocks(blocks: list[dict]) -> list[dict]:
    """
    テキストブロック一覧に "role" フィールドを付与する

    役割種別
    --------
    - company  : 会社名
    - name     : 氏名
    - title    : 役職
    - address  : 住所
    - tel      : 電話番号
    - email    : メールアドレス
    - url      : URL
    - other    : その他

    Parameters
    ----------
    blocks : list[dict]
        スケール済みテキストブロック（mm座標）

    Returns
    -------
    list[dict]
        role フィールドが追加されたブロック一覧
    """
    if not blocks:
        return blocks

    # フォントサイズでソートして最大を取得
    sizes = [b.get("font_size", 0) for b in blocks]
    max_size = max(sizes) if sizes else 0
    min_size = min(sizes) if sizes else 0
    size_range = max_size - min_size if max_size != min_size else 1

    results = []
    name_assigned = False
    company_assigned = False

    for b in blocks:
        role = _detect_role(b, max_size, size_range, name_assigned, company_assigned)
        if role == "name":
            name_assigned = True
        elif role == "company":
            company_assigned = True
        b = dict(b)
        b["role"] = role
        results.append(b)

    return results


def _detect_role(
    b: dict,
    max_size: float,
    size_range: float,
    name_assigned: bool,
    company_assigned: bool,
) -> str:
    text = b.get("text", "")
    fs = b.get("font_size", 0)
    y_mm = b.get("y", 0)
    card_h = 58.0

    # --- 連絡先系（パターン一致が最優先）---
    if _TEL_RE.search(text) or re.search(r"\b0\d{1,4}[-ー]\d{2,4}[-ー]\d{4}\b", text):
        return "tel"
    if _MAIL_RE.search(text):
        return "email"
    if _URL_RE.search(text):
        return "url"

    # --- 住所 ---
    if _POSTAL_RE.search(text) or any(kw in text for kw in _ADDRESS_KW):
        return "address"

    # --- 役職 ---
    if any(kw in text for kw in _TITLE_KW):
        return "title"

    # --- 氏名 / 会社名 / ロゴ（フォントサイズと位置で推定）---
    normalized_size = (fs - (max_size - size_range)) / size_range if size_range > 0 else 0.5

    # --- ロゴの可能性 ---
    stripped = text.strip()
    if 1 <= len(stripped) <= 5 and re.match(r'^[A-Za-z0-9&.\-]+$', stripped):
        # 大きめの英数字のみ、または上部に位置する場合はロゴ扱い
        if normalized_size > 0.4 or (y_mm < card_h * 0.4 and normalized_size > 0.2):
            return "logo"

    # 最大フォントかつ未割り当て → 氏名
    if not name_assigned and fs >= max_size * 0.9:
        return "name"

    # 上部 (y < 25%) かつ中サイズ → 会社名
    if not company_assigned and y_mm < card_h * 0.35 and normalized_size > 0.3:
        return "company"

    return "other"
