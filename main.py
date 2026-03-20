#!/usr/bin/env python3
"""
main.py - CLI エントリーポイント
名刺画像 → SVG 変換システムのコマンドラインインターフェース
"""

from __future__ import annotations
import argparse
import sys
import os
import time


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="card2svg",
        description="名刺画像 → 構造化SVG 変換システム",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用例:
  python main.py --input card.png --output output.svg
  python main.py --input card.jpg --output output.svg --json debug.json --verbose
  python main.py --input card.pdf --output output.svg
        """,
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="入力画像ファイルパス (PNG / JPG / PDF)",
    )
    parser.add_argument(
        "--output", "-o",
        default="output.svg",
        help="出力 SVG ファイルパス (デフォルト: output.svg)",
    )
    parser.add_argument(
        "--json", "-j",
        default=None,
        help="中間データ JSON 保存先 (デバッグ用, 省略可)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="進捗メッセージを表示する",
    )

    args = parser.parse_args()

    # 入力ファイル存在確認
    if not os.path.exists(args.input):
        print(f"[エラー] 入力ファイルが見つかりません: {args.input}", file=sys.stderr)
        sys.exit(1)

    # 拡張子確認
    ext = os.path.splitext(args.input)[1].lower()
    if ext not in {".png", ".jpg", ".jpeg", ".pdf"}:
        print(f"[エラー] 非対応ファイル形式: {ext}", file=sys.stderr)
        print("  対応形式: PNG, JPG, JPEG, PDF", file=sys.stderr)
        sys.exit(1)

    print(f"📇 名刺 → SVG 変換開始")
    print(f"   入力: {args.input}")
    print(f"   出力: {args.output}")
    if args.json:
        print(f"   JSON: {args.json}")
    print()

    start = time.time()

    try:
        from src.pipeline import run_pipeline
        result = run_pipeline(
            image_path=args.input,
            output_svg=args.output,
            output_json=args.json,
            verbose=args.verbose,
        )
    except Exception as e:
        print(f"[エラー] 処理中に例外が発生しました: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    elapsed = time.time() - start
    n_texts = len(result.get("texts", []))
    n_shapes = len(result.get("shapes", []))

    print(f"✅ 完了!")
    print(f"   テキストブロック: {n_texts} 件")
    print(f"   図形ブロック:     {n_shapes} 件")
    print(f"   処理時間:         {elapsed:.1f} 秒")
    print(f"   出力ファイル:     {os.path.abspath(args.output)}")


if __name__ == "__main__":
    main()
