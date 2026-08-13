"""5%以上を持つ株主の売買を、大量保有報告書から組み立てる。

「持株の推移」は各期末の断面なので、期の途中で誰かが降りても年1回か2回の
点でしか見えず、しかも**理由が分からない**。大量保有報告書は保有割合が
1%動くたびに5営業日以内に出るため、日付単位で追えるうえに
「提出事由」と「保有目的」という形で理由が書いてある。

対象は5%以上を持つ人だけなので、創業者・資産管理会社・VC・機関投資家が
中心になる。逆にいえば、そこから外れた小さな売買はここには出てこない。

出所は collectors/large_holding_collector.py が落とした
data/output/large_holdings/<銘柄コード>.tsv。
"""
from __future__ import annotations

import csv
import logging
import os
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "output", "large_holdings")

# 割合がこれ以上動いた回だけを「動き」とみなす。提出事由には
# 「重要な契約の締結」のように株数が変わらないものも混ざる
MOVE_THRESHOLD = 0.001

# 保有目的の長い定型文を、一覧で読める短さに畳む。長文はそのまま持たせて
# ツールチップで出す
_PURPOSE_TAGS = (
    ("経営参画", ("経営参画", "経営に参画", "重要提案行為")),
    ("長期保有", ("長期保有", "安定株主")),
    ("政策保有", ("取引関係", "業務提携", "政策投資", "取引先")),
    ("純投資", ("純投資", "投資運用", "資産運用", "投資一任", "信託財産")),
)

_cache: Dict[str, tuple] = {}


def _path(company_code: str) -> str:
    return os.path.join(DATA_DIR, f"{str(company_code).strip()}.tsv")


def _num(value) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def purpose_tag(text: str) -> str:
    """保有目的の一言まとめ。当てはまらなければ空"""
    for label, words in _PURPOSE_TAGS:
        if any(w in text for w in words):
            return label
    return ""


def _action(share_diff: Optional[float], ratio_diff: Optional[float]) -> str:
    """売ったのか買ったのかを言い切る。

    判定は**株数**で行う。提出事由（「1％以上の減少」など）は共同保有者の
    合計に対する事由なので、本人が1株も売っていなくても「減少」と書かれる。
    フィットイージーの2025-10-15がまさにそれで、株式会社オリーブは
    7,500,000株のまま、増資による希薄化で割合だけ 47.20%→45.40% に落ちた。
    ここを事由で判定すると「オリーブも売った」と読めてしまう。
    """
    if share_diff is None:
        return "新たに5%超"
    if share_diff < 0:
        return "減らした"
    if share_diff > 0:
        return "増やした"
    if ratio_diff is not None and ratio_diff <= -MOVE_THRESHOLD:
        return "希薄化"
    return ""


def _load(company_code: str) -> List[dict]:
    path = _path(company_code)
    if not os.path.exists(path):
        return []
    mtime = os.path.getmtime(path)
    cached = _cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
    except Exception as e:
        logger.warning("大量保有報告書の読み込みに失敗 %s: %s", company_code, e)
        return []
    _cache[path] = (mtime, rows)
    return rows


def _name_key(name: str) -> str:
    """同じ人を同じ系列にまとめる。書類によって空白の入り方が違う"""
    return "".join(re.sub(r"[（(].*?[）)]", "", name).split())


def get_large_holdings(company_code) -> Optional[dict]:
    """5%超の株主の売買。データが無ければ None"""
    rows = _load(company_code)
    if not rows:
        return None

    # 同じ人の前回の株数と突き合わせて増減を出す。書類に載る「前回割合」は
    # 割合であって株数ではなく、増資があると株数が動かなくても割合が動く
    previous: Dict[str, float] = {}
    events = []
    for row in sorted(rows, key=lambda r: (r.get("提出日") or "", r.get("保有者") or "")):
        shares = _num(row.get("株数"))
        ratio = _num(row.get("保有割合"))
        last_ratio = _num(row.get("前回割合"))
        name = (row.get("保有者") or "").strip()
        if not name or shares is None:
            continue
        key = _name_key(name)
        before = previous.get(key)
        previous[key] = shares
        share_diff = None if before is None else shares - before
        ratio_diff = None if ratio is None or last_ratio is None else ratio - last_ratio
        purpose = (row.get("保有目的") or "").strip()
        events.append({
            "date": (row.get("発生日") or row.get("提出日") or "").strip(),
            "filed": (row.get("提出日") or "").strip(),
            "name": name,
            "shares": shares,
            "ratio": ratio,
            "ratio_diff": ratio_diff,
            "share_diff": share_diff,
            "reason": (row.get("提出事由") or "").strip(),
            "action": _action(share_diff, ratio_diff),
            "purpose": purpose,
            "purpose_tag": purpose_tag(purpose),
            # 株数が動いた回と、その人が初めて5%超で現れた回だけを残す。
            # 株数が変わらない届出（契約の締結、他人の売却に伴う割合の変動）は
            # 「売買」の一覧に並べても判断の材料にならない
            "moved": share_diff is None or share_diff != 0,
        })

    moves = [e for e in events if e["moved"]]
    if not moves:
        moves = events[-1:]

    moves.sort(key=lambda e: (e["date"], e["name"]), reverse=True)
    holders = sorted({e["name"] for e in events})
    return {
        "events": moves,
        "total": len(events),
        "holders": holders,
        "latest": moves[0]["date"] if moves else "",
    }
