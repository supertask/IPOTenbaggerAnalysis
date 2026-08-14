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


def get_markers(company_code: str, limit: int = MAX_MARKERS) -> Dict[str, Any]:
    """日付ごとにまとめた開示。新しい順、ラベル付き"""
    from collectors import disclosure_pdf

    code = str(company_code or "").strip().upper()
    if not code:
        return {"markers": [], "全件数": 0}

    rows = disclosure_pdf.find(code, months=240)
    by_date: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        if len(row) < 6 or not row[0]:
            continue
        by_date.setdefault(row[0], []).append({
            "時刻": row[1], "タイトル": row[4],
            # TSVには東証のサイト内のパスだけが入っている
            "url": ("https://www2.jpx.co.jp" + row[5]
                    if row[5].startswith("/") else row[5]),
        })

    markers = []
    for i, date in enumerate(sorted(by_date, reverse=True)):
        markers.append({
            "date": date,
            "label": _label(i),
            "件数": len(by_date[date]),
            "開示": sorted(by_date[date], key=lambda d: d["時刻"], reverse=True),
        })

    return {
        # チャートに立てるのは新しいほうから limit 件まで。
        # **リストには全部出す**（古い開示も辿れるように）
        "markers": markers[:limit],
        "全件数": len(markers),
        "打ち切り": len(markers) > limit,
    }
