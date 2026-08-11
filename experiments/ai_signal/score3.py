"""従業員1人あたりの売上・利益が、その後の株価と関係するかを見る。

「1拠点あたりの採算を競合と比べれば、その事業モデルが実際に効いているか
分かるのでは」という仮説の検証。店舗数はどこにも無いので、代わりに
従業員数を使う（97%の銘柄で取れる）。

比較の相手は2通り用意する。
  - 競合企業（登録がある銘柄のみ）
  - 同業種の中央値（全銘柄で取れる）

  python experiments/ai_signal/score3.py
"""
import csv
import json
import os
import sqlite3
import statistics
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE))
SRC = os.path.join(ROOT, "data", "output", "combiner", "all_companies.tsv")
DB = os.path.join(ROOT, "data", "output", "index", "visualizer.db")


def num(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def latest(row, key):
    """企業業績5年分から、その項目の直近値を取る"""
    raw = row.get("企業業績のデータ（5年分）")
    if not raw:
        return None
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        return None
    for item in items or []:
        for name, values in (item or {}).items():
            if name.startswith(key):
                pairs = sorted((str(k).replace("\n", ""), num(v))
                               for k, v in values.items())
                pairs = [(k, v) for k, v in pairs if v is not None]
                if pairs:
                    return pairs[-1][1]
    return None


def per_employee(row):
    """1人あたり売上と1人あたり経常利益（百万円）"""
    employees = num(row.get("従業員数"))
    if not employees:
        return None, None
    sales = latest(row, "売上高")
    profit = latest(row, "経常利益")
    return (sales / employees if sales is not None else None,
            profit / employees if profit is not None else None)


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
    num_ = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num_ / den if den else None


def quartile_table(items, title):
    """相対値の大きさで4分割し、群ごとの株価倍率を見る"""
    items = sorted(items, key=lambda x: x[0])
    if len(items) < 8:
        print(f"\n{title}: 件数不足（{len(items)}社）")
        return
    size = len(items) // 4
    print(f"\n{title}  （{len(items)}社）")
    print(f"{'':16s}{'社数':>5s}{'相対値の中央値':>14s}{'現在何倍株の中央値':>18s}{'3倍以上':>8s}")
    names = ["下位25%", "中下位", "中上位", "上位25%"]
    for i, name in enumerate(names):
        chunk = items[i * size:(i + 1) * size] if i < 3 else items[3 * size:]
        if not chunk:
            continue
        rel = statistics.median(x[0] for x in chunk)
        mult = statistics.median(x[1] for x in chunk)
        over3 = sum(1 for x in chunk if x[1] >= 3) / len(chunk) * 100
        print(f"{name:16s}{len(chunk):>5d}{rel:>14.2f}{mult:>18.2f}{over3:>7.0f}%")
    rho = spearman(items)
    print(f"  順位相関: {'計算不可' if rho is None else format(rho, '+.3f')}")


def main():
    with open(SRC, encoding="utf-8", newline="") as f:
        rows = {}
        for r in csv.DictReader(f, delimiter="\t"):
            rows.setdefault(r["コード"], r)

    with open(os.path.join(BASE, "answers2.tsv"), encoding="utf-8", newline="") as f:
        answers = list(csv.DictReader(f, delimiter="\t"))

    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    # 業種ごとの中央値（比較の物差し）
    sector_sales, sector_profit = defaultdict(list), defaultdict(list)
    for r in rows.values():
        sector = (r.get("業種") or "").strip()
        if not sector:
            continue
        s, p = per_employee(r)
        if s is not None:
            sector_sales[sector].append(s)
        if p is not None:
            sector_profit[sector].append(p)

    vs_comp_sales, vs_comp_profit = [], []
    vs_sector_sales, vs_sector_profit = [], []
    absolute_profit = []

    for a in answers:
        row = rows.get(a["コード"])
        mult = num(a.get("現在何倍株"))
        if not row or mult is None:
            continue
        sales, profit = per_employee(row)
        sector = (row.get("業種") or "").strip()

        if profit is not None:
            absolute_profit.append((profit, mult))

        # 競合との比較
        comps = [c[0] for c in conn.execute(
            "SELECT competitor_code FROM competitors WHERE company_code=?", (a["コード"],))]
        comp_sales, comp_profit = [], []
        for code in comps:
            cr = rows.get(code)
            if not cr:
                continue
            cs, cp = per_employee(cr)
            if cs is not None:
                comp_sales.append(cs)
            if cp is not None:
                comp_profit.append(cp)
        if sales is not None and comp_sales:
            base = statistics.median(comp_sales)
            if base > 0:
                vs_comp_sales.append((sales / base, mult))
        if profit is not None and comp_profit:
            base = statistics.median(comp_profit)
            if base > 0:
                vs_comp_profit.append((profit / base, mult))

        # 同業種との比較
        if sales is not None and len(sector_sales.get(sector, [])) >= 5:
            base = statistics.median(sector_sales[sector])
            if base > 0:
                vs_sector_sales.append((sales / base, mult))
        if profit is not None and len(sector_profit.get(sector, [])) >= 5:
            base = statistics.median(sector_profit[sector])
            if base > 0:
                vs_sector_profit.append((profit / base, mult))

    print("従業員1人あたりの採算と、その後の株価倍率の関係")
    quartile_table(absolute_profit, "=== 1人あたり経常利益（絶対値）===")
    quartile_table(vs_comp_sales, "=== 1人あたり売上 ÷ 競合の中央値 ===")
    quartile_table(vs_comp_profit, "=== 1人あたり経常利益 ÷ 競合の中央値 ===")
    quartile_table(vs_sector_sales, "=== 1人あたり売上 ÷ 同業種の中央値 ===")
    quartile_table(vs_sector_profit, "=== 1人あたり経常利益 ÷ 同業種の中央値 ===")


if __name__ == "__main__":
    main()
