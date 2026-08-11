"""証券口座のポートフォリオ画面スクリーンショットから保有銘柄を起こすためのモジュール。

画像の読み取り自体は人（またはLLM）が行い、その結果をこのモジュールの
`Holding` として渡すと、評価額・保有割合の計算とTSV出力を行う。

  python -m collectors.portfolio_screenshot_parser

出力先: data/output/portfolio/<name>.tsv
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from typing import List, Optional

OUTPUT_DIR = os.path.join("data", "output", "portfolio")

# TSVの列順
COLUMNS = [
    "銘柄コード",
    "銘柄名",
    "保有株数",
    "取得単価",
    "現在値",
    "評価額",
    "評価損益",
    "保有割合%",
    "口座区分",
]


@dataclass
class Holding:
    """1銘柄の保有情報。数量・価格が読み取れない場合は None を入れる。

    投資信託は「口数」と「1万口あたりの基準価額」で表示されるため、
    unit_divisor に 10000 を指定する（株式は既定の 1 のまま）。
    """

    code: str
    name: str
    shares: Optional[int]
    avg_cost: Optional[float]
    price: Optional[float]
    profit: Optional[int] = None
    accounts: List[str] = field(default_factory=list)
    note: str = ""
    unit_divisor: int = 1

    @property
    def market_value(self) -> Optional[float]:
        if self.shares is None or self.price is None:
            return None
        return self.shares * self.price / self.unit_divisor


def merge_duplicates(holdings: List[Holding]) -> List[Holding]:
    """同一銘柄コードが複数口座にまたがる場合に合算する（取得単価は加重平均）"""
    merged: dict = {}
    for h in holdings:
        cur = merged.get(h.code)
        if cur is None:
            merged[h.code] = Holding(
                code=h.code, name=h.name, shares=h.shares, avg_cost=h.avg_cost,
                price=h.price, profit=h.profit, accounts=list(h.accounts), note=h.note,
                unit_divisor=h.unit_divisor,
            )
            continue
        if cur.shares is not None and h.shares is not None:
            total = cur.shares + h.shares
            if cur.avg_cost is not None and h.avg_cost is not None and total:
                cur.avg_cost = round((cur.avg_cost * cur.shares + h.avg_cost * h.shares) / total, 2)
            cur.shares = total
        if cur.profit is not None and h.profit is not None:
            cur.profit += h.profit
        cur.price = h.price if cur.price is None else cur.price
        for a in h.accounts:
            if a not in cur.accounts:
                cur.accounts.append(a)
        if h.note and h.note not in cur.note:
            cur.note = (cur.note + " " + h.note).strip()
    return list(merged.values())


def to_rows(holdings: List[Holding]) -> List[dict]:
    """保有割合を計算して行の辞書リストにする。

    保有割合は「評価額が判明している銘柄の合計」を分母にする。
    金額が読み取れない銘柄は分母から除外し、割合を空欄にする。
    """
    known_total = sum(h.market_value for h in holdings if h.market_value is not None)
    rows = []
    for h in sorted(holdings, key=lambda x: -(x.market_value or -1)):
        mv = h.market_value
        rows.append({
            "銘柄コード": h.code,
            "銘柄名": h.name,
            "保有株数": "" if h.shares is None else h.shares,
            "取得単価": "" if h.avg_cost is None else h.avg_cost,
            "現在値": "" if h.price is None else h.price,
            "評価額": "" if mv is None else int(mv),
            "評価損益": "" if h.profit is None else h.profit,
            "保有割合%": "" if mv is None or not known_total else round(mv / known_total * 100, 2),
            "口座区分": "/".join(h.accounts) + (f"（{h.note}）" if h.note else ""),
        })
    return rows


def write_tsv(rows: List[dict], name: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"{name}.tsv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return path
