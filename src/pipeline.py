"""
pipeline.py - 統合パイプライン
入力画像 → 中間 JSON → SVG の全処理を統括する
"""

from __future__ import annotations
import os
import re
import json
import numpy as np
from PIL import Image

from src.ocr import run_ocr, estimate_font_size_pt, get_reader
from src.layout import detect_non_text_regions, scale_to_mm
from src.classifier import classify_blocks
from src.font_mapper import detect_font_group
from src.shape_extractor import build_shapes
from src.svg_builder import build_svg
from src.img_preprocess import prepare_for_ocr
from src.ocr_postproc import apply_all as ocr_fix

# 名刺サイズ
CARD_W_MM = 94.0
CARD_H_MM = 58.0

# EasyOCR バウンディングボックス → 実テキスト高さ補正
FONT_SIZE_SCALE = 0.72

# 最小信頼度
MIN_CONFIDENCE = 0.3

# フォントサイズ上限・下限 (mm, viewBox単位)
FONT_SIZE_MAX_MM = 18.0
FONT_SIZE_MIN_MM = 2.0

# CJK Unicode範囲（全角文字判定用）
_CJK_RE = re.compile(r'[\u3040-\u9fff\uff00-\uffef]')


def load_image(path: str) -> np.ndarray:
    """画像を読み込み RGB numpy 配列として返す（PDF対応）"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        try:
            import fitz
            doc = fitz.open(path)
            page = doc[0]
            mat = fitz.Matrix(300 / 72, 300 / 72)
            pix = page.get_pixmap(matrix=mat)
            arr = np.frombuffer(pix.samples, dtype=np.uint8)
            arr = arr.reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:
                arr = arr[:, :, :3]
            return arr
        except ImportError:
            raise RuntimeError("PDF を読み込むには PyMuPDF が必要です: pip install pymupdf")
    else:
        img = Image.open(path).convert("RGB")
        return np.array(img)


def extract_text_color(image: np.ndarray, x: int, y: int, w: int, h: int) -> str:
    """テキスト領域の代表色（最暗値）を取得する"""
    roi = image[y : y + h, x : x + w]
    if roi.size == 0:
        return "#000000"
    gray = np.mean(roi, axis=2)
    flat_idx = np.argmin(gray)
    fy, fx = divmod(flat_idx, roi.shape[1])
    r, g, b = roi[fy, fx]
    return f"#{int(r):02X}{int(g):02X}{int(b):02X}"


def _iou(a: dict, b: dict) -> float:
    """2つのピクセルブロック間の IoU を計算する"""
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = ax1 + a["w"], ay1 + a["h"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = bx1 + b["w"], by1 + b["h"]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


def deduplicate_blocks(blocks: list[dict], iou_threshold: float = 0.4) -> list[dict]:
    """IoU ベースで重複テキストブロックを除去する（信頼度優先）"""
    sorted_blocks = sorted(blocks, key=lambda b: b.get("confidence", 0), reverse=True)
    kept = []
    for candidate in sorted_blocks:
        if not any(_iou(candidate, k) >= iou_threshold for k in kept):
            kept.append(candidate)
    kept.sort(key=lambda b: (b["y"], b["x"]))
    return kept


def estimate_letter_spacing(
    text: str, bbox_w_mm: float, font_size_mm: float, role: str
) -> float:
    """
    テキストの bbox 幅と文字数からレタースペーシングを推定する

    名刺上で「伯 野 祥 展」のように文字間が空いている場合、
    bbox 幅 / (font_size × 文字数) > 1.3 を目安に letter-spacing を付与する

    Returns
    -------
    float
        SVG letter-spacing 値 (mm, viewBox単位)。不要なら 0.0
    """
    if role not in ("name",):
        return 0.0

    if not text or font_size_mm <= 0 or bbox_w_mm <= 0:
        return 0.0

    char_count = len(text)
    # CJK 文字数（全角 = 1em 幅）
    cjk_count = len(_CJK_RE.findall(text))
    if cjk_count < 2:
        return 0.0  # 英数字のみは対象外

    # 全角文字の理論幅（スペースなし）
    expected_w = font_size_mm * cjk_count
    ratio = bbox_w_mm / expected_w if expected_w > 0 else 1.0

    if ratio < 1.25:
        return 0.0  # スペースは有意ではない

    # 文字間スペースを均等割り付け
    extra_total = bbox_w_mm - expected_w
    spacing = extra_total / max(cjk_count - 1, 1)
    # 上限 5mm、下限 0.5mm
    return round(max(0.0, min(5.0, spacing)), 2)


def run_pipeline(
    image_path: str,
    output_svg: str,
    output_json: str | None = None,
    verbose: bool = False,
) -> dict:
    """名刺画像を解析して SVG を生成する"""
    def log(msg: str):
        if verbose:
            print(f"[pipeline] {msg}")

    # 1. 画像読み込み
    log(f"画像読み込み: {image_path}")
    image_orig = load_image(image_path)
    img_h_orig, img_w_orig = image_orig.shape[:2]
    log(f"  → 元サイズ: {img_w_orig}x{img_h_orig}px")

    # 2. OCR 用前処理（拡大・CLAHE・シャープニング）
    # 強すぎる前処理（CLAHEやシャープニング）が逆にURLなどの小文字認識精度を
    # 下げてしまうケース（ドットが消えて図形判定される等）があるため、
    # 元画像をそのまま使用して安定した OCR 結果を得る。
    log("前処理をスキップ（元画像を使用）...")
    image_proc = image_orig
    img_h_proc, img_w_proc = img_h_orig, img_w_orig

    # 3. OCR（前処理済み画像で実行）
    log("OCR 実行中...")
    reader = get_reader(["ja", "en"])
    raw_blocks = run_ocr(image_proc, reader=reader)
    log(f"  → {len(raw_blocks)} ブロック検出（重複除去前）")

    # 4. 低信頼度フィルタリング
    raw_blocks = [b for b in raw_blocks if b.get("confidence", 1.0) >= MIN_CONFIDENCE]
    log(f"  → {len(raw_blocks)} ブロック（信頼度フィルタ後）")

    # 5. 重複ブロック除去
    raw_blocks = deduplicate_blocks(raw_blocks, iou_threshold=0.4)
    log(f"  → {len(raw_blocks)} ブロック（重複除去後）")

    # 6. フォントサイズ推定（前処理済み画像の座標で計算）
    #    ※ 後で mm スケールするので前処理後の img_h_proc を使う
    for b in raw_blocks:
        b["font_size_pt"] = estimate_font_size_pt(b["h"], img_h_proc)
        raw_fs = b["h"] / img_h_proc * CARD_H_MM * FONT_SIZE_SCALE
        b["font_size"] = round(
            max(FONT_SIZE_MIN_MM, min(FONT_SIZE_MAX_MM, raw_fs)), 2
        )
        # 色は元画像から取得（前処理後は色が変化している場合があるため）
        scale_x = img_w_orig / img_w_proc
        scale_y = img_h_orig / img_h_proc
        ox = int(b["x"] * scale_x)
        oy = int(b["y"] * scale_y)
        ow = int(b["w"] * scale_x)
        oh = int(b["h"] * scale_y)
        b["color"] = extract_text_color(image_orig, ox, oy, ow, oh)

    # 7. mm 座標に変換（前処理済み画像の解像度基準）
    text_blocks_mm = scale_to_mm(raw_blocks, img_w_proc, img_h_proc, CARD_W_MM, CARD_H_MM)

    # 8. テキスト役割分類
    log("テキスト分類中...")
    classified = classify_blocks(text_blocks_mm)

    # 9. フォントグループ推定 + OCR後処理 + letter-spacing 推定
    for b in classified:
        role = b.get("role", "other")
        b["font_group"] = detect_font_group(b["text"], role)
        
        # フォントファミリとウェイトの設定
        if "font_family" not in b:
            b["font_family"] = "Noto Serif JP" if b["font_group"] == "mincho" else "Noto Sans JP"
        if "font_weight" not in b:
            b["font_weight"] = "700" if role in ("company", "name") else "400"

        # OCR テキスト後処理（〒修正、ドット補完、ロゴ大文字化等）
        b["text"] = ocr_fix(b["text"], role)

        # letter-spacing 推定（名前や会社名など文字間が広い場合）
        b["letter_spacing"] = estimate_letter_spacing(
            b["text"], b.get("w", 0), b["font_size"], role
        )

    # 10. 非テキスト領域検出（元画像で検出、座標もmm変換）
    log("非テキスト領域検出中...")
    # raw_blocksは前処理画像座標なので元画像座標に戻す
    raw_blocks_orig = []
    for b, c_block in zip(raw_blocks, classified):
        br = dict(b)
        br["role"] = c_block.get("role")
        br["x"] = int(b["x"] * img_w_orig / img_w_proc)
        br["y"] = int(b["y"] * img_h_orig / img_h_proc)
        br["w"] = int(b["w"] * img_w_orig / img_w_proc)
        br["h"] = int(b["h"] * img_h_orig / img_h_proc)
        raw_blocks_orig.append(br)

    non_text = detect_non_text_regions(image_orig, raw_blocks_orig)
    log(f"  → {len(non_text)} 領域検出")
    shapes, extracted_images = build_shapes(non_text, image_orig, img_w_orig, img_h_orig, CARD_W_MM, CARD_H_MM)

    # ロゴ判定されたテキストは editable text 群から除外
    final_texts = [t for t in classified if t.get("role") != "logo"]

    # 11. 中間データ構築
    intermediate = {
        "image_path": image_path,
        "image_size": {"w": img_w_orig, "h": img_h_orig},
        "card_size_mm": {"w": CARD_W_MM, "h": CARD_H_MM},
        "texts": final_texts,
        "shapes": shapes,
        "images": extracted_images,
    }

    # 12. JSON 保存（オプション）
    if output_json:
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(intermediate, f, ensure_ascii=False, indent=2)
        log(f"中間 JSON 保存: {output_json}")

    # 13. SVG 生成
    log("SVG 生成中...")
    build_svg(intermediate, output_svg)
    log(f"  → 完了: {output_svg}")

    return intermediate
