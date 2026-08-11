"""第2ラウンドの標本を作る。第1ラウンドの反省を3つ反映する。

- 銘柄コードを伏せて連番IDにする。コードが見えると有名企業を特定できてしまい、
  評価者が結果を知った状態で判定することになる
- 標本を200社に増やす（第1ラウンドは60社で、群によっては5社しかなかった）
- 第1ラウンドで使った60社は除く（答えを知ってしまっているため）

採点時に上場時PERで層別できるよう、答え側にPERも入れておく。

  python experiments/ai_signal/sample2.py
"""
import csv
import os
import random
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(BASE, "data", "output", "combiner", "all_companies.tsv")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

YEAR_FROM, YEAR_TO = 2015, 2020
SAMPLE_SIZE = 200
SEED = 20260812_2


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main():
    used = set()
    round1 = os.path.join(OUT_DIR, "questions.tsv")
    if os.path.exists(round1):
        with open(round1, encoding="utf-8", newline="") as f:
            used = {r["コード"] for r in csv.DictReader(f, delimiter="\t")}

    with open(SRC, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    pool, seen = [], set()
    for r in rows:
        code = r.get("コード")
        if code in seen or code in used:
            continue
        seen.add(code)
        year = number(r.get("上場年"))
        peak = number(r.get("最大何倍株"))
        business = (r.get("事業内容") or "").strip()
        if not (year and peak and business):
            continue
        if not (YEAR_FROM <= year <= YEAR_TO):
            continue
        pool.append({
            "コード": code, "企業名": r.get("企業名", ""),
            "業種": (r.get("業種") or "").strip(), "事業内容": business,
            "上場年": int(year), "最大何倍株": peak,
            "現在何倍株": number(r.get("現在何倍株")), "PER": number(r.get("PER")),
        })

    random.seed(SEED)
    sample = random.sample(pool, min(SAMPLE_SIZE, len(pool)))
    random.shuffle(sample)   # 業種順などの並びから推測されないようにする

    with open(os.path.join(OUT_DIR, "questions2.tsv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ID", "業種", "事業内容"], delimiter="\t")
        w.writeheader()
        for i, s in enumerate(sample, 1):
            w.writerow({"ID": f"Q{i:03d}", "業種": s["業種"], "事業内容": s["事業内容"]})

    with open(os.path.join(OUT_DIR, "answers2.tsv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["ID", "コード", "企業名", "上場年", "最大何倍株",
                           "現在何倍株", "PER"], delimiter="\t")
        w.writeheader()
        for i, s in enumerate(sample, 1):
            row = {k: s[k] for k in
                   ("コード", "企業名", "上場年", "最大何倍株", "現在何倍株", "PER")}
            row["ID"] = f"Q{i:03d}"
            w.writerow(row)

    print(f"母集団 {len(pool)}社（第1ラウンドの{len(used)}社を除外）から "
          f"{len(sample)}社を抽出", file=sys.stderr)


if __name__ == "__main__":
    main()
