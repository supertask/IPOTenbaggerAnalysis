"""AIが書いた開示の要約を、元のPDFと突き合わせて検算する。

**目で見るだけでは改善したか分からない。** プロンプトを直すたびに同じ物差しで
測れるように、機械でできる検査をまとめてある。

    python collectors/disclosure_ai_check.py --codes 7115
    python collectors/disclosure_ai_check.py --limit 50 --show 5

## 何を見るか

| 検査 | なぜ |
|---|---|
| **要約の数字が本文にあるか** | いちばん怖いのは数字のでっち上げ。実際に配当37円を74円と書いた例があった（コンテキスト不足で本文が切れていた） |
| 長さ | 画面の狭い欄に並べるので、長いと一覧が読めない |
| 判定が4つのどれか | 表記ゆれ（「ポジティブ」など）が混ざると画面のバッジが出ない |
| 決算短信で「判断できない」 | 前年同期比が必ず載っているので、これを選ぶのは読めていない証拠 |
| 推測の言い回し | 「可能性がある」「とみられる」は本文に無いことを書いている合図 |

**数字の照合は「本文に出てくるか」だけを見る。** 意味が合っているかまでは
機械では見られないので、そこは `--show` で人が読む。
"""
import argparse
import csv
import io
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors import disclosure_pdf  # noqa: E402

TSV = os.path.join("data", "meta", "disclosure_reading.tsv")
JUDGMENTS = ("好材料", "悪材料", "中立", "判断できない")
MAX_LEN = 130

# 本文に無いことを書いている合図。開示は事実の記載なので、
# 書き手が推し量った言い方が出てきたら、そこは本文に無い
GUESS = re.compile(r"(可能性がある|とみられる|と思われる|だろう|かもしれない|"
                   r"期待される|懸念される|示唆|恐れがある)")

# 数字の拾い方。桁区切りと小数、単位までを1つとして取る
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def normalize(text: str) -> str:
    """全角と半角、桁区切りの有無を吸収して突き合わせる"""
    table = str.maketrans("０１２３４５６７８９，．％（）",
                          "0123456789,.%()")
    return text.translate(table).replace(",", "").replace(" ", "").replace("　", "")


def numbers(text: str):
    return [n.replace(",", "") for n in NUMBER.findall(normalize(text))]


def _same_after_scaling(value: str, flat: str) -> bool:
    """単位を変えただけの数字を、本文にあるとみなす。

    開示は百万円、要約は億円で書くことがある。文字列の一致だけを見ると
    正しい変換を誤りと数えてしまい、**本当の誤りが埋もれる**。
    """
    try:
        num = float(value)
    except ValueError:
        return False
    for factor in (100, 1000, 10000, 0.01, 0.001, 0.0001):
        scaled = num * factor
        for text in ({f"{scaled:.0f}"} if scaled == int(scaled) else
                     {f"{scaled:.1f}", f"{scaled:.2f}"}):
            if len(text) >= 2 and text in flat:
                return True
    return False


def check_row(row, body: str):
    """1件を検査して、見つかった問題を返す"""
    problems = []
    summary = (row.get("要約") or "").strip()
    judge = (row.get("株主にとって") or "").strip()
    title = row.get("タイトル") or ""

    if not summary:
        return ["要約が空"]
    if len(summary) > MAX_LEN:
        problems.append(f"長すぎる（{len(summary)}字）")
    if judge and judge not in JUDGMENTS:
        problems.append(f"判定が想定外（{judge}）")
    if GUESS.search(summary):
        problems.append(f"推測の言い回し（{GUESS.search(summary).group(0)}）")
    if "決算短信" in title and judge == "判断できない":
        problems.append("決算短信なのに判断できない")

    # **本文が取れないときは数字を照合しない。** 照合できないだけで、
    # 要約が間違っているわけではない。混ぜると改善の効果が測れなくなる
    if not body or len(body.strip()) < 200:
        problems.append("本文を取れず（照合できない）")
        return problems

    flat = normalize(body)
    # 1桁の数字は本文のどこにでもあるので照合しない。誤検知が増えるだけ。
    # **単位を変えた書き方も本文にあるとみなす** — 「816百万円」を
    # 「8.16億円」と書くのは正しい変換で、誤りではない
    missing = []
    for n in numbers(summary):
        if len(n) < 2 or n in flat:
            continue
        if _same_after_scaling(n, flat):
            continue
        missing.append(n)
    if missing:
        problems.append(f"本文に無い数字: {', '.join(missing[:5])}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--codes", nargs="+")
    parser.add_argument("--limit", type=int, default=0,
                        help="新しい順に何件見るか（0で全部）")
    parser.add_argument("--show", type=int, default=3,
                        help="問題のあったものを何件、本文つきで出すか")
    parser.add_argument("--since", help="この作成日以降のものだけ（例 2026-08-15）")
    args = parser.parse_args()

    with io.open(TSV, encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f, delimiter="\t") if r.get("要約")]
    if args.codes:
        rows = [r for r in rows if r["銘柄コード"] in set(args.codes)]
    if args.since:
        rows = [r for r in rows if (r.get("作成日") or "") >= args.since]
    rows.sort(key=lambda r: r["開示日"], reverse=True)
    if args.limit:
        rows = rows[:args.limit]

    print(f"検査 {len(rows)}件\n")
    found = []
    lengths = []
    judges = Counter()
    for row in rows:
        body = disclosure_pdf.fetch(row["URL"]) or ""
        problems = check_row(row, body)
        lengths.append(len(row["要約"]))
        judges[row.get("株主にとって") or "（空）"] += 1
        if problems:
            found.append((row, problems))

    kinds = Counter(p.split("（")[0].split(":")[0] for _, ps in found for p in ps)
    ok = len(rows) - len(found)
    print(f"問題なし {ok}/{len(rows)}（{ok / max(len(rows), 1) * 100:.0f}%）")
    print(f"要約の長さ 平均{sum(lengths) / max(len(lengths), 1):.0f}字 "
          f"最大{max(lengths) if lengths else 0}字")
    print(f"判定の内訳: {dict(judges)}")
    if kinds:
        print("\n問題の種類:")
        for k, n in kinds.most_common():
            print(f"  {n:>4}  {k}")

    for row, problems in found[:args.show]:
        print(f"\n--- {row['銘柄コード']} {row['開示日']} {row['タイトル'][:34]}")
        print(f"    問題: {' / '.join(problems)}")
        print(f"    要約: {row['要約']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
