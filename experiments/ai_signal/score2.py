"""第2ラウンドの採点。成長ドライバーの分類に信号があるかを見る。

第1ラウンドで見えた「契約積み上げが最下位」が事業モデルの差なのか、
上場時の評価水準（PER）の差なのかを分けるため、PERで層別しても見る。

  python experiments/ai_signal/score2.py
"""
import csv
import os
import statistics
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
ORDER = ["拠点数", "人員数", "契約積み上げ", "その他"]


def load(name, key):
    with open(os.path.join(BASE, name), encoding="utf-8", newline="") as f:
        return {r[key]: r for r in csv.DictReader(f, delimiter="\t")}


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def table(groups, title):
    print(f"\n{title}")
    print(f"{'ラベル':12s}{'社数':>5s}{'中央値':>9s}{'平均':>9s}{'2倍以上':>8s}{'3倍以上':>8s}")
    for label in ORDER:
        values = groups.get(label) or []
        if not values:
            continue
        over2 = sum(1 for v in values if v >= 2) / len(values) * 100
        over3 = sum(1 for v in values if v >= 3) / len(values) * 100
        print(f"{label:12s}{len(values):>5d}{statistics.median(values):>9.2f}"
              f"{statistics.mean(values):>9.2f}{over2:>7.0f}%{over3:>7.0f}%")


def main():
    answers = load("answers2.tsv", "ID")
    labels = load("labels2.tsv", "ID")

    rows = []
    for qid, label in labels.items():
        answer = answers.get(qid)
        if not answer:
            continue
        rows.append({
            "id": qid, "name": answer.get("企業名", ""),
            "driver": label["成長ドライバー"],
            "peak": number(answer.get("最大何倍株")),
            "now": number(answer.get("現在何倍株")),
            "per": number(answer.get("PER")),
        })

    print(f"照合できた社数: {len(rows)}")
    counts = defaultdict(int)
    for r in rows:
        counts[r["driver"]] += 1
    print("ラベルの内訳:", {k: counts[k] for k in ORDER})

    for key, name in (("now", "現在何倍株"), ("peak", "最大何倍株")):
        groups = defaultdict(list)
        for r in rows:
            if r[key] is not None:
                groups[r["driver"]].append(r[key])
        table(groups, f"=== {name} ===")

    # 上場時のPERで層別する。SaaSは高い評価で上場しがちで、
    # その後の下落が事業モデルの差に見えてしまう
    print("\n=== 上場時PERで層別（現在何倍株の中央値）===")
    bands = [("20倍以下", 0, 20), ("20〜40倍", 20, 40), ("40倍超", 40, 10 ** 9)]
    header = f"{'ラベル':12s}" + "".join(f"{b[0]:>12s}" for b in bands)
    print(header)
    for label in ORDER:
        cells = []
        for _, low, high in bands:
            values = [r["now"] for r in rows
                      if r["driver"] == label and r["now"] is not None
                      and r["per"] is not None and low < r["per"] <= high]
            cells.append(f"{statistics.median(values):.2f}({len(values)})"
                         if values else "-")
        print(f"{label:12s}" + "".join(f"{c:>12s}" for c in cells))

    no_per = sum(1 for r in rows if r["per"] is None)
    print(f"（PER不明 {no_per}社は層別から除外）")

    # ラベルを無視して、上場時PERだけで分けるとどうなるか
    print("\n=== 上場時PERだけで分けた場合（現在何倍株）===")
    print(f"{'PER帯':12s}{'社数':>5s}{'中央値':>9s}{'2倍以上':>8s}{'3倍以上':>8s}")
    for name, low, high in bands:
        values = [r["now"] for r in rows if r["now"] is not None
                  and r["per"] is not None and low < r["per"] <= high]
        if not values:
            continue
        over2 = sum(1 for v in values if v >= 2) / len(values) * 100
        over3 = sum(1 for v in values if v >= 3) / len(values) * 100
        print(f"{name:12s}{len(values):>5d}{statistics.median(values):>9.2f}"
              f"{over2:>7.0f}%{over3:>7.0f}%")

    print("\n=== 現在何倍株の上位10社 ===")
    for r in sorted([r for r in rows if r["now"] is not None],
                    key=lambda x: -x["now"])[:10]:
        print(f"  {r['name'][:22]:24s} {r['now']:6.1f}倍  （{r['driver']}）")


if __name__ == "__main__":
    main()
