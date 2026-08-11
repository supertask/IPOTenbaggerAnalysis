"""保有ポートフォリオを銘柄コードで引けるようにする。

data/output/portfolio/*.tsv（collectors/PORTFOLIO_SCREENSHOT.md の手順で作る）を
読み、visualizer の一覧・詳細で「誰が持っている銘柄か」を出すために使う。

TSVが無い場合は空として扱うので、ファイルを置いていない環境でも動く。
"""
from __future__ import annotations

import csv
import logging
import os
from typing import Dict, List

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_DIR = os.path.join(BASE_DIR, "data", "output", "portfolio")

# TSVのファイル名 -> (表示名, バッジの色クラス)
# ここに足せば表示対象が増える
PORTFOLIOS = [
    ("tenbagger_x", "テンバガーX", "bg-danger"),
    ("myself", "自分", "bg-primary"),
]

# {銘柄コード: [{"label", "css", "shares", "weight"}, ...]}
_holders_cache: Dict[str, List[dict]] = {}
_cache_signature = None


def _signature():
    """読み込み済みTSVの更新時刻。変わっていたら読み直す"""
    sig = []
    for stem, _, _ in PORTFOLIOS:
        path = os.path.join(PORTFOLIO_DIR, f"{stem}.tsv")
        sig.append((stem, os.path.getmtime(path) if os.path.exists(path) else None))
    return tuple(sig)


def _load() -> Dict[str, List[dict]]:
    holders: Dict[str, List[dict]] = {}
    for stem, label, css in PORTFOLIOS:
        path = os.path.join(PORTFOLIO_DIR, f"{stem}.tsv")
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f, delimiter="\t"):
                    code = (row.get("銘柄コード") or "").strip().upper()
                    # (非開示) や (投信) のような銘柄コードでない行は飛ばす
                    if not code or code.startswith("("):
                        continue
                    holders.setdefault(code, []).append({
                        "label": label,
                        "css": css,
                        "shares": (row.get("保有株数") or "").strip(),
                        "weight": (row.get("保有割合%") or "").strip(),
                    })
        except OSError as e:
            logger.warning("ポートフォリオの読み込みに失敗: %s: %s", path, e)
    return holders


def get_all() -> Dict[str, List[dict]]:
    global _holders_cache, _cache_signature
    sig = _signature()
    if sig != _cache_signature:
        _holders_cache = _load()
        _cache_signature = sig
        logger.info("[portfolio] %d銘柄を読み込みました", len(_holders_cache))
    return _holders_cache


def get_holders(company_code) -> List[dict]:
    """その銘柄を保有しているポートフォリオの一覧を返す。無ければ空リスト"""
    if company_code is None:
        return []
    return get_all().get(str(company_code).strip().upper(), [])


def annotate(companies) -> None:
    """企業リストの各要素に holders を追加する（その場で書き換える）"""
    for company in companies or []:
        if isinstance(company, dict):
            company["holders"] = get_holders(company.get("code"))
