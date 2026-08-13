"""適時開示のPDFを落として本文を読む。

`disclosure_check.py` が拾うのはタイトルだけで、「業績予想の修正」が上方か
下方か、社長がなぜ株を売ったのかまでは分からない。理由は本文に書いてある。

  python collectors/disclosure_pdf.py 212A --grep 売出 目的
  python collectors/disclosure_pdf.py 212A --match 売出 --grep 流通株式

JPXの適時開示情報閲覧サービス（www2.jpx.co.jp）から取る。PDFは
data/cache/tdnet_pdf/ に置き、二度目からはそれを読む。
"""
import argparse
import csv
import glob
import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "https://www2.jpx.co.jp"
TDNET_GLOB = os.path.join("data", "output", "tdnet", "*.tsv")
CACHE_DIR = os.path.join("data", "cache", "tdnet_pdf")


def find(code: str, match: str = "", months: int = 24):
    """その銘柄の開示を新しい順に返す"""
    from datetime import datetime, timedelta
    since = (datetime.now() - timedelta(days=months * 31)).strftime("%Y-%m-%d")
    rows = []
    for path in glob.glob(TDNET_GLOB):
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.reader(f, delimiter="\t"):
                if len(row) >= 6 and row[3] == code and row[0] >= since:
                    if not match or match in row[4]:
                        rows.append(row)
    return sorted(rows, reverse=True)


def fetch(url: str) -> str:
    """PDFを落としてテキストにする。取れなければ空文字"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    name = url.strip("/").replace("/", "_")
    pdf_path = os.path.join(CACHE_DIR, name)
    txt_path = pdf_path + ".txt"

    if os.path.exists(txt_path):
        with open(txt_path, encoding="utf-8") as f:
            return f.read()

    if not os.path.exists(pdf_path):
        try:
            res = requests.get(BASE_URL + url, timeout=60, verify=False,
                               headers={"User-Agent": "Mozilla/5.0"})
        except Exception as e:
            print(f"  取得できず: {e}", file=sys.stderr)
            return ""
        if res.status_code != 200 or res.content[:4] != b"%PDF":
            print(f"  PDFではない: HTTP {res.status_code}", file=sys.stderr)
            return ""
        with open(pdf_path, "wb") as f:
            f.write(res.content)

    try:
        from pypdf import PdfReader
    except ImportError:
        print("pypdf が要ります: pip install pypdf", file=sys.stderr)
        return ""
    try:
        reader = PdfReader(pdf_path)
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as e:
        print(f"  読めず: {e}", file=sys.stderr)
        return ""
    text = re.sub(r"[ \t]+", " ", text)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("code")
    parser.add_argument("--match", default="", help="タイトルで絞る")
    parser.add_argument("--grep", nargs="*", default=[],
                        help="本文からこの語を含む行を出す。無ければ冒頭を出す")
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--limit", type=int, default=3, help="読むPDFの数")
    parser.add_argument("--context", type=int, default=2, help="前後の行数")
    args = parser.parse_args()

    rows = find(args.code, args.match, args.months)
    if not rows:
        print("該当する開示がありません")
        return 1

    for row in rows[:args.limit]:
        date, _, name, code, title, url = row[:6]
        print(f"\n{'=' * 70}\n{date} {name} {title}\n{BASE_URL}{url}\n{'=' * 70}")
        text = fetch(url)
        if not text:
            continue
        lines = [ln.rstrip() for ln in text.splitlines()]
        if not args.grep:
            print("\n".join(ln for ln in lines[:40] if ln.strip()))
            continue
        shown = set()
        for i, line in enumerate(lines):
            if any(word in line for word in args.grep):
                lo, hi = max(0, i - args.context), min(len(lines), i + args.context + 1)
                for j in range(lo, hi):
                    if j not in shown and lines[j].strip():
                        print(f"  {lines[j]}")
                        shown.add(j)
                print("  ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
