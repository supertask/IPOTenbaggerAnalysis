"""拠点あたりの利益を「競合と比べて」見ると株価と関係するかを検証する。

第4ラウンドで見たのは絶対値だった。だが1店舗あたりの利益は業態で桁が違う
（コンビニと有料老人ホームでは比較にならない）。同じ土俵で比べないと
「強みがあるか」は判定できない。

そこで自社の拠点あたり利益を、競合の中央値／同業種の中央値で割った相対値で見る。

  python experiments/ai_signal/score5.py
"""
import csv
import os
import sqlite3
import statistics
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE))
DB = os.path.join(ROOT, "data", "output", "index", "visualizer.db")
FACILITIES = os.path.join(ROOT, "data", "output", "facilities", "facility_counts.tsv")
COMBINER = os.path.join(ROOT, "data", "output", "combiner", "all_companies.tsv")

PROFIT_IDS = ("jppfs_cor:OperatingIncome",
              "jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults")


def num(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def spearman(pairs):
    if len(pairs) < 5:
        return None

    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = avg
            i = j + 1
        return out

    xs, ys = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    n = len(pairs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return cov / den if den else None


def quartiles(items, title):
    items = sorted([i for i in items if i[0] is not None], key=lambda x: x[0])
    print(f"\n{title}（{len(items)}社）")
    if len(items) < 8:
        print("  件数不足")
        return
    size = len(items) // 4
    print(f"{'':12s}{'社数':>5s}{'競合比の中央値':>14s}{'現在何倍株':>12s}{'3倍以上':>8s}")
    for i, name in enumerate(["下位25%", "中下位", "中上位", "上位25%"]):
        chunk = items[i * size:(i + 1) * size] if i < 3 else items[3 * size:]
        print(f"{name:12s}{len(chunk):>5d}{statistics.median(x[0] for x in chunk):>14.2f}"
              f"{statistics.median(x[1] for x in chunk):>12.2f}"
              f"{sum(1 for x in chunk if x[1] >= 3) / len(chunk) * 100:>7.0f}%")
    rho = spearman(items)
    print(f"  順位相関: {'計算不可' if rho is None else format(rho, '+.3f')}")


def main():
    facilities = defaultdict(dict)
    with open(FACILITIES, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            value = num(r["拠点数"])
            if value:
                facilities[r["コード"]][r["報告日"]] = value

    rows = {}
    with open(COMBINER, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            rows.setdefault(r["コード"], r)

    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    marks = ",".join("?" * len(PROFIT_IDS))
    profit = defaultdict(dict)
    for code, date, _eid, value in conn.execute(
            f"""SELECT company_code, report_date, element_id, value
                FROM financial_metrics
                WHERE relative_period='当期' AND report_type='annual'
                  AND element_id IN ({marks})""", PROFIT_IDS):
        v = num(value)
        if v is None:
            continue
        if date not in profit[code] or v > profit[code][date]:
            profit[code][date] = v

    competitors = defaultdict(list)
    for a, b in conn.execute("SELECT company_code, competitor_code FROM competitors"):
        if b:
            competitors[a].append(b)

    def per_facility(code, which):
        """which='last' なら直近、'first' なら最初の期の拠点あたり利益（百万円）"""
        shared = sorted(set(facilities.get(code, {})) & set(profit.get(code, {})))
        if not shared:
            return None
        date = shared[-1] if which == "last" else shared[0]
        count = facilities[code][date]
        return profit[code][date] / count / 1e6 if count else None

    # 業種ごとの中央値（比較の物差し）
    sector_values = defaultdict(list)
    for code in facilities:
        row = rows.get(code)
        value = per_facility(code, "last")
        if row and value is not None:
            sector = (row.get("業種") or "").strip()
            if sector:
                sector_values[sector].append(value)

    vs_comp_last, vs_comp_first, vs_sector_last, vs_sector_first = [], [], [], []
    for code in facilities:
        row = rows.get(code)
        if not row:
            continue
        mult = num(row.get("現在何倍株"))
        if mult is None:
            continue
        sector = (row.get("業種") or "").strip()

        for which, comp_bucket, sector_bucket in (
                ("last", vs_comp_last, vs_sector_last),
                ("first", vs_comp_first, vs_sector_first)):
            own = per_facility(code, which)
            if own is None:
                continue

            peers = [per_facility(p, which) for p in competitors.get(code, [])]
            peers = [p for p in peers if p is not None and p > 0]
            if peers:
                base = statistics.median(peers)
                if base > 0:
                    comp_bucket.append((own / base, mult))

            if len(sector_values.get(sector, [])) >= 5:
                base = statistics.median(sector_values[sector])
                if base > 0:
                    sector_bucket.append((own / base, mult))

    print("拠点あたり利益を competitors / 同業種と比べた場合")
    quartiles(vs_comp_last, "=== 直近: 拠点あたり利益 ÷ 競合の中央値 ===")
    quartiles(vs_sector_last, "=== 直近: 拠点あたり利益 ÷ 同業種の中央値 ===")
    print("\n" + "-" * 56)
    print("予測になっているか（最初の期の値で、その後の倍率を説明できるか）")
    print("-" * 56)
    quartiles(vs_comp_first, "=== 最初の期: 拠点あたり利益 ÷ 競合の中央値 ===")
    quartiles(vs_sector_first, "=== 最初の期: 拠点あたり利益 ÷ 同業種の中央値 ===")


if __name__ == "__main__":
    main()
