"""保有銘柄の適時開示から、判定を見直すべきものを拾う。

総括に書いた「降りる条件」が起きていないかを確かめるための道具。
決算短信は毎期出るので数だけ見ても意味がなく、業績予想の修正・大株主の異動・
減損・訴訟といった、判断が変わりうる開示だけを拾う。

  python collectors/disclosure_check.py            # 保有銘柄すべて
  python collectors/disclosure_check.py 212A 160A  # 銘柄を指定
  python collectors/disclosure_check.py --months 6 # 直近6か月だけ
"""
import argparse
import csv
import glob
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.holding_profile_dump import portfolio_codes

TDNET_GLOB = os.path.join("data", "output", "tdnet", "*.tsv")

# 判断が変わりうる開示。決算短信そのものは毎期出るので入れない
IMPORTANT = [
    ("業績予想の修正", ("業績予想の修正", "業績予想の上方修正", "業績予想の下方修正",
                        "通期業績予想", "業績予想と実績値との差異")),
    ("配当", ("配当予想の修正", "増配", "減配", "無配")),
    ("大株主の異動", ("主要株主", "筆頭株主", "大株主の異動", "株式の売出し",
                      "第三者割当", "自己株式")),
    ("組織・資本", ("株式分割", "公募増資", "新株予約権", "資本業務提携",
                    "株式取得", "子会社化", "合併", "会社分割", "事業譲渡", "MBO", "TOB")),
    ("悪材料", ("減損", "特別損失", "訴訟", "課徴金", "行政処分", "不適切",
                "訂正", "上場廃止", "監理銘柄", "債務超過", "継続企業")),
    ("役員の異動", ("代表取締役の異動", "役員の異動", "社長交代")),
]


def load(codes: set) -> dict:
    rows = defaultdict(list)
    for path in glob.glob(TDNET_GLOB):
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.reader(f, delimiter="\t"):
                if len(row) >= 5 and row[3] in codes:
                    rows[row[3]].append((row[0], row[2], row[4]))
    return rows


def classify(title: str):
    for label, words in IMPORTANT:
        if any(word in title for word in words):
            return label
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("codes", nargs="*")
    parser.add_argument("--months", type=int, default=12,
                        help="さかのぼる月数（既定12）")
    args = parser.parse_args()

    codes = args.codes or portfolio_codes()
    since = (datetime.now() - timedelta(days=args.months * 31)).strftime("%Y-%m-%d")
    data = load(set(codes))

    print(f"{since} 以降の、判断が変わりうる開示\n")
    for code in codes:
        items = [r for r in data.get(code, []) if r[0] >= since]
        if not items:
            state = "開示なし" if code not in data else "この期間の開示なし"
            print(f"■ {code}  {state}")
            continue
        name = items[0][1]
        hits = [(d, classify(t), t) for d, _, t in items if classify(t)]
        print(f"■ {code} {name}  期間内 {len(items)}件 / うち要確認 {len(hits)}件")
        for date, label, title in sorted(hits, reverse=True)[:8]:
            print(f"    {date} [{label}] {title[:64]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
