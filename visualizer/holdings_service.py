"""大株主・役員の持株の推移を、有価証券報告書の年次データから組み立てる。

同じ人の株数を期をまたいで並べると「誰が何株売った／買った」が分かる。
ロックアップ解除後に創業者やVCが降りていないかを見るのが目的。
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from visualizer import db as _index_db

logger = logging.getLogger(__name__)

# 表示する人数の上限（株数の多い順）
MAX_HOLDERS = 12


def _rows(company_code: str) -> List[dict]:
    conn = _index_db.get_conn()
    if conn is None:
        return []
    try:
        return [dict(r) for r in conn.execute(
            """SELECT report_date, holder_type, holder_name, shares, ratio
               FROM share_holdings
               WHERE company_code = ?
               ORDER BY report_date""",
            (str(company_code).strip(),),
        )]
    except Exception as e:
        logger.warning("持株の取得に失敗 %s: %s", company_code, e)
        return []


def _split_factors(company_code: str, dates: List[str]) -> Dict[str, float]:
    """各報告日について、その後の分割の累積倍率を求める。

    有報に載る株数は当時の株数そのままなので、分割があると持株数が機械的に
    増える。今の基準に揃えないと、買い増しと分割の区別が付かない。
    """
    from visualizer import price_service

    factors = {}
    for date in dates:
        try:
            factors[date] = price_service.get_split_factor(company_code, date)
        except Exception as e:
            logger.warning("分割倍率の取得に失敗 %s %s: %s", company_code, date, e)
            factors[date] = 1.0
    return factors


def _build(rows: List[dict], holder_type: str, factors: Dict[str, float]) -> Optional[dict]:
    target = [r for r in rows if r["holder_type"] == holder_type and r["shares"] is not None]
    if not target:
        return None

    dates = sorted({r["report_date"] for r in target})
    if len(dates) < 1:
        return None

    by_name: Dict[str, Dict[str, float]] = {}
    for r in target:
        adjusted = r["shares"] * factors.get(r["report_date"], 1.0)
        by_name.setdefault(r["holder_name"], {})[r["report_date"]] = adjusted

    people = []
    for name, per_date in by_name.items():
        values = [per_date.get(d) for d in dates]
        known = [v for v in values if v is not None]
        if not known:
            continue
        # 直近と、その1つ前に記録がある期を比べる
        change = None
        seen = [(d, per_date[d]) for d in dates if d in per_date]
        if len(seen) >= 2:
            change = seen[-1][1] - seen[-2][1]
        people.append({
            "name": name,
            "values": values,
            "latest": seen[-1][1],
            "change": change,
        })

    people.sort(key=lambda p: -(p["latest"] or 0))
    return {"dates": dates, "people": people[:MAX_HOLDERS],
            "truncated": max(0, len(people) - MAX_HOLDERS)}


def get_holdings_history(company_code) -> Optional[dict]:
    """大株主と役員それぞれの持株推移。データが無ければ None"""
    rows = _rows(company_code)
    if not rows:
        return None

    dates = sorted({r["report_date"] for r in rows})
    factors = _split_factors(str(company_code).strip(), dates)
    split_adjusted = any(f != 1.0 for f in factors.values())

    major = _build(rows, "major", factors)
    officer = _build(rows, "officer", factors)
    if not major and not officer:
        return None

    # 役員の合計が減った期は、経営陣が売った可能性がある地点として印を付ける
    decreases = []
    if officer:
        totals = []
        for index, date in enumerate(officer["dates"]):
            total = sum(p["values"][index] for p in officer["people"]
                        if p["values"][index] is not None)
            totals.append((date, total))
        for (prev_date, prev), (date, current) in zip(totals, totals[1:]):
            if current < prev:
                decreases.append({"date": date, "diff": current - prev})
        officer["totals"] = totals

    return {"major": major, "officer": officer, "officer_decreases": decreases,
            "split_adjusted": split_adjusted}
