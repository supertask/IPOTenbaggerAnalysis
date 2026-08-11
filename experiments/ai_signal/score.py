"""付けたラベルと実際の株価倍率を突き合わせて、そのラベルに意味があるかを見る。

  python experiments/ai_signal/score.py

ラベルごとの倍率の中央値が揃っていれば、その問いは投資判断の役に立たない。
"""
import csv
import os
import statistics
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))


def load(name, key="コード"):
    with open(os.path.join(BASE, name), encoding="utf-8", newline="") as f:
        return {r[key]: r for r in csv.DictReader(f, delimiter="\t")}


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def rank_of(potential):
    return {"低": 1, "中": 2, "高": 3}.get(potential, 0)


def summarize(groups, metric):
    print(f"\n=== {metric} ===")
    print(f"{'ラベル':14s}{'社数':>5s}{'中央値':>9s}{'平均':>9s}{'3倍以上':>8s}{'10倍以上':>9s}")
    order = sorted(groups, key=lambda k: -statistics.median(groups[k]) if groups[k] else 0)
    for label in order:
        values = groups[label]
        if not values:
            continue
        over3 = sum(1 for v in values if v >= 3) / len(values) * 100
        over10 = sum(1 for v in values if v >= 10) / len(values) * 100
        print(f"{label:14s}{len(values):>5d}{statistics.median(values):>9.2f}"
              f"{statistics.mean(values):>9.2f}{over3:>7.0f}%{over10:>8.0f}%")


def spearman(pairs):
    """順位相関。ラベルを順序尺度として扱う"""
    if len(pairs) < 3:
        return None

    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        result = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            average = (i + j) / 2 + 1
            for k in range(i, j + 1):
                result[order[k]] = average
            i = j + 1
        return result

    xs = ranks([p[0] for p in pairs])
    ys = ranks([p[1] for p in pairs])
    n = len(pairs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / den if den else None


def main():
    answers = load("answers.tsv")
    labels = load("labels.tsv")

    rows = []
    for code, label in labels.items():
        answer = answers.get(code)
        if not answer:
            continue
        peak = number(answer.get("最大何倍株"))
        now = number(answer.get("現在何倍株"))
        if peak is None:
            continue
        rows.append({
            "code": code, "name": answer.get("企業名", ""),
            "driver": label["成長ドライバー"], "potential": label["ポテンシャル"],
            "peak": peak, "now": now,
        })

    print(f"照合できた社数: {len(rows)}")
    overall = [r["peak"] for r in rows]
    print(f"全体の最大何倍株: 中央値 {statistics.median(overall):.2f} / "
          f"平均 {statistics.mean(overall):.2f}")

    # 最大何倍株は一時的な急騰も拾ってしまうので、現在何倍株でも見る
    for metric_key, metric_name in (("peak", "最大何倍株"), ("now", "現在何倍株")):
        for field, title in (("driver", "成長ドライバー別"), ("potential", "ポテンシャル別")):
            groups = defaultdict(list)
            for r in rows:
                value = r[metric_key]
                if value is not None:
                    groups[r[field]].append(value)
            print(f"\n--- {title} ---")
            summarize(groups, metric_name)

        pairs = [(rank_of(r["potential"]), r[metric_key])
                 for r in rows if r[metric_key] is not None]
        rho = spearman(pairs)
        print(f"  ポテンシャル評価との順位相関: "
              f"{'計算不可' if rho is None else format(rho, '+.3f')}")

    # 「仕組みが読み取れる」かどうかの2群比較
    scalable = [r["peak"] for r in rows if r["driver"] != "その他"]
    other = [r["peak"] for r in rows if r["driver"] == "その他"]
    print("\n--- 成長の仕組みが読み取れるか ---")
    print(f"  読み取れる {len(scalable):2d}社  中央値 {statistics.median(scalable):.2f}")
    print(f"  その他     {len(other):2d}社  中央値 {statistics.median(other):.2f}")

    print("\n--- ポテンシャル「高」と付けた銘柄の実績 ---")
    for r in sorted(rows, key=lambda x: -x["peak"]):
        if r["potential"] == "高":
            print(f"  {r['code']:5s} {r['name'][:20]:22s} 最大 {r['peak']:6.1f}倍")

    print("\n--- 実際に伸びた上位5社 ---")
    for r in sorted(rows, key=lambda x: -x["peak"])[:5]:
        print(f"  {r['code']:5s} {r['name'][:20]:22s} 最大 {r['peak']:6.1f}倍 "
              f"（評価: {r['potential']} / {r['driver']}）")


if __name__ == "__main__":
    main()
