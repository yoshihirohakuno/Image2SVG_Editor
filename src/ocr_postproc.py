"""
ocr_postproc.py - OCR テキスト後処理モジュール
EasyOCR の誤認識パターンをルールベースで修正する
"""

from __future__ import annotations
import re


# ── 郵便番号記号 ── #
# 〒 は OCR で「テ」「ヲ」「〒」等に誤認識される
_POSTAL_PATTERN = re.compile(
    r"^[テヲウ〒〒]?\s*(\d{3}[-ー－]\d{4})"
)

def fix_postal_symbol(text: str) -> str:
    """郵便番号先頭の誤認識を修正: テ101-0052 → 〒101-0052"""
    m = _POSTAL_PATTERN.match(text.strip())
    if m:
        return "〒" + text[m.start(1):]
    return text


# ── URL / ドメイン ── #
def fix_url(text: str) -> str:
    """URL のドット欠落を修正"""
    # www の直後にドット欠落: wwwyour → www.your
    text = re.sub(r'\bwww([a-zA-Z])', r'www.\1', text)
    # .cojp → .co.jp (ドット間欠落)
    text = re.sub(r'cojp\b', 'co.jp', text)
    # .co jp → .co.jp (スペースが入る)
    text = re.sub(r'\.co\s+jp\b', '.co.jp', text)
    # coJP / co JP などの大文字対応
    text = re.sub(r'coJP\b', 'co.jp', text)
    return text


# ── メールアドレス ── #
def fix_email(text: str) -> str:
    """メールアドレスのドット欠落を修正"""
    text = re.sub(r'cojp\b', 'co.jp', text)
    # user@examplecom → user@example.com
    text = re.sub(r'([a-zA-Z0-9_-]+)com\b', r'\1.com', text)
    text = re.sub(r'([a-zA-Z0-9_-]+)net\b', r'\1.net', text)
    text = re.sub(r'([a-zA-Z0-9_-]+)org\b', r'\1.org', text)
    # よくあるドメイン末尾の修正
    text = re.sub(r'\.com?\s', '.com ', text)
    return text


# ── TEL / FAX 表記 ── #
def fix_phone(text: str) -> str:
    """電話番号の区切り文字を正規化"""
    # 全角ハイフン・ダッシュを半角ハイフンに
    text = text.replace('ー', '-').replace('－', '-').replace('‐', '-')
    return text


# ── 大文字小文字 ── #
_SHORT_ALPHA_RE = re.compile(r'^[a-zA-Z]{2,5}$')

def fix_logo_case(text: str, role: str) -> str:
    """
    ロゴ・会社名の大文字小文字を補正
    - 短い欧文テキストでほぼ全部大文字のはずなのに混在している場合に補正
    例: oyC → OYC (company/name で全文字が英字の場合)
    """
    if role in ("company",) and _SHORT_ALPHA_RE.match(text.strip()):
        # 大文字が過半数なら全部大文字にする
        upper_count = sum(1 for c in text if c.isupper())
        if upper_count >= len(text) // 2:
            return text.upper()
    return text


# ── 一括適用 ── #
def apply_all(text: str, role: str = "other") -> str:
    """すべての後処理を適用する"""
    text = fix_postal_symbol(text)
    text = fix_url(text)
    text = fix_email(text)
    text = fix_phone(text)
    text = fix_logo_case(text, role)
    return text.strip()
