"""株価の日足と、そこから求めるPERの時系列を提供する。

yfinance から取得した生の四本値をディスクにキャッシュし、株式分割の補正を
かけてから返す。PERは EDINET から取り込んだEPS（SQLiteインデックス）と
突き合わせて日次で算出する。

株価も財務も外部依存なので、取得できない場合は空を返して呼び出し側で
「データなし」と出せるようにしてある。
"""
from __future__ import annotations

import csv
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from visualizer import db as _index_db

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "data", "cache", "prices")

# キャッシュの有効期間（秒）。日足なので日中に何度も取りに行く必要はない
CACHE_TTL = 6 * 60 * 60

CACHE_COLUMNS = ["date", "open", "high", "low", "close", "volume", "split"]

# yfinanceへの同時アクセスを避ける（複数タブから同じページを開かれた時用）
_fetch_lock = threading.Lock()


def _cache_path(code: str) -> str:
    return os.path.join(CACHE_DIR, f"{code}.tsv")


def _read_cache(code: str) -> Optional[List[dict]]:
    path = _cache_path(code)
    if not os.path.exists(path):
        return None
    if time.time() - os.path.getmtime(path) > CACHE_TTL:
        return None
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f, delimiter="\t"))
    except OSError as e:
        logger.warning("株価キャッシュの読み込みに失敗 %s: %s", path, e)
        return None


def _write_cache(code: str, rows: List[dict]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(code)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CACHE_COLUMNS, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("株価キャッシュの書き込みに失敗 %s: %s", path, e)


def _symbol(code: str) -> str:
    """yfinanceのシンボルにする。^N225 のような指数はそのまま使う"""
    return code if code.startswith("^") else f"{code}.T"


def _fetch(code: str) -> List[dict]:
    """yfinanceから日足を取る。auto_adjust=False で生値と分割イベントを受け取る"""
    import yfinance as yf

    with _fetch_lock:
        hist = yf.Ticker(_symbol(code)).history(period="max", auto_adjust=False)

    rows = []
    for index, row in hist.iterrows():
        close = row.get("Close")
        if close is None or close != close:  # NaN
            continue
        rows.append({
            "date": index.strftime("%Y-%m-%d"),
            "open": row.get("Open"),
            "high": row.get("High"),
            "low": row.get("Low"),
            "close": close,
            "volume": row.get("Volume"),
            "split": row.get("Stock Splits") or 0,
        })
    return rows


def _to_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _split_factors(rows: List[dict]) -> List[float]:
    """各日について「その日より後に起きた分割」の累積倍率を返す。

    Yahooの四本値と出来高は取得時点で既に分割調整済みなので、株価側では使わない。
    使うのはEPSの調整だけ。有価証券報告書のEPSは発表当時の1株あたりの金額で、
    その後に分割があっても遡って直されないため、株価と株数の基準を揃える必要がある。
    """
    factors = [1.0] * len(rows)
    running = 1.0
    for i in range(len(rows) - 1, -1, -1):
        factors[i] = running
        split = _to_float(rows[i].get("split")) or 0
        if split and split > 0:
            running *= split
    return factors


def get_price_series(code: str) -> Dict[str, list]:
    """分割調整済みの日足を返す。取得できなければ空の系列を返す"""
    rows = _read_cache(code)
    if rows is None:
        try:
            rows = _fetch(code)
        except Exception as e:
            logger.warning("株価の取得に失敗 %s: %s", code, e)
            rows = []
        if rows:
            _write_cache(code, rows)

    rows = [r for r in rows if _to_float(r.get("close")) is not None]
    if not rows:
        return {"dates": [], "open": [], "high": [], "low": [], "close": [], "volume": []}

    # Yahooの四本値・出来高は取得時点で分割調整済みなので、ここでは触らない
    out = {"dates": [], "open": [], "high": [], "low": [], "close": [], "volume": []}
    for row in rows:
        out["dates"].append(row["date"])
        for key in ("open", "high", "low", "close"):
            value = _to_float(row.get(key))
            out[key].append(None if value is None else round(value, 2))
        volume = _to_float(row.get("volume"))
        out["volume"].append(None if volume is None else int(volume))
    return out


def _eps_history(code: str) -> List[dict]:
    """有価証券報告書の当期EPSを、報告日の昇順で返す。

    連結（CurrentYearDuration）を優先し、無ければ個別を使う。
    同じ報告日に複数あるときは1件に絞る。
    """
    conn = _index_db.get_conn()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """SELECT report_date, context_id, value
               FROM financial_metrics
               WHERE company_code = ?
                 AND element_id LIKE '%BasicEarningsLossPerShare%'
                 AND relative_period = '当期'
               ORDER BY report_date""",
            (code,),
        ).fetchall()
    except Exception as e:
        logger.warning("EPSの取得に失敗 %s: %s", code, e)
        return []

    by_date: Dict[str, dict] = {}
    for row in rows:
        eps = _to_float(row["value"])
        if eps is None:
            continue
        date = row["report_date"]
        consolidated = "NonConsolidated" not in (row["context_id"] or "")
        current = by_date.get(date)
        # 連結を優先。同条件なら先に出たものを使う
        if current is None or (consolidated and not current["consolidated"]):
            by_date[date] = {"date": date, "eps": eps, "consolidated": consolidated}
    return [by_date[d] for d in sorted(by_date)]


def get_per_series(code: str, prices: Dict[str, list]) -> Dict[str, list]:
    """日ごとのPER（終値 / 直近実績EPS）を返す。

    EPSは発表時点の1株あたりなので、その後の分割で株数が変わっていれば
    株価と同じ倍率で割って揃える。EPSが0以下の期間はPERを出さない。
    """
    dates = prices.get("dates") or []
    if not dates:
        return {"dates": [], "per": []}

    eps_rows = _eps_history(code)
    if not eps_rows:
        return {"dates": [], "per": []}

    # 生の株価を再度読み、EPS報告日時点の分割倍率を求める
    raw = _read_cache(code) or []
    factors = _split_factors(raw)
    factor_by_date = {r["date"]: f for r, f in zip(raw, factors)}

    def factor_at(date: str) -> float:
        """その日以前で最も近い営業日の倍率。無ければ最古の倍率"""
        if date in factor_by_date:
            return factor_by_date[date]
        earlier = [d for d in factor_by_date if d <= date]
        if earlier:
            return factor_by_date[max(earlier)]
        return factors[0] if factors else 1.0

    for row in eps_rows:
        row["adjusted_eps"] = row["eps"] / factor_at(row["date"])

    per = []
    index = 0
    current_eps = None
    for date, close in zip(dates, prices.get("close") or []):
        while index < len(eps_rows) and eps_rows[index]["date"] <= date:
            current_eps = eps_rows[index]["adjusted_eps"]
            index += 1
        if close is None or not current_eps or current_eps <= 0:
            per.append(None)
        else:
            per.append(round(close / current_eps, 2))

    return {"dates": dates, "per": per}


def get_latest_per(code: str) -> Optional[float]:
    """直近のPER。株価かEPSが無ければ None"""
    prices = get_price_series(code)
    if not prices["dates"]:
        return None
    per = get_per_series(code, prices)["per"]
    for value in reversed(per):
        if value is not None:
            return value
    return None


def get_lockup_markers(code: str) -> List[dict]:
    """ロックアップ解除の目安を返す。

    上場日から30日後・180日後と、初値の1.5倍に最初に到達した日。
    いずれも売り圧力が出やすい（＝押し目になりやすい）地点として
    株価チャートに縦線で示す。
    """
    from visualizer import tenbagger_criteria as _criteria

    row = _criteria.get_company_row(code)
    if not row:
        return []

    raw = str(row.get("上場日") or "").strip()
    listing = None
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y年%m月%d日"):
        try:
            listing = datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue
    if listing is None:
        return []

    markers = [
        {"date": (listing + timedelta(days=30)).strftime("%Y-%m-%d"),
         "label": "ロックアップ解除の目安（上場30日後）", "short": "LU30"},
        {"date": (listing + timedelta(days=180)).strftime("%Y-%m-%d"),
         "label": "ロックアップ解除の目安（上場180日後）", "short": "LU180"},
    ]

    initial = _to_float(row.get("初値"))
    if initial and initial > 0:
        prices = get_price_series(code)
        target = initial * 1.5
        for date, high in zip(prices["dates"], prices["high"]):
            if high is not None and high >= target:
                markers.append({
                    "date": date,
                    "label": f"初値の1.5倍（{target:,.0f}円）に到達",
                    "short": "1.5倍",
                })
                break

    last = None
    prices = get_price_series(code)
    if prices["dates"]:
        last = prices["dates"][-1]
    # チャートの範囲外になる目安は出さない
    return [m for m in markers if last is None or m["date"] <= last]


def get_nikkei_series(dates: List[str]) -> List[Optional[float]]:
    """日経平均を、対象銘柄の日付に合わせて返す。

    市場全体が下げているのか、その銘柄だけが下げているのかを見分けるために重ねる。
    水準が違いすぎて同じ軸には乗らないので、期間先頭を100とした指数にする。
    """
    if not dates:
        return []
    nikkei = get_price_series("^N225")
    if not nikkei["dates"]:
        return []

    close_by_date = {d: c for d, c in zip(nikkei["dates"], nikkei["close"]) if c is not None}
    out: List[Optional[float]] = []
    last = None
    for date in dates:
        value = close_by_date.get(date)
        if value is not None:
            last = value
        out.append(last)
    return out


def get_chart_payload(code: str) -> Dict[str, object]:
    """フロントに渡す一式"""
    prices = get_price_series(code)
    per = get_per_series(code, prices) if prices["dates"] else {"dates": [], "per": []}
    nikkei = get_nikkei_series(prices["dates"]) if prices["dates"] else []
    return {
        "code": code,
        "prices": prices,
        "per": per["per"],
        "nikkei": nikkei,
        "lockup": get_lockup_markers(code),
        "per_limit": 40,
        "per_ideal": 20,
        "has_price": bool(prices["dates"]),
        "has_per": any(v is not None for v in per["per"]),
        "has_nikkei": any(v is not None for v in nikkei),
    }
