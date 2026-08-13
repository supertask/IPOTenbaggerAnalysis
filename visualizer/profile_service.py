"""保有銘柄について、AIが読み解いた結果と、買う・持ち続けるの総括を返す。

有報の該当セクションは原文を並べても量が多く、競合と見比べるのが難しい。
収益の源泉・競合との違い・経営陣の経歴が事業のどこに効いているか、といった
固定の項目に落として比較できるようにする。

さらに大事なのは、事業の解説で終わらせないこと。買う・持ち続けるかを決めるには
判定と、持ち続ける条件・降りる条件が要る。それを「総括」として分けて持つ。

数字を扱う他のサービスと違って、ここに入るのは判断であって抽出ではない。
画面でもAI由来であることを明示する。対象は保有銘柄のみ
（data/meta/business_profile.tsv を手で埋める）。
"""
from __future__ import annotations

import csv
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_TSV = os.path.join(BASE_DIR, "data", "meta", "business_profile.tsv")
# 「財務指標の比較」の頭に出す読み方（.claude/skills/metric-reading）
METRIC_TSV = os.path.join(BASE_DIR, "data", "meta", "metric_reading.tsv")

# 事業の内容カードに出す
BUSINESS_SECTIONS = [
    ("収益の源泉", "誰に何を売って、どこで利益が出ているか"),
    ("稼ぎ方の型", "テンバガー条件でいうビジネスモデルの分類"),
    ("競合との違い", "同じ土俵の会社と比べて何が違うか"),
    ("事業の弱み", "事業として崩れうる点"),
    # 総括を書く前の行が残っているあいだの受け皿
    ("気をつける点", "崩れるとしたらどこか"),
]

# 役員の状況カードに出す
OFFICER_SECTIONS = [
    ("経営陣の経歴", "社長・主要役員の前職"),
    ("経歴と事業の噛み合い", "その経歴が業績のどこに効いているか"),
    ("経営陣の懸念", "持株の増減、同族集中、承継など"),
]

# 総括カードに出す
JUDGMENT_SECTIONS = [
    ("買う理由", "なぜ持つ価値があるか"),
    ("持ち続ける条件", "何が続いていれば持つのか"),
    ("降りる条件", "何が起きたら売るのか"),
    ("株価水準", "PERと高値からの位置"),
    ("見たデータ", "使ったもの／見ていないもの"),
]

# 判定の見え方。順に強気から弱気
VERDICT_STYLES = {
    "買い増し検討": "bg-success",
    "継続保有": "bg-primary",
    "様子見": "bg-warning text-dark",
    "縮小検討": "bg-danger",
    "判断保留": "bg-secondary",
}

# 財務指標の比較カードに出す
METRIC_SECTIONS = [
    ("見どころ", "20枚のグラフのうち、まずどれを見るか"),
    ("競合との差", "同じ土俵の会社と並べて何が違うか"),
    ("気をつける点", "そのまま読むと誤るところ"),
]

_cache: Optional[Dict[str, dict]] = None
_cache_mtime: Optional[float] = None
_metric_cache: Optional[Dict[str, dict]] = None
_metric_mtime: Optional[float] = None


def _load() -> Dict[str, dict]:
    global _cache, _cache_mtime
    if not os.path.exists(PROFILE_TSV):
        return {}
    mtime = os.path.getmtime(PROFILE_TSV)
    if _cache is not None and _cache_mtime == mtime:
        return _cache

    data: Dict[str, dict] = {}
    try:
        with open(PROFILE_TSV, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                code = (row.get("コード") or "").strip()
                if code:
                    data[code] = row
    except OSError as e:
        logger.warning("ビジネスプロファイルを読めませんでした: %s", e)
        return {}

    _cache, _cache_mtime = data, mtime
    return data


def _sections(row: dict, spec: List[tuple]) -> List[dict]:
    items = []
    for key, hint in spec:
        value = (row.get(key) or "").strip()
        if value:
            items.append({"label": key, "hint": hint, "text": value})
    return items


def _meta(row: dict) -> dict:
    return {
        "source_date": (row.get("出所報告日") or "").strip(),
        "written_on": (row.get("作成日") or "").strip(),
    }


def get_business_profile(company_code) -> Optional[dict]:
    """事業の内容カードに載せる読み解き"""
    row = _load().get(str(company_code).strip())
    if not row:
        return None
    sections = _sections(row, BUSINESS_SECTIONS)
    return {"sections": sections, **_meta(row)} if sections else None


def get_officer_profile(company_code) -> Optional[dict]:
    """役員の状況カードに載せる読み解き"""
    row = _load().get(str(company_code).strip())
    if not row:
        return None
    sections = _sections(row, OFFICER_SECTIONS)
    return {"sections": sections, **_meta(row)} if sections else None


def _load_metric() -> Dict[str, dict]:
    global _metric_cache, _metric_mtime
    if not os.path.exists(METRIC_TSV):
        return {}
    mtime = os.path.getmtime(METRIC_TSV)
    if _metric_cache is not None and _metric_mtime == mtime:
        return _metric_cache
    data: Dict[str, dict] = {}
    try:
        with open(METRIC_TSV, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                code = (row.get("コード") or "").strip()
                if code:
                    data[code] = row
    except OSError as e:
        logger.warning("財務指標の読み方を読めませんでした: %s", e)
        return {}
    _metric_cache, _metric_mtime = data, mtime
    return data


def get_metric_reading(company_code) -> Optional[dict]:
    """財務指標の比較の頭に載せる読み方。

    比較チャートは20枚近くあり、どれから見ればいいかが分からない。
    数字そのものはグラフが持っているので、ここに書くのは見る順番と、
    そのまま読むと誤るところだけ。
    """
    row = _load_metric().get(str(company_code).strip())
    if not row:
        return None
    sections = _sections(row, METRIC_SECTIONS)
    return {"sections": sections, **_meta(row)} if sections else None


def get_judgment(company_code) -> Optional[dict]:
    """買う・持ち続けるの総括。判定が書かれていない銘柄は None"""
    row = _load().get(str(company_code).strip())
    if not row:
        return None
    verdict = (row.get("判定") or "").strip()
    if not verdict:
        return None
    sections = _sections(row, JUDGMENT_SECTIONS)
    if not sections:
        return None
    return {
        "verdict": verdict,
        "verdict_css": VERDICT_STYLES.get(verdict, "bg-secondary"),
        "sections": sections,
        **_meta(row),
    }
