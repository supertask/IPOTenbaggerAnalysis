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

# 拾った数値の常識的な範囲。1〜2は文章の綾で出やすく、数万は市場規模の話
MIN_COUNT, MAX_COUNT = 3, 20000

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


def _candidates(text: str):
    """(数値, 単位) の候補を返す"""
    body = re.sub(r"<[^>]+>", " ", text).replace("&#160;", " ")
    out = []
    for raw, unit in COUNT_RE.findall(body):
        try:
            value = int(raw.replace(",", ""))
        except ValueError:
            continue
        if MIN_COUNT <= value <= MAX_COUNT:
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
    if not os.path.exists(DB_PATH):
        print(f"インデックスが見つかりません: {DB_PATH}", file=sys.stderr)
        print("先に python -m visualizer.build_index を実行してください", file=sys.stderr)
        return 1

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    reports = list(conn.execute(
        """SELECT company_code, report_date, file_path FROM report_files
           WHERE report_type = 'annual' ORDER BY company_code, report_date"""))
    print(f"有価証券報告書 {len(reports)}件を調べます", file=sys.stderr)

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

    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["コード", "報告日", "拠点数", "単位", "出所", "他の候補"],
            delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    companies = {r["コード"] for r in rows}
    total_companies = {r["company_code"] for r in reports}
    units = Counter(r["単位"] for r in rows)
    print(f"\n抽出 {len(rows)}件 / {len(companies)}社"
          f"（有報がある{len(total_companies)}社中 "
          f"{len(companies) / max(len(total_companies), 1) * 100:.0f}%）", file=sys.stderr)
    print("単位の内訳:", dict(units.most_common(8)), file=sys.stderr)
    print(f"出力: {OUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
