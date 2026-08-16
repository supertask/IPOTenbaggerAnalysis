"""会社自身の業績予想が、決算のたびにどう動いたか。

**有報のXBRLには実績しか無い。会社の見通しは決算短信にしか無い。**

見るものは2つあって、**混ぜてはいけない。**

    期初の予想の年次の伸び … 会社が毎年置く「今期はこれくらい」が去年より
                             どれだけ伸びたか。**成長そのもの**
    期中の修正             … その期初の数字を、期の途中で上げたか下げたか

    6099（12月決算）
      2018-05   9.9億 ← FY2018の期初      2019-05  14.3億 ← FY2019の期初
      2018-08  11.5億 ↑ 期中の上方修正      2019-08  14.3億
      2018-11  12.5億 ↑ 期中の上方修正      2019-11  14.3億

短信を日付順に並べて差を取ると、`2018-11 (12.5億) → 2019-05 (14.3億)` が
「+14%の上方修正」になる。**これは修正ではなく次の年の話。**
期の切れ目は「来期」の予想が出た短信（＝通期決算短信）で分かるので、
そこで束ねてから数える。

**実績より早く出る。** 「利益率が3%を割ったとき」のような実績の条件は
起きてから分かる。会社の見通しが下を向くほうが先に見える。

対象は保有銘柄だけ（短信のXBRLを集めているのが保有銘柄だけのため）。
`collectors/tanshin_xbrl_collector.py` が作ったTSVを読む。
"""
from __future__ import annotations

import csv
import os
from typing import Any, Dict, List, Optional

from visualizer import db as _db

FACTS_DIR = os.path.join(_db.BASE_DIR, "data", "output", "tanshin", "facts")

# 画面に出す順。**利益を先に置く。** 売上が伸びていても利益の見通しが
# 下がっていれば、そちらが効く
METRICS = (
    ("営業利益", ("OperatingIncome", "OperatingIncomeIFRS")),
    ("経常利益", ("OrdinaryIncome", "ProfitBeforeTaxIFRS")),
    ("当期純利益", ("ProfitAttributableToOwnersOfParent", "NetIncome",
                    "ProfitAttributableToOwnersOfParentIFRS")),
    ("売上高", ("NetSales", "SalesIFRS")),
    # **名前を短くする。** 390pxでは指標名が折り返して行が2段になる
    ("配当（1株）", ("DividendPerShare",)),
)

# これより小さい直しは「修正」と数えない。端数の置き直しが混じるため
MIN_CHANGE = 0.03


def _rows(code: str):
    path = os.path.join(FACTS_DIR, f"{code}.tsv")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _points(rows, tags) -> List[dict]:
    """当期・来期の予想を、日付順の1本の並びにする"""
    got = []
    for row in rows:
        if row["区分"] != "予想" or row["タグ"] not in tags or not row["値"]:
            continue
        if row["期"] not in ("当期", "来期"):
            continue
        # 配当は四半期ごとにも出る。年間の合計だけを見る
        if row["四半期"] and row["四半期"] != "合計":
            continue
        try:
            value = float(row["値"])
        except ValueError:
            continue
        got.append({"日付": row["日付"], "期": row["期"], "値": value,
                    "連単": row["連単"]})
    # 同じ日・同じ期に連結と単体の両方が入る。連結を採る
    merged: Dict[tuple, dict] = {}
    for p in got:
        key = (p["日付"], p["期"])
        cur = merged.get(key)
        if cur is None or (p["連単"] == "連結" and cur["連単"] != "連結"):
            merged[key] = p
    # 同じ日なら来期（＝次の期の期初）を先に置く
    return sorted(merged.values(), key=lambda p: (p["日付"], p["期"] != "来期"))


def _fiscal_years(points: List[dict]) -> List[dict]:
    """期ごとに束ねる。

    「来期」の予想が出た短信が通期決算短信で、そこが期の切れ目。
    次の通期決算短信までの「当期」が、同じ期に対する修正になる。
    """
    out: List[dict] = []
    cur: Optional[dict] = None
    prev_period = None
    for p in points:
        if p["期"] == "来期":
            if prev_period != "来期" or cur is None:
                cur = {"点": [p], "連単": p["連単"]}
                out.append(cur)
            else:
                # 期が始まる前の置き直し。まだ期初とみなす
                cur["点"] = [p]
                cur["連単"] = p["連単"]
        else:
            if cur is None:
                cur = {"点": [p], "連単": p["連単"]}
                out.append(cur)
            elif p["連単"] != cur["連単"]:
                # **単体→連結の切り替わりは修正ではない。** 6099は2017年に
                # 連結へ移り、単体7.5億→連結9.0億が「+20%の上方修正」に見えていた
                cur["連単"] = p["連単"]
                cur["点"] = [p]
            else:
                cur["点"].append(p)
        prev_period = p["期"]
    return out


def _rate(before: float, after: float) -> Optional[float]:
    """**符号をまたぐ%は返さない。** 赤字から黒字への「+1656%」は読めない"""
    if before is None or after is None or before <= 0 or after <= 0:
        return None
    return round((after / before - 1) * 100, 1)


def _median(sorted_values: List[float]) -> Optional[float]:
    n = len(sorted_values)
    if not n:
        return None
    mid = n // 2
    if n % 2:
        return round(sorted_values[mid], 1)
    return round((sorted_values[mid - 1] + sorted_values[mid]) / 2, 1)


def get_forecasts(company_code: str) -> Dict[str, Any]:
    """指標ごとに、期で束ねた予想の推移を返す"""
    code = str(company_code or "").strip().upper()
    rows = _rows(code)
    if not rows:
        return {}

    series: Dict[str, List[dict]] = {}
    summary: List[dict] = []
    for label, tags in METRICS:
        points = _points(rows, tags)
        if len(points) < 2:
            continue
        series[label] = [{"日付": p["日付"], "値": p["値"]} for p in points]
        got = _summarize(label, _fiscal_years(points))
        if got:
            summary.append(got)

    return {"コード": code, "系列": series, "要約": summary}


def _summarize(label: str, years: List[dict]) -> Optional[dict]:
    """1指標ぶん。**期をまたいだ変化を修正と数えない**"""
    if not years:
        return None

    ups = downs = misses = 0
    crossed = False          # 赤字をまたいだ期があるか
    for y in years:
        vals = [p["値"] for p in y["点"]]
        for a, b in zip(vals, vals[1:]):
            r = _rate(a, b)
            if r is None:
                crossed = True
                continue
            if r > MIN_CHANGE * 100:
                ups += 1
            elif r < -MIN_CHANGE * 100:
                downs += 1
        if len(vals) >= 2 and vals[-1] < vals[0] - 1e-6:
            misses += 1

    # 期初の予想が、去年の期初よりどれだけ伸びたか。
    # **平均ではなく中央値を採る。** 赤字の翌年や、基数がごく小さい年が
    # 1つあるだけで平均は壊れる（6574は0.1億→30億の年があり平均+462%になる）
    starts = [y["点"][0]["値"] for y in years]
    growth = sorted(r for a, b in zip(starts, starts[1:])
                    if (r := _rate(a, b)) is not None)

    last = years[-1]["点"]
    last_change = None
    for y in years:
        for a, b in zip(y["点"], y["点"][1:]):
            r = _rate(a["値"], b["値"])
            if r is not None and abs(r) > MIN_CHANGE * 100:
                last_change = {"日付": b["日付"],
                               "向き": "上方修正" if r > 0 else "下方修正",
                               "率": r}

    return {
        "指標": label,
        "期数": len(years),
        # **これがいちばん効く。** 保有24銘柄では、年+50%以上の8社が
        # 最高値の91%を保ち、+20%未満の11社は56%まで落ちていた
        "期初の伸び": _median(growth),
        "今期": {
            "期初日": last[0]["日付"], "期初": last[0]["値"],
            "直近日": last[-1]["日付"], "直近": last[-1]["値"],
            "率": _rate(last[0]["値"], last[-1]["値"]),
        },
        "上方修正": ups,
        "下方修正": downs,
        "未達": misses,
        "最後の修正": last_change,
        "赤字またぎ": crossed,
    }
