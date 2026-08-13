"""財務指標の比較を「専門家の見方」に近づけるための材料を出す。

指標を縦に並べるだけだと、書けることが「売上が伸びている」で止まる。
実際に効くのは**指標の組み合わせ**と**比較の相手**で、そこは並べただけでは
出てこない。ここでは4つ足す。

1. 所見 … 組み合わせでしか読めないものを機械で当てる
     売上↑ なのに 利益率↓ → 成長を買っているだけかもしれない
     ROE↑ なのに ROA→   → 借入で嵩上げしている
     営業CF ÷ 営業利益 < 1 が続く → 利益が現金になっていない
2. 業種の中央値 … 営業利益率23.8%が高いのかは業種で変わる
3. **10倍株の同じ上場年次** … このリポジトリの最大の資産。
     実際に10倍になった106社が、上場N年目にどういう数字だったか
4. データの欠け・異常 … 比較できていないことを知らずに比べない

  python collectors/metric_diagnose.py 212A
"""
from __future__ import annotations

import statistics
from datetime import datetime
from typing import Dict, List, Optional

from visualizer import db as _index_db

# 業種・10倍株との比較に使う指標。要素IDから直に引ける単純なものだけにする。
# 比率は下で組み立てる
_BENCH_IDS = {
    "売上高": ("jpcrp_cor:NetSalesSummaryOfBusinessResults",
               "jpcrp_cor:RevenueIFRSSummaryOfBusinessResults"),
    "営業利益": ("jppfs_cor:OperatingIncome",),
    "総資産": ("jpcrp_cor:TotalAssetsSummaryOfBusinessResults",),
    "純資産": ("jpcrp_cor:NetAssetsSummaryOfBusinessResults",),
    "ROE": ("jpcrp_cor:RateOfReturnOnEquitySummaryOfBusinessResults",),
    "自己資本比率": ("jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResults",),
    "営業CF": ("jpcrp_cor:NetCashProvidedByUsedInOperatingActivitiesSummaryOfBusinessResults",),
}

TENBAGGER_MIN = 10.0


def _num(value) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _company(code: str) -> Optional[dict]:
    conn = _index_db.get_conn()
    if conn is None:
        return None
    row = conn.execute(
        "SELECT code, name, ipo_date, ipo_year, market, sector, industry, "
        "max_multiple, current_multiple FROM companies WHERE code = ?",
        (str(code).strip(),)).fetchone()
    return dict(row) if row else None


def _latest_values(codes: List[str]) -> Dict[str, Dict[str, float]]:
    """{銘柄コード: {指標名: 直近の値}}。当期の行のうち提出日が最新のもの"""
    conn = _index_db.get_conn()
    if conn is None or not codes:
        return {}
    ids = [i for group in _BENCH_IDS.values() for i in group]
    out: Dict[str, Dict[str, float]] = {}
    seen: Dict[tuple, str] = {}
    q = (f"SELECT company_code, element_id, report_date, value "
         f"FROM financial_metrics "
         f"WHERE relative_period = '当期' "
         f"AND element_id IN ({','.join('?' * len(ids))}) "
         f"AND company_code IN ({','.join('?' * len(codes))})")
    for code, element, date, value in conn.execute(q, ids + list(codes)):
        name = next((n for n, group in _BENCH_IDS.items() if element in group), None)
        v = _num(value)
        if name is None or v is None:
            continue
        key = (code, name)
        if key in seen and seen[key] >= date:
            continue
        seen[key] = date
        out.setdefault(code, {})[name] = v
    for values in out.values():
        if values.get("売上高"):
            values["営業利益率"] = (values.get("営業利益") or 0) / values["売上高"] * 100
        if values.get("営業利益"):
            values["利益の質"] = (values.get("営業CF") or 0) / values["営業利益"]
    return out


def _values_at_year(codes: List[str], years_after_ipo: int,
                    ipo_year: Dict[str, int]) -> Dict[str, Dict[str, float]]:
    """上場N年目の値。暦年で並べると2011年上場と2024年上場が同じ軸に乗って読めない"""
    conn = _index_db.get_conn()
    if conn is None or not codes:
        return {}
    ids = [i for group in _BENCH_IDS.values() for i in group]
    out: Dict[str, Dict[str, float]] = {}
    q = (f"SELECT company_code, element_id, report_date, value "
         f"FROM financial_metrics "
         f"WHERE relative_period = '当期' "
         f"AND element_id IN ({','.join('?' * len(ids))}) "
         f"AND company_code IN ({','.join('?' * len(codes))})")
    for code, element, date, value in conn.execute(q, ids + list(codes)):
        base = ipo_year.get(code)
        if not base or not date:
            continue
        if int(date[:4]) - base != years_after_ipo:
            continue
        name = next((n for n, group in _BENCH_IDS.items() if element in group), None)
        v = _num(value)
        if name is None or v is None:
            continue
        out.setdefault(code, {}).setdefault(name, v)
    for values in out.values():
        if values.get("売上高"):
            values["営業利益率"] = (values.get("営業利益") or 0) / values["売上高"] * 100
        if values.get("営業利益"):
            values["利益の質"] = (values.get("営業CF") or 0) / values["営業利益"]
    return out


def _median(values: Dict[str, Dict[str, float]], name: str) -> Optional[tuple]:
    got = [v[name] for v in values.values() if v.get(name) is not None]
    if len(got) < 5:
        return None
    return statistics.median(got), len(got)


def _rank(value: Optional[float], values: Dict[str, Dict[str, float]],
          name: str) -> str:
    if value is None:
        return ""
    got = sorted(v[name] for v in values.values() if v.get(name) is not None)
    if len(got) < 5:
        return ""
    above = sum(1 for g in got if g > value)
    return f"上位{above / len(got):.0%}"


def _series(metrics: dict, name: str) -> List[tuple]:
    got = {k: v for k, v in (metrics.get(name) or {}).items() if v is not None}
    return sorted(got.items())


def _growth(series: List[tuple]) -> List[tuple]:
    out = []
    for (_, before), (date, after) in zip(series, series[1:]):
        if before and before > 0:
            out.append((date, (after - before) / before * 100))
    return out


def findings(metrics: dict) -> List[str]:
    """組み合わせでしか読めないものを当てる。断定はせず、確かめる場所を示す"""
    out = []

    sales = _series(metrics, "売上高")
    margin = _series(metrics, "営業利益率")
    if len(sales) >= 3 and len(margin) >= 3:
        sales_up = sales[-1][1] > sales[-3][1]
        margin_down = margin[-1][1] < margin[-3][1]
        if sales_up and margin_down:
            out.append(f"⚠ 売上は伸びているが営業利益率は下がっている"
                       f"（{margin[-3][0][:7]} {margin[-3][1] * 100:.1f}% → "
                       f"{margin[-1][0][:7]} {margin[-1][1] * 100:.1f}%）。"
                       f"成長を買っているだけかもしれない")

    growth = _growth(sales)
    if len(growth) >= 3:
        last3 = [g for _, g in growth[-3:]]
        if last3[0] > last3[1] > last3[2]:
            out.append(f"⚠ 売上の伸びが3期続けて鈍っている"
                       f"（{last3[0]:+.0f}% → {last3[1]:+.0f}% → {last3[2]:+.0f}%）")
        elif last3[2] > last3[1] > last3[0]:
            out.append(f"✓ 売上の伸びが3期続けて加速している"
                       f"（{last3[0]:+.0f}% → {last3[1]:+.0f}% → {last3[2]:+.0f}%）")

    roe = _series(metrics, "ROE（自己資本利益率）")
    roa = _series(metrics, "ROA（総資産利益率）")
    equity = _series(metrics, "自己資本比率")
    if roe and roa and equity:
        r, a, e = roe[-1][1], roa[-1][1], equity[-1][1]
        if r > 0.15 and a < r / 3:
            out.append(f"⚠ ROE {r * 100:.1f}% に対しROAは {a * 100:.1f}%。"
                       f"自己資本比率 {e * 100:.1f}%。借入で嵩上げされている可能性")
        elif r > 0.15 and a >= r / 3:
            out.append(f"✓ ROE {r * 100:.1f}%、ROA {a * 100:.1f}%、"
                       f"自己資本比率 {e * 100:.1f}%。借入で嵩上げした高ROEではない")

    quality = _series(metrics, "利益の質（営業CF÷営業利益）")
    if quality:
        low = [d for d, v in quality if v < 1.0]
        if len(low) >= 2 and quality[-1][1] < 1.0:
            out.append(f"⚠ 営業CFが営業利益に届いていない期が{len(low)}／{len(quality)}期"
                       f"（直近 {quality[-1][1]:.2f}）。利益が現金になっているかを確かめる")
        elif quality[-1][1] >= 1.0:
            out.append(f"✓ 営業CFは営業利益を上回っている（直近 {quality[-1][1]:.2f}）")

    debt = _series(metrics, "有利子負債")
    cash = _series(metrics, "現金及び現金同等物")
    if debt and cash:
        d, c = debt[-1][1], cash[-1][1]
        if c > d:
            out.append(f"✓ 現金 {c / 1e6:,.0f}百万 が有利子負債 {d / 1e6:,.0f}百万 を"
                       f"上回っており実質無借金")
        else:
            out.append(f"⚠ 有利子負債 {d / 1e6:,.0f}百万 が現金 {c / 1e6:,.0f}百万 を"
                       f"上回っている。成長が止まったときに効く")

    shares = _series(metrics, "発行済株式数")
    if len(shares) >= 3 and shares[0][1]:
        change = (shares[-1][1] - shares[-3][1]) / shares[-3][1] * 100
        if change > 5:
            out.append(f"⚠ 発行済株式数が直近2期で {change:+.1f}%。"
                       f"分割でなければ1株あたりが薄まっている")

    temp = _series(metrics, "臨時雇用の比率")
    if temp and temp[-1][1] > 0.3:
        out.append(f"⚠ 臨時雇用が総人員の {temp[-1][1] * 100:.0f}%。"
                   f"「従業員一人当たり営業利益」は正社員だけで割っているので"
                   f"実態より良く出る。総人員あたりで見る")

    inventory = _series(metrics, "在庫の伸び − 売上の伸び")
    if inventory:
        bad = [d for d, v in inventory[-3:] if v > 0]
        if len(bad) >= 2:
            out.append(f"⚠ 在庫の伸びが売上の伸びを上回る期が直近3期で{len(bad)}回。"
                       f"売れ残りが積み上がっていないか")

    return out


def diagnose(code: str, metrics: dict) -> dict:
    """所見・業種の中央値・10倍株との比較・データの欠けをまとめる"""
    info = _company(code) or {}
    conn = _index_db.get_conn()
    result = {"info": info, "findings": findings(metrics),
              "sector": [], "tenbagger": [], "gaps": []}
    if conn is None:
        return result

    mine = _latest_values([str(code).strip()]).get(str(code).strip(), {})

    # 同じ業種の中央値
    sector = (info.get("sector") or "").strip()
    if sector and sector not in ("nan", "Unknown"):
        peers = [r[0] for r in conn.execute(
            "SELECT code FROM companies WHERE sector = ? AND code != ?",
            (sector, str(code).strip()))]
        values = _latest_values(peers)
        for name in ("売上高", "営業利益率", "ROE", "自己資本比率", "利益の質"):
            got = _median(values, name)
            if not got:
                continue
            median, n = got
            result["sector"].append({
                "name": name, "mine": mine.get(name), "median": median,
                "n": n, "rank": _rank(mine.get(name), values, name)})
        result["sector_name"] = f"{sector} {len(values)}社"

    # 10倍になった会社の、同じ上場年次
    ipo_year = info.get("ipo_year")
    if ipo_year:
        years_after = min(max(datetime.now().year - int(ipo_year), 1), 10)
        rows = list(conn.execute(
            "SELECT code, ipo_year FROM companies "
            "WHERE max_multiple >= ? AND ipo_year IS NOT NULL", (TENBAGGER_MIN,)))
        base = {r[0]: int(r[1]) for r in rows if r[1]}
        values = _values_at_year(list(base), years_after, base)
        for name in ("売上高", "営業利益率", "ROE", "自己資本比率", "利益の質"):
            got = _median(values, name)
            if not got:
                continue
            median, n = got
            result["tenbagger"].append({
                "name": name, "mine": mine.get(name), "median": median, "n": n})
        result["tenbagger_label"] = (
            f"最大10倍以上になった{len(base)}社の、上場{years_after}年目"
            f"（データが揃ったのは{len(values)}社）")
        result["years_after"] = years_after

    # 欠け・異常
    # 「取れていない」ではなく「グラフに出ていない」と書く。インデックスには
    # あるのに DataService の文脈判定で落ちることがあり、下の中央値の表には
    # 出てくるので、断定すると食い違って見える
    for name in ("営業キャッシュフロー", "現金及び現金同等物", "売上総利益率",
                 "有利子負債", "平均臨時雇用人員", "発行済株式数"):
        if not (metrics.get(name) or {}):
            result["gaps"].append(f"{name} のグラフが出ていない（この銘柄では比較できない）")
    for name, series in metrics.items():
        if not isinstance(series, dict) or len(series) < 3:
            continue
        items = sorted((k, v) for k, v in series.items() if v is not None)
        dupes = [b[0] for a, b in zip(items, items[1:]) if a[1] == b[1] and a[1]]
        if dupes:
            result["gaps"].append(
                f"{name} に同じ値が続く期がある（{dupes[0][:10]}）。期の重複を疑う")
    return result
