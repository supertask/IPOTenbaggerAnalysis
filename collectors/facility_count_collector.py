"""有価証券報告書の本文から、店舗数・拠点数を年ごとに取り出す。

店舗数は標準化された開示項目ではないため、XBRLにタグ付けされた要素が無い
（NumberOfStores のような要素は存在しない）。本文中に「○○店舗を展開」と
書かれるだけなので、複数のセクションを横断して拾う。

拾える場所は企業によって違う。事業の内容に書く会社もあれば、経営者による
分析（MD&A）にしか書かない会社もある。1箇所に絞ると取りこぼすので全部見る。

    python -m collectors.facility_count_collector

出力: data/output/facilities/facility_counts.tsv
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "output", "index", "visualizer.db")
OUT_DIR = os.path.join(BASE_DIR, "data", "output", "facilities")
OUT_PATH = os.path.join(OUT_DIR, "facility_counts.tsv")
# 期中の報告書から拾ったぶん。有報より新しい拠点数が分かるが、期中の売上・利益は
# 半期ぶんなので、1拠点あたりの計算には混ぜられない。ファイルを分けて持つ
INTERIM_PATH = os.path.join(OUT_DIR, "facility_counts_interim.tsv")

# 拾いに行くセクション。前に置いたものほど信頼して使う
SOURCE_BLOCKS = [
    ("DescriptionOfBusinessTextBlock", "事業の内容"),
    ("ManagementAnalysisOfFinancialPositionOperatingResultsAndCashFlowsTextBlock", "MD&A"),
    ("BusinessResultsOfGroupTextBlock", "業績等の概要"),
    ("BusinessPolicyBusinessEnvironmentIssuesToAddressEtcTextBlock", "経営方針"),
]

# 「1拠点あたりの採算」が意味を持つのは、拠点を増やすことが成長の形に
# なっている業態に限られる。工場・倉庫・支店・営業所は数えられはするが
# 採算の単位ではないので入れない（拠点を工場数で割ると実態から外れる）。
# 病院も外した。医療情報の会社が「顧客の705病院」を自社の拠点として
# 拾ってしまうため。
UNITS = ("店舗", "拠点", "事業所", "施設", "ホーム", "教室", "サロン",
         "センター", "校", "店",
         "ホテル", "保育園", "園", "クリニック", "医院", "診療所",
         "ジム", "スタジオ")
# 長いものを先に並べる。「店」が先にあると「店舗」が拾えない
_UNIT_RE = "|".join(sorted(UNITS, key=len, reverse=True))
COUNT_RE = re.compile(rf"([0-9][0-9,]{{0,6}})\s*(?:の|)({_UNIT_RE})")

# 拠点ではないが、積み上がることが成長の形になっている単位。
# サブリースの管理戸数、車両の管理台数など。**言い回しごとでしか拾わない。**
# 「戸」「台」「件」だけで拾うと誤検出が多い（実際に試すと、319Aの
# 「持ち込まれたM&A案件は累計2,398件」＝収益の単位ではない、350Aの
# 「最終保障供給契約の契約件数45,871件」＝電力制度全体の数、9388の
# 「21,400名古屋営業所」＝面積のあとに地名、を拾ってしまった）
STOCK_RE = re.compile(
    r"(?:総|)(?:管理|受託|稼働|マスターリース|サブリース)"
    r"(?:台数|戸数|室数)(?:（[^）]{0,14}）)?[^0-9]{0,12}?"
    r"([0-9][0-9,]{2,8})\s*(台|戸|室)")
# 台数・戸数は拠点より桁が大きい。上限は別に持つ。
# 下限を1,000にしているのは、小さい数だと本業の単位ではないものを拾うため
# （日本駐車場開発の2018年の「115台」がそれで、本業は時間貸駐車場の区画数）
MIN_STOCK, MAX_STOCK = 1000, 2000000

# 拾った数値の常識的な範囲。1〜2は文章の綾で出やすく、数万は市場規模の話
MIN_COUNT, MAX_COUNT = 3, 20000

# 自社の拠点ではない数字を落とすための手がかり。有報の本文には
#
#   「ＣＳセット導入施設数は…2,830施設となりました」（＝取引先の医療機関）
#   「全国の訪問看護ステーション数は…約18,000事業所へ」（＝市場規模）
#   「Skip Cartの…導入店舗数は258店舗」（＝自社製品の導入先、社外を含む）
#
# のように、同じ「○○店舗」の形で他社の数が出てくる。数だけ見ていると
# これを自社の拠点として拾い、1拠点あたりの利益が桁違いに小さくなる。
NEGATIVE_CONTEXT = ("導入", "提携", "取引先", "掲載", "全国の", "市場",
                    "業界", "顧客", "関わる", "契約先", "加盟企業")

# 総数ではなく動いたぶんの数。これらは必ず数値の手前に来るので前しか見ない。
# 「2026年3月末で95拠点であり、今後も積極的な新規拠点展開を」のように、
# 総数のあとに出てくることがあり、後ろまで見ると正しい値まで落ちる
NEGATIVE_BEFORE = ("新規", "新設", "開設", "純増", "譲り受け", "改装")
# 数値の前後どれだけを見るか
CONTEXT_BEFORE, CONTEXT_AFTER = 45, 15

# 直後に増減や開設が来るものは、動いたぶんであって総数ではない。
#   「前年同期比18拠点増」「ホスピス施設11施設を新規開設したことによる」
# 距離を切るのは、総数のあとに続くだけの文と区別するため。
#   「95拠点であり、今後も積極的な新規拠点展開を予定しています」は総数
DELTA_AFTER = re.compile(r"^[^。]{0,8}?(?:[増減]|新規|開設)")

# 直前にこれがあれば総数とみなし、上の打ち消しより優先する。
# 「新規出店12店舗（閉店1店舗）を実施し、当連結会計年度末の店舗数は73店舗」の
# ように、総数の直前に新規出店の話が来ることがあるため
POSITIVE_BEFORE = ("店舗数", "拠点数", "施設数", "事業所数", "教室数", "校数",
                   "合計", "総数", "末時点", "末現在", "運営し")
NEAR_BEFORE, NEAR_AFTER = 18, 8

ENCODINGS = ("utf-16", "utf-16-le", "utf-8-sig", "utf-8", "cp932")


def _read(path: str):
    for enc in ENCODINGS:
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
        except OSError:
            return None
    return None


def _stock_candidates(text: str):
    """管理台数・管理戸数などの (数値, 単位)。言い回しごとで拾う"""
    body = re.sub(r"<[^>]+>", " ", text).replace("&#160;", " ")
    body = re.sub(r"[ \t　]+", " ", body)
    out = []
    for match in STOCK_RE.finditer(body):
        try:
            value = int(match.group(1).replace(",", ""))
        except ValueError:
            continue
        if not (MIN_STOCK <= value <= MAX_STOCK):
            continue
        # 「前年同期比2,130戸増」のように動いたぶんは採らない
        head = body[max(0, match.start() - 12):match.start()]
        if any(word in head for word in ("前年", "前期", "比")):
            continue
        out.append((value, match.group(2)))
    return out


def _candidates(text: str):
    """(数値, 単位) の候補を返す。自社の拠点でなさそうな出現は落とす"""
    body = re.sub(r"<[^>]+>", " ", text).replace("&#160;", " ")
    body = re.sub(r"[ \t　]+", " ", body)
    out = []
    for match in COUNT_RE.finditer(body):
        raw, unit = match.group(1), match.group(2)
        try:
            value = int(raw.replace(",", ""))
        except ValueError:
            continue
        if not (MIN_COUNT <= value <= MAX_COUNT):
            continue
        # 「約18,000事業所」のように概数で書かれるのは市場規模の話。
        # 自社の拠点数は期末時点の実数なので概数にはならない
        head = body[:match.start()].rstrip()
        if head.endswith(("約", "計約")):
            continue
        # 「前年同期比18拠点増」は増えたぶんの数
        if DELTA_AFTER.match(body[match.end():match.end() + NEAR_AFTER]):
            continue
        near_before = body[max(0, match.start() - NEAR_BEFORE):match.start()]
        # すぐ手前に打ち消しがあるものは、総数の言い回しでも自社の数ではない。
        # 「導入も含む導入店舗数は258店舗」は「店舗数は」が付いていても
        # 自社の店舗ではなく、自社製品を入れた他社の店舗
        if any(word in near_before for word in NEGATIVE_CONTEXT + NEGATIVE_BEFORE):
            continue
        if not any(word in near_before for word in POSITIVE_BEFORE):
            before = body[max(0, match.start() - CONTEXT_BEFORE):match.start()]
            after = body[match.end():match.end() + CONTEXT_AFTER]
            if any(word in before for word in NEGATIVE_BEFORE):
                continue
            if any(word in before + after for word in NEGATIVE_CONTEXT):
                continue
        out.append((value, unit))
    return out


def extract_from_report(path: str):
    """1つの有報から拠点数を1つ決める。決められなければ None

    複数のセクションに同じ数字が出てくるほど確からしいので、
    「何箇所に出たか」を優先し、次に数値の大きさで選ぶ。
    グループ全体の店舗数が最大値になることが多いため。
    """
    text = _read(path)
    if not text:
        return None

    blocks = {}
    for line in text.splitlines():
        parts = line.split("\t")
        element = parts[0].strip('"')
        for key, label in SOURCE_BLOCKS:
            if element.endswith(key) and label not in blocks:
                blocks[label] = parts[-1]

    if not blocks:
        return None

    # 管理台数・管理戸数が書いてあれば、そちらを拠点より優先する。
    # 「管理戸数は27,354戸」と書く会社は、それが積み上がる単位だと
    # 自分で言っている。3300は賃貸仲介の17店舗で割るより、
    # サブリースの管理戸数で割るほうが型に合う
    stock = defaultdict(set)
    for label, raw in blocks.items():
        for value, unit in _stock_candidates(raw):
            stock[(value, unit)].add(label)
    if stock:
        (value, unit), labels = max(
            stock.items(), key=lambda kv: (len(kv[1]), kv[0][0]))
        return {
            "count": value,
            "unit": unit,
            "sources": "/".join(sorted(labels)),
            "candidates": ",".join(
                str(v) for v in sorted({v for (v, _u) in stock}, reverse=True)[:5]),
        }

    seen = defaultdict(set)      # (値, 単位) -> それが出たセクション
    for label, raw in blocks.items():
        for value, unit in _candidates(raw):
            seen[(value, unit)].add(label)

    if not seen:
        return None

    (value, unit), labels = max(
        seen.items(), key=lambda kv: (len(kv[1]), kv[0][0]))
    others = sorted({v for (v, _u) in seen}, reverse=True)[:5]
    return {
        "count": value,
        "unit": unit,
        "sources": "/".join(sorted(labels)),
        "candidates": ",".join(str(v) for v in others),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interim", action="store_true",
                        help="有報ではなく期中の報告書（四半期・半期）から拾う")
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"インデックスが見つかりません: {DB_PATH}", file=sys.stderr)
        print("先に python -m visualizer.build_index を実行してください", file=sys.stderr)
        return 1

    report_type = "quarterly" if args.interim else "annual"
    out_path = INTERIM_PATH if args.interim else OUT_PATH

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    reports = list(conn.execute(
        """SELECT company_code, report_date, file_path FROM report_files
           WHERE report_type = ? ORDER BY company_code, report_date""",
        (report_type,)))
    label = "期中の報告書" if args.interim else "有価証券報告書"
    print(f"{label} {len(reports)}件を調べます", file=sys.stderr)

    os.makedirs(OUT_DIR, exist_ok=True)
    rows = []
    started = time.time()
    for index, report in enumerate(reports, 1):
        result = extract_from_report(report["file_path"])
        if result:
            rows.append({
                "コード": report["company_code"],
                "報告日": report["report_date"],
                "拠点数": result["count"],
                "単位": result["unit"],
                "出所": result["sources"],
                "他の候補": result["candidates"],
            })
        if index % 2000 == 0:
            elapsed = time.time() - started
            print(f"  {index}/{len(reports)}件 ({index / elapsed:.0f}件/秒) "
                  f"抽出 {len(rows)}件", file=sys.stderr)

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["コード", "報告日", "拠点数", "単位", "出所", "他の候補"],
            delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    companies = {r["コード"] for r in rows}
    total_companies = {r["company_code"] for r in reports}
    units = Counter(r["単位"] for r in rows)
    print(f"\n抽出 {len(rows)}件 / {len(companies)}社"
          f"（{label}がある{len(total_companies)}社中 "
          f"{len(companies) / max(len(total_companies), 1) * 100:.0f}%）", file=sys.stderr)
    print("単位の内訳:", dict(units.most_common(8)), file=sys.stderr)
    print(f"出力: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
