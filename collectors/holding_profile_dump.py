"""保有銘柄とその競合の「事業の内容」「役員の状況」を読める形で出す。

business_profile.tsv を書くための下ごしらえ。有報の該当セクションはHTMLの
テーブルが素のまま入っていて、そのままでは読み込みに耐えないので、
タグを落として要点だけ残す。

  python collectors/holding_profile_dump.py 212A
  python collectors/holding_profile_dump.py --list
"""
import argparse
import csv
import glob
import html
import os
import re
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "output", "index", "visualizer.db")
PORTFOLIO_GLOB = os.path.join(BASE_DIR, "data", "output", "portfolio", "*.tsv")

BUSINESS_LIMIT = 2600
OFFICER_LIMIT = 2600
PEER_LIMIT = 1100


def portfolio_codes() -> list:
    codes = []
    for path in sorted(glob.glob(PORTFOLIO_GLOB)):
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        if not rows:
            continue
        key = next((k for k in rows[0] if "コード" in k), None)
        for row in rows:
            code = (row.get(key) or "").strip()
            if code and not code.startswith("(") and code not in codes:
                codes.append(code)
    return codes


def plain(raw: str) -> str:
    """HTMLを落として、行の区切りだけ残す"""
    if not raw:
        return ""
    text = re.sub(r"(?i)</(tr|p|div|h\d)>", "\n", raw)
    text = re.sub(r"(?i)</t[dh]>", " / ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace(" ", " ")
    lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t　]+", " ", line).strip(" /").strip()
        if line and line != "/":
            lines.append(line)
    return "\n".join(lines)


def fetch(conn, code: str):
    row = conn.execute(
        """SELECT c.name,
                  b.latest_html AS business, b.latest_source_report_date AS b_date,
                  o.latest_html AS officers, o.latest_source_report_date AS o_date
           FROM companies c
           LEFT JOIN business_descriptions b ON b.company_code = c.code
           LEFT JOIN officers_info        o ON o.company_code = c.code
           WHERE c.code = ?""",
        (code,),
    ).fetchone()
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("code", nargs="*", help="銘柄コード（複数可）")
    parser.add_argument("--list", action="store_true", help="保有銘柄を一覧する")
    parser.add_argument("--no-peers", action="store_true", help="競合を出さない")
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    if args.list:
        for code in portfolio_codes():
            row = fetch(conn, code)
            peers = conn.execute(
                "SELECT COUNT(*) n FROM competitors WHERE company_code = ?", (code,)
            ).fetchone()["n"]
            has_b = "事業○" if row and row["business"] else "事業×"
            has_o = "役員○" if row and row["officers"] else "役員×"
            print(f"{code:6} {(row['name'] if row else '?')[:24]:26} "
                  f"{has_b} {has_o} 競合{peers}社")
        return 0

    if not args.code:
        parser.error("銘柄コードを指定してください")

    for code in args.code:
        row = fetch(conn, code)
        if row is None:
            print(f"{code} は見つかりません", file=sys.stderr)
            continue

        print(f"\n########## {code} {row['name']} ##########")
        print(f"\n===== 事業の内容（{row['b_date']}） =====")
        print(plain(row["business"])[:BUSINESS_LIMIT] or "(なし)")
        print(f"\n===== 役員の状況（{row['o_date']}） =====")
        print(plain(row["officers"])[:OFFICER_LIMIT] or "(なし)")

        if args.no_peers:
            continue
        peers = conn.execute(
            """SELECT competitor_code AS code, competitor_name AS name
               FROM competitors WHERE company_code = ? ORDER BY rank""",
            (code,),
        ).fetchall()
        for peer in peers:
            prow = fetch(conn, peer["code"])
            print(f"\n===== 競合: {peer['code']} {peer['name']} =====")
            if prow is None or not prow["business"]:
                print("(事業の内容が取れていません)")
                continue
            print(plain(prow["business"])[:PEER_LIMIT])
    return 0


if __name__ == "__main__":
    sys.exit(main())
