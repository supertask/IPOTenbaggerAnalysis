"""有価証券報告書の「設備投資等の概要」から、その期の設備投資額を取り出す。

拠点数の増加と突き合わせると、1店舗いくらで出しているか（出店単価）が分かる。
多店舗展開型の企業では、これが安いほど同じ資金で多く出店できるので、
拡大のペースと採算に直結する。

設備投資額は決まった要素でタグ付けされていないため、本文から拾う。

    python -m collectors.capex_collector

出力: data/output/facilities/capex.tsv
"""
from __future__ import annotations

import csv
import os
import re
import sqlite3
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "output", "index", "visualizer.db")
OUT_DIR = os.path.join(BASE_DIR, "data", "output", "facilities")
OUT_PATH = os.path.join(OUT_DIR, "capex.tsv")

BLOCK = "OverviewOfCapitalExpendituresEtcTextBlock"
# 「設備の新設、除却等の計画」。投資予定金額と、完成後に増える店舗数が並ぶ
PLAN_BLOCK = "PlannedAdditionsRetirementsEtcOfFacilitiesTextBlock"
STORE_RE = re.compile(r"([0-9０-９]{1,4})\s*(店舗|拠点|施設|事業所|ホーム)")
_ZEN = str.maketrans("０１２３４５６７８９", "0123456789")
ENCODINGS = ("utf-16", "utf-16-le", "utf-8-sig", "utf-8", "cp932")

# 金額の単位。百万円に揃える
SCALE = {"億円": 100.0, "百万円": 1.0, "千円": 0.001}
AMOUNT_RE = re.compile(r"([0-9][0-9,]*)\s*(億円|百万円|千円)")
# 「総額」の直後に出る金額を本命とする。無ければ最初に出た金額
TOTAL_RE = re.compile(r"総額[^0-9]{0,12}([0-9][0-9,]*)\s*(億円|百万円|千円)")


def _read(path: str):
    for enc in ENCODINGS:
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
        except OSError:
            return None
    return None


def _to_million(raw: str, unit: str):
    try:
        return float(raw.replace(",", "")) * SCALE[unit]
    except (ValueError, KeyError):
        return None


def _plain_block(text: str, key: str):
    for line in text.splitlines():
        if key in line.split("\t")[0]:
            body = line.split("\t")[-1]
            return " ".join(
                re.sub(r"<[^>]+>", " ", body).replace("&#160;", " ").split())
    return None


def _planned_per_store(text: str):
    """計画に書かれた投資予定金額と増える店舗数から、1店舗あたりを出す。

    表が1行だけ（店舗数の記載が1箇所）のときに限る。複数の計画が並ぶと
    どの金額がどの店舗に対応するか本文からは決められないため。
    """
    plain = _plain_block(text, PLAN_BLOCK)
    if not plain:
        return None
    stores = STORE_RE.findall(plain)
    if len(stores) != 1:
        return None
    try:
        count = int(stores[0][0].translate(_ZEN))
    except ValueError:
        return None
    if count <= 0:
        return None

    # 計画は表なので、金額に単位が付かず見出しに「（千円）」等とあるだけ。
    # 見出しから単位を拾い、桁区切りの数字を金額として扱う。
    unit = None
    for candidate in ("千円", "百万円", "億円"):
        if f"（{candidate}）" in plain or f"({candidate})" in plain:
            unit = candidate
            break
    if unit is None:
        return None

    amounts = [_to_million(m.group(0), unit)
               for m in re.finditer(r"\d{1,3}(?:,\d{3})+", plain)]
    amounts = [a for a in amounts if a]
    if not amounts:
        return None
    total = max(amounts)
    return {"planned_total": total, "planned_stores": count,
            "planned_per_store": total / count}


def extract(path: str):
    text = _read(path)
    if not text:
        return None

    plain = _plain_block(text, BLOCK)
    result = {}
    if plain:
        match = TOTAL_RE.search(plain)
        if match:
            amount = _to_million(match.group(1), match.group(2))
        else:
            first = AMOUNT_RE.search(plain)
            amount = _to_million(first.group(1), first.group(2)) if first else None
        if amount is not None:
            result = {"amount": amount, "excerpt": plain[:160]}

    planned = _planned_per_store(text)
    if planned:
        result.update(planned)
    return result or None


def main() -> int:
    if not os.path.exists(DB_PATH):
        print(f"インデックスがありません: {DB_PATH}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    reports = list(conn.execute(
        """SELECT company_code, report_date, file_path FROM report_files
           WHERE report_type = 'annual' ORDER BY company_code, report_date"""))
    print(f"有価証券報告書 {len(reports)}件から設備投資額を探します", file=sys.stderr)

    os.makedirs(OUT_DIR, exist_ok=True)
    rows = []
    started = time.time()
    for index, report in enumerate(reports, 1):
        result = extract(report["file_path"])
        if result:
            rows.append({
                "コード": report["company_code"],
                "報告日": report["report_date"],
                "設備投資額_百万円": (round(result["amount"], 1)
                              if result.get("amount") is not None else ""),
                "計画_投資額_百万円": (round(result["planned_total"], 1)
                               if result.get("planned_total") else ""),
                "計画_店舗数": result.get("planned_stores", ""),
                "計画_1店舗あたり_百万円": (round(result["planned_per_store"], 1)
                                 if result.get("planned_per_store") else ""),
                "原文": result.get("excerpt", ""),
            })
        if index % 5000 == 0:
            print(f"  {index}/{len(reports)}件 "
                  f"({index / (time.time() - started):.0f}件/秒) "
                  f"抽出 {len(rows)}件", file=sys.stderr)

    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["コード", "報告日", "設備投資額_百万円",
                           "計画_投資額_百万円", "計画_店舗数",
                           "計画_1店舗あたり_百万円", "原文"],
            delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    companies = {r["コード"] for r in rows}
    print(f"\n抽出 {len(rows)}件 / {len(companies)}社", file=sys.stderr)
    print(f"出力: {OUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
