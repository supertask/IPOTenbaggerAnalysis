"""テンバガー候補かどうかを11の条件で判定する。

条件は『トイレスマホで「無限10倍株」』(テンバガー投資家X, KADOKAWA) の
スクリーニング基準を、手元のデータで機械的に判定できる形にしたもの。

全部を満たす必要はなく、満たす数が多いほど良いという扱い。ただし
ビジネスモデル・売上・利益・PERの4つは必須条件として別枠で数える。

機械では判断しきれない条件（ビジネスモデルの型、ニッチトップかどうか）は
キーワードから候補を出すだけにして、自動でOKにはしない。推測で埋めると
一番重要な条件が一番あてにならない表示になるため。
"""
from __future__ import annotations

import csv
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

from visualizer import db as _index_db

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALL_COMPANIES_TSV = os.path.join(
    BASE_DIR, "data", "output", "combiner", "all_companies.tsv")
# 人がビジネスモデルを判断した結果を置く場所（無ければ「要確認」のまま）
BUSINESS_MODEL_TSV = os.path.join(BASE_DIR, "data", "meta", "business_model.tsv")

PASS, PARTIAL, FAIL, UNKNOWN = "pass", "partial", "fail", "unknown"

MARKET_CAP_LIMIT = 20_000_000_000     # 200億円
PER_LIMIT = 40.0
PER_IDEAL = 20.0
TARGET_SECTORS = ("サービス業", "情報・通信業")

# 条件2のビジネスモデル判定を助けるキーワード
BUSINESS_MODEL_HINTS = {
    "ストック型": ("サブリース", "定額", "月額", "継続課金", "サブスク", "リカーリング",
                "保守", "運用管理", "会費", "レンタル", "リース", "賃貸"),
    "多店舗展開型": ("店舗", "出店", "チェーン", "拠点", "ホーム", "施設", "教室", "サロン"),
    "営業人員依存型": ("人材", "派遣", "紹介", "コンサル", "営業支援", "採用支援", "ＦＰ", "相談"),
}
NICHE_HINTS = ("専門", "特化", "唯一", "国内初", "シェア", "トップ", "オンリーワン", "独自")
WARRANTY_HINTS = ("家賃保証", "保証事業", "保証サービス", "保証会社", "債務保証", "賃料保証")

# 各条件の「なぜ見るのか」と「どう判定しているのか」。UIで展開して読ませる
DESCRIPTIONS = {
    1: ("上場して間もないほど、株価が育つ余地が残っている。上場1年以内に絞ると"
        "調べる対象が絞れて効率が良い。5年以内までなら候補として見る。",
        "上場日から今日までの経過年数で判定。1年以内なら○、5年以内なら△。"),
    2: ("業績が伸び続ける裏付けになるのがビジネスモデル。継続課金が積み上がる"
        "ストック型、拠点を増やすほど伸びる多店舗展開型、人員を増やして伸ばす"
        "営業人員依存型の3つが有望とされる。11条件の中で最重要。",
        "事業内容の文章からキーワードで候補だけ出す。断定はできないので"
        "「要確認」のままにしている。data/meta/business_model.tsv に分類を"
        "書けばそれを使う。"),
    3: ("ビジネスモデルが良くても売上に表れていなければ意味がない。一時的な"
        "特需ではなく、継続して伸びていることが要る。",
        "目論見書の5年分の売上高が毎年増えていれば○、1度だけ落ちて全体では"
        "増えていれば△。"),
    4: ("売上だけ伸びて利益が残らない企業は、株価が長期で伸び続けない。"
        "逆にコスト削減だけで利益が出ている場合も成長とは言えない。",
        "5年分の経常利益と当期純利益の推移で判定。営業利益は目論見書の"
        "5年データに無いため、財務指標のチャート側で確認する。"),
    5: ("赤字のまま上場する企業もあるが、限られた資金で数年内に数倍を狙うには"
        "リスクが高い。黒字化してから入るほうが安全とされる。",
        "5年分の当期純利益がすべて黒字なら○、直近だけ黒字なら△。"),
    6: ("大手が来ない小さな市場で強い立場にあると、価格を決める力を持てる。"
        "同業が少ないほど稼ぐ力が強くなる。",
        "事業内容に「専門」「特化」などの記述があるかを手がかりとして出すだけで、"
        "判定はしていない。"),
    7: ("保証ビジネスはストック型の一形態で、保証する件数が積み上がるほど"
        "収入が伸びる。家賃保証・住宅ローン保証などが典型。",
        "事業内容に家賃保証・債務保証などの語があれば○、「保証」だけなら△。"),
    8: ("国内向けのサービス業・情報通信業は、景気や為替、国際情勢の影響を"
        "受けにくい。テンバガー達成銘柄にこの2業種が多いとされる。",
        "業種が「サービス業」「情報・通信業」かどうかで判定。"),
    9: ("規模が小さいほど株価が伸びる余地が大きい。大型株が10倍になるのは"
        "難しいが、小型株なら現実的。",
        "公開価格を基準にした想定時価総額が200億円以下かで判定。"),
    10: ("創業者が大株主なら、株価が上がることが自分の利益になるので株主と"
         "利害が一致する。逆にVCの比率が高いと、ロックアップ解除後の売り圧力に"
         "なりやすい。役員に株が分散している場合も、退任時の売却に注意。",
         "社長の保有比率が20%以上でVCが20%未満なら○、社長10%以上なら△。"),
    11: ("良い銘柄でも割高な時に買うと、下落したときの傷が深くなる。割安で"
         "入れれば下値の余地が小さく、上昇したときの値幅も大きい。",
         "40倍以下で○、20倍以下なら理想的。株価から求めた現在のPERを使い、"
         "取れない場合は公開価格時のPERを使う。"),
}

_rows_cache: Optional[Dict[str, dict]] = None
_manual_cache: Optional[Dict[str, dict]] = None


def _load_manual() -> Dict[str, dict]:
    global _manual_cache
    if _manual_cache is not None:
        return _manual_cache
    manual: Dict[str, dict] = {}
    if os.path.exists(BUSINESS_MODEL_TSV):
        try:
            with open(BUSINESS_MODEL_TSV, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f, delimiter="\t"):
                    code = (row.get("コード") or "").strip().upper()
                    if code:
                        manual[code] = row
        except OSError as e:
            logger.warning("ビジネスモデルの手動指定を読めませんでした: %s", e)
    _manual_cache = manual
    return manual


def _load_rows() -> Dict[str, dict]:
    """all_companies を銘柄コード引きできる形で読む（DB優先）"""
    global _rows_cache
    if _rows_cache is not None:
        return _rows_cache

    rows: Dict[str, dict] = {}
    conn = _index_db.get_conn()
    if conn is not None:
        try:
            for r in conn.execute(
                    "SELECT code, all_companies_json FROM companies "
                    "WHERE all_companies_json IS NOT NULL"):
                try:
                    rows[str(r["code"]).strip().upper()] = json.loads(r["all_companies_json"])
                except (TypeError, ValueError):
                    continue
        except Exception as e:
            logger.warning("DBからの企業データ読み込みに失敗: %s", e)

    if not rows and os.path.exists(ALL_COMPANIES_TSV):
        try:
            with open(ALL_COMPANIES_TSV, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f, delimiter="\t"):
                    code = (row.get("コード") or "").strip().upper()
                    if code:
                        rows[code] = row
        except OSError as e:
            logger.warning("all_companies.tsv を読めませんでした: %s", e)

    _rows_cache = rows
    return rows


def get_company_row(code) -> Optional[dict]:
    if code is None:
        return None
    return _load_rows().get(str(code).strip().upper())


def _num(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _series_pairs(row: dict, key: str):
    """企業業績のデータ（5年分）から指定項目を (期, 値) の古い順で取り出す"""
    raw = row.get("企業業績のデータ（5年分）")
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return []
    for item in raw or []:
        for name, values in (item or {}).items():
            if name.startswith(key):
                pairs = [(str(k).replace("\n", ""), _num(v)) for k, v in values.items()]
                pairs = [(k, v) for k, v in pairs if v is not None]
                pairs.sort(key=lambda kv: kv[0])
                return pairs
    return []


def _series(row: dict, key: str) -> List[float]:
    return [v for _, v in _series_pairs(row, key)]


def _series_evidence(row: dict, key: str, unit: str = "百万円") -> List[dict]:
    """根拠として出す実数値の並び"""
    return [{"label": period, "value": f"{value:,.0f}{unit}"}
            for period, value in _series_pairs(row, key)]


def _snippet(text: str, word: str, width: int = 40) -> str:
    """該当語の前後を切り出して、どこで引っかかったか分かるようにする"""
    index = (text or "").find(word)
    if index < 0:
        return ""
    start = max(0, index - width // 2)
    end = min(len(text), index + len(word) + width // 2)
    return ("…" if start else "") + text[start:end].replace("\n", " ") + ("…" if end < len(text) else "")


def _trend(values: List[float]) -> str:
    """毎年増えていれば pass、1度だけ落ちて全体では増えていれば partial"""
    if len(values) < 3:
        return UNKNOWN
    dips = sum(1 for a, b in zip(values, values[1:]) if b < a)
    if dips == 0:
        return PASS
    if dips == 1 and values[-1] > values[0]:
        return PARTIAL
    return FAIL


def _growth_note(values: List[float]) -> str:
    if len(values) < 2 or not values[0]:
        return ""
    years = len(values) - 1
    try:
        cagr = (values[-1] / values[0]) ** (1 / years) - 1
    except (ValueError, ZeroDivisionError):
        return ""
    return f"{len(values)}期 年率{cagr * 100:+.0f}%"


def _hits(text: str, words) -> List[str]:
    return [w for w in words if w in (text or "")]


def _years_since_ipo(row: dict) -> Optional[float]:
    raw = str(row.get("上場日") or "").strip()
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y年%m月%d日"):
        try:
            return (datetime.now() - datetime.strptime(raw, fmt)).days / 365.25
        except ValueError:
            continue
    year = _num(row.get("上場年"))
    if year:
        return datetime.now().year - year
    return None


def evaluate(row: Optional[dict], current_per: Optional[float] = None) -> Optional[dict]:
    """11条件を判定する。current_per を渡すとPER判定に現在値を使う"""
    if not row:
        return None

    business = str(row.get("事業内容") or "")
    items: List[dict] = []

    def add(no, title, status, detail, required=False, evidence=None):
        why, how = DESCRIPTIONS.get(no, ("", ""))
        items.append({"no": no, "title": title, "status": status,
                      "detail": detail, "required": required,
                      "evidence": evidence or [], "why": why, "how": how})

    # 1 上場からの経過年数
    years = _years_since_ipo(row)
    ipo_evidence = []
    if row.get("上場日"):
        ipo_evidence.append({"label": "上場日", "value": str(row.get("上場日"))})
    if years is not None:
        ipo_evidence.append({"label": "経過年数", "value": f"{years:.1f}年"})
    if years is None:
        add(1, "上場1年以内", UNKNOWN, "上場日が不明", evidence=ipo_evidence)
    elif years <= 1:
        add(1, "上場1年以内", PASS, f"上場から{years:.1f}年", evidence=ipo_evidence)
    elif years <= 5:
        add(1, "上場1年以内", PARTIAL, f"上場から{years:.1f}年（5年以内）", evidence=ipo_evidence)
    else:
        add(1, "上場1年以内", FAIL, f"上場から{years:.1f}年", evidence=ipo_evidence)

    # 2 ビジネスモデル（必須・人の判断が要る）
    manual = _load_manual().get(str(row.get("コード") or "").strip().upper(), {})
    manual_model = (manual.get("分類") or "").strip()
    if manual_model:
        add(2, "成長性の高いビジネスモデル", PASS, manual_model, required=True,
            evidence=[{"label": "手動指定", "value": manual_model}])
    else:
        model_evidence = []
        found = []
        for name, words in BUSINESS_MODEL_HINTS.items():
            hits = _hits(business, words)
            if hits:
                found.append(name)
                model_evidence.append({"label": name,
                                       "value": "／".join(hits[:4]) + " を検出"})
                model_evidence.append({"label": "該当箇所",
                                       "value": _snippet(business, hits[0])})
        hint = "／".join(found) + "の可能性" if found else "手がかりなし"
        add(2, "成長性の高いビジネスモデル", UNKNOWN, f"要確認（{hint}）", required=True,
            evidence=model_evidence)

    # 3 売上
    sales = _series(row, "売上高")
    status = _trend(sales)
    note = _growth_note(sales) or "データ不足"
    add(3, "売上が右肩上がり", status, note, required=True,
        evidence=_series_evidence(row, "売上高"))

    # 4 利益（IPO時の5年データには営業利益が無いので経常利益で見る）
    ordinary = _series(row, "経常利益")
    net = _series(row, "当期純利益")
    profit_evidence = ([{"label": "― 経常利益 ―", "value": ""}]
                       + _series_evidence(row, "経常利益")
                       + [{"label": "― 当期純利益 ―", "value": ""}]
                       + _series_evidence(row, "当期純利益"))
    statuses = [s for s in (_trend(ordinary), _trend(net)) if s != UNKNOWN]
    if not statuses:
        add(4, "経常利益・当期純利益が伸びている", UNKNOWN, "データ不足", required=True,
            evidence=profit_evidence)
    elif all(s == PASS for s in statuses):
        add(4, "経常利益・当期純利益が伸びている", PASS, _growth_note(net) or "増益継続",
            required=True, evidence=profit_evidence)
    elif FAIL in statuses:
        add(4, "経常利益・当期純利益が伸びている", FAIL, "減益の年がある", required=True,
            evidence=profit_evidence)
    else:
        add(4, "経常利益・当期純利益が伸びている", PARTIAL, "1期のみ減益", required=True,
            evidence=profit_evidence)

    net_evidence = _series_evidence(row, "当期純利益")
    if not net:
        add(5, "黒字企業", UNKNOWN, "データ不足", evidence=net_evidence)
    elif net[-1] > 0 and all(v > 0 for v in net):
        add(5, "黒字企業", PASS, f"直近 {net[-1]:,.0f}百万円", evidence=net_evidence)
    elif net[-1] > 0:
        add(5, "黒字企業", PARTIAL, "直近は黒字（過去に赤字あり）", evidence=net_evidence)
    else:
        add(5, "黒字企業", FAIL, f"直近 {net[-1]:,.0f}百万円", evidence=net_evidence)

    # 6 ニッチトップ（人の判断が要る）
    niche = _hits(business, NICHE_HINTS)
    niche_evidence = []
    if niche:
        niche_evidence.append({"label": "検出した語", "value": "／".join(niche[:5])})
        niche_evidence.append({"label": "該当箇所", "value": _snippet(business, niche[0], 60)})
    add(6, "ニッチ市場でトップ／オンリーワン", UNKNOWN,
        "要確認（" + ("／".join(niche[:3]) + " の記述あり" if niche else "手がかりなし") + "）",
        evidence=niche_evidence)

    # 7 保証ビジネス
    warranty = _hits(business, WARRANTY_HINTS)
    if warranty:
        add(7, "保証ビジネス", PASS, "／".join(warranty[:2]),
            evidence=[{"label": "検出した語", "value": "／".join(warranty)},
                      {"label": "該当箇所", "value": _snippet(business, warranty[0], 60)}])
    elif "保証" in business:
        add(7, "保証ビジネス", PARTIAL, "「保証」の記述あり（要確認）",
            evidence=[{"label": "該当箇所", "value": _snippet(business, "保証", 60)}])
    else:
        add(7, "保証ビジネス", FAIL, "該当なし")

    # 8 業種
    sector = str(row.get("業種") or "").strip()
    sector_evidence = [{"label": "業種", "value": sector or "（空）"}]
    if row.get("industry"):
        sector_evidence.append({"label": "industry", "value": str(row.get("industry"))})
    if sector in TARGET_SECTORS:
        add(8, "サービス業・情報通信業", PASS, sector, evidence=sector_evidence)
    elif not sector or sector == "-":
        add(8, "サービス業・情報通信業", UNKNOWN, "業種が不明", evidence=sector_evidence)
    else:
        add(8, "サービス業・情報通信業", FAIL, sector, evidence=sector_evidence)

    # 9 時価総額
    cap = _num(row.get("想定時価総額"))
    if cap is None:
        add(9, "時価総額200億円以下", UNKNOWN, "データなし")
    else:
        oku = cap / 100_000_000
        cap_evidence = [{"label": "想定時価総額", "value": f"{cap:,.0f}円（{oku:,.1f}億円）"},
                        {"label": "基準", "value": "200億円以下"}]
        for key, label in (("公開価格", "公開価格"), ("上場時発行済株数", "上場時発行済株数")):
            value = _num(row.get(key))
            if value:
                cap_evidence.append({"label": label, "value": f"{value:,.0f}"})
        add(9, "時価総額200億円以下",
            PASS if cap <= MARKET_CAP_LIMIT else FAIL, f"{oku:,.0f}億円",
            evidence=cap_evidence)

    # 10 創業社長が大株主
    president = _num(row.get("社長_株%"))
    vc = _num(row.get("VC_ファンド_株%")) or 0.0
    officers = _num(row.get("役員_株%")) or 0.0
    holder_evidence = []
    for key, label in (("社長_株%", "社長"), ("役員_株%", "役員"), ("家族_株%", "家族"),
                       ("親会社_株%", "親会社"), ("従業員_株%", "従業員"),
                       ("VC_ファンド_株%", "VC・ファンド")):
        value = _num(row.get(key))
        if value:
            holder_evidence.append({"label": label, "value": f"{value:.1f}%"})
    top = row.get("株主名と比率")
    if isinstance(top, str):
        try:
            top = json.loads(top)
        except (TypeError, ValueError):
            top = []
    for s in (top or [])[:3]:
        ratio = _num(s.get("比率"))
        if ratio is not None:
            lockup = str(s.get("ロックアップ") or "").strip()
            suffix = f"／{lockup}" if lockup and lockup != "None" else ""
            holder_evidence.append({"label": s.get("株主名") or "",
                                    "value": f"{ratio:.2f}%{suffix}"})
    if president is None:
        add(10, "創業社長が大株主", UNKNOWN, "株主データなし", evidence=holder_evidence)
    else:
        note = f"社長{president:.1f}%"
        if vc:
            note += f" / VC{vc:.1f}%"
        if officers >= 20:
            note += f" / 役員分散{officers:.1f}%"
        if president >= 20 and vc < 20:
            add(10, "創業社長が大株主", PASS, note, evidence=holder_evidence)
        elif president >= 10:
            add(10, "創業社長が大株主", PARTIAL, note, evidence=holder_evidence)
        else:
            add(10, "創業社長が大株主", FAIL, note, evidence=holder_evidence)

    # 11 PER（現在値が取れていればそちらを使う）
    per = current_per if current_per is not None else _num(row.get("PER"))
    source = "現在" if current_per is not None else "公開価格時"
    per_evidence = []
    if current_per is not None:
        per_evidence.append({"label": "現在のPER",
                             "value": f"{current_per:.1f}倍（終値 ÷ 直近の実績EPS）"})
    ipo_per = _num(row.get("PER"))
    if ipo_per:
        per_evidence.append({"label": "公開価格時のPER", "value": f"{ipo_per:.1f}倍"})
    per_evidence.append({"label": "基準", "value": f"{PER_LIMIT:.0f}倍以下（理想は{PER_IDEAL:.0f}倍以下）"})
    if per is None or per <= 0:
        add(11, f"PER{PER_LIMIT:.0f}倍以下", UNKNOWN, "PERなし（赤字など）", required=True,
            evidence=per_evidence)
    elif per <= PER_IDEAL:
        add(11, f"PER{PER_LIMIT:.0f}倍以下", PASS,
            f"{source} {per:.1f}倍（理想の{PER_IDEAL:.0f}倍以下）", required=True,
            evidence=per_evidence)
    elif per <= PER_LIMIT:
        add(11, f"PER{PER_LIMIT:.0f}倍以下", PASS, f"{source} {per:.1f}倍", required=True,
            evidence=per_evidence)
    else:
        add(11, f"PER{PER_LIMIT:.0f}倍以下", FAIL, f"{source} {per:.1f}倍", required=True,
            evidence=per_evidence)

    passed = sum(1 for i in items if i["status"] == PASS)
    required = [i for i in items if i["required"]]
    required_failed = [i["no"] for i in required if i["status"] == FAIL]
    return {
        "items": items,
        "passed": passed,
        "total": len(items),
        "required_passed": sum(1 for i in required if i["status"] == PASS),
        "required_total": len(required),
        "required_failed": required_failed,
        # 条件2は文章からは判定できず「要確認」のままなので、必須が全部OKになることは
        # ほぼ無い。足切りには「必須条件に✕が無いか」を使う。
        "required_no_fail": not required_failed,
    }


def evaluate_by_code(code, current_per: Optional[float] = None) -> Optional[dict]:
    return evaluate(get_company_row(code), current_per)


def annotate(companies) -> None:
    """企業リストに条件の該当数を付ける（一覧用。PERは公開価格時の値を使う）"""
    for company in companies or []:
        if not isinstance(company, dict):
            continue
        result = evaluate_by_code(company.get("code"))
        if result:
            company["criteria_passed"] = result["passed"]
            company["criteria_total"] = result["total"]
            company["criteria_required_ok"] = result["required_no_fail"]
