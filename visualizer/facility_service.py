"""拠点数と、拠点あたりの売上・利益を組み立てる。

多店舗展開型のビジネスモデルが実際に効いているかは、拠点を増やしながら
1拠点あたりの採算を保てているかで判断する。拠点数は業態によって桁が違うので
（コンビニと有料老人ホームでは比較にならない）、単体の水準ではなく
競合と並べて見るのが要点。

拠点数は collectors/facility_count_collector.py が有報の本文から取ったもの。
標準化された開示項目ではないため、取れる企業は限られる（約23%）。
"""
from __future__ import annotations

import csv
import logging
import os
from typing import Dict, List, Optional

from visualizer import db as _index_db

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACILITY_TSV = os.path.join(
    BASE_DIR, "data", "output", "facilities", "facility_counts.tsv")

SALES_IDS = ("jpcrp_cor:NetSalesSummaryOfBusinessResults",
             "jpcrp_cor:RevenueIFRSSummaryOfBusinessResults")
PROFIT_IDS = ("jppfs_cor:OperatingIncome",
              "jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults")

_cache: Optional[Dict[str, Dict[str, dict]]] = None
_cache_mtime: Optional[float] = None


def _num(value) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _load() -> Dict[str, Dict[str, dict]]:
    """{銘柄コード: {報告日: {count, unit, sources, candidates}}}"""
    global _cache, _cache_mtime
    if not os.path.exists(FACILITY_TSV):
        return {}
    mtime = os.path.getmtime(FACILITY_TSV)
    if _cache is not None and _cache_mtime == mtime:
        return _cache

    data: Dict[str, Dict[str, dict]] = {}
    try:
        with open(FACILITY_TSV, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                count = _num(row.get("拠点数"))
                if not count:
                    continue
                data.setdefault(row["コード"], {})[row["報告日"]] = {
                    "count": count,
                    "unit": (row.get("単位") or "拠点").strip(),
                    "sources": (row.get("出所") or "").strip(),
                    "candidates": (row.get("他の候補") or "").strip(),
                }
    except OSError as e:
        logger.warning("拠点数ファイルを読めませんでした: %s", e)
        return {}

    _cache, _cache_mtime = data, mtime
    return data


def _financials(codes) -> Dict[str, Dict[str, Dict[str, float]]]:
    """{銘柄: {報告日: {sales, profit}}}"""
    conn = _index_db.get_conn()
    if conn is None or not codes:
        return {}
    ids = SALES_IDS + PROFIT_IDS
    placeholders = ",".join("?" * len(ids))
    code_marks = ",".join("?" * len(codes))
    out: Dict[str, Dict[str, Dict[str, float]]] = {}
    try:
        rows = conn.execute(
            f"""SELECT company_code, report_date, element_id, value
                FROM financial_metrics
                WHERE relative_period = '当期' AND report_type = 'annual'
                  AND element_id IN ({placeholders})
                  AND company_code IN ({code_marks})""",
            tuple(ids) + tuple(codes),
        ).fetchall()
    except Exception as e:
        logger.warning("業績の取得に失敗: %s", e)
        return {}

    for row in rows:
        value = _num(row["value"])
        if value is None:
            continue
        key = "sales" if row["element_id"] in SALES_IDS else "profit"
        bucket = out.setdefault(row["company_code"], {}).setdefault(row["report_date"], {})
        # 同じ期に複数あるときは大きいほう（連結を優先したい）
        if key not in bucket or value > bucket[key]:
            bucket[key] = value
    return out


def _series(code: str, facilities: dict, financials: dict) -> Optional[dict]:
    dates = sorted(facilities)
    points = []
    for date in dates:
        entry = facilities[date]
        money = (financials.get(code) or {}).get(date) or {}
        count = entry["count"]
        points.append({
            "date": date,
            "count": count,
            "unit": entry["unit"],
            "sales_per": (money["sales"] / count / 1e6
                          if money.get("sales") and count else None),
            "profit_per": (money["profit"] / count / 1e6
                           if money.get("profit") and count else None),
        })
    if not points:
        return None
    latest = points[-1]
    return {
        "points": points,
        "latest": latest,
        "sources": facilities[dates[-1]]["sources"],
        "candidates": facilities[dates[-1]]["candidates"],
    }


def get_facility_view(company_code, competitors: Optional[List[dict]] = None
                      ) -> Optional[dict]:
    """詳細ページ用。拠点数の推移と、競合と並べた拠点あたり指標を返す"""
    data = _load()
    code = str(company_code).strip()
    if code not in data:
        return None

    peer_codes = [str(c.get("code")).strip() for c in (competitors or [])
                  if c.get("code") and str(c.get("code")).strip() in data]
    financials = _financials([code] + peer_codes)

    own = _series(code, data[code], financials)
    if not own:
        return None

    peers = []
    for peer in (competitors or []):
        peer_code = str(peer.get("code") or "").strip()
        if peer_code not in data:
            continue
        series = _series(peer_code, data[peer_code], financials)
        if series and series["latest"]["profit_per"] is not None:
            peers.append({
                "code": peer_code,
                "name": peer.get("name") or peer_code,
                "latest": series["latest"],
            })

    # 競合と比べて何倍か。業態で桁が違うので、水準そのものより比のほうが意味を持つ
    ratio = None
    peer_values = sorted(p["latest"]["profit_per"] for p in peers)
    if peer_values and own["latest"]["profit_per"] is not None:
        middle = peer_values[len(peer_values) // 2] if len(peer_values) % 2 else \
            (peer_values[len(peer_values) // 2 - 1] + peer_values[len(peer_values) // 2]) / 2
        if middle > 0:
            ratio = own["latest"]["profit_per"] / middle

    return {
        "own": own,
        "peers": sorted(peers, key=lambda p: -(p["latest"]["profit_per"] or 0)),
        "ratio_to_peers": ratio,
        "has_series": len(own["points"]) >= 2,
    }
