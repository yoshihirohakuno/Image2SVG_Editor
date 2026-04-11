"""
svg_builder.py - SVG生成モジュール
名刺の解析結果から 94×58mm の印刷対応SVGを生成する
"""

from __future__ import annotations
import svgwrite
from svgwrite import Drawing
from src.font_mapper import get_font_family, get_font_weight


def hex_to_cmyk_string(hex_color: str) -> str:
    """RGB Hex (#RRGGBB) から CMYK を計算し SVG の device-cmyk() 文字列を返す"""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return "device-cmyk(0, 0, 0, 1)"
        
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    
    if r == 0 and g == 0 and b == 0:
        return "device-cmyk(0, 0, 0, 1)"
        
    # K100 (純黒) へのスナップ
    # 名刺の文字などの濃いグレーは4色ベタ塗り(Rich Black)を避けるためK単色に寄せる
    if r < 80 and g < 80 and b < 80 and max(r,g,b) - min(r,g,b) < 15:
        k = 1.0 - max(r, g, b) / 255.0
        if k > 0.8:
            k = 1.0
        return f"device-cmyk(0, 0, 0, {round(k, 3)})"
        
    r_f = r / 255.0
    g_f = g / 255.0
    b_f = b / 255.0
    
    k = 1.0 - max(r_f, g_f, b_f)
    if k == 1.0:
        return "device-cmyk(0, 0, 0, 1)"
        
    c = (1.0 - r_f - k) / (1.0 - k)
    m = (1.0 - g_f - k) / (1.0 - k)
    y = (1.0 - b_f - k) / (1.0 - k)
    
    return f"device-cmyk({round(c, 3)}, {round(m, 3)}, {round(y, 3)}, {round(k, 3)})"



# 名刺サイズ定数
CARD_W_MM = 94.0
CARD_H_MM = 58.0

# Google Fonts インポート用URL
GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css2?family=Dela+Gothic+One"
    "&family=M+PLUS+Rounded+1c:wght@400;700"
    "&family=Noto+Sans+JP:wght@300;400;500;700"
    "&family=Noto+Serif+JP:wght@300;400;500;700"
    "&family=Yusei+Magic"
    "&family=Zen+Kaku+Gothic+New:wght@400;700"
    "&display=swap"
)


def build_svg(intermediate: dict, output_path: str) -> str:
    """
    中間 JSON データから SVG ファイルを生成する

    Parameters
    ----------
    intermediate : dict
        {texts: [...], shapes: [...], ...}
    output_path : str
        出力先 SVG ファイルパス

    Returns
    -------
    str
        生成した SVG の文字列
    """
    dwg = Drawing(
        output_path,
        size=(f"{CARD_W_MM}mm", f"{CARD_H_MM}mm"),
        viewBox=f"0 0 {CARD_W_MM} {CARD_H_MM}",
        profile="full",
    )

    # --- スタイル定義（Google Fonts）---
    dwg.defs.add(dwg.style(
        f"@import url('{GOOGLE_FONTS_URL}');\n"
        "text { font-variant-numeric: tabular-nums; }"
    ))

    # --- clipPath（枠内にクリップ）---
    clip = dwg.defs.add(dwg.clipPath(id="card-clip"))
    clip.add(dwg.rect(
        insert=(0, 0),
        size=(CARD_W_MM, CARD_H_MM),
    ))

    # --- 背景白 ---
    bg = dwg.add(dwg.g(clip_path="url(#card-clip)"))
    bg.add(dwg.rect(
        insert=(0, 0),
        size=(CARD_W_MM, CARD_H_MM),
        fill="white",
    ))

    # --- 図形レイヤー ---
    shape_group = dwg.add(dwg.g(id="shapes", clip_path="url(#card-clip)"))
    for s in intermediate.get("shapes", []):
        _add_shape(shape_group, dwg, s)

    # --- 画像レイヤー（ユーザー配置ロゴなど） ---
    image_group = dwg.add(dwg.g(id="images", clip_path="url(#card-clip)"))
    for img_data in intermediate.get("images", []):
        _add_image(image_group, dwg, img_data)

    # --- テキストレイヤー ---
    text_group = dwg.add(dwg.g(id="texts", clip_path="url(#card-clip)"))
    for t in intermediate.get("texts", []):
        _add_text(text_group, dwg, t)

    # --- 外枠（マゼンタ, 0.25mm 線幅）---
    dwg.add(dwg.rect(
        insert=(0, 0),
        size=(CARD_W_MM, CARD_H_MM),
        fill="none",
        stroke="magenta",
        stroke_width="0.25",
    ))

    dwg.save(pretty=True)
    return dwg.tostring()


def _add_text(group, dwg: Drawing, t: dict) -> None:
    """テキストブロックを SVG <text> として追加する"""
    x = t.get("x", 0)
    y = t.get("y", 0)
    text_str = t.get("text", "")
    color = t.get("color", "#000000")
    font_group = t.get("font_group", "gothic")
    font_size = t.get("font_size", 3)
    letter_spacing = t.get("letter_spacing", 0.0)

    font_family = t.get("font_family", "Noto Sans JP")
    font_weight = str(t.get("font_weight", "400"))
    
    # Illustratorは font-family="'Noto Sans JP', sans-serif" のような
    # クォーテーションや代替フォント（カンマ区切り）が含まれるとフォント名解析に失敗し、
    # ペナルティとしてテキストの塗りや線のスタイル情報まで一緒に破棄（初期化）してしまうバグがあるため、
    # 純粋なフォント名のみをクォートなしで渡す。
    ff_str = font_family

    # 静的カウンタ（IDを一意にする）
    _add_text._count = getattr(_add_text, "_count", 0) + 1
    role = t.get("role", "other")

    # ★ font-size は単位なし数値で指定（viewBox座標系 = mm 系）
    #   "Xmm" の絶対単位を使うと SVG スケーリング時に座標系と乖離する
    # ★ baseline 補正: SVG の text は baseline 基準
    baseline_y = round(y + font_size * 0.85, 3)

    extra = {}
    if letter_spacing and letter_spacing > 0:
        extra["letter_spacing"] = letter_spacing  # svgwrite は letter-spacing に変換

    # テキスト等装飾の物理化 (Illustrator等での互換性対応)
    
    # イタリック: Illustratorが和文フォントの斜体に非対応な場合が多いため、transformで物理的に傾ける
    transform_val = ""
    if t.get("font_style") == "italic":
        # 基点(x, baseline_y)でskewXする
        transform_val = f"translate({x},{baseline_y}) skewX(-15) translate({-x},{-baseline_y})"
        extra["transform"] = transform_val

    # アウトライン (stroke): Illustratorがstyleタグ内の不正な構文でエラーを起こすのを防ぐため属性で指定
    stroke_color = t.get("stroke_color")
    stroke_width = t.get("stroke_width", 0)
    if stroke_color and stroke_width > 0:
        extra["stroke"] = stroke_color
        extra["stroke_width"] = stroke_width

    # Illustratorは <text> ではなく中の <tspan> に直接色塗りを指定しないと
    # 黒色(継承バグ)になってしまうことがあるため、スタイル系属性は tspan にも直接渡す準備をする
    tspan_style = {
        "fill": color,
        "font_family": ff_str,
        "font_size": font_size,
        "font_weight": font_weight,
    }
    if "letter_spacing" in extra:
        tspan_style["letter_spacing"] = extra["letter_spacing"]
    if stroke_color and stroke_width > 0:
        tspan_style["stroke"] = stroke_color
        tspan_style["stroke_width"] = stroke_width

    text_elem = dwg.text(
        "",
        insert=(x, baseline_y),
        fill=color,
        font_family=ff_str,
        font_size=font_size,
        font_weight=font_weight,
        id=f"{role}_{_add_text._count}",
        **extra,
    )

    lines = text_str.split("\n")
    if len(lines) == 1:
        # 1行のみの場合は tspan を使わず直接テキストを入れる（Illustrator最適化）
        text_elem.text = lines[0]
    else:
        for i, line in enumerate(lines):
            if i == 0:
                t_span = dwg.tspan(line, x=[x], **tspan_style)
            else:
                t_span = dwg.tspan(line, x=[x], dy=["1.2em"], **tspan_style)
            text_elem.add(t_span)

    group.add(text_elem)

    # 下線・取り消し線を物理的な <line> 要素として描画 (Illustratorで無視されないように)
    has_ul = t.get("text_underline")
    has_st = t.get("text_linethrough")
    
    if has_ul or has_st:
        max_len = max([len(l) for l in lines] + [1]) # div-zero対策
        render_w = t.get("render_width", font_size * max_len * 0.8) # JSから取得した描画幅(無い場合のフォールバック)
        
        line_thickness = max(font_size * 0.08, 0.2) # 線の太さ（最低0.2mm）
        dec_color = color # テキスト本体の色に合わせる
        dec_cmyk = hex_to_cmyk_string(dec_color)
        
        line_group = dwg.g()
        if transform_val:
            line_group["transform"] = transform_val
            
        for i, line in enumerate(lines):
            ratio = len(line) / max_len if max_len > 0 else 1.0
            cur_line_w = render_w * ratio
            line_base_y = round(baseline_y + i * (font_size * 1.2), 3)
            
            if has_ul:
                # 下線のY位置：ベースラインから少し下（フォントサイズの12%分）
                uy = line_base_y + font_size * 0.12
                line_group.add(dwg.line(start=(x, uy), end=(x + cur_line_w, uy), 
                                        stroke=dec_color, stroke_width=line_thickness, 
                                        style=f"stroke: {dec_cmyk};"))
            if has_st:
                # 取消線のY位置：ベースラインから少し上（フォントサイズの35%分）
                sy = line_base_y - font_size * 0.35
                line_group.add(dwg.line(start=(x, sy), end=(x + cur_line_w, sy), 
                                        stroke=dec_color, stroke_width=line_thickness, 
                                        style=f"stroke: {dec_cmyk};"))
        group.add(line_group)



def _add_shape(group, dwg: Drawing, s: dict) -> None:
    """図形データを SVG 要素として追加する"""
    x = s.get("x", 0)
    y = s.get("y", 0)
    w = s.get("w", 10)
    h = s.get("h", 10)
    fill = s.get("fill", "#CCCCCC")
    shape_type = s.get("type", "rect")
    cmyk_val = hex_to_cmyk_string(fill)

    if shape_type == "circle":
        cx = x + w / 2
        cy = y + h / 2
        r = min(w, h) / 2
        group.add(dwg.circle(
            center=(cx, cy),
            r=r,
            fill=fill,
            style=f"fill: {cmyk_val}; stroke: device-cmyk(0,0,0,0.4);",
            stroke="#999999",
            stroke_width="0.1",
        ))
    elif shape_type == "rounded_rect":
        radius = min(w, h) * 0.15
        group.add(dwg.rect(
            insert=(x, y),
            size=(w, h),
            rx=radius,
            ry=radius,
            fill=fill,
            style=f"fill: {cmyk_val}; stroke: device-cmyk(0,0,0,0.4);",
            stroke="#999999",
            stroke_width="0.1",
        ))
    else:  # rect
        group.add(dwg.rect(
            insert=(x, y),
            size=(w, h),
            fill=fill,
            style=f"fill: {cmyk_val}; stroke: device-cmyk(0,0,0,0.4);",
            stroke="#999999",
            stroke_width="0.1",
        ))

def _add_image(group, dwg: Drawing, img_data: dict) -> None:
    """Base64エンコードされた画像をSVG要素として追加する"""
    x = img_data.get("x", 0)
    y = img_data.get("y", 0)
    w = img_data.get("w", 10)
    h = img_data.get("h", 10)
    href = img_data.get("href", "") # data:image/png;base64,...

    if href:
        group.add(dwg.image(
            href=href,
            insert=(x, y),
            size=(w, h)
        ))

def build_svg_from_scratch(
    texts: list[dict] | None = None,
    shapes: list[dict] | None = None,
    output_path: str = "output.svg",
) -> str:
    """
    テキスト・図形データを直接渡して SVG を生成するユーティリティ関数
    """
    intermediate = {
        "texts": texts or [],
        "shapes": shapes or [],
    }
    return build_svg(intermediate, output_path)
