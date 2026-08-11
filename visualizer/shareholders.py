"""株主構成を詳細ページ向けに整形する。

元データは all_companies の「株主名と比率」（各株主の比率とロックアップ条件）と、
社長・役員・VCなどの区分ごとの保有比率。
"""
from __future__ import annotations

import json
from typing import Optional

from visualizer import tenbagger_criteria as _criteria

# (列名, 表示名, バッジの色)
SUMMARY_FIELDS = [
    ("社長_株%", "社長", "bg-primary"),
    ("役員_株%", "役員", "bg-secondary"),
    ("家族_株%", "家族", "bg-secondary"),
    ("親会社_株%", "親会社", "bg-info text-dark"),
    ("従業員_株%", "従業員", "bg-secondary"),
    ("VC_ファンド_株%", "VC・ファンド", "bg-warning text-dark"),
]


def _num(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def get_shareholders(company_code) -> Optional[dict]:
    row = _criteria.get_company_row(company_code)
    if not row:
        return None

    summary = []
    for key, label, css in SUMMARY_FIELDS:
        value = _num(row.get(key))
        if value:
            summary.append((label, value, css))

    raw = row.get("株主名と比率")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = []

    rows = []
    for s in raw or []:
        ratio = _num(s.get("比率"))
        if ratio is None:
            continue
        lockup = str(s.get("ロックアップ") or "").strip()
        rows.append({
            "name": s.get("株主名") or "",
            "ratio": ratio,
            "lockup": "" if lockup in ("None", "なし") else lockup,
            "is_ceo": bool(s.get("isCEO")),
        })
    rows.sort(key=lambda r: -r["ratio"])

    if not summary and not rows:
        return None
    return {"summary": summary, "rows": rows}
