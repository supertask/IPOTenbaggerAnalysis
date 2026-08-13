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
import glob
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "output", "large_holdings")
TDNET_GLOB = os.path.join(BASE_DIR, "data", "output", "tdnet", "*.tsv")

# 割合がこれ以上動いた回だけを「動き」とみなす。提出事由には
# 「重要な契約の締結」のように株数が変わらないものも混ざる
MOVE_THRESHOLD = 0.001

# 保有目的の長い定型文を、一覧で読める短さに畳む。長文はそのまま持たせて
# ツールチップで出す。上から順に当てる
_PURPOSE_TAGS = (
    # 証券会社が売買を仲介するために持っている在庫。日々動くうえに
    # 会社の中身とは関係がなく、これが並ぶと肝心の内部者の動きが埋もれる
    ("在庫", ("商品在庫", "証券業務", "自己勘定", "トレーディング",
              "マーケットメイク")),
    ("経営参画", ("経営参画", "経営に参画", "重要提案行為")),
    ("内部者", ("代表取締役", "取締役", "監査役", "執行役", "資産管理会社",
                "安定株主", "創業")),
    ("政策保有", ("取引関係", "業務提携", "政策投資", "取引先")),
    ("純投資", ("純投資", "投資運用", "資産運用", "投資一任", "信託財産",
                "運用資産", "投資収益")),
)

# 経営陣や創業家の動きを読むうえで、並べても邪魔にしかならない区分。
# 既定では畳んで、開けば見られるようにする
_NOISE_TAGS = ("在庫", "純投資")

# 売買の前後どれだけの開示を「その売買にまつわるもの」として並べるか。
# 売出しは発表から受渡まで3週間ほどあるので前を広めに取る
_DISCLOSURE_BEFORE = 35
_DISCLOSURE_AFTER = 7

# 株主の増減に効く開示だけを引く。決算短信は毎期出るので入れない
_DISCLOSURE_WORDS = (
    "売出", "募集", "新株式", "第三者割当", "自己株式", "立会外分売",
    "主要株主", "筆頭株主", "大株主", "株式分割", "資本業務提携",
    "公開買付", "株式の取得", "株式の譲渡", "新株予約権", "ロックアップ",
    "支配株主", "親会社", "子会社化", "株式交換", "合併",
)

# 売買の理由。「増減の内訳」に1件ずつ日本語で書かれているものを型に落とす。
# 上から順に当てるので、細かいものを先に置く
_REASON_LABELS = (
    ("株式分割", ("株式分割", "分割により", "無償割当")),
    ("株式併合", ("株式併合", "併合により")),
    ("IPOの売出し", ("新規株式上場", "新規上場", "上場に伴う売出")),
    ("追加売出し", ("グリーンシュー", "オーバーアロットメント", "ＯＡ")),
    ("立会外分売", ("立会外分売",)),
    ("公開買付", ("公開買付", "ＴＯＢ")),
    ("第三者割当", ("第三者割当",)),
    ("自己株買い", ("自己株式",)),
    ("組織再編", ("株式交換", "合併", "会社分割", "株式移転")),
    ("新株予約権", ("新株予約権", "ストックオプション")),
    ("売出し", ("売出",)),
    ("募集", ("募集により", "公募")),
    ("相続・贈与", ("相続", "贈与")),
    ("担保処分", ("担保権", "担保の実行")),
    ("相対で譲渡", ("譲渡", "譲受", "相対")),
    ("市場で売買", ("市場内", "市場買付", "市場売却", "取引所")),
)

# 「2024年7月23日付の新規株式上場に伴う売出しにより2,900,000株売却」が
# 区切り文字なしで連なっている。次の日付の手前までを1件と見る
_BREAKDOWN_ITEM = re.compile(
    r"(?P<y>\d{4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日付?(?:けで|付け|で|の)?"
    r"(?P<body>.*?)(?=\d{4}年\d{1,2}月\d{1,2}日付|$)")
_BREAKDOWN_SHARES = re.compile(r"([\d,]+)\s*株")
_BREAKDOWN_SIDE = re.compile(r"(取得|売却|処分|譲受|譲渡)")

_cache: Dict[str, tuple] = {}
_tdnet_cache: Optional[Dict[str, list]] = None


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


def _load_tdnet() -> Dict[str, list]:
    """{銘柄コード: [(開示日, タイトル, URL), ...]}

    大量保有報告書に載る「保有目的」は届出の定型文で、売った当日の書類でも
    「安定株主として長期保有を目的としております」のままだったりする。
    売った本当の理由は適時開示の本文にしかないので、同じ時期の開示を
    突き合わせて出す。開示を集めているのは保有銘柄だけなので、それ以外は空。
    """
    global _tdnet_cache
    if _tdnet_cache is not None:
        return _tdnet_cache
    rows: Dict[str, list] = defaultdict(list)
    for path in glob.glob(TDNET_GLOB):
        try:
            with open(path, encoding="utf-8", newline="") as f:
                for row in csv.reader(f, delimiter="\t"):
                    if len(row) >= 6 and any(w in row[4] for w in _DISCLOSURE_WORDS):
                        rows[row[3]].append((row[0], row[4], row[5]))
        except Exception as e:
            logger.warning("適時開示の読み込みに失敗 %s: %s", path, e)
    for items in rows.values():
        items.sort(reverse=True)
    _tdnet_cache = dict(rows)
    return _tdnet_cache


def reason_label(text: str) -> str:
    """売買の理由を一言にする。当てはまらなければ空"""
    for label, words in _REASON_LABELS:
        if any(w in text for w in words):
            return label
    return ""


def _parse_breakdown(text: str) -> Dict[str, dict]:
    """「増減の内訳」を日付ごとの {理由, 株数, 向き} にばらす。

    ここが「なぜ売買したか」の本体。保有目的と違って定型文ではなく、
    1件ずつ実際の理由が書かれている。

      2024年7月23日付の新規株式上場に伴う売出しにより2,900,000株売却
      2024年8月20日付のグリーンシューオプション行使により307,900株を売却
      2022年10月31日付の株式分割（1:1,000）により648,351株取得
    """
    out: Dict[str, dict] = {}
    for m in _BREAKDOWN_ITEM.finditer(text or ""):
        # 「2024年7月23日付の新規株式上場に伴う…」の助詞が残ることがある
        body = m.group("body").strip(" 　、。").lstrip("のでけ付")
        if not body:
            continue
        date = f"{int(m.group('y')):04d}-{int(m.group('m')):02d}-{int(m.group('d')):02d}"
        shares = _BREAKDOWN_SHARES.search(body)
        side = _BREAKDOWN_SIDE.search(body)
        # 同じ日に複数件あるときは、株数の大きいほうを代表にする
        value = {
            "text": body,
            "label": reason_label(body),
            "shares": float(shares.group(1).replace(",", "")) if shares else None,
            "side": side.group(1) if side else "",
        }
        previous = out.get(date)
        if previous and (previous["shares"] or 0) >= (value["shares"] or 0):
            continue
        out[date] = value
    return out


def _parse_trades(text: str) -> Dict[str, dict]:
    """「売買明細」（最近60日間の取得又は処分）を日付ごとにばらす。

    collector が 日付|数量|市場内外|取得処分|単価 の形にしてある。
    ここには**いくらで売ったか**が入る。
    """
    out: Dict[str, dict] = {}
    for chunk in (text or "").split(";"):
        parts = chunk.split("|")
        if len(parts) != 5 or not parts[0]:
            continue
        out[parts[0]] = {
            "shares": _num(parts[1]),
            "place": parts[2],
            "side": parts[3],
            "price": _num(parts[4]),
        }
    return out


def _pick_trade(trades: Dict[str, dict], on: str,
                share_diff: Optional[float]) -> Optional[dict]:
    """その回の売買にあたる明細を選ぶ。

    明細は60日ぶん載るので、前回の報告のぶんが残っていることがある。
    また1回の報告のあいだに何日かに分けて売ることがあり、その場合は
    個々の行ではなく合計が今回の増減と一致する。合計で拾えたときは
    株数のいちばん大きい日を代表にする（単価と市場内外はそこから取る）。
    """
    if not trades:
        return None
    exact = trades.get(on) or _closest(trades, on)
    if share_diff is None:
        return exact
    want = abs(share_diff)
    if exact and abs((exact["shares"] or 0) - want) <= 1:
        return exact
    total = sum(t["shares"] or 0 for t in trades.values())
    if abs(total - want) <= 1:
        biggest = max(trades.values(), key=lambda t: t["shares"] or 0)
        return {**biggest, "shares": total}
    return None


def _mark_transfers(events: List[dict]) -> None:
    """同じ日に、同じ株数の減と増があれば関係者間の移動とみなす。

    創業者が自分の資産管理会社に持ち替えるとよく起きる。放っておくと
    「創業者が180万株売った」と読めてしまうが、実際には外に出ていない。
    """
    by_date: Dict[str, List[dict]] = defaultdict(list)
    for e in events:
        if e["share_diff"]:
            by_date[e["date"]].append(e)
    for same_day in by_date.values():
        for a in same_day:
            if a["share_diff"] >= 0:
                continue
            for b in same_day:
                if b["share_diff"] > 0 and abs(a["share_diff"] + b["share_diff"]) <= 1:
                    a["transfer"] = b["name"]
                    b["transfer"] = a["name"]


def _nearby_disclosures(code: str, on: str, limit: int = 2) -> List[dict]:
    """その売買の前後に出た、株主の増減に効く開示"""
    items = _load_tdnet().get(str(code).strip())
    if not items or not on:
        return []
    try:
        day = datetime.strptime(on, "%Y-%m-%d")
    except ValueError:
        return []
    lo = (day - timedelta(days=_DISCLOSURE_BEFORE)).strftime("%Y-%m-%d")
    hi = (day + timedelta(days=_DISCLOSURE_AFTER)).strftime("%Y-%m-%d")
    return [{"date": d, "title": t, "url": u}
            for d, t, u in items if lo <= d <= hi][:limit]


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


def _closest(items: Dict[str, dict], on: str, days: int = 5) -> Optional[dict]:
    """日付がぴったり合わないときに、近いものを採る"""
    if not items or not on:
        return None
    try:
        target = datetime.strptime(on, "%Y-%m-%d")
    except ValueError:
        return None
    best, gap = None, None
    for date, value in items.items():
        try:
            diff = abs((datetime.strptime(date, "%Y-%m-%d") - target).days)
        except ValueError:
            continue
        if diff <= days and (gap is None or diff < gap):
            best, gap = value, diff
    return best


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
        tag = purpose_tag(purpose)
        date = (row.get("発生日") or row.get("提出日") or "").strip()

        # なぜ売買したか。報告義務が生じた日と、実際に売買した日は同じはず
        # だが、書類によって数日ずれるので近いものを採る
        breakdown = _parse_breakdown(row.get("増減の内訳"))
        trades = _parse_trades(row.get("売買明細"))
        why = breakdown.get(date) or _closest(breakdown, date)
        trade = _pick_trade(trades, date, share_diff)

        near = _nearby_disclosures(company_code, date)
        # 内訳を書かない提出者もいる。そのときは会社側の開示から理由を当てる。
        # 立会外分売のように、開示のタイトルだけで型が決まるものが多い
        label = why["label"] if why else ""
        if not label:
            label = next((reason_label(d["title"]) for d in near
                          if reason_label(d["title"])), "")
        if not label and trade and trade["place"]:
            label = "市場で売買" if trade["place"] == "市場内" else "市場外で相対"

        events.append({
            "date": date,
            "filed": (row.get("提出日") or "").strip(),
            "name": name,
            "shares": shares,
            "ratio": ratio,
            "ratio_diff": ratio_diff,
            "share_diff": share_diff,
            "reason": (row.get("提出事由") or "").strip(),
            "action": _action(share_diff, ratio_diff),
            "purpose": purpose,
            "purpose_tag": tag,
            "noise": tag in _NOISE_TAGS,
            "disclosures": near,
            # 「なぜ」の3点。理由の型・原文・いくらで・市場の内外
            "why": label,
            "why_text": why["text"] if why else "",
            "price": trade["price"] if trade else None,
            "place": trade["place"] if trade else "",
            "contract": (row.get("重要な契約") or "").strip(),
            "transfer": "",
            # 株数が動いた回と、その人が初めて5%超で現れた回だけを残す。
            # 株数が変わらない届出（契約の締結、他人の売却に伴う割合の変動）は
            # 「売買」の一覧に並べても判断の材料にならない
            "moved": share_diff is None or share_diff != 0,
        })

    _mark_transfers(events)
    for e in events:
        # 持ち替えは書類に理由が書かれないことが多いが、機械的に分かる
        if e["transfer"] and not e["why"]:
            e["why"] = "関係者間で移動"
            e["why_text"] = f"同じ日に {e['transfer']} が同数を反対に動かしています"

    moves = [e for e in events if e["moved"]]
    if not moves:
        moves = events[-1:]
    moves.sort(key=lambda e: (e["date"], e["name"]), reverse=True)

    # 証券会社の在庫や信託の純投資は、日々動くうえに会社の中身と関係がない。
    # 混ぜて並べると経営陣や創業家の動きが埋もれるので、既定では畳む
    main = [e for e in moves if not e["noise"]]
    noise = [e for e in moves if e["noise"]]
    if not main:
        main, noise = noise, []

    return {
        "events": main,
        "noise": noise,
        "total": len(events),
        "holders": sorted({e["name"] for e in events}),
        "has_disclosures": any(e["disclosures"] for e in moves),
        "latest": main[0]["date"] if main else "",
    }
