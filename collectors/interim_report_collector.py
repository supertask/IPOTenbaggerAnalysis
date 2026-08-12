"""保有銘柄だけ、期中の報告書（四半期・半期）も落としてくる。

大株主の持株は有報だと年1回しか分からず、ロックアップ解除の直後に誰が
降りたのかが1年遅れでしか見えない。期中の報告書にも大株主の欄があるので、
これを足すと年2回になる。

実データで確かめた前提（2026-08時点）:

  - 四半期報告書（140）は中間期のものだけ大株主が載る。第1・第3は載らない
  - 四半期報告書は2024年4月に廃止され、半期報告書（160）に置き換わった。
    半期報告書は同じ要素IDで大株主が載る
  - どちらにも役員の持株は載らない。役員は有報の年1回のまま

全上場企業に広げると書類が数万件になるので、対象は
data/output/portfolio/*.tsv に入っている保有銘柄に絞る。
"""
import argparse
import csv
import glob
import gzip
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.edinet_report_downloader import EdinetReportDownloader
from collectors.file_utils import sanitize_filename

PORTFOLIO_GLOB = os.path.join("data", "output", "portfolio", "*.tsv")

# 半期報告書の制度が始まった日。これより前に160は存在しない
SEMIANNUAL_START = "2024-04-01"

# 補完済みを覚えておくファイル。無いと「一番古い160の日付より前」を
# 毎回走査してしまう（実際には書類が無いので永久に埋まらない）
BACKFILL_MARKER = "semiannual_backfilled.txt"

# 保存先。build_index.py が quarterly_reports を「期中の報告書」として
# 読むようになっているので、半期報告書も同じ場所に置く
SUBDIR = "quarterly_reports"


def portfolio_codes() -> set:
    """保有銘柄の証券コード（4桁）。銘柄コードが無い行は落とす"""
    codes = set()
    for path in sorted(glob.glob(PORTFOLIO_GLOB)):
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        if not rows:
            continue
        key = next((k for k in rows[0] if "コード" in k), None)
        if key is None:
            continue
        for row in rows:
            code = (row.get(key) or "").strip()
            # 「(投信)」「(非開示)」のような銘柄コードでない行が混ざる
            if code and not code.startswith("("):
                codes.add(code)
    return codes


def backfill_semiannual_metadata(downloader: EdinetReportDownloader,
                                 companies: dict, cache_path: str) -> None:
    """キャッシュに半期報告書が入っていない期間を埋める。

    キャッシュを作った時点では160を拾っていなかったので、制度開始日から
    さかのぼって一度だけ走らせる必要がある。
    """
    marker = os.path.join(os.path.dirname(cache_path), BACKFILL_MARKER)
    if os.path.exists(marker):
        print("半期報告書のメタデータは補完済みです")
        return

    start = datetime.strptime(SEMIANNUAL_START, "%Y-%m-%d")
    end = datetime.now()
    print(f"半期報告書のメタデータを補完します: "
          f"{start:%Y-%m-%d} 〜 {end:%Y-%m-%d}")
    new_data = downloader.download_incremental_data(start, end, companies)
    if len(new_data):
        downloader.merge_and_save_cache(new_data, cache_path)
    else:
        print("補完できる書類はありませんでした")
    with open(marker, "w", encoding="utf-8") as f:
        f.write(f"{start:%Y-%m-%d}\t{end:%Y-%m-%d}\n")


def download_interim_reports(downloader: EdinetReportDownloader,
                             companies: dict, cache_path: str,
                             codes: set) -> None:
    with gzip.open(cache_path, "rt", encoding="utf-8") as f:
        full = pd.read_csv(f, sep="\t", dtype=str)

    by_code4 = {}
    for edinet_code, company in companies.items():
        code4 = company["company_code"][:-1]
        if code4 in codes:
            by_code4[code4] = (edinet_code, company["company_name"])

    missing = sorted(codes - set(by_code4))
    if missing:
        print(f"EDINETコードが引けなかった銘柄: {', '.join(missing)}")

    # EDINETは古い書類を配信しなくなる。10年より前のdocIDは404が返るだけなので
    # 最初から要求しない
    oldest = (datetime.now()
              - timedelta(days=downloader.recent_docs_years * 365)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")

    for code4 in sorted(by_code4):
        edinet_code, name = by_code4[code4]
        docs = full[full["edinet_code"] == edinet_code]
        folder = os.path.join(downloader.REPORTS_DIR,
                              f"{code4}_{sanitize_filename(name)}", SUBDIR)
        for doc_type, label in ((downloader.DOC_TYPE_CODE_QUARTERLY_REPORT, "四半期報告書"),
                                (downloader.DOC_TYPE_CODE_SEMIANNUAL_REPORT, "半期報告書")):
            if docs[docs["docTypeCode"] == doc_type].empty:
                continue
            downloader.save_securities_docs(
                docs, doc_type, folder, label, code4, name, oldest, today)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-backfill", action="store_true",
                        help="半期報告書のメタデータ補完を行わない")
    args = parser.parse_args()

    downloader = EdinetReportDownloader()
    downloader.is_debug = False
    cache_path = os.path.join(downloader.EDINET_CODE_DIR,
                              downloader.incremental_cache_file)
    if not os.path.exists(cache_path):
        sys.exit(f"メタデータのキャッシュがありません: {cache_path}\n"
                 "先に edinet_report_downloader.py を走らせてください")

    codes = portfolio_codes()
    print(f"対象: {len(codes)}銘柄")

    companies = downloader.get_company_dict()
    if not args.skip_backfill:
        backfill_semiannual_metadata(downloader, companies, cache_path)
    download_interim_reports(downloader, companies, cache_path, codes)


if __name__ == "__main__":
    main()
