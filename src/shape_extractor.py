"""
shape_extractor.py - 非テキスト領域の図形抽出モジュール
OpenCV を使用して輪郭検出し、簡易図形として分類する
"""

from __future__ import annotations
import cv2
import numpy as np
import base64

from src.layout import classify_shape


def extract_dominant_color(
    image: np.ndarray, x: int, y: int, w: int, h: int
) -> str:
    """
    指定領域の代表色を取得する（16進数文字列）

    Parameters
    ----------
    image : np.ndarray
        RGB 画像
    x, y, w, h : int
        領域座標（ピクセル）

    Returns
    -------
    str
        "#RRGGBB" 形式
    """
    roi = image[y : y + h, x : x + w]
    if roi.size == 0:
        return "#CCCCCC"
    # 中央の小領域のみサンプリング（周辺エッジの影響を避ける）
    cy, cx = roi.shape[0] // 2, roi.shape[1] // 2
    margin = max(2, min(cy, cx) // 3)
    sample = roi[cy - margin : cy + margin + 1, cx - margin : cx + margin + 1]
    if sample.size == 0:
        sample = roi
    mean = np.mean(sample.reshape(-1, 3), axis=0)
    r, g, b = int(mean[0]), int(mean[1]), int(mean[2])
    return f"#{r:02X}{g:02X}{b:02X}"


def build_shapes(
    non_text_regions: list[dict],
    image: np.ndarray,
    img_w: int,
    img_h: int,
    card_w_mm: float = 94.0,
    card_h_mm: float = 58.0,
) -> list[dict]:
    """
    非テキスト領域を mm 座標の図形データに変換する

    Parameters
    ----------
    non_text_regions : list[dict]
        [{x, y, w, h}] ピクセル座標
    image : np.ndarray
        元画像（色取得用）
    img_w, img_h : int
        画像サイズ

    Returns
    -------
    tuple[list[dict], list[dict]]
        (shapes: [{type, x, y, w, h, fill}], images: [{type, x, y, w, h, href}]) mm 座標
    """
    shapes = []
    images = []
    for r in non_text_regions:
        px, py, pw, ph = r["x"], r["y"], r["w"], r["h"]
        # 領域の複雑度（分散）を計算して、単純な図形かロゴ(画像)かを判定
        roi = image[py:py+ph, px:px+pw]
        if roi.size == 0:
            continue
            
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        std_dev = np.std(gray)
        
        # 分散が15.0より大きければ多色・複雑な形（ロゴやアイコン）とみなす
        if std_dev > 15.0:
            # ラスタ画像として抽出する際は、アンチエイリアスや影の欠けを防ぐため余白を設ける
            pad = 6
            px1 = max(0, px - pad)
            py1 = max(0, py - pad)
            px2 = min(img_w, px + pw + pad)
            py2 = min(img_h, py + ph + pad)
            
            roi_padded = image[py1:py2, px1:px2]
            
            roi_bgr = cv2.cvtColor(roi_padded, cv2.COLOR_RGB2BGR)
            _, buffer = cv2.imencode('.png', roi_bgr)
            b64_str = base64.b64encode(buffer).decode('utf-8')
            
            # 余白を含めたサイズの mm 座標を計算
            x_mm_pad = round(px1 / img_w * card_w_mm, 2)
            y_mm_pad = round(py1 / img_h * card_h_mm, 2)
            w_mm_pad = round((px2 - px1) / img_w * card_w_mm, 2)
            h_mm_pad = round((py2 - py1) / img_h * card_h_mm, 2)

            images.append({
                "type": "image",
                "x": x_mm_pad,
                "y": y_mm_pad,
                "w": w_mm_pad,
                "h": h_mm_pad,
                "href": f"data:image/png;base64,{b64_str}"
            })
        else:
            # 単純な図形（ベタ塗り）
            color = extract_dominant_color(image, px, py, pw, ph)
            shape_type = classify_shape(pw, ph)

            # ジャストサイズの mm 座標を計算
            x_mm = round(px / img_w * card_w_mm, 2)
            y_mm = round(py / img_h * card_h_mm, 2)
            w_mm = round(pw / img_w * card_w_mm, 2)
            h_mm = round(ph / img_h * card_h_mm, 2)

            shapes.append({
                "type": shape_type,
                "x": x_mm,
                "y": y_mm,
                "w": w_mm,
                "h": h_mm,
                "fill": color,
            })

    return shapes, images
