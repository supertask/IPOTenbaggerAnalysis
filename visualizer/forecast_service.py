"""会社自身の業績予想が、決算のたびにどう動いたか。

**有報のXBRLには実績しか無い。会社の見通しは決算短信にしか無い。**
短信ごとに並べると「会社が見通しを上げ続けているか、下げ始めたか」が出る。

    5592  今期営業利益  12.3億 → 15.1億 → 18.0億 → 22.0億 → 24.5億（5回引き上げ）
    9158  来期営業利益  55億 → 38億（下方修正）

**実績より早く出る。** 「利益率が3%を割ったとき」のような実績の条件は、
起きてから分かる。会社の見通しが下を向くほうが先に見える。

対象は保有銘柄だけ（短信のXBRLを集めているのが保有銘柄だけのため）。
`collectors/tanshin_xbrl_collector.py` が作ったTSVを読む。
"""
from __future__ import annotations

import csv
import os
from typing import Any, Dict, List

from visualizer import db as _db

FACTS_DIR = os.path.join(_db.BASE_DIR, "data", "output", "tanshin", "facts")

# 画面に出す順。**利益を先に置く。** 売上が伸びていても利益の見通しが
# 下がっていれば、そちらが効く
METRICS = (
    ("営業利益", ("OperatingIncome", "OperatingIncomeIFRS")),
    ("経常利益", ("OrdinaryIncome", "ProfitBeforeTaxIFRS")),
    ("売上高", ("NetSales", "SalesIFRS")),
    ("当期純利益", ("ProfitAttributableToOwnersOfParent", "NetIncome",
                    "ProfitAttributableToOwnersOfParentIFRS")),
    ("1株当たり配当金", ("DividendPerShare",)),
)


def _rows(code: str):
    path = os.path.join(FACTS_DIR, f"{code}.tsv")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def get_forecasts(company_code: str) -> Dict[str, Any]:
    """指標ごとに、短信の日付順の予想の並びを返す"""
    code = str(company_code or "").strip().upper()
    rows = _rows(code)
    if not rows:
        return {}

    series: Dict[str, List[dict]] = {}
    for label, tags in METRICS:
        for period in ("当期", "来期"):
            points = []
            for row in rows:
                if row["区分"] != "予想" or row["期"] != period:
                    continue
                if row["タグ"] not in tags or not row["値"]:
                    continue
                # 配当は四半期ごとにも出る。年間の合計だけを見る
                if row["四半期"] and row["四半期"] != "合計":
                    continue
                try:
                    value = float(row["値"])
                except ValueError:
                    continue
                points.append({"日付": row["日付"], "値": value,
                               "連単": row["連単"]})
            if len(points) < 2:
                continue
            points.sort(key=lambda p: p["日付"])
            # 同じ日に複数入ることがある（連結と単体）。連結を優先して1点にする
            merged: Dict[str, dict] = {}
            for p in points:
                cur = merged.get(p["日付"])
                if cur is None or (p["連単"] == "連結" and cur["連単"] != "連結"):
                    merged[p["日付"]] = p
            points = [merged[d] for d in sorted(merged)]
            if len(points) < 2:
                continue
            series[f"{period} {label}"] = points

    return {"コード": code, "系列": series, "要約": _summarize(series)}


def _summarize(series: Dict[str, List[dict]]) -> List[dict]:
    """指標ごとに「何回上げて何回下げたか」と、直近の向きを出す。

    **これが見たいものそのもの。** グラフを目で追わなくても、
    上方修正が続いているのか、直近で下を向いたのかが分かる。
    """
    out = []
    for name, points in series.items():
        ups = downs = 0
        for prev, cur in zip(points, points[1:]):
            if cur["値"] > prev["値"]:
                ups += 1
            elif cur["値"] < prev["値"]:
                downs += 1
        last_change = None
        for prev, cur in zip(points, points[1:]):
            if cur["値"] != prev["値"]:
                last_change = {
                    "日付": cur["日付"],
                    "向き": "上方修正" if cur["値"] > prev["値"] else "下方修正",
                    "率": round((cur["値"] / prev["値"] - 1) * 100, 1)
                    if prev["値"] else None,
                }
        out.append({
            "指標": name,
            "回数": len(points),
            "上方修正": ups,
            "下方修正": downs,
            "初回": points[0],
            "直近": points[-1],
            "累計の変化率": round((points[-1]["値"] / points[0]["値"] - 1) * 100, 1)
            if points[0]["値"] else None,
            "最後の修正": last_change,
        })
    # 下方修正があるものを先に出す。**悪い知らせを埋もれさせない**
    out.sort(key=lambda r: (-r["下方修正"], -r["上方修正"]))
    return out
