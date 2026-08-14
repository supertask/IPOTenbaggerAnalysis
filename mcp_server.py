"""保有銘柄の判断材料を、MCPでClaudeから直接呼べるようにする。

    python mcp_server.py          # stdio で起動（クライアントが起動するので手では叩かない）

いままでは `holding_judgment_dump.py` や `metric_compare_dump.py` を
コマンドで叩いて出力を読ませていた。ターミナルの無いところ（claude.ai や
スマホ）からは触れなかったのを、ここで埋める。

## 守っていること

**インデックスを直接引かない。visualizer のサービス層だけを呼ぶ。**
2026-08-14に、同じインデックスを読む場所が3つに分かれてタグの持ち方が
ずれていたせいで、営業利益率0.07%（IFRSの会社で基準の違う数字どうしの
割り算）、表とグラフの食い違い、拠点あたりの中央値ずれが同時に起きた。
ここが4つ目の読み手になって同じずれを生まないよう、**画面と同じ関数**を通す。

**対象は保有銘柄だけ。** 全銘柄に広げるとトークンが持たない
（`CLAUDE.md` の「重いデータは保有銘柄だけ」と同じ方針）。
保有外のコードを渡されたら、その旨を返して計算しない。
"""
from __future__ import annotations

import functools
import io
import os
import sys
from contextlib import redirect_stdout
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from mcp.server.mcpserver import MCPServer  # noqa: E402


def quiet(func):
    """**標準出力に何も漏らさない。**

    stdioでJSONRPCをやりとりするので、print が1行でも出るとプロトコルが壊れる。
    collectors は進捗や見出しを print する作りなので、ツールの中で呼ぶ間は
    標準出力を捨てる（戻り値だけを返す）。取りこぼしを人が追えるよう、
    捨てた内容は標準エラーに流す。
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                return func(*args, **kwargs)
        finally:
            leaked = buf.getvalue()
            if leaked.strip():
                print(leaked, file=sys.stderr, end="")
    return wrapper

server = MCPServer(
    name="ipo-tenbagger",
    instructions=(
        "日本のIPO銘柄のうち、ユーザーが保有・監視している32銘柄について、"
        "有価証券報告書・適時開示・大量保有報告書から作った判断材料を返す。"
        "数字はすべて画面（visualizer）と同じ計算を通しているので、"
        "画面と食い違うことはない。保有外の銘柄には答えられない。"
    ),
)


# --- 遅延読み込み。起動を軽くし、DBが無い環境でも import は通るようにする ---

def _portfolio_codes() -> List[str]:
    from collectors.holding_profile_dump import portfolio_codes
    return sorted(portfolio_codes())


def _guard(code: str) -> Optional[Dict[str, str]]:
    """保有銘柄でなければ、理由を添えて断る"""
    code = str(code or "").strip().upper()
    if not code:
        return {"error": "銘柄コードが空です"}
    if code not in _portfolio_codes():
        return {
            "error": f"{code} は保有銘柄ではありません",
            "理由": "重いデータは保有銘柄だけを対象にしている（トークンとディスクのため）",
            "保有銘柄": _portfolio_codes(),
        }
    return None


def _profile_row(code: str) -> Dict[str, str]:
    """business_profile.tsv の1行。AIが書いた解釈で、抽出した数字とは別もの"""
    import csv
    path = os.path.join(BASE_DIR, "data", "meta", "business_profile.tsv")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if (row.get("コード") or "").strip() == code:
                return {k: v for k, v in row.items() if (v or "").strip()}
    return {}


def _round(value, digits=2):
    return round(value, digits) if isinstance(value, (int, float)) else value


@server.tool(
    description=(
        "ユーザーが保有・監視している銘柄の一覧を返す。"
        "銘柄コード・銘柄名・上場年・最大何倍まで上がったか・"
        "どのポートフォリオが持っているか・AIの判定（買い増し検討/継続保有/"
        "様子見/縮小検討/判断保留）。どの銘柄について聞かれているか分からないとき、"
        "まずこれを呼ぶ。"
    )
)
@quiet
def list_holdings() -> Dict[str, Any]:
    from visualizer import db as _index_db
    from visualizer import portfolio as _portfolio

    codes = _portfolio_codes()
    conn = _index_db.get_conn()
    info = {}
    if conn is not None:
        for row in conn.execute(
                "SELECT code, name, ipo_year, max_multiple, industry FROM companies"):
            info[row["code"]] = row

    out = []
    for code in codes:
        row = info.get(code)
        profile = _profile_row(code)
        out.append({
            "コード": code,
            "銘柄名": (row["name"] if row else None) or profile.get("銘柄名"),
            "上場年": (row["ipo_year"] if row else None),
            "最大倍率": _round(row["max_multiple"], 1) if row else None,
            "業種": (row["industry"] if row else None),
            "保有": [h["label"] for h in _portfolio.get_holders(code)],
            "判定": profile.get("判定"),
            "稼ぎ方の型": profile.get("稼ぎ方の型"),
        })
    return {"件数": len(out), "銘柄": out,
            "注記": "判定と稼ぎ方の型はAIが書いた解釈。数字の抽出とは別もの"}


@server.tool(
    description=(
        "1銘柄の事業・経営陣・投資判断の読み解きを返す。"
        "収益の源泉、稼ぎ方の型、競合との違い、事業の弱み、経営陣の経歴と懸念、"
        "判定、買う理由、持ち続ける条件、降りる条件、株価水準。"
        "**これはAIが有報を読んで書いた解釈**で、抽出した数字とは区別している。"
        "「この会社はどういう会社か」「持ち続けていいか」に答えるときに使う。"
    )
)
@quiet
def company_profile(code: str) -> Dict[str, Any]:
    bad = _guard(code)
    if bad:
        return bad
    code = str(code).strip().upper()
    profile = _profile_row(code)
    if not profile:
        return {"error": f"{code} の読み解きはまだ書かれていない"}
    return {"コード": code, "読み解き": profile,
            "注記": "AIによる解釈。画面では「AIによる解釈」のバッジが付く欄と同じ内容"}


@server.tool(
    description=(
        "1銘柄の財務指標を、競合・同じ業種の中央値・"
        "「上場後に何倍になったか」で分けた3群（10倍以上／3〜10倍／2倍未満）と"
        "並べて返す。売上・営業利益率・ROE・ROA・自己資本比率・PER・PEG・PSR・"
        "キャッシュフロー・有利子負債など38指標。"
        "所見（売上↑なのに利益率↓、借入で嵩上げされたROEなど）と、"
        "データの欠けも付く。財務の良し悪しを聞かれたらこれを使う。"
    )
)
@quiet
def company_metrics(code: str, brief: bool = True) -> Dict[str, Any]:
    bad = _guard(code)
    if bad:
        return bad
    code = str(code).strip().upper()

    import io
    from contextlib import redirect_stdout
    from collectors import metric_compare_dump

    buf = io.StringIO()
    with redirect_stdout(buf):
        metric_compare_dump.dump(code, brief=brief, diagnose=True)
    text = buf.getvalue().strip()
    if not text:
        return {"error": f"{code} の財務データが取れなかった"}
    return {
        "コード": code,
        "本文": text,
        "注記": (
            "画面の「財務指標の比較」と同じ計算。"
            "PER・利益の質・ネットキャッシュ比率・希薄化率は、実測で10倍株を"
            "見分ける力が無いと分かっているので、そこで劣っていても弱点ではない"
        ),
    }


@server.tool(
    description=(
        "1銘柄の「1拠点あたりの採算」を競合と並べて返す。"
        "単位は会社によって違い、店舗・施設のほか、サブリースの管理戸数や"
        "車両の管理台数のこともある。多店舗展開型のビジネスモデルが実際に"
        "効いているか（拠点を増やしながら採算を保てているか）を見るのに使う。"
        "原価の構成（原価率・仕入・労務費）も返す。"
    )
)
@quiet
def company_facilities(code: str) -> Dict[str, Any]:
    bad = _guard(code)
    if bad:
        return bad
    code = str(code).strip().upper()

    from visualizer import facility_service
    from visualizer.next_tenbagger.data_service import DataService

    view = facility_service.get_facility_view(
        code, DataService.get_competitors(code))
    if not view:
        return {"error": f"{code} は拠点数が取れないか、拠点あたりが成り立たない業態",
                "注記": "工場・倉庫・営業所は採算の単位ではないので入れていない"}

    own = view["own"]["latest"]
    return {
        "コード": code,
        "単位": view.get("unit"),
        "自社": {"期": own["date"], "数": own["count"], "単位": own.get("unit"),
                 "1単位あたり売上_百万": _round(own.get("sales_per")),
                 "1単位あたり利益_百万": _round(own.get("profit_per"))},
        "競合": [{"名前": p["name"], "期": p["latest"]["date"],
                  "数": p["latest"]["count"], "単位": p["latest"].get("unit"),
                  "1単位あたり利益_百万": _round(p["latest"].get("profit_per"))}
                 for p in view["peers"]],
        "競合中央値との比": _round(view.get("ratio_to_peers")),
        "単位が違う競合": view.get("mixed_units"),
        "期中の最新": view.get("latest_interim"),
        "原価の構成": view.get("cost_structure"),
        "注記": "単位の種類が違う競合とは倍率を出さない（1台あたりと1店舗あたりの比に意味がないため）",
    }


@server.tool(
    description=(
        "1銘柄の株主の動きを返す。大株主・役員の持株の推移（有報から）と、"
        "5%超の株主の売買（大量保有報告書から、日付単位）。"
        "売買には理由のタグ（売出し・立会外分売・公開買付・関係者間で移動など）と、"
        "その前後に出た適時開示のAI要約が付く。"
        "**経営陣が売っているかを確かめるときに使う。**"
        "株数が減っていても、分割調整のずれや関係者間の移動、"
        "上場基準を満たすための売出しのことがあるので、理由まで見ること。"
    )
)
@quiet
def company_shareholders(code: str) -> Dict[str, Any]:
    bad = _guard(code)
    if bad:
        return bad
    code = str(code).strip().upper()

    import io
    from contextlib import redirect_stdout
    from collectors import holding_judgment_dump

    buf = io.StringIO()
    with redirect_stdout(buf):
        holding_judgment_dump.show_holdings(code)
    holders = buf.getvalue().strip()

    from visualizer import large_holding_service
    large = large_holding_service.get_large_holdings(code) or {}
    # events が本筋の売買、noise は証券会社の在庫など畳んでいるもの
    events = (large.get("events") or [])[:40]
    trades = [{
        "日付": e.get("date"), "保有者": e.get("name"),
        "動き": e.get("action"), "なぜ": e.get("reason"),
        "保有割合": e.get("ratio"), "株数": e.get("shares"),
        "開示": [{"日付": d.get("date"), "タイトル": d.get("title"),
                  "要約": d.get("summary"), "AIが書いた": d.get("by_ai")}
                 for d in (e.get("disclosures") or [])],
    } for e in events]

    return {
        "コード": code,
        "持株の推移": holders[:6000],
        "5%超の売買": trades,
        "売買の総数": large.get("total"),
        "保有者": large.get("holders"),
        "注記": (
            "大量保有報告書はEDINETに5年しか残らない。"
            "「なぜ」が不明なのは、書類に書かれていないという意味で、推測ではない。"
            "株数が減っていても、分割調整のずれ・関係者間の移動・上場基準を"
            "満たすための売出しのことがあるので、理由まで見ること"
        ),
    }


@server.tool(
    description=(
        "1銘柄の適時開示（TDnet）を新しい順に返す。日付・タイトル・"
        "AIが読んで書いた要約・PDFのURL。"
        "業績予想の修正、配当、自己株買い、M&A、大株主の異動、"
        "ストックオプションなどが入っている。"
        "「最近この会社に何があったか」に答えるときに使う。"
    )
)
@quiet
def company_disclosures(code: str, limit: int = 30) -> Dict[str, Any]:
    bad = _guard(code)
    if bad:
        return bad
    code = str(code).strip().upper()

    import csv
    from visualizer import large_holding_service as lhs

    items = lhs._load_tdnet().get(code) or []
    readings = {}
    path = os.path.join(BASE_DIR, "data", "meta", "disclosure_reading.tsv")
    if os.path.exists(path):
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                readings[row["URL"]] = row.get("要約")

    summaries = lhs._load_summaries()
    out = []
    for date, title, url in sorted(items, reverse=True)[:limit]:
        ai = readings.get(url)
        rule, _by_ai = summaries.get(url, ("", False))
        out.append({"日付": date, "タイトル": title,
                    "要約": ai or rule or None,
                    "要約はAIが書いた": bool(ai), "URL": url})
    return {
        "コード": code, "件数": len(out), "開示": out,
        "注記": (
            "適時開示を集めているのは保有銘柄だけ。"
            "要約がAIのものは前後の文脈を読んで書いたもの、"
            "そうでないものは本文から規則で1文を抜いただけ"
        ),
    }


if __name__ == "__main__":
    server.run(transport="stdio")
