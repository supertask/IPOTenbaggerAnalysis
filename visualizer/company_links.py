"""詳細ページに出す外部リンクのうち、**データが無いと作れないもの。**

IRバンクとトレーダーズは銘柄コードからURLを組み立てられるが、
会社のホームページと「IPOの基礎知識」のページは組み立てられない。
後者は `https://www.ipokiso.com/company/2024/fiteasy.html` のように
**会社ごとのスラッグ**が入るため。上場時に集めた `kiso_details` に
入っていて、`companies.all_companies_json` にそのまま残っている。
"""
from __future__ import annotations

import json
from typing import Any, Dict

from visualizer import db as _db

# all_companies.tsv の列名 → 画面に出すときの名前とアイコン
_LINKS = (
    ("会社URL", "会社ホームページ", "bi-house"),
    ("IPO情報URL", "IPOの基礎知識", "bi-journal-text"),
)


def get_links(company_code: str) -> Dict[str, Any]:
    """その銘柄の外部リンク。取れないものは入れない"""
    conn = _db.get_conn()
    if conn is None:
        return {}
    row = conn.execute(
        "SELECT all_companies_json FROM companies WHERE code = ?",
        (str(company_code),),
    ).fetchone()
    if not row or not row["all_companies_json"]:
        return {}
    try:
        data = json.loads(row["all_companies_json"])
    except ValueError:
        return {}

    links = []
    for key, label, icon in _LINKS:
        url = str(data.get(key) or "").strip()
        # 「-」や「未定」が入っていることがある。httpで始まらないものは出さない
        if not url.startswith("http"):
            continue
        links.append({"url": url, "label": label, "icon": icon})
    return {"links": links}
