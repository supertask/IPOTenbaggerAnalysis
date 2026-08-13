"""保有銘柄の比較企業を四季報から取り直し、インデックスにも反映する。

比較企業は四季報オンラインの自動選定で、**向こうが入れ替える**。
`comparision_collector.py` は一度取れたら二度と見に行かないので古いまま残る。
デジタルグリッド(350A)は上場直後に取ったレジル・GMOペイ・ラクスルのままで、
いまはグリムス・GMOペイ・Eチェンジに変わっていた。

比較企業は財務指標のグラフの相手そのものなので、間違っていると比較全体が
意味を失う。保有銘柄だけでも定期的に取り直す。

  python collectors/refresh_competitors.py            # 保有銘柄
  python collectors/refresh_competitors.py 350A 212A
"""
import argparse
import csv
import glob
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.holding_profile_dump import portfolio_codes

COMPARISON_DIR = os.path.join("data", "output", "comparison")
COMPARISON_GLOB = os.path.join(COMPARISON_DIR, "companies_*.tsv")
# 上場年ごとのTSVは2024年以前が無く、古い銘柄は書き戻す行が存在しない。
# ビルドは companies_*.tsv を新しい順に読んで先勝ちで採るので、
# 名前の後ろに来るこのファイルに書けば、どの年のTSVより優先されて残る
REFRESHED_TSV = os.path.join(COMPARISON_DIR, "companies_zz_refreshed.tsv")
INDEX_DB = os.path.join("data", "output", "index", "visualizer.db")


def update_tsv(cache, codes):
    """取り直した結果を companies_*.tsv の「競合リスト」に書き戻す。

    書き戻せた銘柄コードを返す（残りは REFRESHED_TSV に回す）"""
    touched = set()
    for path in sorted(glob.glob(COMPARISON_GLOB)):
        if os.path.abspath(path) == os.path.abspath(REFRESHED_TSV):
            continue
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        if not rows:
            continue
        columns = list(rows[0].keys())
        changed = False
        for row in rows:
            code = (row.get("コード") or "").strip()
            if code in codes and cache.get(code):
                touched.add(code)
                new = json.dumps(cache[code], ensure_ascii=False)
                if row.get("競合リスト") != new:
                    row["競合リスト"] = new
                    changed = True
        if changed:
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, columns, delimiter="\t",
                                        extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
    return touched


def write_refreshed(cache, codes, already):
    """上場年のTSVに行が無い銘柄を、専用のTSVに書き出す。

    ここに書かないと、インデックスを作り直したときに取り直しが消える"""
    rows = {}
    if os.path.exists(REFRESHED_TSV):
        with open(REFRESHED_TSV, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                rows[(row.get("コード") or "").strip()] = row
    names = company_names()
    added = 0
    for code in sorted(codes):
        if code in already or not cache.get(code):
            continue
        rows[code] = {"コード": code, "企業名": names.get(code, ""),
                      "競合リスト": json.dumps(cache[code], ensure_ascii=False)}
        added += 1
    if not rows:
        return 0
    os.makedirs(COMPARISON_DIR, exist_ok=True)
    with open(REFRESHED_TSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, ["コード", "企業名", "競合リスト"],
                                delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for code in sorted(rows):
            writer.writerow(rows[code])
    return added


def company_names():
    """インデックスから企業名を引く。人が見て分かるようにするだけで、
    ビルドはこの列を読まない"""
    if not os.path.exists(INDEX_DB):
        return {}
    conn = sqlite3.connect(f"file:{INDEX_DB}?mode=ro", uri=True)
    try:
        return {code: name for code, name in
                conn.execute("SELECT code, name FROM companies")}
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


def update_index(cache, codes):
    """インデックスの competitors だけ差し替える。
    全体のビルドは50分かかるので、この表だけ書き換える"""
    if not os.path.exists(INDEX_DB):
        print("インデックスがありません。ビルドしてから実行してください")
        return 0
    conn = sqlite3.connect(INDEX_DB)
    written = 0
    for code in codes:
        peers = cache.get(code)
        if not peers:
            continue
        conn.execute("DELETE FROM competitors WHERE company_code = ?", (code,))
        for rank, item in enumerate(peers):
            conn.execute(
                "INSERT OR REPLACE INTO competitors "
                "(company_code, rank, competitor_code, competitor_name) "
                "VALUES (?, ?, ?, ?)",
                (code, rank, (item.get("code") or "").strip(),
                 (item.get("name") or "").strip() or None))
            written += 1
    conn.commit()
    conn.close()
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("codes", nargs="*")
    parser.add_argument("--from-cache", action="store_true",
                        help="四季報を見に行かず、手元のキャッシュから書き戻すだけ")
    args = parser.parse_args()

    codes = set(args.codes) if args.codes else portfolio_codes()

    from collectors.comparision_collector import ComparisonCollector
    collector = ComparisonCollector()
    collector.is_debug = False
    if args.from_cache:
        print(f"キャッシュから書き戻す銘柄: {len(codes)}\n")
    else:
        print(f"取り直す銘柄: {len(codes)}\n")
        collector.refresh(codes)

    touched = update_tsv(collector.comparison_cache, codes)
    added = write_refreshed(collector.comparison_cache, codes, touched)
    written = update_index(collector.comparison_cache, codes)
    print(f"上場年のTSVに{len(touched)}銘柄、{os.path.basename(REFRESHED_TSV)}に"
          f"{added}銘柄、インデックスに{written}行書きました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
