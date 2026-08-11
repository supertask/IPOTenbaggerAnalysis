"""有価証券報告書から原価の構成を取り出す。

「安く仕入れられているか」は仕入単価そのものが開示されないので直接は分からないが、
売上原価に占める仕入高の割合や、労務費の比率は分かる。拠点数と違って定義が
揺れないので、企業をまたいだ比較に使いやすい。

売上原価と販管費はXBRLにタグ付けされているのでそこから取る。
仕入高と労務費は売上原価明細書の本文にしか無いので、そこから拾う。

    python -m collectors.cost_structure_collector

出力: data/output/facilities/cost_structure.tsv
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
OUT_PATH = os.path.join(OUT_DIR, "cost_structure.tsv")

ENCODINGS = ("utf-16", "utf-16-le", "utf-8-sig", "utf-8", "cp932")
COST_BLOCK = "DetailedScheduleOfCostOfSalesTextBlock"

# XBRLにタグ付けされている合計値（円単位）
TAGGED = {
    "jppfs_cor:NetSales": "売上高",
    "jpcrp_cor:NetSalesSummaryOfBusinessResults": "売上高",
    "jppfs_cor:CostOfSales": "売上原価",
    "jppfs_cor:SellingGeneralAndAdministrativeExpenses": "販管費",
}

# 明細書の本文から拾う項目。同じ名前が複数出るときは金額の大きいほうを採る
# （主たる区分の行が最大になる）
LINE_ITEMS = {
    "当期仕入高": "仕入高",
    "労務費": "労務費",
    "材料費": "材料費",
}
UNIT_SCALE = {"千円": 0.001, "百万円": 1.0, "円": 0.000001}


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


def _tagged_values(text: str):
    """当期の売上高・売上原価・販管費（百万円）"""
    out = {}
    for line in text.splitlines():
        f = [x.strip('"') for x in line.split("\t")]
        if len(f) < 9:
            continue
        label = TAGGED.get(f[0])
        if not label:
            continue
        context = f[2] or ""
        if not context.startswith("CurrentYear"):
            continue
        try:
            value = float(f[-1]) / 1e6
        except ValueError:
            continue
        # 連結を優先。無ければ単体
        if label not in out or "NonConsolidated" not in context:
            out[label] = value
    return out


def _line_items(text: str):
    """売上原価明細書の本文から仕入高・労務費を拾う"""
    body = None
    for line in text.splitlines():
        if COST_BLOCK in line.split("\t")[0]:
            body = line.split("\t")[-1]
            break
    if body is None:
        return {}

    plain = " ".join(
        re.sub(r"<[^>]+>", " ", body).replace("&#160;", " ").split())
    scale = None
    for unit, factor in UNIT_SCALE.items():
        if f"金額（{unit}）" in plain or f"（{unit}）" in plain:
            scale = factor
            break
    if scale is None:
        return {}

    out = {}
    for keyword, label in LINE_ITEMS.items():
        best = None
        # 「当期仕入高 1,809,253 3,019,243」のように前期・当期が横に並び、当期は右側。
        # 「労務費 221,3707.6 247,6105.7」のように金額と構成比が連結する行もあるので、
        # 桁区切りの形に厳密に一致させたうえで、項目名の後ろ一定範囲の最後の金額を採る。
        number = re.compile(r"\d{1,3}(?:,\d{3})+")
        for match in re.finditer(re.escape(keyword), plain):
            window = plain[match.end():match.end() + 45]
            amounts = number.findall(window)
            if not amounts:
                continue
            # 前期・当期の順に並ぶので2つ目が当期。それ以上は次の項目なので見ない
            raw = amounts[1] if len(amounts) >= 2 else amounts[0]
            try:
                value = float(raw.replace(",", "")) * scale
            except ValueError:
                continue
            if best is None or value > best:
                best = value
        if best is not None:
            out[label] = best
    return out


def extract(path: str):
    text = _read(path)
    if not text:
        return None
    values = _tagged_values(text)
    values.update(_line_items(text))
    if not values.get("売上原価") and not values.get("仕入高"):
        return None
    return values


def main() -> int:
    if not os.path.exists(DB_PATH):
        print(f"インデックスがありません: {DB_PATH}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    reports = list(conn.execute(
        """SELECT company_code, report_date, file_path FROM report_files
           WHERE report_type = 'annual' ORDER BY company_code, report_date"""))
    print(f"有価証券報告書 {len(reports)}件から原価の構成を探します", file=sys.stderr)

    os.makedirs(OUT_DIR, exist_ok=True)
    fields = ["コード", "報告日", "売上高_百万円", "売上原価_百万円", "販管費_百万円",
              "仕入高_百万円", "労務費_百万円", "原価率_％", "仕入高対原価_％"]
    rows = []
    started = time.time()
    for index, report in enumerate(reports, 1):
        values = extract(report["file_path"])
        if values:
            sales = values.get("売上高")
            cost = values.get("売上原価")
            purchase = values.get("仕入高") or values.get("材料費")
            rows.append({
                "コード": report["company_code"],
                "報告日": report["report_date"],
                "売上高_百万円": round(sales, 1) if sales else "",
                "売上原価_百万円": round(cost, 1) if cost else "",
                "販管費_百万円": (round(values["販管費"], 1)
                            if values.get("販管費") else ""),
                "仕入高_百万円": round(purchase, 1) if purchase else "",
                "労務費_百万円": (round(values["労務費"], 1)
                           if values.get("労務費") else ""),
                "原価率_％": (round(cost / sales * 100, 1)
                          if sales and cost else ""),
                "仕入高対原価_％": (round(purchase / cost * 100, 1)
                             if cost and purchase else ""),
            })
        if index % 5000 == 0:
            print(f"  {index}/{len(reports)}件 "
                  f"({index / (time.time() - started):.0f}件/秒) "
                  f"抽出 {len(rows)}件", file=sys.stderr)

    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    with_purchase = sum(1 for r in rows if r["仕入高_百万円"] != "")
    print(f"\n抽出 {len(rows)}件 / {len({r['コード'] for r in rows})}社"
          f"（うち仕入高が取れたもの {with_purchase}件）", file=sys.stderr)
    print(f"出力: {OUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
