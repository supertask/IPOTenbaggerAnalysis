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
CAPEX_TSV = os.path.join(BASE_DIR, "data", "output", "facilities", "capex.tsv")
COST_TSV = os.path.join(
    BASE_DIR, "data", "output", "facilities", "cost_structure.tsv")

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


_capex_cache: Optional[Dict[str, Dict[str, float]]] = None
_capex_mtime: Optional[float] = None
# 「設備の新設計画」に書かれた1店舗あたりの投資予定額。_load_capex が埋める
_planned_cache: Dict[str, dict] = {}


def _load_capex() -> Dict[str, Dict[str, float]]:
    """{銘柄コード: {報告日: 設備投資額（百万円）}}"""
    global _capex_cache, _capex_mtime
    if not os.path.exists(CAPEX_TSV):
        return {}
    mtime = os.path.getmtime(CAPEX_TSV)
    if _capex_cache is not None and _capex_mtime == mtime:
        return _capex_cache

    data: Dict[str, Dict[str, float]] = {}
    planned: Dict[str, dict] = {}
    try:
        with open(CAPEX_TSV, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                amount = _num(row.get("設備投資額_百万円"))
                if amount is not None:
                    data.setdefault(row["コード"], {})[row["報告日"]] = amount
                per_store = _num(row.get("計画_1店舗あたり_百万円"))
                if per_store:
                    # 新しい報告日のものを残す
                    current = planned.get(row["コード"])
                    if current is None or row["報告日"] > current["date"]:
                        planned[row["コード"]] = {
                            "date": row["報告日"],
                            "per_store": per_store,
                            "total": _num(row.get("計画_投資額_百万円")),
                            "stores": _num(row.get("計画_店舗数")),
                        }
    except OSError as e:
        logger.warning("設備投資額を読めませんでした: %s", e)
        return {}
    _planned_cache.clear()
    _planned_cache.update(planned)

    _capex_cache, _capex_mtime = data, mtime
    return data


_cost_cache: Optional[Dict[str, dict]] = None
_cost_mtime: Optional[float] = None


def _load_cost_structure() -> Dict[str, dict]:
    """{銘柄コード: 直近期の原価の構成}"""
    global _cost_cache, _cost_mtime
    if not os.path.exists(COST_TSV):
        return {}
    mtime = os.path.getmtime(COST_TSV)
    if _cost_cache is not None and _cost_mtime == mtime:
        return _cost_cache

    latest: Dict[str, dict] = {}
    try:
        with open(COST_TSV, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                code = row["コード"]
                current = latest.get(code)
                if current and row["報告日"] <= current["date"]:
                    continue
                cost = _num(row.get("売上原価_百万円"))
                labor = _num(row.get("労務費_百万円"))
                latest[code] = {
                    "date": row["報告日"],
                    "cost_ratio": _num(row.get("原価率_％")),
                    "purchase_ratio": _num(row.get("仕入高対原価_％")),
                    "purchase": _num(row.get("仕入高_百万円")),
                    "labor": labor,
                    "labor_ratio": (labor / cost * 100
                                    if labor is not None and cost else None),
                }
    except OSError as e:
        logger.warning("原価の構成を読めませんでした: %s", e)
        return {}

    _cost_cache, _cost_mtime = latest, mtime
    return latest


def _opening_cost(code: str, points: List[dict]) -> Optional[dict]:
    """1拠点あたりの出店額。設備投資額 ÷ その期に増えた拠点数

    拠点が減った期や、増加が無い期は計算できない。設備投資には本社や
    システムへの投資も含まれるので、出店だけの費用ではない点に注意。
    """
    capex = _load_capex().get(code) or {}
    if len(points) < 2 or not capex:
        return None

    samples = []
    for previous, current in zip(points, points[1:]):
        added = current["count"] - previous["count"]
        amount = capex.get(current["date"])
        if amount is None or added <= 0:
            continue
        samples.append({
            "date": current["date"],
            "added": added,
            "capex": amount,
            "per_new": amount / added,
        })
    if not samples:
        return None

    values = sorted(s["per_new"] for s in samples)
    middle = (values[len(values) // 2] if len(values) % 2
              else (values[len(values) // 2 - 1] + values[len(values) // 2]) / 2)
    return {"samples": samples[-5:], "median": middle, "count": len(samples)}


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

    # 出店単価。安く出せているかを見る材料
    _load_capex()
    opening = _opening_cost(code, own["points"])
    planned = _planned_cache.get(code)
    peer_openings = []
    for peer in peers:
        series = _series(peer["code"], data[peer["code"]], financials)
        cost = _opening_cost(peer["code"], series["points"]) if series else None
        if cost:
            peer_openings.append({"name": peer["name"], "median": cost["median"]})

    # 原価の構成。拠点数に依存しないので、拠点数の定義揺れの影響を受けずに比べられる
    costs = _load_cost_structure()
    own_cost = costs.get(code)
    peer_costs = []
    for peer in (competitors or []):
        peer_code = str(peer.get("code") or "").strip()
        entry = costs.get(peer_code)
        if entry and entry.get("cost_ratio") is not None:
            peer_costs.append({"name": peer.get("name") or peer_code, **entry})

    return {
        "own": own,
        "peers": sorted(peers, key=lambda p: -(p["latest"]["profit_per"] or 0)),
        "ratio_to_peers": ratio,
        "has_series": len(own["points"]) >= 2,
        "opening_cost": opening,
        "planned_cost": planned,
        "peer_opening_costs": sorted(peer_openings, key=lambda p: p["median"]),
        "cost_structure": own_cost,
        "peer_cost_structures": sorted(peer_costs, key=lambda p: p["cost_ratio"]),
    }
