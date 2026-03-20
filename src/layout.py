"""
layout.py - レイアウト解析モジュール
OpenCV を使用して名刺画像内の非テキスト領域を検出する
"""

from __future__ import annotations
import cv2
import numpy as np


def preprocess(image: np.ndarray) -> np.ndarray:
    """
    画像を前処理する（グレースケール変換、ノイズ除去）

    Parameters
    ----------
    image : np.ndarray
        入力画像（RGB or BGR, HxWx3）

    Returns
    -------
    np.ndarray
        前処理済みグレースケール画像
    """
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    return denoised


def mask_text_regions(image: np.ndarray, text_blocks: list[dict]) -> np.ndarray:
    """
    OCRで検出されたテキスト領域をマスクする

    Parameters
    ----------
    image : np.ndarray
        元画像
    text_blocks : list[dict]
        OCR結果 [{x, y, w, h, ...}, ...]

    Returns
    -------
    np.ndarray
        テキスト領域が白塗りされたマスク済み画像
    """
    masked = image.copy()
    for block in text_blocks:
        if block.get("role") == "logo":
            continue  # ロゴ判定されたテキストブロックはマスクせず、抽出対象に残す
        x, y, w, h = block["x"], block["y"], block["w"], block["h"]
        padding = 1
        x1 = max(0, x - padding)
        y1 = max(0, y - padding)
        x2 = min(image.shape[1], x + w + padding)
        y2 = min(image.shape[0], y + h + padding)
        cv2.rectangle(masked, (x1, y1), (x2, y2), (255, 255, 255), -1)
    return masked


def detect_non_text_regions(
    image: np.ndarray,
    text_blocks: list[dict],
    min_area: int = 500,
) -> list[dict]:
    """
    テキスト以外の領域（ロゴ・図形・写真）を検出する

    Parameters
    ----------
    image : np.ndarray
        RGB 画像
    text_blocks : list[dict]
        OCR検出済みテキストブロック
    min_area : int
        検出する最小領域面積（ピクセル²）

    Returns
    -------
    list[dict]
        [{x, y, w, h}, ...]
    """
    # テキスト領域をマスクしてから輪郭検出
    masked = mask_text_regions(image, text_blocks)
    gray = cv2.cvtColor(masked, cv2.COLOR_RGB2GRAY)

    # 背景色を推定（最頻値）
    bg_color = int(np.median(gray))

    # エッジ検出
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # 明るい背景の場合は反転
    if bg_color > 128:
        pass  # 白背景 → 暗い領域を検出（binary_inv が正解）
    else:
        binary = cv2.bitwise_not(binary)

    # モルフォロジー演算でノイズ除去・分離したパーツの結合（Pマーク等）
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    # 輪郭検出
    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    regions = []
    img_h, img_w = image.shape[:2]
    full_area = img_h * img_w

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        # 画像全体の95%以上を占める領域は除外（背景輪郭）
        if area > full_area * 0.95:
            continue

        x, y, w, h = cv2.boundingRect(cnt)

        # すでに検出済み OCR テキスト領域と大きく重なるものは除外
        if _overlaps_text(x, y, w, h, text_blocks, threshold=0.7):
            continue

        regions.append({"x": x, "y": y, "w": w, "h": h})

    return regions


def _overlaps_text(x: int, y: int, w: int, h: int, text_blocks: list[dict], threshold: float = 0.7) -> bool:
    """図形領域とテキスト領域の重複率を計算し、閾値以上なら True"""
    region_area = w * h
    if region_area == 0:
        return False
    for t in text_blocks:
        if t.get("role") == "logo":
            continue
        ix = max(x, t["x"])
        iy = max(y, t["y"])
        iw = min(x + w, t["x"] + t["w"]) - ix
        ih = min(y + h, t["y"] + t["h"]) - iy
        if iw > 0 and ih > 0:
            overlap = (iw * ih) / region_area
            if overlap >= threshold:
                return True
    return False


def classify_shape(w: int, h: int) -> str:
    """
    アスペクト比から図形タイプを分類する

    Returns
    -------
    str
        "circle" | "rect" | "rounded_rect"
    """
    aspect = w / h if h > 0 else 1.0
    if 0.8 <= aspect <= 1.2:
        return "circle"
    elif aspect > 2.5:
        return "rect"  # 横長
    else:
        return "rounded_rect"


def scale_to_mm(
    blocks: list[dict],
    img_w: int,
    img_h: int,
    card_w_mm: float = 94.0,
    card_h_mm: float = 58.0,
) -> list[dict]:
    """
    ピクセル座標を名刺実寸 mm 座標に変換する
    """
    results = []
    for b in blocks:
        scaled = dict(b)
        scaled["x"] = round(b["x"] / img_w * card_w_mm, 2)
        scaled["y"] = round(b["y"] / img_h * card_h_mm, 2)
        scaled["w"] = round(b["w"] / img_w * card_w_mm, 2)
        scaled["h"] = round(b["h"] / img_h * card_h_mm, 2)
        results.append(scaled)
    return results
