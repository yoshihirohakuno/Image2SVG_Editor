"""
text_outliner.py - テキストを SVG パスにアウトライン化するモジュール
fonttools を使って Google Fonts の TTF/OTF を取得し、各グリフを SVG path に変換する。
フォントファイルは書き込み可能なキャッシュディレクトリに保存する。
"""

from __future__ import annotations
import os
import re
import math
import pathlib
import tempfile
import urllib.request

# ── Google Fonts の TTF 直リンク（Static サブセット） ──
# wght@400 と wght@700 のみ用意。必要に応じて追加可能。
FONT_URLS: dict[tuple[str, int], str] = {
    ("Noto Sans JP", 400): (
        "https://github.com/google/fonts/raw/main/ofl/notosansjp/static/NotoSansJP-Regular.ttf"
    ),
    ("Noto Sans JP", 700): (
        "https://github.com/google/fonts/raw/main/ofl/notosansjp/static/NotoSansJP-Bold.ttf"
    ),
    ("Noto Serif JP", 400): (
        "https://github.com/google/fonts/raw/main/ofl/notoserifjp/static/NotoSerifJP-Regular.ttf"
    ),
    ("Noto Serif JP", 700): (
        "https://github.com/google/fonts/raw/main/ofl/notoserifjp/static/NotoSerifJP-Bold.ttf"
    ),
}

_font_cache: dict[str, object] = {}  # path -> TTFont


def _ensure_cache_dir() -> pathlib.Path:
    """書き込み可能なフォントキャッシュディレクトリを返す。"""
    candidates = []

    env_dir = os.environ.get("IMAGE2SVG_FONT_CACHE")
    if env_dir:
        candidates.append(pathlib.Path(env_dir))

    project_cache = pathlib.Path(__file__).resolve().parent.parent / ".cache" / "image2svg_fonts"
    candidates.append(project_cache)
    candidates.append(pathlib.Path(tempfile.gettempdir()) / "image2svg_fonts")
    candidates.append(pathlib.Path.home() / ".cache" / "image2svg_fonts")

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return candidate
        except Exception:
            continue

    raise OSError("利用可能なフォントキャッシュディレクトリを作成できませんでした。")


def _get_font_path(family: str, weight: int) -> pathlib.Path | None:
    """フォントファイルのパスを返す（必要に応じてダウンロード）"""
    # weight を既存キー {400,700} に丸める
    w = 700 if weight >= 600 else 400
    key = (family, w)
    url = FONT_URLS.get(key)
    if not url:
        # フォールバック: Noto Sans JP Regular
        key = ("Noto Sans JP", 400)
        url = FONT_URLS[key]

    fname = url.split("/")[-1]
    cache_dir = _ensure_cache_dir()
    fpath = cache_dir / fname
    if not fpath.exists():
        print(f"[outliner] フォントをDL中: {fname}")
        urllib.request.urlretrieve(url, fpath)
        print(f"[outliner] 完了: {fpath}")
    return fpath


def _load_ttfont(fpath: pathlib.Path):
    """fonttools TTFont をロード（キャッシュ付き）"""
    key = str(fpath)
    if key not in _font_cache:
        from fonttools.ttLib import TTFont
        _font_cache[key] = TTFont(fpath)
    return _font_cache[key]


# ── SVG PathPen ──
class SVGPathCollector:
    """fonttools Pen プロトコルを実装し、SVG path d= 文字列を収集する"""

    def __init__(self):
        self.parts: list[str] = []
        self._cx = 0.0
        self._cy = 0.0

    def moveTo(self, pt):
        x, y = pt
        self.parts.append(f"M {x:.3f} {y:.3f}")
        self._cx, self._cy = x, y

    def lineTo(self, pt):
        x, y = pt
        self.parts.append(f"L {x:.3f} {y:.3f}")
        self._cx, self._cy = x, y

    def curveTo(self, *pts):
        # cubic bezier (from TrueType decompose)
        args = " ".join(f"{p[0]:.3f} {p[1]:.3f}" for p in pts)
        self.parts.append(f"C {args}")
        self._cx, self._cy = pts[-1]

    def qCurveTo(self, *pts):
        # quadratic → cubic 変換
        if len(pts) == 2:
            p1, p2 = pts
            cx, cy = self._cx, self._cy
            cp1x = cx + 2/3 * (p1[0] - cx)
            cp1y = cy + 2/3 * (p1[1] - cy)
            cp2x = p2[0] + 2/3 * (p1[0] - p2[0])
            cp2y = p2[1] + 2/3 * (p1[1] - p2[1])
            self.parts.append(f"C {cp1x:.3f} {cp1y:.3f} {cp2x:.3f} {cp2y:.3f} {p2[0]:.3f} {p2[1]:.3f}")
            self._cx, self._cy = p2
        else:
            # 複数制御点 → 順に変換
            prev = (self._cx, self._cy)
            for i in range(len(pts) - 1):
                mid = ((pts[i][0] + pts[i+1][0]) / 2, (pts[i][1] + pts[i+1][1]) / 2) if i < len(pts) - 2 else pts[-1]
                self.qCurveTo(pts[i], mid)
                prev = mid

    def closePath(self):
        self.parts.append("Z")

    def endPath(self):
        pass

    def addComponent(self, name, transformation):
        pass  # コンポーネントは decompose で処理済み

    def get_d(self) -> str:
        return " ".join(self.parts)


def glyph_to_svg_path(ttfont, glyph_name: str, scale_x: float, scale_y: float,
                       offset_x: float, offset_y: float) -> str:
    """1グリフを SVG path d= 文字列に変換。Y軸は反転（SVG座標系）"""
    from fonttools.pens.transformPen import TransformPen
    from fonttools.pens.pointPen import SegmentToPointPen

    collector = SVGPathCollector()
    # フォント座標 → SVG座標変換（Y反転）
    # matrix: (sx, 0, shx, sy, dx, dy) → TransformPen は (a,b,c,d,e,f) 形式
    # a=scale_x, b=0, c=0, d=-scale_y (Y反転), e=offset_x, f=offset_y
    transform = (scale_x, 0, 0, -scale_y, offset_x, offset_y)
    tp = TransformPen(collector, transform)
    try:
        gs = ttfont.getGlyphSet()
        if glyph_name in gs:
            gs[glyph_name].draw(tp)
    except Exception as e:
        print(f"[outliner] グリフ変換エラー: {glyph_name}: {e}")
    return collector.get_d()


def text_to_svg_paths(
    text: str,
    family: str,
    weight: int,
    font_size_mm: float,
    x_mm: float,
    y_mm: float,
    letter_spacing_mm: float = 0.0,
) -> list[dict]:
    """
    テキスト文字列を SVG path dicts のリストに変換する。

    Returns
    -------
    list of { "d": str, "advance_x": float }
      d: SVG path d属性
      各パスは既に x_mm, y_mm でオフセット済み
    実際の描画幅（最右端）も返す
    """
    try:
        fpath = _get_font_path(family, weight)
        if fpath is None:
            return []
        ttfont = _load_ttfont(fpath)
    except Exception as e:
        print(f"[outliner] フォントロードエラー: {e}")
        return []

    from fonttools.ttLib import TTFont

    cmap = ttfont.getBestCmap()
    glyph_set = ttfont.getGlyphSet()
    units_per_em = ttfont["head"].unitsPerEm

    # フォントユニット → mm への変換係数
    scale = font_size_mm / units_per_em

    # ベースライン Y（SVG座標: y_mm + ascender分）
    ascender = ttfont["OS/2"].sTypoAscender * scale
    baseline_y = y_mm + ascender

    paths = []
    cursor_x = x_mm

    for ch in text:
        code = ord(ch)
        glyph_name = cmap.get(code) if cmap else None
        if glyph_name is None or glyph_name not in glyph_set:
            # 未知文字はスペース幅だけ進める
            glyph_name = cmap.get(0x20) if cmap else None  # スペース

        if glyph_name and glyph_name in glyph_set:
            glyph = glyph_set[glyph_name]
            advance_x = glyph.width * scale

            d = glyph_to_svg_path(
                ttfont,
                glyph_name,
                scale_x=scale,
                scale_y=scale,
                offset_x=cursor_x,
                offset_y=baseline_y,
            )
            if d.strip():
                paths.append({"d": d, "char": ch, "x": cursor_x, "advance": advance_x})

            cursor_x += advance_x + letter_spacing_mm
        else:
            cursor_x += font_size_mm * 0.5 + letter_spacing_mm

    return paths


def outline_text_block(t: dict) -> list[dict] | None:
    """
    テキストブロック dict を SVG path dict リストに変換する。
    失敗した場合は None を返す（呼び出し側で通常テキスト描画にフォールバック）。
    """
    text = t.get("text", "")
    family = t.get("font_family", "Noto Sans JP")
    weight = int(t.get("font_weight", 400))
    font_size_mm = float(t.get("font_size", 3))
    x_mm = float(t.get("x", 0))
    y_mm = float(t.get("y", 0))
    ls_mm = float(t.get("letter_spacing", 0) or 0)

    lines = text.split("\n")
    all_paths = []
    line_height_mm = font_size_mm * 1.2

    for ln_idx, line in enumerate(lines):
        if not line:
            continue
        line_y = y_mm + ln_idx * line_height_mm
        paths = text_to_svg_paths(
            line, family, weight, font_size_mm,
            x_mm, line_y, ls_mm
        )
        all_paths.extend(paths)

    return all_paths if all_paths else None
