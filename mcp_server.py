"""保有銘柄の**生データ**を、MCPでClaudeから直接呼べるようにする。

    python mcp_server.py          # stdio で起動（クライアントが起動するので手では叩かない）

いままでは `holding_judgment_dump.py` や `metric_compare_dump.py` を
コマンドで叩いて出力を読ませていた。ターミナルの無いところ（claude.ai や
スマホ）からは触れなかったのを、ここで埋める。

## 出すのは生データだけ。AIが書いた解釈は出さない

`data/meta/business_profile.tsv`（事業の読み解き・判定・買う理由）と
`data/meta/disclosure_reading.tsv`（開示の要約）は、**AIが書いたもの**なので
ここからは出さない。**書いた時点のAIの精度がそのまま残り、あとから読む側の
判断を古い結論で縛ってしまう。** 呼ぶ側がそのつど生データから判断できるよう、
有報の本文・XBRLの値・適時開示のPDF本文・大量保有報告書といった
**一次資料と、そこから機械的に計算した数字**だけを返す。

画面（visualizer）はAIの解釈も出すが、あちらは「AIによる解釈」のバッジで
区別している。MCPは区別する手段が無いので、最初から混ぜない。

## 守っていること

**インデックスを直接引かず、visualizer のサービス層と collectors を通す。**
2026-08-14に、同じインデックスを読む場所が3つに分かれてタグの持ち方が
ずれていたせいで、営業利益率0.07%（IFRSの会社で基準の違う数字どうしの
割り算）、表とグラフの食い違い、拠点あたりの中央値ずれが同時に起きた。
ここが新しい読み手になって同じずれを生まないよう、**画面と同じ関数**を通す。

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
        "有価証券報告書・適時開示・大量保有報告書の**生データ**と、"
        "そこから機械的に計算した指標を返す。"
        "AIが書いた解釈（事業の読み解き・投資判断・開示の要約）は含まない。"
        "解釈が要るときは、ここで取った生データを読んでそのつど判断すること。"
        "保有外の銘柄には答えられない。"
    ),
)


# --- 遅延読み込み。起動を軽くし、DBが無い環境でも import は通るようにする ---

def _portfolio_codes() -> List[str]:
    from collectors.holding_profile_dump import portfolio_codes
    return sorted(portfolio_codes())


def _guard(code: str) -> Optional[Dict[str, Any]]:
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


def _rename(value, mapping: Dict[str, str]):
    """辞書のキーを日本語に置き換える。無いキーはそのまま残す"""
    if not isinstance(value, dict):
        return value
    return {mapping.get(k, k): v for k, v in value.items()}


def _round(value, digits=2):
    return round(value, digits) if isinstance(value, (int, float)) else value


def _report_path(code: str, report_type: str = "annual",
                 year: Optional[int] = None) -> Optional[tuple]:
    """その銘柄の報告書のファイル。(パス, 提出日)

    year を渡すと、その年に提出されたものを返す。既定は最新。
    6099は有報を12年ぶん、3496は8年ぶん持っているので、
    「何年前はどう書いていたか」を読める
    """
    from visualizer import db as _index_db
    conn = _index_db.get_conn()
    if conn is None:
        return None
    if year:
        row = conn.execute(
            "SELECT file_path, report_date FROM report_files "
            "WHERE company_code = ? AND report_type = ? "
            "AND report_date LIKE ? ORDER BY report_date DESC LIMIT 1",
            (code, report_type, f"{year}%")).fetchone()
    else:
        row = conn.execute(
            "SELECT file_path, report_date FROM report_files "
            "WHERE company_code = ? AND report_type = ? "
            "ORDER BY report_date DESC LIMIT 1",
            (code, report_type)).fetchone()
    return (row["file_path"], row["report_date"]) if row else None


def _report_years(code: str, report_type: str = "annual") -> List[str]:
    """持っている報告書の提出日。どの年が読めるかを示すため"""
    from visualizer import db as _index_db
    conn = _index_db.get_conn()
    if conn is None:
        return []
    return [r["report_date"] for r in conn.execute(
        "SELECT report_date FROM report_files WHERE company_code = ? "
        "AND report_type = ? ORDER BY report_date DESC", (code, report_type))]


@server.tool(
    description=(
        "ユーザーが保有・監視している銘柄の一覧を返す。"
        "銘柄コード・銘柄名・上場年・上場してから最大何倍まで上がったか・業種・"
        "どのポートフォリオ（自分／テンバガーX／お気に入り）が持っているか。"
        "どの銘柄について聞かれているか分からないとき、まずこれを呼ぶ。"
        "すべて事実で、AIの判断は含まない。"
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
                "SELECT code, name, ipo_year, ipo_date, max_multiple, "
                "current_multiple, industry, market FROM companies"):
            info[row["code"]] = row

    out = []
    for code in codes:
        row = info.get(code)
        out.append({
            "コード": code,
            "銘柄名": row["name"] if row else None,
            "上場日": row["ipo_date"] if row else None,
            "上場年": row["ipo_year"] if row else None,
            "市場": row["market"] if row else None,
            "業種": row["industry"] if row else None,
            "最大倍率": _round(row["max_multiple"], 1) if row else None,
            "現在倍率": _round(row["current_multiple"], 1) if row else None,
            "保有": [h["label"] for h in _portfolio.get_holders(code)],
        })
    return {"件数": len(out), "銘柄": out}


@server.tool(
    description=(
        "1銘柄の財務指標を、競合・同じ業種の中央値・"
        "「上場後に何倍になったか」で分けた3群（10倍以上／3〜10倍／2倍未満）と"
        "並べて返す。売上・営業利益率・ROE・ROA・自己資本比率・PER・PEG・PSR・"
        "キャッシュフロー・有利子負債など38指標。"
        "所見（売上↑なのに利益率↓、借入で嵩上げされたROEなど）は規則で当てたもので、"
        "AIの判断ではない。データの欠けも付く。財務の良し悪しを聞かれたらこれを使う。"
    )
)
@quiet
def company_metrics(code: str, brief: bool = True) -> Dict[str, Any]:
    bad = _guard(code)
    if bad:
        return bad
    code = str(code).strip().upper()

    from collectors import metric_compare_dump

    got = metric_compare_dump.collect(code, brief=brief, diagnose=True)
    if got.get("error"):
        return {"error": f"{code}: {got['error']}"}
    got["注記"] = (
        "画面の「財務指標の比較」と同じ計算。"
        "`値` は生の値、`表示` は指標ごとに揃えた単位を掛けたあとの文字列。"
        "PER・利益の質・ネットキャッシュ比率・希薄化率は、実測で10倍株を"
        "見分ける力が無いと分かっているので、そこで劣っていても弱点ではない"
    )
    return got


@server.tool(
    description=(
        "有価証券報告書のXBRLの生の値を、タグ名か項目名で検索して返す。"
        "**画面に出している38指標より広い。** 1銘柄あたり380種類ほどのタグがあり、"
        "研究開発費・設備投資・セグメント情報・リース・税金・従業員の内訳など、"
        "画面では扱っていない項目もここから取れる。"
        "query は要素IDか項目名の一部（例: ResearchAndDevelopment、研究開発、"
        "セグメント、CapitalExpenditure）。"
        "query を空にすると、その報告書にあるタグの一覧だけを返す。"
        "year を渡すと過去の年度の有報を読む（何年ぶんあるかは list_holdings ではなく"
        "この関数の error に「読める提出日」として出る）。"
        "report_type は annual（有報・年1回）／quarterly（四半期・半期報告書、"
        "保有銘柄のみ）／securities_registration（上場時の届出書）。"
        "**会社の予想はここには無い。実績だけ。予想は tanshin_xbrl。**"
    )
)
@quiet
def annual_report_xbrl(code: str, query: str = "", limit: int = 60,
                       report_type: str = "annual",
                       year: Optional[int] = None) -> Dict[str, Any]:
    bad = _guard(code)
    if bad:
        return bad
    code = str(code).strip().upper()

    from collectors.facility_count_collector import _read

    found = _report_path(code, report_type, year)
    if not found:
        return {"error": f"{code} の{report_type}が見つからない",
                "読める提出日": _report_years(code, report_type)}
    path, date = found
    text = _read(path) or ""
    lines = text.splitlines()
    if not lines:
        return {"error": "報告書を読めなかった"}

    rows = []
    tags = set()
    for line in lines[1:]:
        parts = [p.strip('"') for p in line.split("\t")]
        if len(parts) < 9:
            continue
        element, label = parts[0], parts[1]
        tags.add((element, label))
        if query and query.lower() not in element.lower() and query not in label:
            continue
        value = parts[8]
        # TextBlockは本文なので、ここでは頭だけ。全文は annual_report_text で
        if element.endswith("TextBlock") and len(value) > 200:
            value = value[:200] + "…（全文は annual_report_text で）"
        rows.append({"要素ID": element, "項目名": label,
                     "相対年度": parts[3], "連結個別": parts[4],
                     "期間時点": parts[5], "単位": parts[7], "値": value})

    if not query:
        return {"コード": code, "提出日": date, "タグの種類": len(tags),
                "タグ一覧": [{"要素ID": e, "項目名": l} for e, l in sorted(tags)],
                "注記": "query に一部を渡すと、その値を返す"}

    return {"コード": code, "提出日": date, "検索語": query,
            "件数": len(rows), "行": rows[:limit],
            "注記": "有報のXBRLそのまま。画面に出している38指標より広い範囲が取れる"}


@server.tool(
    description=(
        "有価証券報告書の**本文**を返す。section で選ぶ。"
        "business=事業の内容、officers=役員の状況、mdna=経営者による分析（MD&A）、"
        "risk=事業等のリスク、rd=研究開発活動、capex=設備投資等の概要、"
        "segment=セグメント情報、policy=経営方針。"
        "**日本語の節名でも受ける**（事業の内容・役員の状況・事業等のリスクなど）。"
        "section を空にすると、その報告書にある本文セクションの一覧を返す。"
        "year を渡すと過去の年度の有報を読む（6099は12年ぶん、3496は8年ぶんある）。"
        "report_type は annual（有報・年1回）／quarterly（四半期・半期報告書、"
        "保有銘柄のみ）／securities_registration（上場時の届出書）。"
        "会社が自分の言葉で書いた一次資料なので、事業の中身を知りたいときはここ。"
        "**四半期ごとの経営成績の説明は有報には無い。** 決算短信のPDFにあるので、"
        "company_disclosures で「決算短信」を引いて disclosure_text で読む。"
    )
)
@quiet
def annual_report_text(code: str, section: str = "", chars: int = 6000,
                       report_type: str = "annual",
                       year: Optional[int] = None) -> Dict[str, Any]:
    bad = _guard(code)
    if bad:
        return bad
    code = str(code).strip().upper()

    from collectors.facility_count_collector import _read
    from collectors.holding_profile_dump import plain

    known = {
        "business": ("DescriptionOfBusinessTextBlock", "事業の内容"),
        "officers": ("InformationAboutOfficersTextBlock", "役員の状況"),
        "mdna": ("ManagementAnalysisOfFinancialPositionOperatingResults"
                 "AndCashFlowsTextBlock", "経営者による分析"),
        "risk": ("BusinessRisksTextBlock", "事業等のリスク"),
        "rd": ("ResearchAndDevelopmentActivitiesTextBlock", "研究開発活動"),
        "capex": ("OverviewOfCapitalExpendituresEtcTextBlock", "設備投資等の概要"),
        "segment": ("NotesSegmentInformationEtcFinancialStatementsTextBlock",
                    "セグメント情報"),
        "policy": ("BusinessPolicyBusinessEnvironmentIssuesToAddressEtcTextBlock",
                   "経営方針"),
    }

    found = _report_path(code, report_type, year)
    if not found:
        return {"error": f"{code} の{report_type}が見つからない",
                "読める提出日": _report_years(code, report_type)}
    path, date = found
    text = _read(path) or ""

    blocks = {}
    for line in text.splitlines()[1:]:
        parts = [p.strip('"') for p in line.split("\t")]
        if len(parts) >= 9 and parts[0].endswith("TextBlock") and parts[8]:
            blocks.setdefault(parts[0], (parts[1], parts[8]))

    if not section:
        return {
            "コード": code, "提出日": date,
            "使えるsection": [k for k, (tag, _n) in known.items()
                              if any(t.endswith(tag) for t in blocks)],
            "報告書にある本文すべて": [{"要素ID": t, "項目名": v[0],
                                        "文字数": len(v[1])}
                                       for t, v in sorted(blocks.items())],
        }

    # **日本語でも受ける。** 説明文に「事業の内容・役員の状況」と書いてあるので、
    # 呼ぶ側はそのまま渡してくる。英語のキーだけだと毎回1往復むだになる
    aliases = {label: key for key, (_tag, label) in known.items()}
    aliases.update({"事業": "business", "役員": "officers", "リスク": "risk",
                    "研究開発": "rd", "設備": "capex", "セグメント": "segment",
                    "経営方針": "policy", "mdna": "mdna", "md&a": "mdna",
                    "経営者による分析": "mdna", "業績": "mdna"})

    raw_section = section.strip()
    key = aliases.get(raw_section, raw_section.lower())
    if key not in known:
        return {"error": f"section は {sorted(known)} のどれか"
                         f"（{sorted(aliases)} の日本語でも受ける）"}
    tag, name = known[key]
    for element, (label, raw) in blocks.items():
        if element.endswith(tag):
            body = plain(raw)
            return {"コード": code, "提出日": date, "section": key,
                    "項目名": label or name, "文字数": len(body),
                    "本文": body[:chars],
                    "注記": "有報の本文そのまま。会社が書いた一次資料"}
    return {"error": f"{code} の{report_type}に「{name}」が無い"}


@server.tool(
    description=(
        "1銘柄の適時開示（TDnet）の一覧を新しい順に返す。日付・タイトル・PDFのURL。"
        "業績予想の修正、配当、自己株買い、M&A、大株主の異動、"
        "ストックオプションなどが入っている。"
        "match にキーワードを渡すとタイトルで絞れる（例: 業績予想、自己株式、売出）。"
        "**中身を読むには disclosure_text にURLを渡す。**"
    )
)
@quiet
def company_disclosures(code: str, match: str = "", limit: int = 40,
                        months: int = 60) -> Dict[str, Any]:
    bad = _guard(code)
    if bad:
        return bad
    code = str(code).strip().upper()

    from collectors import disclosure_pdf

    rows = disclosure_pdf.find(code, match=match, months=months)
    out = [{"日付": r[0], "タイトル": r[4], "URL": r[5]} for r in rows[:limit]]
    return {"コード": code, "件数": len(out), "全件数": len(rows), "開示": out,
            "注記": "適時開示を集めているのは保有銘柄だけ。本文は disclosure_text で読む"}


_TANSHIN_FACTS = os.path.join(BASE_DIR, "data", "output", "tanshin", "facts")
# 予想の修正を追うときに見る項目。会社が出しているのはこの粒度。
# **IFRSの会社はタグが別で、経常利益の代わりに税引前利益が来る**
# （保有銘柄では3774・6574・9158）
_FORECAST_TAGS = ("NetSales", "OperatingIncome", "OrdinaryIncome",
                  "ProfitAttributableToOwnersOfParent", "NetIncome",
                  "NetIncomePerShare", "DividendPerShare",
                  "SalesIFRS", "OperatingIncomeIFRS", "ProfitBeforeTaxIFRS",
                  "ProfitIFRS", "ProfitAttributableToOwnersOfParentIFRS",
                  "BasicEarningsPerShareIFRS")


def _tanshin_rows(code: str) -> Optional[List[Dict[str, str]]]:
    import csv

    path = os.path.join(_TANSHIN_FACTS, f"{code}.tsv")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


@server.tool(
    description=(
        "決算短信サマリーのXBRLを返す。**会社自身の業績予想はここにしか無い。**"
        "有報のXBRL（annual_report_xbrl）は実績だけなので、"
        "「会社が今期・来期をどう見ているか」「予想を何回、いつ、どれだけ"
        "上方／下方修正したか」を知りたいときはこちら。"
        "既定では予想の推移（売上・営業利益・経常利益・純利益・EPS・配当を"
        "短信ごとに並べたもの）と、最新の短信の全項目を返す。"
        "query に語を渡すと項目名かタグで絞る（例: 配当、自己資本比率、"
        "CashFlows）。date を渡すとその日の短信だけ。"
        "**四半期の実績も入っている**（有報は年1回なので期中はこちらが唯一の数字）。"
    )
)
@quiet
def tanshin_xbrl(code: str, query: str = "", date: str = "",
                 limit: int = 120) -> Dict[str, Any]:
    bad = _guard(code)
    if bad:
        return bad
    code = str(code).strip().upper()

    rows = _tanshin_rows(code)
    if rows is None:
        return {"error": f"{code} の決算短信XBRLがまだ無い。"
                         f"collectors/tdnet_disclosure_scraper.py --codes {code} "
                         f"--refresh のあと collectors/tanshin_xbrl_collector.py "
                         f"--codes {code} で取れる。"
                         "東証に上場していない銘柄（353A・9388）は取れない"}
    if not rows:
        return {"error": f"{code} の決算短信XBRLが空"}

    dates = sorted({r["日付"] for r in rows})

    # 予想の推移。同じ項目を短信ごとに並べると、いつ何を見直したかが出る
    trend: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        if r["タグ"] not in _FORECAST_TAGS or r["区分"] != "予想" or not r["値"]:
            continue
        if r["四半期"] and r["四半期"] != "合計":
            continue  # 配当は四半期ごとに出るので、年間の合計だけ見る
        key = f"{r['期']} {r['項目名'] or r['タグ']}"
        trend.setdefault(key, []).append(
            {"短信の日付": r["日付"], "値": float(r["値"]),
             "連単": r["連単"], "表示": r["表示"]})
    for key in trend:
        trend[key].sort(key=lambda x: x["短信の日付"])

    target = date or dates[-1]
    picked = [r for r in rows if r["日付"] == target]
    if query:
        q = query.lower()
        picked = [r for r in rows
                  if q in (r["項目名"] or "").lower() or q in r["タグ"].lower()]
        picked.sort(key=lambda r: (r["日付"], r["タグ"]))

    out = [{"日付": r["日付"], "書類": r["書類"], "期": r["期"], "連単": r["連単"],
            "区分": r["区分"], "四半期": r["四半期"],
            "項目名": r["項目名"] or r["タグ"], "タグ": r["タグ"],
            "値": (float(r["値"]) if r["値"] else None),
            "単位": r["単位"], "表示": r["表示"]}
           for r in picked[:limit]]

    return {
        "コード": code,
        "短信の件数": len(dates),
        "短信の日付": dates,
        "予想の推移": trend,
        "対象": ("query一致" if query else target),
        "件数": len(out),
        "全件数": len(picked),
        "項目": out,
        "注記": (
            "東証の適時開示ページから取ったサマリーのiXBRL。会社が出した一次資料。"
            "`値` は scale を掛けたあとの生の値で、円・株・比率（0.168は16.8%）。"
            "`単位` の Pure は比率、JPY は円、JPYPerShares は1株当たり。"
            "予想は ForecastMember、実績は ResultMember。"
            "予想に幅を出す会社は「予想の上限」「予想の下限」も入る"
        ),
    }


@server.tool(
    description=(
        "適時開示のPDFの**本文**を返す。company_disclosures で得たURLを渡す。"
        "会社が書いた一次資料そのもので、要約ではない。"
        "grep に語を渡すと、その語の周りだけを抜く（例: 修正の理由、目的、"
        "取得した株式の総数）。長い開示から必要なところだけ読みたいときに使う。"
    )
)
@quiet
def disclosure_text(url: str, grep: str = "", chars: int = 6000) -> Dict[str, Any]:
    import re as _re
    from collectors import disclosure_pdf

    url = str(url or "").strip()
    if not url.startswith("/disc/"):
        return {"error": "URLは company_disclosures が返す /disc/... の形で渡す"}
    text = disclosure_pdf.fetch(url)
    if not text:
        return {"error": "PDFを取れなかった（消えているか、画像だけのPDF）"}

    if grep:
        hits = []
        for m in _re.finditer(_re.escape(grep), text):
            start = max(0, m.start() - 200)
            hits.append(text[start:m.end() + 600])
        if not hits:
            return {"URL": url, "検索語": grep, "件数": 0,
                    "注記": f"「{grep}」は本文に無い。全文を見るなら grep を空にする"}
        return {"URL": url, "検索語": grep, "件数": len(hits),
                "抜粋": [h[:1200] for h in hits[:5]]}

    return {"URL": url, "文字数": len(text), "本文": text[:chars],
            "注記": "開示PDFの本文そのまま" +
                    ("（続きがある。grepで絞るか chars を増やす）"
                     if len(text) > chars else "")}


@server.tool(
    description=(
        "1銘柄の株主の動きを返す。大株主・役員の持株の推移（有報から）と、"
        "5%超の株主の売買（大量保有報告書から、日付単位）。"
        "売買には提出事由と、書類の「増減の内訳」から読んだ理由のタグ"
        "（売出し・立会外分売・公開買付・関係者間で移動など）が付く。"
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

    from visualizer import holdings_service

    # 画面と同じサービスから構造のまま取る。テキストに整形したものを
    # 渡すと、読む側が毎回パースし直すことになる
    view = holdings_service.get_holdings_history(code) or {}
    holders: Dict[str, Any] = {}
    for key, label in (("major", "大株主"), ("officer", "役員")):
        table = view.get(key)
        if not table:
            continue
        periods = [{"期": c["date"], "中間期": bool(c["interim"])}
                   for c in table["columns"]]
        holders[label] = {
            "期": periods,
            "人": [{"名前": p["name"], "株数": p["values"],
                    "増減": p.get("change")}
                   for p in table["people"]],
        }
    if view.get("officer_decreases"):
        holders["役員の合計が減った期"] = [
            {"期": d["date"], "増減": d["diff"]} for d in view["officer_decreases"]]

    from visualizer import large_holding_service
    large = large_holding_service.get_large_holdings(code) or {}
    events = (large.get("events") or [])[:40]
    trades = [{
        "日付": e.get("date"), "保有者": e.get("name"),
        "動き": e.get("action"), "提出事由": e.get("reason"),
        "保有割合": e.get("ratio"), "株数": e.get("shares"),
        "関連する開示": [{"日付": d.get("date"), "タイトル": d.get("full") or d.get("title"),
                          "URL": d.get("url")}
                         for d in (e.get("disclosures") or [])],
    } for e in events]

    return {
        "コード": code,
        "持株の推移": holders,
        "5%超の売買": trades,
        "売買の総数": large.get("total"),
        "保有者": large.get("holders"),
        "注記": (
            "大量保有報告書はEDINETに5年しか残らない。"
            "理由が不明なのは、書類に書かれていないという意味で推測ではない。"
            "関連する開示の中身は disclosure_text にURLを渡して読む"
        ),
    }


@server.tool(
    description=(
        "1銘柄の「1拠点あたりの採算」を競合と並べて返す。"
        "単位は会社によって違い、店舗・施設のほか、サブリースの管理戸数や"
        "車両の管理台数のこともある。多店舗展開型のビジネスモデルが実際に"
        "効いているか（拠点を増やしながら採算を保てているか）を見るのに使う。"
        "拠点数は有報の本文から拾った数字で、原価の構成（原価率・仕入・労務費）も返す。"
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
        "推移": [{"期": p.get("date"), "数": p.get("count"),
                  "1単位あたり利益_百万": _round(p.get("profit_per"))}
                 for p in (view["own"].get("points") or [])],
        "競合": [{"名前": p["name"], "期": p["latest"]["date"],
                  "数": p["latest"]["count"], "単位": p["latest"].get("unit"),
                  "1単位あたり利益_百万": _round(p["latest"].get("profit_per"))}
                 for p in view["peers"]],
        "競合中央値との比": _round(view.get("ratio_to_peers")),
        "単位が違う競合": view.get("mixed_units"),
        # サービス層は英語のキーで返す。**MCPの外に出すところで日本語に揃える** —
        # 同じ戻りの中でキーの言語が混ざると、読む側が名前を推測することになる
        "期中の最新": _rename(view.get("latest_interim"), {
            "date": "期", "count": "数", "unit": "単位", "sources": "出所"}),
        "原価の構成": _rename(view.get("cost_structure"), {
            "date": "期", "cost_ratio": "原価率", "purchase": "仕入",
            "purchase_ratio": "仕入の比率", "labor": "労務費",
            "labor_ratio": "労務費の比率"}),
        "注記": "単位の種類が違う競合とは倍率を出さない（1台あたりと1店舗あたりの比に意味がないため）",
    }


@server.tool(
    description=(
        "1銘柄の株価を返す。いまの株価・公開価格・初値・上場来高値と"
        "そこからの位置・現在何倍か・最大何倍まで行ったか・"
        "2倍/3倍/5倍/10倍に何年かかったか。"
        "days を渡すと、その日数ぶんの終値も返す（既定は返さない）。"
        "「いま買う水準か」「高値からどれだけ落ちているか」に答えるときに使う。"
    )
)
@quiet
def price_history(code: str, days: int = 0) -> Dict[str, Any]:
    bad = _guard(code)
    if bad:
        return bad
    code = str(code).strip().upper()

    import csv as _csv
    import glob as _glob

    # yfinance の集計（現在何倍・最大何倍・N倍まで何年）
    facts = {}
    for path in _glob.glob(os.path.join(BASE_DIR, "data", "output",
                                        "yfinance", "companies_*.tsv")):
        with open(path, encoding="utf-8", newline="") as f:
            for row in _csv.DictReader(f, delimiter="\t"):
                if (row.get("コード") or "").strip() == code:
                    facts = {k: v for k, v in row.items() if (v or "").strip()}
                    break
        if facts:
            break

    series = []
    if days > 0:
        try:
            from visualizer import price_service  # type: ignore
            series = price_service.get_price_history(code, days)  # noqa
        except Exception:
            try:
                import yfinance
                hist = yfinance.Ticker(f"{code}.T").history(period=f"{days}d")
                series = [{"日付": str(i.date()), "終値": _round(float(v), 1)}
                          for i, v in hist["Close"].items()]
            except Exception as e:
                series = [{"error": f"株価を取れなかった: {e}"}]

    return {"コード": code, "yfinanceの集計": facts,
            "終値": series[-200:] if series else "days を渡すと返す",
            "注記": "倍率は上場時の初値を基準にしている"}


@server.tool(
    description=(
        "1銘柄の**上場時の諸元**を返す。想定価格・仮条件・公開価格・初値・"
        "想定時価総額・社長の持株比率・オーナー株比率・公募と売出しの比率・"
        "オーバーアロットメント・注目度・代表者の上場時の年齢・主幹事など。"
        "テンバガーの条件（社長の持株が多いか、公開規模が小さいか）を"
        "確かめるときに使う。上場時点の事実で、AIの判断は入っていない。"
    )
)
@quiet
def ipo_facts(code: str) -> Dict[str, Any]:
    bad = _guard(code)
    if bad:
        return bad
    code = str(code).strip().upper()

    import csv as _csv
    import glob as _glob

    out: Dict[str, Any] = {"コード": code}
    # 3つのTSVに分かれている。どれも上場時の事実
    for label, pattern, key in (
            ("公開価格と初値", "traders/companies_*.tsv", "コード"),
            ("上場時の諸元", "kiso_details/companies_*.tsv", "コード"),
            ("上場後の集計", "combiner/companies_*.tsv", "コード")):
        for path in _glob.glob(os.path.join(BASE_DIR, "data", "output", pattern)):
            with open(path, encoding="utf-8", newline="") as f:
                for row in _csv.DictReader(f, delimiter="\t"):
                    if (row.get(key) or "").strip() == code:
                        out[label] = {k: v for k, v in row.items()
                                      if (v or "").strip() and k != key}
                        break
            if label in out:
                break
    if len(out) == 1:
        return {"error": f"{code} の上場時の諸元が見つからない",
                "注記": "上場が古い銘柄はIPO情報のTSVに無いことがある"}
    return out


# --- 投資本。本文はこのリポジトリに置かない（公開リポジトリのため） ---

def _book_dir() -> str:
    """本文の置き場所。環境変数 BOOK_TEXTS_DIR で指す。

    **本文は非公開の別リポジトリにあり、ここには置かない。**
    サブモジュールにすると、非公開リポジトリを参照していることが
    URLごと公開されるうえ、他人のcloneが失敗するので使わない。
    """
    return os.environ.get(
        "BOOK_TEXTS_DIR",
        os.path.join(os.path.dirname(BASE_DIR), "BookScraper",
                     "book_texts", "stock_investment"))


# 検索の対象にしない本。置き場所には入っているが、この用途では見ない。
# エミン・ユルマズの『世界インフレ時代の経済指標』は経済指標（CPI・雇用統計など）
# の本で、**個別株の選び方は書かれていない。** エミンの10倍株の条件は
# 本ではなくネット記事が出所なので、そちらを別ファイルで置いている
_SKIP_BOOKS = ("世界インフレ時代の経済指標",)


def _book_files() -> List[str]:
    import glob as _glob
    directory = _book_dir()
    return [p for p in sorted(_glob.glob(os.path.join(directory, "*")))
            if os.path.isfile(p)
            and not any(s in os.path.basename(p) for s in _SKIP_BOOKS)]


@server.tool(
    description=(
        "投資本の原文を検索して、その語の**周辺だけ**返す。"
        "リンチ『株で勝つ』、清原達郎『我が投資術』、"
        "テンバガー投資家X『トイレスマホで無限10倍株』、"
        "エミン・ユルマズ『世界インフレ時代の経済指標』などが対象。"
        "query は本文中の語（例: 在庫、ネットキャッシュ、PER、成長率、社長）。"
        "**要約ではなく原文**なので、その人が実際にどう書いたかを確かめられる。"
        "抜き書きではなく原文にあたりたいときに使う。"
    )
)
@quiet
def search_books(query: str, limit: int = 8, around: int = 400) -> Dict[str, Any]:
    import glob as _glob
    import re as _re

    directory = _book_dir()
    if not os.path.isdir(directory):
        return {
            "error": f"本文の置き場所が見つからない: {directory}",
            "対処": (
                "環境変数 BOOK_TEXTS_DIR に、本文のテキストを置いた"
                "ディレクトリを指定する。本文は著作物なのでこのリポジトリには"
                "置いていない（公開リポジトリのため）"
            ),
        }
    query = str(query or "").strip()
    if not query:
        return {"error": "検索語が空です"}

    hits = []
    for path in _book_files():
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        book = os.path.splitext(os.path.basename(path))[0]
        for m in _re.finditer(_re.escape(query), text):
            start = max(0, m.start() - around)
            snippet = text[start:m.end() + around]
            snippet = " ".join(snippet.split())
            hits.append({"本": book, "位置": m.start(), "原文": snippet})
            if len(hits) >= limit * 3:
                break

    if not hits:
        return {"検索語": query, "件数": 0,
                "本": [os.path.splitext(os.path.basename(p))[0]
                       for p in _book_files()],
                "注記": f"「{query}」はどの本にも出てこない"}

    # 本ごとに散らして返す。1冊に偏らせない
    by_book: Dict[str, List[dict]] = {}
    for h in hits:
        by_book.setdefault(h["本"], []).append(h)
    picked = []
    while len(picked) < limit and any(by_book.values()):
        for book in list(by_book):
            if by_book[book]:
                picked.append(by_book[book].pop(0))
            if len(picked) >= limit:
                break

    return {"検索語": query, "件数": len(hits), "返した数": len(picked),
            "抜粋": picked,
            "注記": "本文そのまま。要約ではない"}


@server.tool(
    description=(
        "検索できる投資本の一覧を返す。書名と文字数。"
        "search_books で何が引けるかを知りたいときに使う。"
    )
)
@quiet
def list_books() -> Dict[str, Any]:
    import glob as _glob

    directory = _book_dir()
    if not os.path.isdir(directory):
        return {
            "error": f"本文の置き場所が見つからない: {directory}",
            "対処": "環境変数 BOOK_TEXTS_DIR にディレクトリを指定する",
        }
    books = []
    for path in _book_files():
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                n = len(f.read())
        except OSError:
            n = None
        books.append({"書名": os.path.splitext(os.path.basename(path))[0],
                      "文字数": n})
    return {"置き場所": directory, "冊数": len(books), "本": books}


if __name__ == "__main__":
    server.run(transport="stdio")
