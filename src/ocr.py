"""
ocr.py - OCR処理モジュール
EasyOCR を使用して名刺画像からテキストを抽出する
"""

from __future__ import annotations
import numpy as np
from PIL import Image
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import easyocr


def get_reader(langs: list[str] | None = None) -> "easyocr.Reader":
    """EasyOCR Reader のシングルトン取得"""
    import easyocr  # 遅延インポート（初期化に時間がかかるため）
    if langs is None:
        langs = ["ja", "en"]
    return easyocr.Reader(langs, gpu=False)


def run_ocr(image: np.ndarray, reader=None) -> list[dict]:
    """
    画像に対して OCR を実行し、テキストブロック一覧を返す

    Parameters
    ----------
    image : np.ndarray
        BGR または RGB の numpy 配列
    reader : easyocr.Reader, optional
        再利用する Reader インスタンス

    Returns
    -------
    list[dict]
        [{text, x, y, w, h, confidence}, ...]
        ※ 座標はピクセル単位（元画像基準）
    """
    if reader is None:
        reader = get_reader()

    # EasyOCR は RGB を期待
    if image.shape[2] == 3:
        rgb = image  # すでに RGB
    else:
        rgb = image[:, :, :3]

    results = reader.readtext(rgb, detail=1, paragraph=False)

    blocks = []
    for bbox, text, conf in results:
        # bbox は [[x1,y1],[x2,y1],[x2,y2],[x1,y2]] 形式
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        x = int(min(xs))
        y = int(min(ys))
        w = int(max(xs) - min(xs))
        h = int(max(ys) - min(ys))
        blocks.append({
            "text": text.strip(),
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "confidence": round(float(conf), 3),
        })

    # 上から下、左から右の順にソート
    blocks.sort(key=lambda b: (b["y"], b["x"]))
    return blocks


def estimate_font_size_pt(h_px: int, img_height_px: int, card_height_mm: float = 58.0) -> float:
    """
    ピクセル高さからフォントサイズ（pt）を推定する
    1mm ≈ 2.835pt の変換を使用

    Parameters
    ----------
    h_px : int
        テキストブロックのピクセル高さ
    img_height_px : int
        画像全体の高さ（ピクセル）
    card_height_mm : float
        名刺の実際の高さ（デフォルト 58mm）
    """
    px_per_mm = img_height_px / card_height_mm
    h_mm = h_px / px_per_mm
    pt = h_mm * 2.835
    return round(pt, 1)
