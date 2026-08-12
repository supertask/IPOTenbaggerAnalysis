"""保有銘柄の「事業の内容」「役員の状況」をAIが読み解いた結果を返す。

有報の該当セクションは原文をそのまま並べても量が多く、競合と見比べるのが
難しい。収益の源泉・競合との違い・経営陣の経歴が事業のどこに効いているか、
といった固定の項目に落として比較できるようにする。

数字を扱う他のサービスと違って、ここに入るのは判断であって抽出ではない。
画面でもAI由来であることを明示する。対象は保有銘柄のみ
（data/meta/business_profile.tsv を手で埋める）。
"""
from __future__ import annotations

import csv
import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_TSV = os.path.join(BASE_DIR, "data", "meta", "business_profile.tsv")

# 表示する順番と見出し。TSVの列名と対応する
SECTIONS = [
    ("収益の源泉", "誰に何を売って、どこで利益が出ているか"),
    ("稼ぎ方の型", "テンバガー条件でいうビジネスモデルの分類"),
    ("競合との違い", "同じ土俵の会社と比べて何が違うか"),
    ("経営陣の経歴", "社長・主要役員の前職"),
    ("経歴と事業の噛み合い", "その経歴が業績のどこに効いているか"),
    ("気をつける点", "崩れるとしたらどこか"),
]

_cache: Optional[Dict[str, dict]] = None
_cache_mtime: Optional[float] = None


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


def get_profile(company_code) -> Optional[dict]:
    """詳細ページ用。書かれていない銘柄は None"""
    row = _load().get(str(company_code).strip())
    if not row:
        return None

    # キー名を items にしない。Jinjaで dict.items と衝突する
    sections = []
    for key, hint in SECTIONS:
        value = (row.get(key) or "").strip()
        if value:
            sections.append({"label": key, "hint": hint, "text": value})
    if not sections:
        return None

    return {
        "sections": sections,
        "source_date": (row.get("出所報告日") or "").strip(),
        "written_on": (row.get("作成日") or "").strip(),
    }
