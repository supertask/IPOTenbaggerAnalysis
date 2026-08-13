"""大量保有報告書から「誰がいつ何株売買したか」と、その理由を集める。

有報の大株主は期末の断面しか無く、期中の報告書を足しても年2回が上限。
これに対し5%以上を持つ人は、保有割合が1%動くたびに5営業日以内に
大量保有報告書（350）または変更報告書（360）を出す義務がある。
創業者・資産管理会社・VCはたいてい該当するので、こちらのほうが
はるかに粒度が細かく、しかも**理由が書いてある**。

取れるもの（XBRLのタグ、実データで確認済み）:

  jplvh_cor:ReasonForFilingChangeReportCoverPage  提出事由（1%以上の減少 など）
  jplvh_cor:PurposeOfHolding                      保有目的（純投資／長期保有／経営参画）
  jplvh_cor:TotalNumberOfStocksEtcHeld            保有株券等の総数
  jplvh_cor:HoldingRatioOfShareCertificatesEtc    保有割合
  ...EtcPerLastReport                             前回報告書の保有割合
  jplvh_cor:DateWhenFilingRequirementAroseCoverPage  提出義務発生日（実際に動いた日）

**なぜ売買したかは、次の3つに書いてある。** 保有目的は定型文なので使えないが、
こちらは1回ごとに理由が入っている。

  DetailsOfAcquisitionsAndDisposals...   最近60日間の取得又は処分の状況。
                                         日付・数量・市場内外・取得処分・単価の表
  BreakdownOfTotalAmountFromOtherSources 増減の内訳。「2024年7月23日付の新規株式
                                         上場に伴う売出しにより2,900,000株売却」
                                         のように、1件ずつ日付と理由が日本語で入る
  SignificantContractsRelatedToSaidStocks... 担保契約等重要な契約。ロックアップの
                                         期限や、銀行への担保差入れが分かる

共同保有者はコンテキストID（...FilerLargeVolumeHolder<N>Member）で1人ずつに
分かれる。共同保有者が居ない書類ではその軸が無く、素の FilingDateInstant が
その1人ぶんになる。

使い方:

  python collectors/large_holding_collector.py                 # 保有銘柄だけ
  python collectors/large_holding_collector.py --codes 212A 5592
  python collectors/large_holding_collector.py --all           # 全銘柄（一晩かかる）
  python collectors/large_holding_collector.py --index-only    # 一覧だけ作る

書類の一覧（どの日に誰が出したか）は全銘柄ぶん作っても10分ほどで、
data/output/large_holdings/doc_index.tsv に貯まる。重いのは本文の取得のほうで、
そちらは --all を付けたときだけ全銘柄に広がる（5〜6時間）。

**EDINETは大量保有報告書を5年しか置いていない。** 有報の10年より短く、
しかも境目は日が経つと前に進む。落としたTSVは5年より前の唯一の記録になるので、
再生成できるデータとして扱わないこと。
"""
import argparse
import csv
import gzip
import io
import os
import re
import sys
import time
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import List

import requests
import urllib3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.holding_profile_dump import portfolio_codes

urllib3.disable_warnings()

API = "https://api.edinet-fsa.go.jp/api/v2/documents"
OUT_DIR = os.path.join("data", "output", "large_holdings")
# 落とした素のCSV。項目を増やすたびに落とし直さなくて済むように残す
CACHE_DIR = os.path.join("data", "cache", "large_holdings")
DOC_INDEX = os.path.join(OUT_DIR, "doc_index.tsv")
# 走査済みの日。書類が1件も無い日は一覧に行が残らないので、
# これが無いと毎回その日を取り直すことになる（10年ぶんだと無視できない）
SCANNED_DAYS = os.path.join(OUT_DIR, "scanned_days.txt")
EDINET_CODES = os.path.join("data", "output", "edinet_db", "edinet_codes",
                            "EdinetcodeDlInfo.csv")

# 大量保有報告書と、その変更報告書
DOC_TYPES = ("350", "360")

# EDINETは大量保有報告書を**5年しか置いていない**（有報の10年より短い）。
# 2026-08-13時点で調べたところ、2021-09以降は取れて2021-08以前は0件だった。
# しかも境目は日が経つと動いていく。
#
#   → ここで落としたTSVが、5年より前の唯一の記録になる。消さないこと
#
# 余裕を1ヶ月見て5年1ヶ月前から走査する。それより前を走査しても空振りする
RETENTION_DAYS = 365 * 5 + 31

DOC_INDEX_COLUMNS = ["提出日", "書類種別", "銘柄コード", "発行会社EDINETコード",
                     "提出者", "書類ID"]

HOLDING_COLUMNS = ["提出日", "発生日", "書類種別", "提出者", "保有者", "株数",
                   "保有割合", "前回割合", "提出事由", "保有目的",
                   "売買明細", "増減の内訳", "重要な契約", "書類ID"]

# 1人ぶんの値を束ねるタグ。素の FilingDateInstant は共同保有者の合計。
# 要素IDの前方一致で見る（末尾に NA / TextBlock が付く版があるため）
_PER_HOLDER = {
    "jplvh_cor:FilerNameInJapaneseDEI": "保有者",
    "jplvh_cor:TotalNumberOfStocksEtcHeld": "株数",
    "jplvh_cor:HoldingRatioOfShareCertificatesEtc": "保有割合",
    "jplvh_cor:HoldingRatioOfShareCertificatesEtcPerLastReport": "前回割合",
    "jplvh_cor:PurposeOfHolding": "保有目的",
}
# 中身がHTMLの表や文章になっているもの。前方一致で拾う
_PER_HOLDER_TEXT = {
    "jplvh_cor:DetailsOfAcquisitionsAndDisposals": "売買明細",
    "jplvh_cor:BreakdownOfTotalAmountFromOtherSources": "増減の内訳",
    "jplvh_cor:SignificantContractsRelatedToSaidStocks": "重要な契約",
}
# 書類に1つしかないタグ
_COVER = {
    "jplvh_cor:FilingDateCoverPage": "提出日",
    "jplvh_cor:DateWhenFilingRequirementAroseCoverPage": "発生日",
    "jplvh_cor:ReasonForFilingChangeReportCoverPage": "提出事由",
    "jplvh_cor:NameCoverPage": "提出者",
}
_HOLDER_AXIS = "FilerLargeVolumeHolder"


def _key() -> str:
    key = os.environ.get("EDINET_API_KEY", "").rstrip()
    if not key:
        sys.exit("環境変数 EDINET_API_KEY が設定されていません")
    return key


def code_map() -> dict:
    """発行会社のEDINETコード → 証券コード4桁"""
    for encoding in ("cp932", "utf-8-sig"):
        try:
            with open(EDINET_CODES, encoding=encoding, newline="") as f:
                rows = list(csv.reader(f))
            break
        except UnicodeDecodeError:
            continue
    else:
        sys.exit(f"読めません: {EDINET_CODES}")
    header = rows[1]
    sec, edi = header.index("証券コード"), header.index("ＥＤＩＮＥＴコード")
    return {r[edi]: r[sec].strip()[:4] for r in rows[2:]
            if len(r) > sec and r[sec].strip()}


def load_doc_index() -> list:
    if not os.path.exists(DOC_INDEX):
        return []
    with open(DOC_INDEX, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def save_doc_index(rows: list) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    seen, unique = set(), []
    for row in sorted(rows, key=lambda r: (r["提出日"], r["書類ID"])):
        if row["書類ID"] in seen:
            continue
        seen.add(row["書類ID"])
        unique.append(row)
    with open(DOC_INDEX, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, DOC_INDEX_COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(unique)


def load_scanned_days() -> set:
    if not os.path.exists(SCANNED_DAYS):
        return set()
    with open(SCANNED_DAYS, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def save_scanned_days(days: set) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(SCANNED_DAYS, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(days)) + "\n")


def scan_documents(since: date, until: date, codes: dict) -> list:
    """日ごとの書類一覧から大量保有報告書だけ拾う。本文は落とさない"""
    key = _key()
    existing = load_doc_index()
    done = load_scanned_days()
    rows = list(existing)
    day, found, scanned = since, 0, 0
    while day <= until:
        # 走査済みの日は飛ばす。ただし当日ぶんは追加提出があるので取り直す
        if day.isoformat() in done and day < date.today():
            day += timedelta(days=1)
            continue
        try:
            res = requests.get(API + ".json",
                               params={"date": day.isoformat(), "type": 2,
                                       "Subscription-Key": key},
                               timeout=30, verify=False)
            docs = res.json().get("results") or []
        except Exception as e:
            print(f"  {day} 取得できず: {e}")
            day += timedelta(days=1)
            continue
        scanned += 1
        done.add(day.isoformat())
        for d in docs:
            if d.get("docTypeCode") not in DOC_TYPES:
                continue
            issuer = d.get("issuerEdinetCode") or d.get("subjectEdinetCode")
            code = codes.get(issuer)
            if not code:
                continue
            rows.append({"提出日": day.isoformat(), "書類種別": d["docTypeCode"],
                         "銘柄コード": code, "発行会社EDINETコード": issuer,
                         "提出者": d.get("filerName") or "", "書類ID": d["docID"]})
            found += 1
        if scanned % 60 == 0:
            print(f"  {day} まで走査、{found}件")
            save_doc_index(rows)
            save_scanned_days(done)
        day += timedelta(days=1)
        time.sleep(0.15)
    save_doc_index(rows)
    save_scanned_days(done)
    print(f"一覧: {scanned}日ぶんを走査し {found}件を追加 → {DOC_INDEX}")
    return load_doc_index()


def _decode(raw: bytes) -> str:
    for encoding in ("utf-16", "utf-8-sig", "utf-8", "cp932"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return ""


# 元号。60日間の表だけ「令和７年10月15日」と和暦で書かれている
_ERA_START = {"令和": 2018, "平成": 1988, "昭和": 1925}
_ZEN = str.maketrans("０１２３４５６７８９", "0123456789")
_ERA_DATE = re.compile(r"(令和|平成|昭和)\s*([0-9０-９元]{1,2})\s*年\s*"
                       r"([0-9０-９]{1,2})\s*月\s*([0-9０-９]{1,2})\s*日")
_WEST_DATE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def to_iso(text: str) -> str:
    """和暦・西暦のどちらでも YYYY-MM-DD にする。読めなければ空"""
    m = _ERA_DATE.search(text)
    if m:
        year = m.group(2).translate(_ZEN)
        year = 1 if year == "元" else int(year)
        return (f"{_ERA_START[m.group(1)] + year:04d}-"
                f"{int(m.group(3).translate(_ZEN)):02d}-"
                f"{int(m.group(4).translate(_ZEN)):02d}")
    m = _WEST_DATE.search(text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""


def _flatten(html: str) -> str:
    """文章のテキストブロックを1行にする"""
    text = re.sub(r"<[^>]+>", " ", html)
    text = (text.replace("&#160;", " ").replace("&nbsp;", " ")
            .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))
    return " ".join(text.split())


# 「最近60日間の取得又は処分の状況」の1行ぶん。
#
# EDINETのCSVでは表のセルが平文になるが、**区切りが入らない書類が多い。**
#
#   令和４年４月15日株券（普通）8000.01市場内取得       ← 区切りなし
#   令和７年10月15日 普通株式 1,500,000 9.08 市場外 処分 2684.5  ← 空白あり
#
# 前者は数量800と割合0.01がくっついて「8000.01」になっている。
# 割合は必ず小数なので、数量を貪欲に取ってから小数へ後戻りさせると割れる。
# 空白で区切られている書類も同じ式で通る。
_TRADE_RE = re.compile(
    r"(?P<date>(?:令和|平成|昭和)\s*[0-9０-９元]{1,2}\s*年\s*[0-9０-９]{1,2}\s*月"
    r"\s*[0-9０-９]{1,2}\s*日|\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)"
    r"[^\d]{0,40}?"                                   # 株券等の種類
    r"(?P<qty>[\d,]+)\s*株?\s*"                        # 数量（「株」が付く書類がある）
    # 割合。%が付く書類と、小数点をカンマで打ち間違えた書類がある
    # （フィットイージーの2024-08-20は「1,94」）。後ろに数字が続かないことで
    # 数量のカンマ区切り（307,900）と区別する
    r"(?P<ratio>\d+[.,]\d{1,2})(?!\d)\s*[%％]?"
    r"\s*(?P<place>市場内|市場外)"
    # 取得／処分を書かない書類がある。次の行に食い込まないよう手前で切る
    r"(?:[^取処\d]{0,8}(?P<side>取得|処分))?"
    r"(?:[^\d]{0,8}(?P<price>[\d,]+\.?\d*))?")


def parse_trades(text: str) -> str:
    """「最近60日間の取得又は処分の状況」を1行の文字列にする。

    列は 年月日 / 株券等の種類 / 数量 / 割合 / 市場内外取引の別 /
    取得又は処分の別 / 単価。日付は和暦のこともある。

      2025-10-15|1500000|市場外|処分|2684.5

    のように詰め、複数回あればセミコロンで並べる。該当が無い書類には
    見出しだけが入っているので空になる。
    """
    body = _flatten(text)
    trades = []
    for m in _TRADE_RE.finditer(body):
        date = to_iso(m.group("date"))
        if not date:
            continue
        trades.append("|".join((
            date,
            m.group("qty").replace(",", ""),
            m.group("place") or "",
            m.group("side") or "",
            (m.group("price") or "").replace(",", "").strip("."))))
    return ";".join(trades)


def parse_csv(text: str) -> list:
    """1書類ぶんのCSVから、保有者ごとの行を作る"""
    cover, per_holder = {}, defaultdict(dict)
    for line in text.splitlines():
        parts = [p.strip('"') for p in line.split("\t")]
        if len(parts) < 3:
            continue
        element, context, value = parts[0], parts[2], parts[-1]
        if value in ("", "－", "-"):
            continue
        if element in _COVER:
            cover.setdefault(_COVER[element], value)
        field = _PER_HOLDER.get(element)
        if field is None:
            # テキストブロックは末尾に NA / TextBlock が付く版があるので前方一致
            for prefix, name in _PER_HOLDER_TEXT.items():
                if element.startswith(prefix):
                    field = name
                    break
        if not field:
            continue
        if field == "売買明細":
            value = parse_trades(value)
        elif field in ("増減の内訳", "重要な契約"):
            value = _flatten(value)
        if not value:
            # 該当が無い書類には見出しだけの空の表が入っている
            continue
        # 共同保有者が居ない書類には保有者の軸が無い。素の文脈を1人ぶんとみなす
        # 同じタグが表と総括表で2度出るので、先に出たほうを採る
        who = context if _HOLDER_AXIS in context else "単独"
        per_holder[who].setdefault(field, value)

    # 保有者の軸がある書類では、合計だけの文脈（単独）は捨てる
    if any(k != "単独" for k in per_holder):
        per_holder.pop("単独", None)

    rows = []
    for values in per_holder.values():
        if not values.get("保有者"):
            continue
        rows.append({
            "提出日": cover.get("提出日", ""),
            "発生日": cover.get("発生日", ""),
            "提出者": cover.get("提出者", ""),
            "提出事由": cover.get("提出事由", ""),
            "保有者": values.get("保有者", ""),
            "株数": values.get("株数", ""),
            "保有割合": values.get("保有割合", ""),
            "前回割合": values.get("前回割合", ""),
            "保有目的": " ".join((values.get("保有目的") or "").split()),
            "売買明細": values.get("売買明細", ""),
            "増減の内訳": values.get("増減の内訳", ""),
            "重要な契約": values.get("重要な契約", ""),
        })
    return rows


def fetch_doc(doc_id: str, key: str, network: bool = True) -> str:
    """書類のCSVを返す。一度落としたものはキャッシュから読む。

    取り出す項目を増やすたびに6万件を落とし直すのは現実的でないので、
    素のCSVを圧縮して置いておく。全銘柄ぶんで300MBほど。
    `--reparse` はこれだけを読み、通信をしない。
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{doc_id}.csv.gz")
    if os.path.exists(path):
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return f.read()
        except Exception:
            os.remove(path)
    if not network:
        return ""

    res = requests.get(f"{API}/{doc_id}",
                       params={"type": 5, "Subscription-Key": key},
                       timeout=60, verify=False)
    if res.status_code != 200 or res.content[:2] != b"PK":
        return ""
    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names:
            return ""
        text = _decode(z.read(names[0]))
    if text:
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write(text)
    return text


def out_path(code: str) -> str:
    return os.path.join(OUT_DIR, f"{code}.tsv")


def collect_bodies(docs: list, codes: set, reparse: bool = False) -> None:
    """対象銘柄の書類だけ本文を落とし、銘柄ごとのTSVに書く。

    reparse なら通信をせず、キャッシュにある書類だけを読み直してTSVを作る。
    取り出す項目を増やしたときに使う。
    """
    key = "" if reparse else _key()
    targets = [d for d in docs if d["銘柄コード"] in codes]
    by_code = defaultdict(list)
    for d in targets:
        by_code[d["銘柄コード"]].append(d)

    print(f"本文の{'読み直し' if reparse else '取得'}: "
          f"{len(by_code)}銘柄 / {len(targets)}件")
    started, fetched, failed = time.time(), 0, 0
    for i, code in enumerate(sorted(by_code), 1):
        path = out_path(code)
        existing, done = [], set()
        if os.path.exists(path) and not reparse:
            with open(path, encoding="utf-8", newline="") as f:
                existing = list(csv.DictReader(f, delimiter="\t"))
            # 列を増やしたあとの古いTSVは作り直す。書類はキャッシュにあるので
            # 落とし直しにはならない
            if existing and any(c not in existing[0] for c in HOLDING_COLUMNS):
                existing = []
            done = {r["書類ID"] for r in existing}

        rows = list(existing)
        for doc in by_code[code]:
            if doc["書類ID"] in done:
                continue
            text = fetch_doc(doc["書類ID"], key, network=not reparse)
            if not reparse:
                time.sleep(0.15)
            if not text:
                failed += 1
                continue
            for row in parse_csv(text):
                row["書類種別"] = doc["書類種別"]
                row["書類ID"] = doc["書類ID"]
                row.setdefault("提出日", doc["提出日"])
                if not row["提出日"]:
                    row["提出日"] = doc["提出日"]
                rows.append(row)
            fetched += 1

        if not rows or (existing and len(rows) == len(existing)):
            continue
        os.makedirs(OUT_DIR, exist_ok=True)
        rows.sort(key=lambda r: (r.get("提出日") or "", r.get("保有者") or ""))
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, HOLDING_COLUMNS, delimiter="\t",
                                    extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        if i % 25 == 0 or i == len(by_code):
            per = (time.time() - started) / max(fetched, 1)
            print(f"  {i}/{len(by_code)}銘柄  取得{fetched}件 "
                  f"({per:.2f}秒/件)  失敗{failed}件")
    print(f"完了: {fetched}件を取得、{failed}件が取れず → {OUT_DIR}/")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true",
                        help="全銘柄の本文を落とす（一晩かかる）")
    parser.add_argument("--codes", nargs="*", help="銘柄コードで絞る")
    parser.add_argument("--since", help="この日以降を走査（既定は2015-01-01）")
    parser.add_argument("--index-only", action="store_true",
                        help="書類の一覧だけ作り、本文は落とさない")
    parser.add_argument("--skip-scan", action="store_true",
                        help="一覧の更新をせず、手元の一覧から本文だけ落とす")
    parser.add_argument("--reparse", action="store_true",
                        help="通信をせず、落とし済みの書類からTSVを作り直す")
    args = parser.parse_args()

    issuer_to_code = code_map()
    print(f"証券コードを持つEDINET提出者: {len(issuer_to_code):,}社")

    if args.skip_scan or args.reparse:
        docs = load_doc_index()
        print(f"手元の一覧: {len(docs):,}件")
    else:
        since = (datetime.strptime(args.since, "%Y-%m-%d").date()
                 if args.since else date.today() - timedelta(days=RETENTION_DAYS))
        docs = scan_documents(since, date.today(), issuer_to_code)

    if args.index_only:
        return 0

    if args.codes:
        codes = set(args.codes)
    elif args.all:
        codes = {d["銘柄コード"] for d in docs}
    else:
        codes = portfolio_codes()
    print(f"対象: {len(codes)}銘柄")
    collect_bodies(docs, codes, reparse=args.reparse)
    return 0


if __name__ == "__main__":
    sys.exit(main())
