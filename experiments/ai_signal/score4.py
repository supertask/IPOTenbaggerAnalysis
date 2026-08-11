"""拠点あたりの採算が、その後の株価と関係するかを見る。

第3ラウンドは従業員単位かつ上場時の1時点だったので相関しなかった。今回は
有報から取った拠点数を使い、しかも「1時点の水準」ではなく「期をまたいだ変化」
を見る。規模を広げながら採算を保てているか、という元々の仮説に近い形。

  python experiments/ai_signal/score4.py
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

SALES_IDS = ("jpcrp_cor:NetSalesSummaryOfBusinessResults",
             "jpcrp_cor:RevenueIFRSSummaryOfBusinessResults")
PROFIT_IDS = ("jppfs_cor:OperatingIncome",
              "jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults")


def num(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def load_facilities():
    if not os.path.exists(FACILITIES):
        raise SystemExit(f"{FACILITIES} がありません。"
                         "先に python -m collectors.facility_count_collector を実行してください")
    out = defaultdict(dict)
    with open(FACILITIES, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            count = num(r["拠点数"])
            if count:
                out[r["コード"]][r["報告日"]] = count
    return out


def load_financials(conn, codes):
    """会社ごと・報告日ごとの当期売上と当期利益"""
    sales, profit = defaultdict(dict), defaultdict(dict)
    marks = ",".join("?" * len(SALES_IDS + PROFIT_IDS))
    query = f"""SELECT company_code, report_date, element_id, value
                FROM financial_metrics
                WHERE relative_period = '当期' AND report_type = 'annual'
                  AND element_id IN ({marks})"""
    for row in conn.execute(query, SALES_IDS + PROFIT_IDS):
        code = row[0]
        if code not in codes:
            continue
        value = num(row[3])
        if value is None:
            continue
        target = sales if row[2] in SALES_IDS else profit
        # 同じ期に複数の値があるときは大きいほうを採る（連結を優先したい）
        if row[1] not in target[code] or value > target[code][row[1]]:
            target[code][row[1]] = value
    return sales, profit


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


def quartiles(items, title, unit=""):
    items = [i for i in items if i[0] is not None and i[1] is not None]
    items.sort(key=lambda x: x[0])
    print(f"\n{title}（{len(items)}社）")
    if len(items) < 8:
        print("  件数不足")
        return
    size = len(items) // 4
    print(f"{'':12s}{'社数':>5s}{'指標の中央値':>14s}{'現在何倍株':>12s}{'3倍以上':>8s}")
    for i, name in enumerate(["下位25%", "中下位", "中上位", "上位25%"]):
        chunk = items[i * size:(i + 1) * size] if i < 3 else items[3 * size:]
        if not chunk:
            continue
        print(f"{name:12s}{len(chunk):>5d}"
              f"{statistics.median(x[0] for x in chunk):>13.2f}{unit:1s}"
              f"{statistics.median(x[1] for x in chunk):>12.2f}"
              f"{sum(1 for x in chunk if x[1] >= 3) / len(chunk) * 100:>7.0f}%")
    rho = spearman(items)
    print(f"  順位相関: {'計算不可' if rho is None else format(rho, '+.3f')}")


def main():
    facilities = load_facilities()
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    multiples = {}
    with open(COMBINER, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            multiples.setdefault(r["コード"], num(r.get("現在何倍株")))

    codes = set(facilities) & set(multiples)
    sales, profit = load_financials(conn, codes)

    growth_rows, margin_rows, expand_rows = [], [], []
    for code in codes:
        mult = multiples.get(code)
        if mult is None:
            continue
        years = sorted(facilities[code])
        # 拠点数と売上の両方が揃う期だけを使う
        usable = [y for y in years if y in sales.get(code, {})]
        if len(usable) < 3:
            continue
        first, last = usable[0], usable[-1]
        span = (int(last[:4]) - int(first[:4])) or 1

        per_first = sales[code][first] / facilities[code][first]
        per_last = sales[code][last] / facilities[code][last]
        if per_first > 0:
            # 拠点あたり売上が何倍になったか（年率）
            growth_rows.append(((per_last / per_first) ** (1 / span), mult))

        expand_rows.append(
            ((facilities[code][last] / facilities[code][first]) ** (1 / span), mult))

        if code in profit and last in profit[code] and facilities[code][last]:
            margin_rows.append((profit[code][last] / facilities[code][last] / 1e6, mult))

    print(f"拠点数が取れた企業: {len(facilities)}社")
    print(f"うち倍率と3期以上の突き合わせができた企業: {len(expand_rows)}社")

    quartiles(expand_rows, "=== 拠点の増加ペース（年率）===", "倍")
    quartiles(growth_rows, "=== 拠点あたり売上の変化（年率）===", "倍")
    quartiles(margin_rows, "=== 直近の拠点あたり利益（百万円）===")

    # ここから対照実験。
    # 「直近の拠点あたり利益」は株価と同じ時点の値なので、予測できたのではなく
    # 「今もうかっている会社は株価も上がっている」を見ているだけかもしれない。
    # また利益÷拠点数なので、拠点で割ったことに意味があるのか、単に利益の
    # 効果なのかも分からない。両方を切り分ける。
    first_rows, abs_profit_rows, margin_pct_rows, first_abs_rows = [], [], [], []
    for code in codes:
        mult = multiples.get(code)
        if mult is None:
            continue
        years = sorted(facilities[code])
        usable = [y for y in years if y in sales.get(code, {})]
        if len(usable) < 3:
            continue
        first, last = usable[0], usable[-1]

        # 予測になっているか: 最初の期の拠点あたり利益で将来の倍率を説明できるか
        if code in profit and first in profit[code] and facilities[code][first]:
            first_rows.append((profit[code][first] / facilities[code][first] / 1e6, mult))
            first_abs_rows.append((profit[code][first] / 1e6, mult))

        # 拠点で割ったことに意味があるか: 利益そのもの、利益率と比べる
        if code in profit and last in profit[code]:
            abs_profit_rows.append((profit[code][last] / 1e6, mult))
            if sales[code].get(last):
                margin_pct_rows.append(
                    (profit[code][last] / sales[code][last] * 100, mult))

    print("\n" + "=" * 56)
    print("対照実験: 上の +0.442 が本物かを確かめる")
    print("=" * 56)
    quartiles(first_abs_rows, "--- 最初の期の利益（百万円）→ その後の倍率 ---")
    quartiles(first_rows, "--- 最初の期の拠点あたり利益（百万円）→ その後の倍率 ---")
    quartiles(abs_profit_rows, "--- 直近の利益（百万円・拠点で割らない）---")
    quartiles(margin_pct_rows, "--- 直近の利益率（％）---", "%")


if __name__ == "__main__":
    main()
