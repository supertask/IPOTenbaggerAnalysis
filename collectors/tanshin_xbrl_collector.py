"""決算短信サマリーのiXBRLを落として、数字をTSVに開く。

**狙いは会社自身の予想。** 有報のXBRLには実績しか無いので、
「会社が来期をどう見ているか」がこれまでどこにも無かった。決算短信の
サマリーには来期予想が売上・営業利益・経常利益・純利益・EPS・配当まで
タグ付きで入っていて、上方修正・下方修正もここで追える。

URLは `collectors/tdnet_disclosure_scraper.py` が
`data/output/tanshin/index.tsv` に貯めている。PDFのURLからは導けないので
（拡張子を .zip に変えても404）、東証のページで拾うしかない。

    python collectors/tanshin_xbrl_collector.py            # 保有銘柄ぜんぶ
    python collectors/tanshin_xbrl_collector.py --codes 5592

**取れる範囲は東証のページに並んでいるぶんだけ。** 上場が古い会社ほど多く、
6099は43件、上場して間もない5592は11件だった。「さらに表示」を押せなかった
銘柄は1ページ目で止まるので、`--refresh` で流し直すと増えることがある。
"""
import argparse
import csv
import glob
import os
import re
import sys
import time
from decimal import Decimal, InvalidOperation

import requests

INDEX_PATH = "data/output/tanshin/index.tsv"
FACTS_DIR = "data/output/tanshin/facts"
BASE = "https://www2.jpx.co.jp"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"}

# **自己終了タグ（`<ix:nonFraction ... />`）を別に扱う。** 値が無い項目は
# xsi:nil で自己終了して書かれる。開始と終了が対になる前提で書くと、
# 自己終了タグが次の項目の終了タグと対になり、**あいだの項目が丸ごと消える。**
# 212Aの決算短信では、これで来期予想の売上・営業利益が1件も取れていなかった
FACT_RE = re.compile(
    r"<ix:(nonFraction|nonNumeric)\b([^>]*?)(?:/>|>(.*?)</ix:\1>)", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")

# 短信サマリーの数字。実績と予想が同じタグで、区別はコンテキストが持つ
LABELS = {
    "NetSales": "売上高",
    "ChangeInNetSales": "売上高の増減率",
    "OperatingIncome": "営業利益",
    "ChangeInOperatingIncome": "営業利益の増減率",
    "OrdinaryIncome": "経常利益",
    "ChangeInOrdinaryIncome": "経常利益の増減率",
    "ProfitAttributableToOwnersOfParent": "親会社株主に帰属する当期純利益",
    "ChangeInProfitAttributableToOwnersOfParent": "親会社株主に帰属する当期純利益の増減率",
    "NetIncome": "当期純利益",
    "ChangeInNetIncome": "当期純利益の増減率",
    "ComprehensiveIncome": "包括利益",
    "ChangeInComprehensiveIncome": "包括利益の増減率",
    "NetIncomePerShare": "1株当たり当期純利益",
    "DilutedNetIncomePerShare": "潜在株式調整後1株当たり当期純利益",
    "TotalAssets": "総資産",
    "NetAssets": "純資産",
    "OwnersEquity": "自己資本",
    "CapitalAdequacyRatio": "自己資本比率",
    "NetAssetsPerShare": "1株当たり純資産",
    "CashFlowsFromOperatingActivities": "営業キャッシュフロー",
    "CashFlowsFromInvestingActivities": "投資キャッシュフロー",
    "CashFlowsFromFinancingActivities": "財務キャッシュフロー",
    "CashAndEquivalentsEndOfPeriod": "現金及び現金同等物の期末残高",
    "DividendPerShare": "1株当たり配当金",
    "PayoutRatio": "配当性向",
    "TotalDividendPaidAnnual": "配当金総額",
    "RatioOfTotalAmountOfDividendsToNetAssets": "純資産配当率",
    "NetIncomeToShareholdersEquityRatio": "自己資本当期純利益率(ROE)",
    "OrdinaryIncomeToTotalAssetsRatio": "総資産経常利益率(ROA)",
    "OperatingIncomeToNetSalesRatio": "売上高営業利益率",
    "InvestmentProfitLossOnEquityMethod": "持分法投資損益",
    "AverageNumberOfShares": "期中平均株式数",
    "NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock":
        "期末発行済株式数(自己株式を含む)",
    "NumberOfTreasuryStockAtTheEndOfFiscalYear": "期末自己株式数",
    "NumberOfSubsidiariesNewlyConsolidated": "新規連結子会社数",
    "NumberOfSubsidiariesExcludedFromConsolidation": "除外子会社数",
    "CompanyName": "会社名",
    "SecuritiesCode": "証券コード",
    "DocumentName": "書類名",
    "FilingDate": "提出日",
    "FiscalYearEnd": "決算期末",
    "QuarterlyPeriod": "四半期",
    "NameRepresentative": "代表者名",
    "TitleRepresentative": "代表者の役職",
    "URL": "URL",
    "TitleForForecasts": "業績予想の見出し",
    "NoteToForecasts": "業績予想の注記",
    "NotesForUsingForecastedInformationAndOthers": "将来情報の利用に関する注意",
    "NoteToOperatingResults": "経営成績の注記",
    "NoteToFinancialResults": "業績の注記",
    "NoteToDividends": "配当の注記",
    "CorrectionOfConsolidatedFinancialForecastInThisQuarter": "当四半期における業績予想の修正",
    "CorrectionOfDividendForecastInThisQuarter": "当四半期における配当予想の修正",
    "SignificantChangesInTheScopeOfConsolidationDuringThePeriod": "期中の連結範囲の重要な変更",
    "NameOfSubsidiariesNewlyConsolidated": "新規連結子会社の名称",
    "NameOfSubsidiariesExcludedFromConsolidation": "除外子会社の名称",
    "ChangesBasedOnRevisionsOfAccountingStandard": "会計基準等の改正に伴う変更",
    "ChangesOtherThanOnesBasedOnRevisionsOfAccountingStandard": "それ以外の会計方針の変更",
    "ChangesInAccountingEstimates": "会計上の見積りの変更",
    "RetrospectiveRestatement": "修正再表示",
    # IFRSの会社は別のタグを使う。**経常利益が無く、税引前利益になる。**
    # 保有銘柄では3774・6574・9158がこちら
    "SalesIFRS": "売上収益（IFRS）",
    "ChangeInSalesIFRS": "売上収益の増減率（IFRS）",
    "OperatingIncomeIFRS": "営業利益（IFRS）",
    "ChangeInOperatingIncomeIFRS": "営業利益の増減率（IFRS）",
    "ProfitBeforeTaxIFRS": "税引前利益（IFRS）",
    "ChangeInProfitBeforeTaxIFRS": "税引前利益の増減率（IFRS）",
    "ProfitIFRS": "当期利益（IFRS）",
    "ChangeInProfitIFRS": "当期利益の増減率（IFRS）",
    "ProfitAttributableToOwnersOfParentIFRS": "親会社の所有者に帰属する当期利益（IFRS）",
    "ChangeInProfitAttributableToOwnersOfParentIFRS":
        "親会社の所有者に帰属する当期利益の増減率（IFRS）",
    "ComprehensiveIncomeIFRS": "当期包括利益（IFRS）",
    "ChangeInComprehensiveIncomeIFRS": "当期包括利益の増減率（IFRS）",
    "BasicEarningsPerShareIFRS": "基本的1株当たり当期利益（IFRS）",
    "DilutedEarningsPerShareIFRS": "希薄化後1株当たり当期利益（IFRS）",
    "TotalAssetsIFRS": "資産合計（IFRS）",
    "EquityIFRS": "資本合計（IFRS）",
    "EquityAttributableToOwnersOfParentIFRS": "親会社の所有者に帰属する持分（IFRS）",
    "RatioOfOwnersEquityToGrossAssetsIFRS": "親会社所有者帰属持分比率（IFRS）",
    "EquityPerShareAttributableToOwnersOfParentIFRS":
        "1株当たり親会社所有者帰属持分（IFRS）",
    "RatioOfProfitToEquityAttributableToOwnersOfParentIFRS":
        "親会社所有者帰属持分当期利益率（IFRS）",
    "RatioOfProfitBeforeTaxToTotalAssetsIFRS": "資産合計税引前利益率（IFRS）",
    "RatioOfOperatingIncomeToSalesIFRS": "売上収益営業利益率（IFRS）",
}

# コンテキストIDの部品
PERIODS = {
    "CurrentYear": "当期",
    "PriorYear": "前期",
    "NextYear": "来期",
    "CurrentAccumulatedQ1": "当期第1四半期累計",
    "CurrentAccumulatedQ2": "当期第2四半期累計",
    "CurrentAccumulatedQ3": "当期第3四半期累計",
    "CurrentAccumulatedQ4": "当期第4四半期累計",
    "PriorAccumulatedQ1": "前期第1四半期累計",
    "PriorAccumulatedQ2": "前期第2四半期累計",
    "PriorAccumulatedQ3": "前期第3四半期累計",
    "PriorAccumulatedQ4": "前期第4四半期累計",
}
KINDS = {
    "ResultMember": "実績",
    "ForecastMember": "予想",
    "UpperMember": "予想の上限",
    "LowerMember": "予想の下限",
}
QUARTERS = {
    "FirstQuarterMember": "第1四半期末",
    "SecondQuarterMember": "第2四半期末",
    "ThirdQuarterMember": "第3四半期末",
    "YearEndMember": "期末",
    "AnnualMember": "合計",
}
DOC_KINDS = {"a": "年次", "q": "四半期", "s": "半期"}


def parse_context(context):
    """`NextYearDuration_ConsolidatedMember_ForecastMember` を読み解く"""
    head, _, rest = context.partition("_")
    period, moment = "", ""
    for key, label in PERIODS.items():
        if head.startswith(key):
            period = label
            moment = head[len(key):]  # Duration / Instant
            break
    members = [m for m in rest.split("_") if m]
    kind = next((KINDS[m] for m in members if m in KINDS), "")
    quarter = next((QUARTERS[m] for m in members if m in QUARTERS), "")
    if "ConsolidatedMember" in members:
        basis = "連結"
    elif "NonConsolidatedMember" in members:
        basis = "単体"
    else:
        basis = ""
    return period, moment, basis, kind, quarter


def doc_kind(url):
    """ファイル名の tse-acedjpsm / qcedjpsm / scedjpsy から年次・四半期・半期"""
    m = re.search(r"tse-([aqs])c?ed", url)
    return DOC_KINDS.get(m.group(1), "") if m else ""


def attr(blob, key):
    """開始タグの属性を1つ取る。属性名の頭を留めないと、別の属性の一部に
    当たりうる（scale と decimals のような並びで取り違える）"""
    m = re.search(r'(?:^|\s)' + key + r'="([^"]*)"', blob)
    return m.group(1) if m else ""


def parse_ixbrl(html, url):
    """iXBRLのHTMLから fact を取り出す。

    **scale を必ず掛ける。** 売上は「14,400」と scale="6" で書かれていて、
    そのまま読むと1万4千円になる。比率は scale="-2" なので 16.8 は 0.168。
    """
    kind_of_doc = doc_kind(url)
    facts = []
    for tag_kind, blob, body in FACT_RE.findall(html):
        name = attr(blob, "name")
        if not name:
            continue
        short = name.split(":")[-1]
        context = attr(blob, "contextRef")
        shown = TAG_RE.sub("", body or "").strip()
        shown = re.sub(r"\s+", " ", shown)
        if not shown or shown in ("－", "-", "―", "‐"):
            continue

        value = ""
        if tag_kind.lower() == "nonfraction":
            # **floatで掛けない。** 27.4 に 10**-2 を掛けると
            # 0.27399999999999997 になり、比率がそのまま残る
            try:
                num = Decimal(shown.replace(",", "").replace("△", "-"))
            except InvalidOperation:
                num = None
            if num is not None:
                scale = attr(blob, "scale")
                if scale:
                    num = num.scaleb(int(scale))
                if attr(blob, "sign") == "-":
                    num = -num
                value = format(num, "f")

        period, _moment, basis, result_kind, quarter = parse_context(context)
        facts.append({
            "書類": kind_of_doc,
            "期": period,
            "連単": basis,
            "区分": result_kind,
            "四半期": quarter,
            "項目名": LABELS.get(short, ""),
            "タグ": short,
            "値": value,
            "単位": attr(blob, "unitRef"),
            "表示": shown[:400],
            "コンテキスト": context,
        })
    return facts


COLUMNS = ["日付", "書類", "期", "連単", "区分", "四半期",
           "項目名", "タグ", "値", "単位", "表示", "コンテキスト", "出所"]


def read_index(codes=None):
    if not os.path.exists(INDEX_PATH):
        sys.exit(f"{INDEX_PATH} が無い。先に "
                 f"python collectors/tdnet_disclosure_scraper.py --portfolio --refresh")
    with open(INDEX_PATH, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    if codes:
        rows = [r for r in rows if r["コード"] in set(codes)]
    return rows


def existing_sources(path):
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8", newline="") as f:
        return {r["出所"] for r in csv.DictReader(f, delimiter="\t") if r.get("出所")}


def portfolio_codes():
    codes = []
    for path in sorted(glob.glob("data/output/portfolio/*.tsv")):
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        if not rows:
            continue
        key = next((k for k in rows[0] if "コード" in k), None)
        for row in rows:
            code = (row.get(key) or "").strip()
            if code and not code.startswith("(") and code not in codes:
                codes.append(code)
    return codes


def relabel(codes):
    """項目名の列を LABELS から付け直す。

    項目名はタグから決まるだけなので、**落とし直す必要はない。**
    IFRSのタグを足したときのように、対応表だけが増えた場合に使う。
    """
    for code in sorted(codes):
        path = os.path.join(FACTS_DIR, f"{code}.tsv")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        changed = 0
        for row in rows:
            name = LABELS.get(row["タグ"], "")
            if name and name != row["項目名"]:
                row["項目名"] = name
                changed += 1
        if not changed:
            continue
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, COLUMNS, delimiter="\t",
                                    lineterminator="\n", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        print(f"{code}: {changed}行の項目名を付け直した")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--codes", nargs="+", help="銘柄コードで絞る")
    parser.add_argument("--force", action="store_true",
                        help="取得済みの短信も落とし直す")
    parser.add_argument("--relabel", action="store_true",
                        help="項目名だけ LABELS から付け直す。タグから決まる列なので"
                             "落とし直さなくていい（IFRSのタグを足したときなど）")
    args = parser.parse_args()

    codes = args.codes or portfolio_codes()
    if args.relabel:
        return relabel(codes)
    rows = read_index(codes)
    by_code = {}
    for row in rows:
        by_code.setdefault(row["コード"], []).append(row)

    os.makedirs(FACTS_DIR, exist_ok=True)
    total_new = 0
    for code in sorted(by_code):
        path = os.path.join(FACTS_DIR, f"{code}.tsv")
        done = set() if args.force else existing_sources(path)
        todo = [r for r in by_code[code] if r["iXBRLのURL"] not in done]
        if not todo:
            print(f"{code}: 取得済み {len(by_code[code])}件")
            continue

        write_header = args.force or not os.path.exists(path)
        mode = "w" if args.force else "a"
        with open(path, mode, encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, COLUMNS, delimiter="\t",
                                    lineterminator="\n", extrasaction="ignore")
            if write_header:
                writer.writeheader()
            for row in sorted(todo, key=lambda r: r["日付"]):
                url = row["iXBRLのURL"]
                try:
                    res = requests.get(BASE + url, headers=HEADERS, timeout=30)
                    res.raise_for_status()
                except Exception as exc:
                    print(f"{code} {row['日付']}: 取得できず {exc}")
                    continue
                res.encoding = res.apparent_encoding
                facts = parse_ixbrl(res.text, url)
                for fact in facts:
                    fact["日付"] = row["日付"]
                    fact["出所"] = url
                    writer.writerow(fact)
                total_new += 1
                print(f"{code} {row['日付']} {row['タイトル'][:28]}: {len(facts)}件")
                time.sleep(1.2)

    print(f"\n短信 {total_new}件を追加")


if __name__ == "__main__":
    main()
