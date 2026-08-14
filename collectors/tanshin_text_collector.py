"""決算短信の添付資料（定性的情報）を本文として落とす。

**四半期のBS・PL・CF・セグメント情報はここにしか無い。**
有報は年1回、四半期報告書は保有銘柄で361件しか持っていない。短信の添付なら
667件あり、上場からずっと並ぶ。会社が四半期ごとに書いた経営成績の説明と
今後の見通しも同じ資料に入っている。

    ○添付資料の目次
    １．経営成績等の概況（経営成績／財政状態／CF／今後の見通し）
    ３．連結財務諸表及び主な注記
       （１）連結貸借対照表 （２）連結損益計算書及び連結包括利益計算書
       （３）連結株主資本等変動計算書 （４）連結キャッシュ・フロー計算書
       （セグメント情報等）

**PDFではなくHTMLなので表が崩れない。** 同じ内容は短信のPDFにも入っているが、
そちらは pypdf で読むと列が混ざる。

URLは決算短信サマリーのiXBRLと同じIDで、末尾だけが違う。

    081220260511522814_tse-acedjpsm-55920-20260514355920-ixbrl.htm
    081220260511522814_qualitative.htm

    python collectors/tanshin_text_collector.py            # 保有銘柄ぜんぶ
    python collectors/tanshin_text_collector.py --codes 5592

**添付HTMLを出し始めた時期は会社ごとに違う。** 市場全体で一斉に始まった
わけではなく、保有銘柄では2022年2月（8037・6099）から2025年7月（369A）まで
ばらけていた。**それより古い短信では行にリンクが2本（PDFとiXBRL）しか無く、
404が返る。** 取り逃しではないので、記録して次へ進む。
実測で667件中337件（50%）。**2023年以降はほぼ揃っている。**

**対象は保有銘柄だけ**（`CLAUDE.md` の「重いデータは保有銘柄だけ」）。
全銘柄に広げると1社ずつ東証のページを開くところで87時間かかり、桁が変わる。
"""
import argparse
import html as html_module
import os
import re
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.tanshin_xbrl_collector import (  # noqa: E402
    BASE, HEADERS, portfolio_codes, read_index)

TEXT_DIR = os.path.join("data", "output", "tanshin", "text")


def qualitative_url(ixbrl_url: str) -> str:
    """iXBRLのURLから定性的情報のURLを作る。IDまでが同じで末尾だけ違う"""
    head, _, tail = ixbrl_url.rpartition("/")
    doc_id = tail.split("_", 1)[0]
    return f"{head}/{doc_id}_qualitative.htm"


def to_text(raw_html: str) -> str:
    """HTMLを本文にする。

    **表はタブ区切りで残す。** 財務諸表がまるごと入っているので、
    セルを詰めてしまうと数字がどの科目のものか分からなくなる。
    """
    text = re.sub(r"<(style|script|title)\b.*?</\1>", " ", raw_html,
                  flags=re.S | re.I)
    text = re.sub(r"</t[dh]>", "\t", text, flags=re.I)
    text = re.sub(r"<br\s*/?>|</p>|</tr>|</div>|</table>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_module.unescape(text)
    lines = []
    in_toc = False
    for line in text.splitlines():
        line = re.sub(r"[ 　]+", " ", line).strip()
        line = re.sub(r"\t ?", "\t", line).rstrip("\t")
        if not line:
            continue
        # **目次を落とす。** 見出しがそのまま並んでいるので、grepすると
        # どの語もまず目次に当たり、本文にたどり着けない。
        # 点リーダの行と、その次に来るページ番号だけの行が目次
        if "添付資料の目次" in line:
            in_toc = True
            continue
        if re.search(r"…{2,}", line):
            in_toc = True
            continue
        if in_toc and re.fullmatch(r"[0-9０-９]{1,3}", line):
            continue
        in_toc = False
        lines.append(line)
    return "\n".join(lines)


def doc_label(title: str) -> str:
    """ファイル名に使う短い種類名。第何四半期かが分かればいい"""
    for pattern, label in ((r"第[１1一]四半期", "Q1"), (r"第[２2二]四半期", "Q2"),
                           (r"中間", "Q2"), (r"第[３3三]四半期", "Q3")):
        if re.search(pattern, title):
            return label
    return "FY"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--codes", nargs="+", help="銘柄コードで絞る")
    parser.add_argument("--force", action="store_true",
                        help="取得済みの短信も落とし直す")
    args = parser.parse_args()

    rows = read_index(args.codes or portfolio_codes())
    by_code = {}
    for row in rows:
        by_code.setdefault(row["コード"], []).append(row)

    got = skipped = missing = 0
    for code in sorted(by_code):
        out_dir = os.path.join(TEXT_DIR, code)
        os.makedirs(out_dir, exist_ok=True)
        for row in sorted(by_code[code], key=lambda r: r["日付"]):
            name = f"{row['日付']}_{doc_label(row['タイトル'])}.txt"
            path = os.path.join(out_dir, name)
            if os.path.exists(path) and not args.force:
                skipped += 1
                continue

            url = BASE + qualitative_url(row["iXBRLのURL"])
            try:
                res = requests.get(url, headers=HEADERS, timeout=40)
            except Exception as exc:
                print(f"{code} {row['日付']}: 取得できず {exc}")
                missing += 1
                continue
            if res.status_code != 200:
                # 添付資料を出していない短信がある（業績予想の修正だけ、など）
                print(f"{code} {row['日付']}: HTTP {res.status_code} 添付なし")
                missing += 1
                time.sleep(0.6)
                continue

            res.encoding = res.apparent_encoding
            body = to_text(res.text)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(f"{row['日付']}\t{code}\t{row['タイトル']}\n")
                f.write(f"{url}\n\n{body}\n")
            got += 1
            print(f"{code} {name}: {len(body):,}字")
            time.sleep(1.2)

    print(f"\n取得 {got}件 / 既存 {skipped}件 / 取れず {missing}件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
