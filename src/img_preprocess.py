"""
img_preprocess.py - OCR用画像前処理モジュール
解像度向上・コントラスト強調・シャープニングで OCR 精度を高める
"""

from __future__ import annotations
import cv2
import numpy as np

# OCR に渡す最小解像度幅（ピクセル）
MIN_WIDTH_FOR_OCR = 2000


def upscale_if_needed(image: np.ndarray) -> np.ndarray:
    """
    画像幅が MIN_WIDTH_FOR_OCR 未満の場合に Lanczos4 で拡大する
    （EasyOCR は大きな画像ほど認識精度が上がるため）
    """
    h, w = image.shape[:2]
    if w >= MIN_WIDTH_FOR_OCR:
        return image
    scale = MIN_WIDTH_FOR_OCR / w
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)


def enhance_contrast(image: np.ndarray) -> np.ndarray:
    """
    CLAHE（適応的コントラスト強調）を RGB 画像に適用する
    明るい名刺でもテキストが鮮明になる
    """
    lab = cv2.cvtColor(image, cv2.COLOR_RGB2LAB)
    l_channel, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l_channel)

    merged = cv2.merge([l_enhanced, a, b])
    return cv2.cvtColor(merged, cv2.COLOR_LAB2RGB)


def sharpen(image: np.ndarray, strength: float = 0.4) -> np.ndarray:
    """
    アンシャープマスクでテキスト輪郭を強調する

    Parameters
    ----------
    image : np.ndarray
        RGB 画像
    strength : float
        シャープニング強度（0.0〜1.0、デフォルト 0.4）
    """
    blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=2.0)
    sharpened = cv2.addWeighted(image, 1 + strength, blurred, -strength, 0)
    return sharpened


def prepare_for_ocr(image: np.ndarray) -> np.ndarray:
    """
    OCR 実行前のすべての前処理を適用する

    処理順序
    --------
    1. 解像度不足なら拡大（Lanczos4）
    2. CLAHE コントラスト強調
    3. アンシャープマスク

    Parameters
    ----------
    image : np.ndarray
        元の RGB 画像

    Returns
    -------
    np.ndarray
        前処理済み RGB 画像
    """
    image = upscale_if_needed(image)
    image = enhance_contrast(image)
    image = sharpen(image, strength=0.35)
    return image
