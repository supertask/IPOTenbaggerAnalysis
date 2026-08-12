"""1銘柄について、買う・持ち続けるの判断に要る数字を全部出す。

読み解きを書く前にこれを走らせる。事業の説明だけ書いても投資の判断には
使えないので、テンバガー条件・株価とPER・拠点あたりの採算・原価の構成・
大株主と役員の持株・上場時の諸元を、同じ画面に並べて見る。

  python collectors/holding_judgment_dump.py 212A
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from visualizer import db as _db
from visualizer import facility_service, holdings_service, price_service
from visualizer import tenbagger_criteria as criteria

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALL_COMPANIES = os.path.join(
    BASE_DIR, "data", "output", "combiner", "all_companies.tsv")
PORTFOLIO_DIR = os.path.join(BASE_DIR, "data", "output", "portfolio")

# 上場時の諸元のうち、長期で持てるかの判断に効くものだけ
IPO_FIELDS = ["上場日", "市場", "業種", "想定時価総額", "公開価格", "初値",
              "現在何倍株", "最大何倍株", "社長_株%", "役員_株%", "家族_株%",
              "VC_ファンド_株%", "従業員数", "設立年", "代表者名",
              "代表者の上場時の年齢", "決算伸び率%"]


def _fmt(value, digits=2, suffix=""):
    if value is None:
        return "–"
    return f"{value:,.{digits}f}{suffix}"


def show_ipo(code: str) -> None:
    if not os.path.exists(ALL_COMPANIES):
        return
    with open(ALL_COMPANIES, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if (row.get("コード") or "").strip() != code:
                continue
            print("--- 上場時の諸元 ---")
            for key in IPO_FIELDS:
                if row.get(key):
                    print(f"  {key}: {row[key]}")
            perf = (row.get("企業業績のデータ（5年分）") or "").strip()
            if perf:
                print(f"  業績(5年): {perf[:400]}")
            return


def show_price(code: str) -> None:
    prices = price_service.get_price_series(code)
    if not prices["dates"]:
        print("--- 株価 --- 取得できず")
        return
    per = price_service.get_per_series(code, prices)
    closes = [c for c in prices["close"] if c is not None]
    latest = closes[-1] if closes else None
    pers = [v for v in per["per"] if v is not None]
    print("--- 株価とPER ---")
    print(f"  期間: {prices['dates'][0]} 〜 {prices['dates'][-1]}（{len(prices['dates'])}営業日）")
    print(f"  直近終値: {_fmt(latest, 0)}円 / 上場来高値 {_fmt(max(closes), 0)} / 安値 {_fmt(min(closes), 0)}")
    if latest and closes:
        print(f"  高値からの位置: {latest / max(closes) * 100:.0f}%")
    if pers:
        print(f"  直近PER: {_fmt(pers[-1], 1)}倍 / 期間中の最大 {_fmt(max(pers), 1)} 最小 {_fmt(min(pers), 1)}")
    quality = price_service._price_quality(prices)
    if quality:
        print(f"  注意: {quality['message']}")
    lockup = price_service.get_lockup_markers(code)
    if lockup:
        print("  ロックアップ解除の目安:",
              ", ".join(f"{m['date']}({m.get('short') or m.get('label')})" for m in lockup[:5]))


def show_criteria(code: str) -> None:
    per = price_service.get_latest_per(code)
    result = criteria.evaluate_by_code(code, per)
    if not result:
        print("--- テンバガー条件 --- 判定できず")
        return
    items = result.get("items") or []
    ok = sum(1 for i in items if i.get("status") == "pass")
    print(f"--- テンバガー条件 {ok}/{len(items)} ---")
    for item in items:
        mark = {"pass": "○", "partial": "△", "fail": "✕"}.get(item.get("status"), "?")
        detail = (item.get("detail") or "").replace("\n", " ")
        print(f"  {mark} {item.get('title')}: {detail[:70]}")
        for ev in (item.get("evidence") or [])[:2]:
            print(f"      {ev.get('label')}: {str(ev.get('value'))[:70]}")


def show_facility(code: str) -> None:
    conn = _db.get_conn()
    peers = []
    if conn is not None:
        peers = [dict(code=r["competitor_code"], name=r["competitor_name"])
                 for r in conn.execute(
                     "SELECT competitor_code, competitor_name FROM competitors "
                     "WHERE company_code = ? ORDER BY rank", (code,))]
    view = facility_service.get_facility_view(code, peers)
    print(f"--- 拠点あたりの採算（競合{len(peers)}社） ---")
    if not view:
        print("  出せない（拠点数が取れないか、業態として成り立たない）")
        cost = facility_service._load_cost_structure().get(code)
        if cost:
            print(f"  原価率 {_fmt(cost.get('cost_ratio'), 1)}% "
                  f"仕入/原価 {_fmt(cost.get('purchase_ratio'), 1)}% "
                  f"労務費/原価 {_fmt(cost.get('labor_ratio'), 1)}%")
        return
    own = view["own"]["latest"]
    print(f"  自社 {own['date'][:7]} {own['count']:,.0f}{own['unit']} "
          f"売上/拠点 {_fmt(own['sales_per'], 1)}百万 利益/拠点 {_fmt(own['profit_per'], 2)}百万")
    for peer in view["peers"]:
        p = peer["latest"]
        print(f"  競合 {peer['name']} {p['count']:,.0f}{p['unit']} "
              f"利益/拠点 {_fmt(p['profit_per'], 2)}百万")
    if view.get("ratio_to_peers"):
        print(f"  競合中央値との比: {view['ratio_to_peers']:.1f}倍")
    if view.get("latest_interim"):
        li = view["latest_interim"]
        print(f"  直近（期中）: {li['count']:,.0f}{li['unit']}（{li['date'][:7]}）")
    cost = view.get("cost_structure") or {}
    if cost:
        print(f"  原価率 {_fmt(cost.get('cost_ratio'), 1)}% "
              f"仕入/原価 {_fmt(cost.get('purchase_ratio'), 1)}% "
              f"労務費/原価 {_fmt(cost.get('labor_ratio'), 1)}%")
    for peer in view.get("peer_cost_structures") or []:
        print(f"  競合の原価率 {peer['name']}: {_fmt(peer.get('cost_ratio'), 1)}%")
    if view["own"]["points"]:
        series = " → ".join(f"{p['date'][:7]}:{p['count']:,.0f}"
                            for p in view["own"]["points"][-6:])
        print(f"  拠点数の推移: {series}")


def show_holdings(code: str) -> None:
    view = holdings_service.get_holdings_history(code)
    print("--- 大株主と役員の持株 ---")
    if not view:
        print("  取れず")
        return
    for key, label in (("major", "大株主"), ("officer", "役員")):
        table = view.get(key)
        if not table:
            continue
        dates = [c["date"][:7] + ("(中)" if c["interim"] else "")
                 for c in table["columns"]]
        print(f"  [{label}] 期: {' '.join(dates[-6:])}")
        for person in table["people"][:5]:
            values = " ".join("–" if v is None else f"{v:,.0f}"
                              for v in person["values"][-6:])
            change = person.get("change")
            arrow = "" if change in (None, 0) else f"  増減 {change:+,.0f}"
            print(f"    {person['name'][:24]:26} {values}{arrow}")
    if view.get("officer_decreases"):
        print("  役員の合計が減った期:",
              ", ".join(f"{d['date'][:7]}({d['diff']:+,.0f})"
                        for d in view["officer_decreases"]))


def show_financials(code: str) -> None:
    """売上と利益の推移。成長が続いているかを見る"""
    conn = _db.get_conn()
    if conn is None:
        return
    ids = facility_service.SALES_IDS + facility_service.PROFIT_IDS
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"""SELECT report_date, element_id, value FROM financial_metrics
            WHERE company_code = ? AND relative_period = '当期'
              AND report_type = 'annual' AND element_id IN ({marks})
            ORDER BY report_date""",
        (code, *ids)).fetchall()
    by_date: dict = {}
    for row in rows:
        try:
            value = float(row["value"])
        except (TypeError, ValueError):
            continue
        key = "売上" if row["element_id"] in facility_service.SALES_IDS else "利益"
        bucket = by_date.setdefault(row["report_date"], {})
        if key not in bucket or value > bucket[key]:
            bucket[key] = value
    if not by_date:
        return
    print("--- 売上と利益（百万円） ---")
    prev = None
    for date in sorted(by_date):
        sales = by_date[date].get("売上")
        profit = by_date[date].get("利益")
        growth = ""
        if prev and sales and prev.get("売上"):
            growth = f"  売上前年比 {sales / prev['売上'] * 100 - 100:+.0f}%"
        margin = ""
        if sales and profit:
            margin = f"  利益率 {profit / sales * 100:.1f}%"
        print(f"  {date[:7]} 売上 {_fmt((sales or 0) / 1e6, 0)} "
              f"利益 {_fmt((profit or 0) / 1e6, 0)}{margin}{growth}")
        prev = by_date[date]


def portfolio_weight(code: str) -> None:
    for name in ("myself", "tenbagger_x", "favorites"):
        path = os.path.join(PORTFOLIO_DIR, f"{name}.tsv")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                if (row.get("銘柄コード") or "").strip() == code:
                    print(f"--- {name} の保有 ---")
                    for key in ("保有株数", "取得単価", "現在値", "評価額",
                                "評価損益", "保有割合%", "口座区分"):
                        if row.get(key):
                            print(f"  {key}: {row[key]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("codes", nargs="+")
    args = parser.parse_args()

    conn = _db.get_conn()
    for code in args.codes:
        name = "?"
        if conn is not None:
            row = conn.execute("SELECT name FROM companies WHERE code = ?",
                               (code,)).fetchone()
            name = row["name"] if row else "?"
        print(f"\n{'=' * 70}\n{code} {name}\n{'=' * 70}")
        portfolio_weight(code)
        show_ipo(code)
        show_financials(code)
        show_price(code)
        show_criteria(code)
        show_facility(code)
        show_holdings(code)
    return 0


if __name__ == "__main__":
    sys.exit(main())
