"""株価チャートに重ねる適時開示のラベル。

IRバンクと同じ見せ方にする。**開示があった日にA・B・C…の旗を立て、
右のリストからその開示のPDFへ飛べる。** ラベルは新しい日付がAで、
Zの次はAA・AB…と続く。1日に複数の開示があってもラベルは1つで、
リスト側にその日のぶんをまとめて並べる。

対象は保有銘柄だけ（適時開示を集めているのが保有銘柄だけのため）。
**東証に上場していない銘柄は0件になる**（353A・9388）。
"""
from __future__ import annotations

from typing import Any, Dict, List

from visualizer import db as _db

# チャートに立てる旗の上限。多すぎると重なって読めなくなる。
# 6099は開示のある日が130日あり、全部立てるとチャートが埋まる
MAX_MARKERS = 40


def _label(index: int) -> str:
    """0→A, 25→Z, 26→AA, 27→AB …（IRバンクと同じ並び）"""
    letters = ""
    index += 1
    while index > 0:
        index, rest = divmod(index - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def _summaries(code: str) -> Dict[str, Dict[str, str]]:
    """開示のURL → AIが書いた要約と、株主にとっての良し悪し。

    **これはAIの出力なので、画面では「AIによる解釈」と分かるように出す。**
    書いた時点の精度がそのまま残るため、原文（PDF）への導線を必ず残す。
    """
    import csv
    import os

    path = os.path.join(_db.BASE_DIR, "data", "meta", "disclosure_reading.tsv")
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if (row.get("銘柄コード") or "").strip() != code:
                continue
            text = (row.get("要約") or "").strip()
            if text:
                out[(row.get("URL") or "").strip()] = {
                    "要約": text,
                    # 好材料 / 悪材料 / 中立 / 判断できない。
                    # **これは中身の良し悪しで、株価がどう動くかではない。**
                    # 無理に3択へ寄せないので、空や「判断できない」もある
                    "株主にとって": (row.get("株主にとって") or "").strip(),
                }
    return out


def _reaction(prices, date: str) -> Dict[str, Any]:
    """開示の翌営業日と5営業日後の終値の動き。

    **これはAIの判定ではなく実測。** 中身の良し悪し（`株主にとって`）と
    並べて見えるようにするために出す。9166の自己株買い終了は「好材料」と
    書いたが5営業日で-13.4%だった。**ずれている開示ほど読む価値がある。**
    """
    import bisect

    dates = (prices or {}).get("dates") or []
    close = (prices or {}).get("close") or []
    if not dates:
        return {}
    i = bisect.bisect_left(dates, date)
    if i >= len(dates) or close[i] is None:
        return {}
    base = close[i]
    if not base:
        return {}
    out = {}
    for offset, key in ((1, "翌営業日"), (5, "5営業日後")):
        j = i + offset
        if j < len(dates) and close[j] is not None:
            out[key] = round((close[j] / base - 1) * 100, 1)
    return out


def get_markers(company_code: str, limit: int = MAX_MARKERS,
                prices=None) -> Dict[str, Any]:
    """日付ごとにまとめた開示。新しい順、ラベル付き"""
    from collectors import disclosure_pdf

    code = str(company_code or "").strip().upper()
    if not code:
        return {"markers": [], "全件数": 0}

    rows = disclosure_pdf.find(code, months=240)
    notes = _summaries(code)
    by_date: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        if len(row) < 6 or not row[0]:
            continue
        by_date.setdefault(row[0], []).append({
            "時刻": row[1], "タイトル": row[4],
            # TSVには東証のサイト内のパスだけが入っている
            "url": ("https://www2.jpx.co.jp" + row[5]
                    if row[5].startswith("/") else row[5]),
            "要約": (notes.get(row[5]) or {}).get("要約", ""),
            "株主にとって": (notes.get(row[5]) or {}).get("株主にとって", ""),
        })

    markers = []
    for i, date in enumerate(sorted(by_date, reverse=True)):
        items = sorted(by_date[date], key=lambda d: d["時刻"], reverse=True)
        markers.append({
            "date": date,
            "株価の反応": _reaction(prices, date),
            "label": _label(i),
            "件数": len(items),
            "要約あり": sum(1 for d in items if d["要約"]),
            "開示": items,
        })

    return {
        # チャートに立てるのは新しいほうから limit 件まで。
        # **リストには全部出す**（古い開示も辿れるように）
        "markers": markers[:limit],
        "全件数": len(markers),
        "打ち切り": len(markers) > limit,
        "要約の件数": len(notes),
    }
