# 名刺 → 構造化SVG 変換システム (Card2SVG)

名刺ラスタ画像（PNG / JPG / PDF）を OCR + レイアウト解析で解析し、  
**94×58mm 印刷対応の編集可能なSVG** として再構築するシステムです。

> 「画像をトレース」するのではなく、「名刺の構造を再構築する」設計思想に基づきます。

---

## セットアップ

```bash
# 仮想環境作成（推奨）
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate # macOS/Linux

# 依存パッケージインストール
pip install -r requirements.txt
```

## GitHub で動かす場合

このリポジトリは `Flask + OCR + OpenCV` を使うため、`GitHub Pages` では動きません。  
GitHub リポジトリをそのまま接続して公開するなら、`Render` などの Python 対応ホスティングを使うのが現実的です。

このリポジトリには `render.yaml` を入れてあるので、以下で公開できます。

1. GitHub に push する
2. Render で `New +` → `Blueprint` を選ぶ
3. この GitHub リポジトリを接続する
4. `image2svg-editor` サービスを作成する
5. デプロイ完了後、発行された URL にアクセスする

起動コマンドは Render 側で自動的に以下が使われます。

```bash
gunicorn --bind 0.0.0.0:$PORT web.server:app
```

補足:

- `GitHub Pages` は静的 HTML/CSS/JS 配信向けなので、このアプリの `/api/convert` は動きません
- `GitHub Codespaces` なら GitHub 上の開発環境として起動はできますが、常設公開サーバーには向きません
- Render では Python のデフォルト版が変わることがあるため、このリポジトリは `.python-version` で `3.11.11` に固定しています
- PDF 入力も使えるように `PyMuPDF` を依存関係へ追加しています

---

## 使い方

### CLI（コマンドライン）

```bash
# 基本的な変換
python main.py --input card.png --output output.svg

# 詳細ログ + 中間JSON保存
python main.py --input card.jpg --output output.svg --json debug.json --verbose

# PDF入力（PyMuPDF が必要: pip install pymupdf）
python main.py --input card.pdf --output output.svg
```

### Web UI

```bash
# Flaskサーバー起動
python web/server.py

# ブラウザで開く
# http://localhost:5000
```

ブラウザで画像をドラッグ&ドロップ → SVGプレビュー → ダウンロード

本番公開時は `python web/server.py` ではなく `gunicorn` 起動を使ってください。

---

## テスト

```bash
# 実際の画像不要のユニットテスト
python tests/test_pipeline.py

# サンプルSVGが sample_output.svg に出力されます
```

---

## 出力仕様

| 項目 | 値 |
|------|----|
| サイズ | 94mm × 58mm |
| viewBox | `0 0 94 58` |
| 外枠 | マゼンタ, 0.25mm |
| テキスト | `<text>` タグ（OCR結果） |
| フォント | Noto Sans JP / Noto Serif JP / Inter |
| 図形 | `<rect>` / `<circle>` |
| クリップ | clipPath で枠内にクリップ |

---

## プロジェクト構成

```
binary-expanse/
├── main.py                  # CLIエントリーポイント
├── requirements.txt
├── src/
│   ├── pipeline.py          # 統合パイプライン
│   ├── ocr.py               # OCR（EasyOCR）
│   ├── layout.py            # レイアウト解析（OpenCV）
│   ├── classifier.py        # テキスト役割分類
│   ├── font_mapper.py       # フォント近似マッピング
│   ├── shape_extractor.py   # 図形抽出
│   └── svg_builder.py       # SVG生成
├── web/
│   ├── index.html           # WebUI
│   └── server.py            # Flaskサーバー
├── tests/
│   └── test_pipeline.py
└── samples/                 # テスト用名刺画像
```

---

## フォントマッピング

| 分類 | SVGフォント |
|------|------------|
| ゴシック | Noto Sans JP |
| 明朝 | Noto Serif JP |
| 丸ゴ | Zen Maru Gothic |
| 欧文 | Inter |

---

## 今後の拡張予定

- フォント推定精度向上
- ロゴ簡易トレース
- 塗り足し・トンボ追加
- PDF出力対応
- Webエディタ連携
