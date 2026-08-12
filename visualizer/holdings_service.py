"""大株主・役員の持株の推移を組み立てる。

同じ人の株数を期をまたいで並べると「誰が何株売った／買った」が分かる。
ロックアップ解除後に創業者やVCが降りていないかを見るのが目的。

大株主は有報に加えて期中の報告書（中間期の四半期報告書・半期報告書）にも
載るので、保有銘柄については年2回になる。役員は有報にしか載らないため
年1回のまま。どちらの報告書から来た値かは report_type で区別する。
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Dict, List, Optional

from visualizer import db as _index_db

logger = logging.getLogger(__name__)

# 表示する人数の上限（株数の多い順）
MAX_HOLDERS = 12

# 末尾の注記。「日成ビルド工業株式会社（注）」と「日成ビルド工業株式会社」は同じ
_NOTE_SUFFIX = re.compile(r"[（(]注[^）)]*[）)]\s*$")


def _name_key(name: str) -> str:
    """同じ株主を同じ行にまとめるための照合キー。

    書類によって「（信託口）」が半角だったり、英字の全角・半角や空白の
    入り方が違ったりする。そのままだと同一人物が別行に分かれ、
    片方が「–」になるので売却したように見えてしまう。
    """
    text = unicodedata.normalize("NFKC", name)
    text = _NOTE_SUFFIX.sub("", text)
    return "".join(text.split())


def _rows(company_code: str) -> List[dict]:
    conn = _index_db.get_conn()
    if conn is None:
        return []
    try:
        return [dict(r) for r in conn.execute(
            """SELECT report_date, period_end, report_type,
                      holder_type, holder_name, shares, ratio
               FROM share_holdings
               WHERE company_code = ?
               ORDER BY report_date""",
            (str(company_code).strip(),),
        )]
    except Exception as e:
        logger.warning("持株の取得に失敗 %s: %s", company_code, e)
        return []


# 分割の基準日は期末に置かれ、効力発生は翌日というのが通例。株価が落ちる
# 権利落ち日はその数営業日前に来るので、期末時点の名簿はまだ分割前になる
_REGISTER_LAG_DAYS = 7


def _split_factors(company_code: str, rows: List[dict]) -> Dict[tuple, float]:
    """報告日ごとに、その後の分割の累積倍率を求める。

    報告書に載る株数は当時の株数そのままなので、分割があると持株数が機械的に
    増える。今の基準に揃えないと、買い増しと分割の区別が付かない。

    どの日で切るかは大株主と役員で違う。同じ有報の中でも

      - 大株主の状況 … 期末時点
      - 役員の状況   … 提出日現在

    と基準が別で、提出は期末の2〜3ヶ月あと。その間に分割が入る期があるので、
    片方に揃えるともう片方が2倍または半分にずれる。
    """
    from visualizer import price_service

    as_of = {}
    for r in rows:
        if r["holder_type"] == "major":
            # 期末が取れない古い書類は提出日で代用する
            as_of.setdefault(("major", r["report_date"]),
                             (r["period_end"] or r["report_date"],
                              _REGISTER_LAG_DAYS))
        else:
            as_of.setdefault(("officer", r["report_date"]),
                             (r["report_date"], 0))

    factors = {}
    for key, (on, lag) in as_of.items():
        try:
            factors[key] = price_service.get_split_factor(
                company_code, on, register_lag_days=lag)
        except Exception as e:
            logger.warning("分割倍率の取得に失敗 %s %s: %s", company_code, on, e)
            factors[key] = 1.0
    return factors


def _build(rows: List[dict], holder_type: str, factors: Dict[tuple, float]) -> Optional[dict]:
    target = [r for r in rows if r["holder_type"] == holder_type and r["shares"] is not None]
    if not target:
        return None

    dates = sorted({r["report_date"] for r in target})
    if len(dates) < 1:
        return None

    # 期中の報告書から来た列は見出しで区別する。有報と同じ列に混ざると
    # 「1年で半分売った」ように見えてしまう
    interim = {r["report_date"] for r in target if r["report_type"] != "annual"}
    columns = [{"date": d, "interim": d in interim} for d in dates]

    by_name: Dict[str, Dict[str, float]] = {}
    # 表示名は一番新しい報告書の書き方に合わせる
    display: Dict[str, str] = {}
    for r in sorted(target, key=lambda r: r["report_date"]):
        key = _name_key(r["holder_name"])
        adjusted = r["shares"] * factors.get((holder_type, r["report_date"]), 1.0)
        by_name.setdefault(key, {})[r["report_date"]] = adjusted
        display[key] = r["holder_name"]

    people = []
    for key, per_date in by_name.items():
        name = display[key]
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
    return {"dates": dates, "columns": columns, "has_interim": bool(interim),
            "people": people[:MAX_HOLDERS],
            "truncated": max(0, len(people) - MAX_HOLDERS)}


def get_holdings_history(company_code) -> Optional[dict]:
    """大株主と役員それぞれの持株推移。データが無ければ None"""
    rows = _rows(company_code)
    if not rows:
        return None

    factors = _split_factors(str(company_code).strip(), rows)
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
            "split_adjusted": split_adjusted,
            "has_interim": bool(major and major["has_interim"])}
