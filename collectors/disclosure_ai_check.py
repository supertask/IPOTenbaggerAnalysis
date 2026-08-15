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

# 数字の拾い方。桁区切りと小数を1つとして取る。
# **「5億6,758万円」のような書き方を分解しない。** 分解すると
# 167 と 6758 という存在しない数字を照合してしまい、正しい要約を誤りと数える
NUMBER = re.compile(
    r"\d[\d,]*(?:\.\d+)?"           # 先頭の数
    r"(?:[兆億万]\d[\d,]*)*"          # 「億6758」「万3000」が続くぶん
    r"[兆億万]?")                     # 「5億」で終わる形
_UNITS = (("兆", 10 ** 12), ("億", 10 ** 8), ("万", 10 ** 4))


def normalize(text: str) -> str:
    """全角と半角、桁区切りの有無を吸収して突き合わせる"""
    table = str.maketrans("０１２３４５６７８９，．％（）",
                          "0123456789,.%()")
    return text.translate(table).replace(",", "").replace(" ", "").replace("　", "")


def numbers(text: str):
    """要約に出てくる数字。**漢数字の単位をまたぐものは1つの値にまとめる**。

    「5億6,758万円」は 5×10^8 + 6758×10^4 = 567,580,000。
    分解して 5 と 6758 として照合すると、正しい要約を誤りと数えてしまう。
    """
    out = []
    for raw in NUMBER.findall(normalize(text)):
        token = raw.replace(",", "")
        if not any(u in token for u in ("兆", "億", "万")):
            out.append(token)
            continue
        total = 0.0
        rest = token
        for unit, scale in _UNITS:
            if unit not in rest:
                continue
            head, rest = rest.split(unit, 1)
            try:
                total += float(head) * scale
            except ValueError:
                pass
        if rest:
            try:
                total += float(rest)
            except ValueError:
                pass
        out.append(f"{total:.0f}")
    return out


# 「1兆円」「500億円」のような概数は、数値に直すと本文と一致しない。
# **本文に同じ書き方があるかも見る**（normalize後の生の文字列で照合）
_ROUND = re.compile(r"\d+(?:\.\d+)?[兆億万]")


def _written_as_is(summary: str, flat: str) -> set:
    """「1兆」「3,800億」のような書き方が本文にそのままあるか"""
    return {m for m in _ROUND.findall(normalize(summary)) if m in flat}


def _same_after_scaling(value: str, flat: str) -> bool:
    """単位を変えただけの数字を、本文にあるとみなす。

    開示は百万円、要約は億円で書くことがある。文字列の一致だけを見ると
    正しい変換を誤りと数えてしまい、**本当の誤りが埋もれる**。
    """
    try:
        num = float(value)
    except ValueError:
        return False
    # 開示は千円・百万円、要約は万円・億円で書く。**円と万円は10,000倍、
    # 円と億円は100,000,000倍**離れていて、100倍や1000倍だけでは届かない。
    # 実際に「5,539万円」を本文の「55,390,000円」と照合できていなかった
    factors = (100, 1000, 10_000, 100_000, 1_000_000, 10_000_000, 100_000_000,
               0.01, 0.001, 0.0001, 0.00001, 0.000001, 0.0000001, 0.00000001)
    for factor in factors:
        scaled = num * factor
        if scaled < 1:
            continue
        texts = {f"{scaled:.0f}"}
        if scaled != int(scaled):
            texts |= {f"{scaled:.1f}", f"{scaled:.2f}"}
        for text in texts:
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
    # 「1兆円」のような概数が本文にそのまま書かれていれば、数値化した値は
    # 一致しなくてよい。**書き方をそのまま写しているので誤りではない**
    as_is = _written_as_is(summary, flat)
    missing = []
    for n in numbers(summary):
        if len(n) < 2 or n in flat:
            continue
        if _same_after_scaling(n, flat):
            continue
        if as_is and float(n or 0) >= 10 ** 8:
            continue    # 兆・億の概数はここで許す
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
