"""
svg_builder.py - SVG生成モジュール
名刺の解析結果から 94×58mm の印刷対応SVGを生成する
"""

from __future__ import annotations
import svgwrite
from svgwrite import Drawing


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


def _apply_paint_attrs(element, fill=None, stroke=None, stroke_width_mm=0,
                       paint_order=None, opacity=None, letter_spacing_mm=None,
                       extra_attrs: dict | None = None) -> None:
    """Illustrator が解釈しやすいよう presentation attributes で色と線を付与する。"""
    element.attribs["fill"] = fill if fill else "none"
    element.attribs["stroke"] = stroke if stroke and stroke_width_mm > 0 else "none"
    if stroke and stroke_width_mm > 0:
        element.attribs["stroke-width"] = f"{round(stroke_width_mm, 4)}mm"
        element.attribs["stroke-linejoin"] = "round"
        element.attribs["stroke-miterlimit"] = "10"
        if paint_order:
            element.attribs["paint-order"] = paint_order
    if opacity is not None:
        element.attribs["opacity"] = opacity
    if letter_spacing_mm is not None and letter_spacing_mm > 0:
        element.attribs["letter-spacing"] = f"{letter_spacing_mm}mm"
    if extra_attrs:
        for key, value in extra_attrs.items():
            element.attribs[key] = value


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
        debug=False,
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
    """テキストブロックをアウトライン化したSVGパスとして追加する（エフェクト対応・Illustrator互換）"""
    color = t.get("color", "#000000")
    font_size = float(t.get("font_size", 3))
    effect = t.get("text_effect", "normal") or "normal"
    stroke_color = t.get("stroke_color") or ""
    stroke_width_pt = t.get("stroke_width") or 0
    stroke_width_mm = float(stroke_width_pt) * 0.352778 if stroke_width_pt else 0

    # ── アウトライン化を試みる ──
    outline_paths = None
    try:
        from src.text_outliner import outline_text_block
        outline_paths = outline_text_block(t)
    except Exception as e:
        print(f"[svg_builder] アウトライン化失敗（テキスト描画にフォールバック）: {e}")

    if outline_paths:
        # ── パスにエフェクトを適用 ──
        _add_outlined_text(group, dwg, t, outline_paths, color, stroke_color,
                           stroke_width_mm, font_size, effect)
    else:
        # ── フォールバック: 通常テキスト描画 ──
        _add_text_fallback(group, dwg, t)


def _add_outlined_text(group, dwg, t, outline_paths, color, stroke_color,
                        stroke_width_mm, font_size, effect):
    """アウトライン化済みパスにエフェクトを適用してSVGに追加する"""
    from xml.etree import ElementTree as ET

    _add_text._count = getattr(_add_text, "_count", 0) + 1

    def add_paths(fill_val, stroke_val=None, sw=0, paint_order=None,
                  opacity=None, dx=0, dy=0, extra_style="", filter_ref=None):
        """パスセットを group に追加するヘルパー"""
        for p in outline_paths:
            d = p["d"]
            extra_attrs = {}
            if extra_style:
                extra_attrs["style"] = extra_style
            if filter_ref:
                extra_attrs["filter"] = f"url(#{filter_ref})"
            if dx != 0 or dy != 0:
                pe = dwg.path(d=d, transform=f"translate({round(dx,4)},{round(dy,4)})")
            else:
                pe = dwg.path(d=d)
            _apply_paint_attrs(
                pe,
                fill=None if fill_val == "none" else fill_val,
                stroke=stroke_val,
                stroke_width_mm=sw,
                paint_order=paint_order,
                opacity=opacity,
                extra_attrs=extra_attrs,
            )
            group.add(pe)

    # ── エフェクト別レンダリング ──

    if effect == "fukuro":
        # 袋文字: 太いStrokeを後ろに描き、Fillを前面
        sw = stroke_width_mm if stroke_width_mm > 0 else font_size * 0.15
        sc = stroke_color if stroke_color else "#7c6ff7"
        add_paths("none", sc, sw * 2)
        add_paths(color)

    elif effect == "background":
        # 背景: 色付きrect + テキストパス
        bg_color = stroke_color if stroke_color else "#7c6ff7"
        x = t.get("x", 0); y = t.get("y", 0)
        pad = font_size * 0.15
        rect_h = font_size * len((t.get("text") or "").split("\n")) * 1.2
        bg_rect = dwg.rect(
            insert=(x - pad, y - pad),
            size=(CARD_W_MM - x + pad, rect_h + pad * 2),
            fill=bg_color,
            rx=font_size * 0.1,
        )
        group.add(bg_rect)
        add_paths(color)

    elif effect == "splice":
        off = font_size * 0.08
        sc = stroke_color if stroke_color else "#bbaaff"
        sw_back = stroke_width_mm if stroke_width_mm > 0 else font_size * 0.05
        sw_front = stroke_width_mm * 0.5 if stroke_width_mm > 0 else font_size * 0.02
        add_paths("none", sc, sw_back, dx=off, dy=off * 0.5)
        add_paths("none", sc, sw_front)
        add_paths(color)

    elif effect == "nuki":
        sc = stroke_color if stroke_color else color
        sw = stroke_width_mm if stroke_width_mm > 0 else font_size * 0.06
        add_paths("none", sc, sw)

    elif effect == "neon":
        # ネオン: SVGフィルター（Illustratorでも保持される）
        fid = f"neon-{_add_text._count}"
        filt_el = ET.SubElement(dwg.defs.get_xml(), "filter")
        filt_el.set("id", fid)
        filt_el.set("x", "-60%"); filt_el.set("y", "-60%")
        filt_el.set("width", "220%"); filt_el.set("height", "220%")
        b1 = ET.SubElement(filt_el, "feGaussianBlur")
        b1.set("in", "SourceGraphic"); b1.set("stdDeviation", str(round(font_size * 0.3, 2))); b1.set("result", "b1")
        b2 = ET.SubElement(filt_el, "feGaussianBlur")
        b2.set("in", "SourceGraphic"); b2.set("stdDeviation", str(round(font_size * 0.7, 2))); b2.set("result", "b2")
        merge = ET.SubElement(filt_el, "feMerge")
        for v in ["b2", "b2", "b1", "SourceGraphic"]:
            mn = ET.SubElement(merge, "feMergeNode"); mn.set("in", v)
        sc = stroke_color if stroke_color else "#a855f7"
        sw = max(stroke_width_mm, font_size * 0.03)
        add_paths(color, sc, sw, filter_ref=fid)

    elif effect == "glitch":
        off = font_size * 0.06
        add_paths("#00e5ff", opacity=0.8, dx=-off)
        add_paths("#ff0090", opacity=0.8, dx=off)
        add_paths(color)

    else:
        # 通常
        sw = stroke_width_mm if (stroke_color and stroke_width_mm > 0) else 0
        if sw > 0:
            add_paths("none", stroke_color, sw)
        add_paths(color)


def _add_text_fallback(group, dwg: Drawing, t: dict) -> None:
    """アウトライン化が失敗した際のフォールバック: 従来テキスト描画"""
    x = t.get("x", 0)
    y = t.get("y", 0)
    text_str = t.get("text", "")
    color = t.get("color", "#000000")
    font_size = t.get("font_size", 3)
    letter_spacing = t.get("letter_spacing", 0.0)
    font_family = t.get("font_family", "Noto Sans JP")
    font_weight = str(t.get("font_weight", "400"))
    stroke_color = t.get("stroke_color") or ""
    stroke_width_pt = t.get("stroke_width") or 0
    stroke_width_mm = float(stroke_width_pt) * 0.352778 if stroke_width_pt else 0
    ff_str = font_family

    baseline_y = round(y + font_size * 0.85, 3)
    _add_text._count = getattr(_add_text, "_count", 0) + 1
    role = t.get("role", "other")
    transform_val = ""
    if t.get("font_style") == "italic":
        transform_val = f"translate({x},{baseline_y}) skewX(-15) translate({-x},{-baseline_y})"

    text_elem_stroke = None
    if stroke_color and stroke_width_mm > 0:
        text_elem_stroke = dwg.text(
            "", insert=(x, baseline_y),
            fill="none", font_family=ff_str,
            font_size=font_size, font_weight=font_weight,
            id=f"{role}_{_add_text._count}_stroke",
        )
        if transform_val:
            text_elem_stroke.attribs["transform"] = transform_val
        _apply_paint_attrs(
            text_elem_stroke,
            fill=None,
            stroke=stroke_color,
            stroke_width_mm=stroke_width_mm,
            letter_spacing_mm=letter_spacing if letter_spacing and letter_spacing > 0 else None,
        )

    text_elem = dwg.text(
        "", insert=(x, baseline_y),
        fill=color, font_family=ff_str,
        font_size=font_size, font_weight=font_weight,
        id=f"{role}_{_add_text._count}",
    )
    if transform_val:
        text_elem.attribs["transform"] = transform_val
    _apply_paint_attrs(
        text_elem,
        fill=color,
        stroke=None,
        stroke_width_mm=0,
        letter_spacing_mm=letter_spacing if letter_spacing and letter_spacing > 0 else None,
    )
    lines = text_str.split("\n")
    for i, line in enumerate(lines):
        fill_span = dwg.tspan(line, x=[x]) if i == 0 else dwg.tspan(line, x=[x], dy=["1.2em"])
        text_elem.add(fill_span)
        if text_elem_stroke is not None:
            stroke_span = dwg.tspan(line, x=[x]) if i == 0 else dwg.tspan(line, x=[x], dy=["1.2em"])
            text_elem_stroke.add(stroke_span)
    if text_elem_stroke is not None:
        group.add(text_elem_stroke)
    group.add(text_elem)

    has_ul = t.get("text_underline")
    has_st = t.get("text_linethrough")
    if has_ul or has_st:
        max_len = max([len(l) for l in lines] + [1])
        render_w = t.get("render_width", font_size * max_len * 0.8)
        line_thickness = max(font_size * 0.08, 0.2)
        line_group = dwg.g()
        if transform_val:
            line_group.attribs["transform"] = transform_val
        for i, line in enumerate(lines):
            ratio = len(line) / max_len if max_len > 0 else 1.0
            cur_line_w = render_w * ratio
            line_base_y = round(baseline_y + i * (font_size * 1.2), 3)
            if has_ul:
                uy = line_base_y + font_size * 0.12
                line_group.add(dwg.line(
                    start=(x, uy), end=(x + cur_line_w, uy),
                    stroke=color, stroke_width=line_thickness
                ))
            if has_st:
                sy = line_base_y - font_size * 0.35
                line_group.add(dwg.line(
                    start=(x, sy), end=(x + cur_line_w, sy),
                    stroke=color, stroke_width=line_thickness
                ))
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
