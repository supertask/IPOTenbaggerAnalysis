"""AI評価が株価倍率と相関するかを試すための標本を作る。

評価する側が結果を見てしまうと判定が引きずられるので、
出題用（事業内容のみ）と答え用（倍率）を別ファイルに分ける。

  python experiments/ai_signal/sample.py

出力:
  experiments/ai_signal/questions.tsv  … 銘柄コード・業種・事業内容だけ
  experiments/ai_signal/answers.tsv    … 銘柄コードと実際の倍率
"""
import csv
import os
import random
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(BASE, "data", "output", "combiner", "all_companies.tsv")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# 上場からの経過年数が違うと倍率も変わるので、期間を揃える
YEAR_FROM, YEAR_TO = 2015, 2020
SAMPLE_SIZE = 60
SEED = 20260812


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main():
    with open(SRC, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    pool = []
    seen = set()
    for r in rows:
        # all_companies には同じ銘柄が複数行あることがある
        if r.get("コード") in seen:
            continue
        seen.add(r.get("コード"))
        year = number(r.get("上場年"))
        peak = number(r.get("最大何倍株"))
        now = number(r.get("現在何倍株"))
        business = (r.get("事業内容") or "").strip()
        if not (year and peak and business):
            continue
        if not (YEAR_FROM <= year <= YEAR_TO):
            continue
        pool.append({
            "コード": r["コード"], "企業名": r.get("企業名", ""),
            "業種": (r.get("業種") or "").strip(), "事業内容": business,
            "上場年": int(year), "最大何倍株": peak, "現在何倍株": now,
        })

    random.seed(SEED)
    sample = random.sample(pool, min(SAMPLE_SIZE, len(pool)))
    sample.sort(key=lambda x: x["コード"])

    q_path = os.path.join(OUT_DIR, "questions.tsv")
    with open(q_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["コード", "業種", "事業内容"], delimiter="\t")
        w.writeheader()
        for s in sample:
            w.writerow({k: s[k] for k in ("コード", "業種", "事業内容")})

    a_path = os.path.join(OUT_DIR, "answers.tsv")
    with open(a_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["コード", "企業名", "上場年", "最大何倍株", "現在何倍株"],
            delimiter="\t")
        w.writeheader()
        for s in sample:
            w.writerow({k: s[k] for k in
                        ("コード", "企業名", "上場年", "最大何倍株", "現在何倍株")})

    print(f"母集団 {len(pool)}社 から {len(sample)}社を抽出", file=sys.stderr)
    print(f"  出題: {q_path}", file=sys.stderr)
    print(f"  答え: {a_path}（採点まで開かない）", file=sys.stderr)


if __name__ == "__main__":
    main()
