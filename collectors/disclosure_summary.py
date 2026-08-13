"""適時開示のPDFから「なぜそうするのか」の一文を抜き出す。

「5%超の売買」に並ぶ開示は、タイトルを見ても
「新株式発行及び株式売出し並びに主要株主及び親会社以外の支配株主の異動に
関するお知らせ」としか分からない。**創業者が降りたのか、上場基準を満たす
ためなのかは本文にしか書いていない。**

本文は定型の記者発表文で、企業理念から始まって数ページ続く。そこから
判断に効く文だけを、語の重み付けで選ぶ。AIは使っていない。開示の文面が
どの会社もよく似ているので、これで足りる。実際フィットイージーでは

  「東証プライム市場の上場基準である『流通株式比率35%』の充足に加えて、
    当社普通株式の流動性の向上及び投資家層の拡大を図っております」

が1位で出る。

対象は大量保有報告書の売買と時期が重なる開示だけに絞る。全部のPDFを
落とすと量が増えるうえ、判断に関係のないものが大半になるため。

  python collectors/disclosure_summary.py            # 保有銘柄
  python collectors/disclosure_summary.py 212A 160A
"""
import argparse
import csv
import glob
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.disclosure_pdf import fetch
from collectors.holding_profile_dump import portfolio_codes

TDNET_GLOB = os.path.join("data", "output", "tdnet", "*.tsv")
LVH_DIR = os.path.join("data", "output", "large_holdings")
OUT_TSV = os.path.join("data", "output", "tdnet", "summaries.tsv")

COLUMNS = ["開示日", "銘柄コード", "タイトル", "要点", "URL"]

# 売買の前後どれだけを「その売買にまつわる開示」と見るか。
# visualizer/large_holding_service.py と揃えること
BEFORE, AFTER = 35, 7

# 株主の増減に効く開示。large_holding_service._DISCLOSURE_WORDS と揃える
WORDS = (
    "売出", "募集", "新株式", "第三者割当", "自己株式", "立会外分売",
    "主要株主", "筆頭株主", "大株主", "株式分割", "資本業務提携",
    "公開買付", "株式の取得", "株式の譲渡", "新株予約権", "ロックアップ",
    "支配株主", "親会社", "子会社化", "株式交換", "合併",
)

# 記者発表文の定型。外さないと「目的」で引くたびにこれが出る
NOISE = (
    "投資勧誘", "記者発表文", "訂正事項分", "目論見書", "投資家ご自身の判断",
    "将来の予測", "現時点で入手可能な情報", "実際の業績", "以 上", "ご注意",
    "本書面", "1933年", "証券法", "頒布", "企業理念", "MISSION", "VISION",
    "掲げ", "目指します", "参照ください", "以下のとおり", "記載しております",
)

# 投資判断が変わる語ほど重く。飾り文句には点を与えない
SCORES = {
    3: ("流通株式比率", "上場基準", "市場区分", "上場維持基準", "充足",
        "株主還元", "資本効率", "支配株主", "議決権", "筆頭株主",
        "上回る", "下回る", "上振れ", "下振れ", "修正の理由", "見込まれる",
        "資本業務提携", "業務提携", "相続", "解消",
        # 「異動が生じた経緯」は、まさに何が起きたかを書いている節の見出し
        "経緯", "資本政策", "株主価値", "機動的"),
    2: ("資金使途", "充当", "成長投資", "有利子負債", "設備投資", "運転資金",
        "流動性の向上", "投資家層", "株主構成", "安定株主", "ロックアップ",
        "配当性向", "1株当たり", "１株当たり",
        "経営環境", "事業環境", "インセンティブ", "中長期"),
    1: ("目的", "理由", "背景", "方針"),
}
MIN_SCORE = 3
MIN_LEN, MAX_LEN = 25, 190


def _score(sentence: str) -> int:
    return sum(weight * sum(1 for w in words if w in sentence)
               for weight, words in SCORES.items())


# 「１．分売予定株式数 175,000 株 ２．分売実施日 … ６．実施の目的 …」のように、
# 箇条書きが句点なしで続く開示がある。番号で切って、目的・理由・経緯の項だけ残す
_NUMBERED = re.compile(r"(?:^|\s)[０-９0-9]{1,2}\s*[．.]\s*")
_POINT_WORDS = ("目的", "理由", "経緯", "背景")


def _trim_lead(sentence: str) -> str:
    parts = _NUMBERED.split(sentence)
    if len(parts) < 2:
        return sentence
    kept = [p.strip() for p in parts if any(w in p for w in _POINT_WORDS)]
    return " ".join(kept) if kept else sentence


def summarize(text: str, limit: int = 2) -> str:
    """本文から、判断に効く文を点の高い順に選ぶ"""
    flat = re.sub(r"\s+", " ", text)
    ranked = []
    for i, sentence in enumerate(re.split(r"(?<=。)", flat)):
        s = sentence.strip()
        if not (MIN_LEN <= len(s) <= MAX_LEN):
            continue
        if any(n in s for n in NOISE):
            continue
        value = _score(s)
        if value >= MIN_SCORE:
            # 同点なら本文の前のほうを採る
            ranked.append((value, -i, s))
    ranked.sort(reverse=True)
    seen, out = set(), []
    for _, _, s in ranked:
        s = _trim_lead(s)
        if not s or s[:20] in seen:
            continue
        seen.add(s[:20])
        out.append(s)
        if len(out) >= limit:
            break
    return " ".join(out)


def load_disclosures(codes: set) -> dict:
    rows = defaultdict(list)
    for path in glob.glob(TDNET_GLOB):
        if os.path.basename(path) == os.path.basename(OUT_TSV):
            continue
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.reader(f, delimiter="\t"):
                if len(row) >= 6 and row[3] in codes and any(w in row[4] for w in WORDS):
                    rows[row[3]].append((row[0], row[4], row[5]))
    return rows


def event_dates(code: str) -> set:
    """大量保有報告書で株数が動いた日"""
    path = os.path.join(LVH_DIR, f"{code}.tsv")
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8", newline="") as f:
        return {(r.get("発生日") or r.get("提出日") or "").strip()
                for r in csv.DictReader(f, delimiter="\t")} - {""}


def wanted(disclosures: list, dates: set) -> list:
    """売買と時期が重なる開示だけに絞る"""
    windows = []
    for date in dates:
        try:
            day = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            continue
        windows.append(((day - timedelta(days=BEFORE)).strftime("%Y-%m-%d"),
                        (day + timedelta(days=AFTER)).strftime("%Y-%m-%d")))
    return [d for d in disclosures
            if any(lo <= d[0] <= hi for lo, hi in windows)]


def load_done() -> dict:
    if not os.path.exists(OUT_TSV):
        return {}
    with open(OUT_TSV, encoding="utf-8", newline="") as f:
        return {r["URL"]: r for r in csv.DictReader(f, delimiter="\t")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("codes", nargs="*")
    parser.add_argument("--all-disclosures", action="store_true",
                        help="売買と重ならない開示も読む")
    parser.add_argument("--retry-empty", action="store_true",
                        help="要点が取れなかったPDFを読み直す")
    args = parser.parse_args()

    codes = set(args.codes) if args.codes else portfolio_codes()
    disclosures = load_disclosures(codes)
    done = load_done()

    targets = []
    for code in sorted(codes):
        items = disclosures.get(code, [])
        if not args.all_disclosures:
            items = wanted(items, event_dates(code))
        targets += [(code, *d) for d in items]
    # 要点が空のまま覚えてしまうと二度と読み直さない。抽出の規則を直したときや、
    # 暗号化されたPDFが読めるようになったときは --retry-empty で読み直す
    skip = {u for u, r in done.items() if r.get("要点") or not args.retry_empty}
    targets = [t for t in targets if t[3] not in skip]

    print(f"対象: {len(codes)}銘柄 / 読むPDF {len(targets)}件"
          f"（{len(done)}件は取得済み）")

    rows = list(done.values())
    empty = 0
    for i, (code, date, title, url) in enumerate(targets, 1):
        text = fetch(url)
        point = summarize(text) if text else ""
        if not point:
            empty += 1
        rows.append({"開示日": date, "銘柄コード": code, "タイトル": title,
                     "要点": point, "URL": url})
        if i % 25 == 0 or i == len(targets):
            print(f"  {i}/{len(targets)}件  要点が取れず {empty}件")
            _save(rows)
    _save(rows)
    got = sum(1 for r in rows if r["要点"])
    print(f"完了: {len(rows)}件中 {got}件に要点 ({got / max(len(rows),1):.0%}) → {OUT_TSV}")
    return 0


def _save(rows: list) -> None:
    # 同じURLが2つあるときは要点が入っているほうを残す。読み直したときに
    # 新しい結果が古い空行に負けると、いつまでも埋まらない
    best = {}
    for row in rows:
        current = best.get(row["URL"])
        if current is None or (not current["要点"] and row["要点"]):
            best[row["URL"]] = row
    unique = sorted(best.values(), key=lambda r: (r["開示日"], r["URL"]), reverse=True)
    with open(OUT_TSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, COLUMNS, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(unique)


if __name__ == "__main__":
    sys.exit(main())
