"""
テスト用サンプル名刺（テキストのみ）SVGを確認するためのスクリプト
実際の名刺画像なしでパイプライン各モジュールをテストする
"""

import sys
import os
from unittest.mock import patch

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.classifier import classify_blocks
from src.font_mapper import detect_font_group, get_font_family, get_font_weight
from src.svg_builder import build_svg_from_scratch
from src.layout import classify_shape, scale_to_mm


def test_classifier():
    print("=== テスト: テキスト分類 ===")
    blocks = [
        {"text": "株式会社サンプル", "x": 5, "y": 5, "w": 40, "h": 6, "font_size": 6},
        {"text": "山田 太郎",        "x": 5, "y": 20, "w": 30, "h": 9, "font_size": 9},
        {"text": "営業部長",         "x": 5, "y": 32, "w": 20, "h": 5, "font_size": 5},
        {"text": "〒100-0001 東京都千代田区1-1-1", "x": 5, "y": 40, "w": 60, "h": 4, "font_size": 4},
        {"text": "TEL: 03-1234-5678", "x": 5, "y": 47, "w": 40, "h": 4, "font_size": 4},
        {"text": "yamada@sample.co.jp", "x": 5, "y": 52, "w": 45, "h": 4, "font_size": 4},
    ]
    result = classify_blocks(blocks)
    for b in result:
        print(f"  [{b['role']:10s}] {b['text']}")
    assert result[0]["role"] == "company", "会社名の検出失敗"
    assert result[1]["role"] == "name",    "氏名の検出失敗"
    assert result[2]["role"] == "title",   "役職の検出失敗"
    assert result[3]["role"] == "address", "住所の検出失敗"
    assert result[4]["role"] == "tel",     "TELの検出失敗"
    assert result[5]["role"] == "email",    "メールの検出失敗"
    print("  → ✅ 全テスト通過\n")


def test_font_mapper():
    print("=== テスト: フォントマッピング ===")
    cases = [
        ("株式会社サンプル", "company", "bold_gothic"),
        ("山田 太郎",        "name",    "bold_gothic"),
        ("Sample Corp.",    "company", "latin"),
        ("hello world",     "other",   "latin"),
        ("メールアドレス",   "other",    "gothic"),
    ]
    for text, role, expected_group in cases:
        group = detect_font_group(text, role)
        fam = get_font_family(group)
        print(f"  [{group:15s}] {text[:12]:15s} → {fam[:30]}")
        assert group == expected_group, f"フォントグループ不一致: {text!r} → {group} (expected {expected_group})"
    print("  → ✅ 全テスト通過\n")


def test_shape_classify():
    print("=== テスト: 図形分類 ===")
    cases = [
        (50, 50, "circle"),
        (100, 30, "rect"),
        (40, 30, "rounded_rect"),
    ]
    for w, h, expected in cases:
        result = classify_shape(w, h)
        print(f"  {w}x{h} → {result}")
        assert result == expected, f"図形分類失敗: {w}x{h} → {result} (expected {expected})"
    print("  → ✅ 全テスト通過\n")


def test_scale_to_mm():
    print("=== テスト: ピクセル→mm変換 ===")
    blocks = [{"x": 0, "y": 0, "w": 1200, "h": 740}]
    scaled = scale_to_mm(blocks, img_w=1200, img_h=740)
    print(f"  {blocks[0]} → {scaled[0]}")
    assert scaled[0]["w"] == 94.0
    assert scaled[0]["h"] == 58.0
    print("  → ✅ 全テスト通過\n")


def test_svg_generation():
    print("=== テスト: SVG生成 ===")
    texts = [
        {"text": "株式会社サンプル", "x": 5, "y": 5, "w": 50, "h": 6,
         "font_size": 5, "color": "#222222", "font_group": "bold_gothic", "role": "company"},
        {"text": "山田 太郎",        "x": 5, "y": 18, "w": 35, "h": 9,
         "font_size": 8, "color": "#111111", "font_group": "bold_gothic", "role": "name"},
        {"text": "営業部長",          "x": 5, "y": 29, "w": 20, "h": 5,
         "font_size": 4, "color": "#444444", "font_group": "gothic",      "role": "title"},
        {"text": "TEL: 03-1234-5678",  "x": 5, "y": 38, "w": 45, "h": 4,
         "font_size": 3.5, "color": "#333333", "font_group": "latin",    "role": "tel"},
        {"text": "info@sample.co.jp",  "x": 5, "y": 44, "w": 50, "h": 4,
         "font_size": 3.5, "color": "#333333", "font_group": "latin",    "role": "email"},
        {"text": "〒100-0001 東京都千代田区1-1-1", "x": 5, "y": 50, "w": 70, "h": 4,
         "font_size": 3.5, "color": "#333333", "font_group": "gothic",   "role": "address"},
    ]
    shapes = [
        {"type": "rect",   "x": 68, "y": 5, "w": 22, "h": 22, "fill": "#5566cc"},
        {"type": "circle", "x": 72, "y": 32, "w": 14, "h": 14, "fill": "#dddddd"},
    ]
    out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_output.svg")
    svg = build_svg_from_scratch(texts=texts, shapes=shapes, output_path=out_path)
    assert "<svg" in svg, "SVG出力が不正"
    assert "94.0mm" in svg or "94mm" in svg, "幅指定が見つからない"
    assert "magenta" in svg, "マゼンタ枠が見つからない"
    print(f"  出力: {out_path}")
    print(f"  SVGサイズ: {len(svg)} 文字")
    print("  → ✅ SVG生成テスト通過\n")
    return out_path


def test_svg_text_fallback_preserves_fill_and_stroke():
    print("=== テスト: テキストフォールバック時の fill/stroke 保持 ===")
    texts = [{
        "text": "Ag",
        "x": 5,
        "y": 10,
        "font_size": 6,
        "color": "#ffffff",
        "stroke_color": "#7c6ff7",
        "stroke_width": 1.5,
        "font_family": "Noto Sans JP",
        "font_weight": "700",
    }]
    out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_fallback_output.svg")
    with patch("src.text_outliner.outline_text_block", return_value=None):
        svg = build_svg_from_scratch(texts=texts, output_path=out_path)

    text_section = svg.split('<g clip-path="url(#card-clip)" id="texts">', 1)[1].split("</g>", 1)[0]
    assert 'fill="#ffffff"' in svg, "フォールバックSVGに fill 属性が出力されていない"
    assert 'stroke="#7c6ff7"' in svg, "フォールバックSVGに stroke 属性が出力されていない"
    assert 'paint-order="stroke fill"' in svg, "フォールバックSVGに paint-order が出力されていない"
    assert "device-cmyk" not in text_section, "テキスト出力に device-cmyk が残っている"
    print("  → ✅ fill/stroke 保持テスト通過\n")


if __name__ == "__main__":
    print("🧪 ユニットテスト実行\n" + "=" * 50 + "\n")
    test_classifier()
    test_font_mapper()
    test_shape_classify()
    test_scale_to_mm()
    out = test_svg_generation()
    test_svg_text_fallback_preserves_fill_and_stroke()
    print("=" * 50)
    print(f"🎉 全テスト完了！")
    print(f"   サンプルSVG: {out}")
