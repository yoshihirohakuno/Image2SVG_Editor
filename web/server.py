"""
server.py - Flask Web サーバー
ブラウザから名刺画像をアップロードし、SVGに変換してダウンロードできる
"""

from __future__ import annotations
import os
import io
import json
import tempfile
import uuid
from flask import Flask, request, jsonify, send_file, render_template_string

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 最大 16MB

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}


def allowed_file(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


# HTML は同一ファイルに埋め込み（デプロイを簡単にするため）
HTML_TEMPLATE = open(
    os.path.join(os.path.dirname(__file__), "index.html"),
    encoding="utf-8"
).read()


@app.route("/")
def index():
    response = app.make_response(render_template_string(HTML_TEMPLATE))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/convert", methods=["POST"])
def convert():
    """
    POST /api/convert
    Content-Type: multipart/form-data
    Field: file - 画像ファイル

    Returns
    -------
    JSON: {svg: str, intermediate: dict, error: str|null}
    """
    if "file" not in request.files:
        return jsonify({"error": "ファイルが選択されていません"}), 400

    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "ファイル名が空です"}), 400

    if not allowed_file(f.filename):
        return jsonify({"error": "非対応のファイル形式です（PNG/JPG/PDF のみ）"}), 400

    # 一時ファイルに保存
    suffix = os.path.splitext(f.filename)[1].lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_in:
        f.save(tmp_in.name)
        tmp_input = tmp_in.name

    tmp_svg = tmp_input + ".svg"
    tmp_json = tmp_input + ".json"

    try:
        from src.pipeline import run_pipeline  # Web サーバーは親ディレクトリから起動
        intermediate = run_pipeline(
            image_path=tmp_input,
            output_svg=tmp_svg,
            output_json=tmp_json,
            verbose=True,
        )

        with open(tmp_svg, encoding="utf-8") as sf:
            svg_content = sf.read()

        return jsonify({
            "svg": svg_content,
            "intermediate": intermediate,
            "error": None,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        for p in [tmp_input, tmp_svg, tmp_json]:
            if os.path.exists(p):
                os.unlink(p)


@app.route("/api/download", methods=["POST"])
def download():
    """
    POST /api/download
    JSON body: {svg: str, filename: str}
    SVG を添付ファイルとしてレスポンスする
    """
    data = request.get_json()
    if not data or "svg" not in data:
        return jsonify({"error": "SVGデータがありません"}), 400

    svg_bytes = data["svg"].encode("utf-8")
    filename = data.get("filename", "business_card.svg")

    return send_file(
        io.BytesIO(svg_bytes),
        mimetype="image/svg+xml",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/api/build_svg", methods=["POST"])
def build_svg_api():
    """
    POST /api/build_svg
    JSON body: intermediate state dict ({texts, shapes, images, ...})
    フロントエンドで編集された状態から SVG を再生成する
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "データがありません"}), 400

    from src.svg_builder import build_svg
    
    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp_svg_file:
        tmp_svg = tmp_svg_file.name

    try:
        build_svg(data, tmp_svg)
        with open(tmp_svg, encoding="utf-8") as sf:
            svg_content = sf.read()
        return jsonify({"svg": svg_content, "error": None})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(tmp_svg):
            os.unlink(tmp_svg)


if __name__ == "__main__":
    import sys
    # web/ ディレクトリから呼ぶ場合は親をパスに追加
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent not in sys.path:
        sys.path.insert(0, parent)

    print("[INFO] Server started: http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
