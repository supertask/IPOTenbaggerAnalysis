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
import io
import os
import sys
import time
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta

import requests
import urllib3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.holding_profile_dump import portfolio_codes

urllib3.disable_warnings()

API = "https://api.edinet-fsa.go.jp/api/v2/documents"
OUT_DIR = os.path.join("data", "output", "large_holdings")
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
                   "保有割合", "前回割合", "提出事由", "保有目的", "書類ID"]

# 1人ぶんの値を束ねるタグ。素の FilingDateInstant は共同保有者の合計
_PER_HOLDER = {
    "jplvh_cor:FilerNameInJapaneseDEI": "保有者",
    "jplvh_cor:TotalNumberOfStocksEtcHeld": "株数",
    "jplvh_cor:HoldingRatioOfShareCertificatesEtc": "保有割合",
    "jplvh_cor:HoldingRatioOfShareCertificatesEtcPerLastReport": "前回割合",
    "jplvh_cor:PurposeOfHolding": "保有目的",
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
        if not field:
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
        })
    return rows


def fetch_doc(doc_id: str, key: str) -> str:
    res = requests.get(f"{API}/{doc_id}",
                       params={"type": 5, "Subscription-Key": key},
                       timeout=60, verify=False)
    if res.status_code != 200 or res.content[:2] != b"PK":
        return ""
    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names:
            return ""
        return _decode(z.read(names[0]))


def out_path(code: str) -> str:
    return os.path.join(OUT_DIR, f"{code}.tsv")


def collect_bodies(docs: list, codes: set) -> None:
    """対象銘柄の書類だけ本文を落とし、銘柄ごとのTSVに書く"""
    key = _key()
    targets = [d for d in docs if d["銘柄コード"] in codes]
    by_code = defaultdict(list)
    for d in targets:
        by_code[d["銘柄コード"]].append(d)

    print(f"本文の取得: {len(by_code)}銘柄 / {len(targets)}件")
    started, fetched, failed = time.time(), 0, 0
    for i, code in enumerate(sorted(by_code), 1):
        path = out_path(code)
        existing, done = [], set()
        if os.path.exists(path):
            with open(path, encoding="utf-8", newline="") as f:
                existing = list(csv.DictReader(f, delimiter="\t"))
            done = {r["書類ID"] for r in existing}

        rows = list(existing)
        for doc in by_code[code]:
            if doc["書類ID"] in done:
                continue
            text = fetch_doc(doc["書類ID"], key)
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

        if len(rows) == len(existing):
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
    args = parser.parse_args()

    issuer_to_code = code_map()
    print(f"証券コードを持つEDINET提出者: {len(issuer_to_code):,}社")

    if args.skip_scan:
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
    print(f"本文を落とす対象: {len(codes)}銘柄")
    collect_bodies(docs, codes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
