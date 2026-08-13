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
# 本文からの自動抽出を人が上書きするファイル。保有銘柄だけ埋めている
OVERRIDE_TSV = os.path.join(BASE_DIR, "data", "meta", "facility_override.tsv")
# 期中の報告書から拾った拠点数。保有銘柄のみ（期中の書類をそれしか落としていない）
INTERIM_TSV = os.path.join(
    BASE_DIR, "data", "output", "facilities", "facility_counts_interim.tsv")
CAPEX_TSV = os.path.join(BASE_DIR, "data", "output", "facilities", "capex.tsv")
COST_TSV = os.path.join(
    BASE_DIR, "data", "output", "facilities", "cost_structure.tsv")

SALES_IDS = ("jpcrp_cor:NetSalesSummaryOfBusinessResults",
             "jpcrp_cor:RevenueIFRSSummaryOfBusinessResults")
# 後ろにあるものほど優先する。IFRSの会社は jppfs（日本基準）が提出会社の単体に
# なるので、連結の営業利益を先に採る。経常利益は営業利益が取れないときの
# 最後の手当てで、営業利益と混ざると1拠点あたりが別物になる
PROFIT_IDS = ("jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults",
              "jppfs_cor:OperatingIncome",
              "jpigp_cor:OperatingProfitLossIFRS")
_PROFIT_RANK = {element: index for index, element in enumerate(PROFIT_IDS)}
_SALES_RANK = {element: index for index, element in enumerate(SALES_IDS)}

_cache: Optional[Dict[str, Dict[str, dict]]] = None
_cache_mtime: Optional[float] = None


def _sane_share(value: Optional[float], cost: Optional[float]) -> Optional[float]:
    """売上原価の内訳として筋が通らない値を落とす。

    売上原価明細書は本文からの抽出なので、別の行の数字を掴むことがある。
    サンウェルズは売上264億に対し労務費91.6兆円という値が入っていた。
    仕入高は在庫を積めば売上原価を超えうるが、そこまで大きくは離れない。
    """
    if value is None or not cost or value <= 0:
        return None
    return value if value <= cost * 1.2 else None


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

    _apply_overrides(data)
    _cache, _cache_mtime = data, mtime
    return data


def _apply_overrides(data: Dict[str, Dict[str, dict]]) -> None:
    """人が確かめた拠点数で上書きする。

    本文からの抽出は「導入先の店舗数」や「新規開設数」を自社の拠点として
    拾うことがあり、数字だけでは自社のものか判別できない。保有銘柄は
    有報を読んで確かめた値をここに置き、抽出より優先する。
    拠点数を空にした行は、拠点あたりの採算が意味を持たない業態として外す。
    """
    if not os.path.exists(OVERRIDE_TSV):
        return
    try:
        with open(OVERRIDE_TSV, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
    except OSError as e:
        logger.warning("拠点数の上書きを読めませんでした: %s", e)
        return

    for row in rows:
        code = (row.get("コード") or "").strip()
        if not code:
            continue
        count = _num(row.get("拠点数"))
        date = (row.get("報告日") or "").strip()
        if count is None:
            # 業態として拠点あたりを出さない
            data.pop(code, None)
            continue
        if not date:
            # 報告日の指定が無ければ、抽出できている一番新しい期を差し替える
            existing = data.get(code)
            if not existing:
                continue
            date = max(existing)
        data.setdefault(code, {})[date] = {
            "count": count,
            "unit": (row.get("単位") or "拠点").strip(),
            "sources": "本文（読んで確認した値）",
            "candidates": "",
        }


_interim_cache: Optional[Dict[str, Dict[str, dict]]] = None
_interim_mtime: Optional[float] = None


def _load_interim() -> Dict[str, Dict[str, dict]]:
    """期中の報告書から拾った拠点数。有報より新しい数字が分かる"""
    global _interim_cache, _interim_mtime
    if not os.path.exists(INTERIM_TSV):
        return {}
    mtime = os.path.getmtime(INTERIM_TSV)
    if _interim_cache is not None and _interim_mtime == mtime:
        return _interim_cache

    data: Dict[str, Dict[str, dict]] = {}
    try:
        with open(INTERIM_TSV, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                count = _num(row.get("拠点数"))
                if not count:
                    continue
                data.setdefault(row["コード"], {})[row["報告日"]] = {
                    "count": count,
                    "unit": (row.get("単位") or "拠点").strip(),
                    "sources": (row.get("出所") or "").strip(),
                }
    except OSError as e:
        logger.warning("期中の拠点数を読めませんでした: %s", e)
        return {}

    _interim_cache, _interim_mtime = data, mtime
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
                labor = _sane_share(_num(row.get("労務費_百万円")), cost)
                purchase = _sane_share(_num(row.get("仕入高_百万円")), cost)
                latest[code] = {
                    "date": row["報告日"],
                    # 原価率はXBRLのタグ付き値なので、内訳が壊れていても使える
                    "cost_ratio": _num(row.get("原価率_％")),
                    "purchase_ratio": (purchase / cost * 100
                                       if purchase is not None and cost else None),
                    "purchase": purchase,
                    "labor": labor,
                    "labor_ratio": (labor / cost * 100
                                    if labor is not None and cost else None),
                }
    except OSError as e:
        logger.warning("原価の構成を読めませんでした: %s", e)
        return {}

    _cost_cache, _cost_mtime = latest, mtime
    return latest


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
        sales = row["element_id"] in SALES_IDS
        key = "sales" if sales else "profit"
        rank = (_SALES_RANK if sales else _PROFIT_RANK).get(row["element_id"], 0)
        bucket = out.setdefault(row["company_code"], {}).setdefault(row["report_date"], {})
        # まず優先度（IFRSの連結 > 日本基準の営業利益 > 経常利益）、
        # 同じ優先度なら大きいほう（連結と単体が並ぶので連結が残る）
        current = bucket.get(f"_{key}_rank")
        if current is not None and (rank, value) <= current:
            continue
        bucket[f"_{key}_rank"] = (rank, value)
        bucket[key] = value
    for dates in out.values():
        for bucket in dates.values():
            bucket.pop("_sales_rank", None)
            bucket.pop("_profit_rank", None)
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

    # 期中の報告書から拾った、有報より新しい拠点数。1拠点あたりの計算には
    # 使わない（期中の売上・利益は半期ぶんで、年次の分子と噛み合わない）
    interim = _load_interim().get(code) or {}
    latest_interim = None
    if interim:
        date = max(interim)
        if date > max(data[code]):
            latest_interim = {"date": date, **interim[date]}

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

    # 出店単価は、会社が計画として書いた「投資予定額 ÷ 予定店舗数」だけを使う。
    # 設備投資額 ÷ 増えた拠点数でも計算できるが、フランチャイズ店は加盟企業が
    # 投資するため分母と分子が対応せず、実態と大きくずれる
    # （フィットイージーは実績19百万に対し、会社の計画は114百万）。
    _load_capex()
    planned = _planned_cache.get(code)

    # 原価の構成。拠点数に依存しないので、拠点数の定義揺れの影響を受けずに比べられる
    costs = _load_cost_structure()
    own_cost = costs.get(code)
    peer_costs = []
    for peer in (competitors or []):
        peer_code = str(peer.get("code") or "").strip()
        entry = costs.get(peer_code)
        if entry and entry.get("cost_ratio") is not None:
            peer_costs.append({"name": peer.get("name") or peer_code, **entry})

    # 期中の点は棒だけ描く。1拠点あたりの線は年次の点だけを結ぶ
    interim_points = [{"date": d, "count": v["count"]}
                      for d, v in sorted(interim.items())
                      if d not in data[code]]

    return {
        "own": own,
        "peers": sorted(peers, key=lambda p: -(p["latest"]["profit_per"] or 0)),
        "ratio_to_peers": ratio,
        "latest_interim": latest_interim,
        "interim_points": interim_points,
        "has_series": len(own["points"]) + len(interim_points) >= 2,
        "planned_cost": planned,
        "cost_structure": own_cost,
        "peer_cost_structures": sorted(peer_costs, key=lambda p: p["cost_ratio"]),
    }
