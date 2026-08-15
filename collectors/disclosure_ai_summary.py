"""適時開示のPDFを OpenRouter の無料モデルに読ませて、要約と判定を書く。

**保有銘柄の開示は3,649件ある。** Claudeが1件ずつ読むとトークンが持たないので、
数をこなす部分は無料のモデルに任せる（`docs/TODO.md` の積み残し）。
書き先は `holding-review` スキルと同じ `data/meta/disclosure_reading.tsv`。

    python collectors/disclosure_ai_summary.py --codes 7115 --limit 5 --dry-run
    python collectors/disclosure_ai_summary.py --codes 7115
    python collectors/disclosure_ai_summary.py               # 保有銘柄ぜんぶ

**キーは環境変数から取る。** `OPENROUTER_API_KEY_PERSONAL`。
ここは公開リポジトリなので書かない。無ければ何もせずに終わる。

**出力はAIなので、画面では「AIによる解釈」のバッジが付く。** MCPからは返さない
（`CLAUDE.md`）。原文のPDFへのリンクは必ず残すこと。
"""
import argparse
import concurrent.futures
import csv
import io
import logging
import json
import os
import random
import re
import sys
import time
from datetime import date

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pypdfは壊れたPDFで大量に警告を出す。読めてはいるので黙らせる
logging.getLogger("pypdf").setLevel(logging.CRITICAL)

from collectors import disclosure_pdf  # noqa: E402
from collectors.holding_profile_dump import portfolio_codes  # noqa: E402
from collectors.llm_client import BACKENDS, LLM  # noqa: E402

TSV = os.path.join("data", "meta", "disclosure_reading.tsv")
COLUMNS = ["URL", "銘柄コード", "開示日", "タイトル", "要約", "株主にとって", "作成日"]

# 本文をどこまで渡すか。目的・理由・数字は前半に集まっているので、
# 全文を渡してもトークンが増えるだけで精度は上がらない
BODY_CHARS = 6000

JUDGMENTS = ("好材料", "悪材料", "中立", "判断できない")

# **文字がフォントで描かれていて抽出できないPDFがある。** 実測で6%
# （行政処分、内部統制の重要な不備など、落とすと痛いものが混ざる）。
# 埋め込み画像を取り出しても2KBのロゴしか入っていないので、
# **ページをそのまま描画して見せる**しかない
IMAGE_SCALE = 2.0    # 72dpi × 2。小さい字が潰れない程度
IMAGE_PAGES = 3      # 目的と理由は先頭に集まっている
MIN_BODY = 200       # これ未満なら本文が取れていないとみなす

# **画像はテキストの約10倍かかる**（実測 273秒 対 8〜30秒）。
# 混ぜて流すと、画像の1件が並列の枠を4分半ふさいで全体が引きずられる。
# テキストを先に片付けてから、画像だけを少ない並列で流す
IMAGE_WORKERS = 2

# **理由が書かれていない型。** 月次の進捗報告や訂正は、読んでも
# 「何株買った」以上のことが出てこない。無理に要約させると水増しになる
SKIP_TITLE = re.compile(
    r"(新株予約権.*行使状況|決算説明.*資料|補足資料|決算説明会|"
    r"日々の開示事項|定款一部変更|役員人事)")

PROMPT = """あなたは日本株の適時開示を読む担当者です。次の開示PDFの本文を読み、
JSONだけを返してください。前置きも説明も不要です。

{{"要約": "...", "株主にとって": "好材料|悪材料|中立|判断できない"}}

## 要約の書き方
- **1〜2文、110字以内の日本語。これは厳守。** 画面の狭い欄に並べるので、
  超えたら情報を削って収める。数字は大事なものから2〜3個に絞る
- 入れるもの: ①何をしたか（誰が・何株・いくら）②会社が書いている理由
  ③株主にとって何を意味するか
- **本文に書いてあることだけ**。推測や「〜の可能性がある」は書かない
- **数字は本文にある表記をそのまま写す。計算しない。**
  複数の区分（取締役ぶんと従業員ぶんなど）が別々に書かれていても、
  **足し合わせて合計を作らない。** 代表的な1つを選ぶか、区分ごとに書く。
  実際に7,500株と7,326株を足して16,196株という存在しない数字を書いた例がある
- 丸めない。「約5億円」ではなく本文どおりの「25,650,000円」

## 「株主にとって」の決め方
- **中身の良し悪しであって、株価の予測ではない**
- 好材料: 上方修正 / 増配 / 自己株買いの実行（枠の設定ではなく取得の実績）/
  金額が示された受注・提携
- 悪材料: 下方修正 / 減配・無配 / 希薄化を伴う増資 / 大株主の売出し /
  減損・特別損失 / 業績予想の未定への変更
- 中立: 会社自身が「影響は軽微」と書いている / 「〜が期待されます」しかない /
  組織変更・役員異動 / 実質無償のM&A
- 判断できない: 月次の進捗で枠に対する進み具合が読めない / 訂正のみ /
  本文から向きが決められない
- **会社の期待は根拠にしない。** 金額・株数・比率があるときだけ向きを付ける
- **好材料と悪材料が両方あるときは「中立」。** 例: 業績を下方修正したが
  同時に増配した。どちらの向きも読み取れているので「判断できない」ではない
- 「判断できない」は**本文から向きが読み取れないとき**だけ。数字が載っているなら
  必ず好材料・悪材料・中立のどれかになる

### 決算短信の場合（型が決まっているので必ずこの順で判定する）
1. 業績予想を上方修正した → 好材料
2. 業績予想を下方修正した、または未定にした → 悪材料
3. 予想は据え置きで、実績が前年同期比で**増収かつ増益** → 好材料
4. 予想は据え置きで、実績が前年同期比で**減収または減益** → 悪材料
5. 増収減益・減収増益のように向きが割れている → 中立

**同じ決算について「判断できない」を選ばないこと。** 決算短信には必ず
前年同期比の数字が載っているので、上の1〜5のどれかに当てはまる。

## 返し方
考える過程は書かず、**JSONだけ**を返してください。

## 開示
銘柄コード: {code}
開示日: {date}
タイトル: {title}

本文:
{body}
"""


def page_images(url: str):
    """PDFのページを描画してJPEGにする。取れなければ空"""
    import base64  # noqa: F401  （llm_client 側で使う）
    import io as _io
    import os as _os

    try:
        import pypdfium2 as pdfium
    except ImportError:
        return []
    path = _os.path.join(disclosure_pdf.CACHE_DIR,
                         url.strip("/").replace("/", "_"))
    if not _os.path.exists(path):
        disclosure_pdf.fetch(url)
    if not _os.path.exists(path):
        return []
    try:
        doc = pdfium.PdfDocument(path)
        out = []
        for i in range(min(len(doc), IMAGE_PAGES)):
            img = doc[i].render(scale=IMAGE_SCALE).to_pil().convert("RGB")
            buf = _io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            out.append(buf.getvalue())
        return out
    except Exception:
        return []


def unverified_numbers(summary: str, body: str):
    """要約の数字のうち、本文に見当たらないものを返す。

    **書かせたあとに検算する。** いちばん多い誤りが数字のでっち上げで、
    しかも機械で見つけられる。見つけたら言い直させれば直ることが多い。
    判定は `disclosure_ai_check` と同じものを使う（物差しを1つにする）。
    """
    from collectors.disclosure_ai_check import (_same_after_scaling, normalize,
                                                numbers)

    flat = normalize(body)
    missing = []
    for n in numbers(summary):
        if len(n) < 2 or n in flat:
            continue
        if _same_after_scaling(n, flat):
            continue
        missing.append(n)
    return missing


def _drop_numbers(summary: str, bad) -> str:
    """本文に無い数字を含む文を落とす。**残すより消すほうが安全**"""
    from collectors.disclosure_ai_check import normalize

    kept = []
    for part in re.split(r"(?<=。)", summary):
        flat = normalize(part)
        if any(_matches(flat, n) for n in bad):
            continue
        kept.append(part)
    return "".join(kept).strip() or summary


def _matches(flat_part: str, value: str) -> bool:
    """その文にその数字が入っているか（桁の書き方の違いを吸収する）"""
    from collectors.disclosure_ai_check import numbers

    return value in numbers(flat_part)


def load_tsv():
    if not os.path.exists(TSV):
        return []
    with io.open(TSV, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def save_tsv(rows):
    rows.sort(key=lambda r: (r.get("銘柄コード", ""), r.get("開示日", "")))
    with io.open(TSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLUMNS, delimiter="\t", lineterminator="\n",
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


MAX_SUMMARY = 130   # 110字を目安に指示しているが、少しの超過は許す


def parse(text: str):
    """モデルの返答からJSONを取り出す。前置きが付くことがある"""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        got = json.loads(m.group(0))
    except ValueError:
        return None
    summary = str(got.get("要約") or "").strip()
    judge = str(got.get("株主にとって") or "").strip()
    if not summary:
        return None
    if judge not in JUDGMENTS:
        judge = "判断できない"
    if len(summary) > MAX_SUMMARY:
        return None      # 長すぎる。呼び出し側が言い直して投げ直す
    return {"要約": summary, "株主にとって": judge}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--codes", nargs="+", help="銘柄コードで絞る")
    parser.add_argument("--limit", type=int, default=0, help="件数の上限")
    parser.add_argument("--backend", choices=sorted(BACKENDS),
                        help="openrouter（既定）か lmstudio。環境変数 LLM_BACKEND でも指定できる")
    parser.add_argument("--model", help="バックエンドの既定モデルを上書きする")
    parser.add_argument("--dry-run", action="store_true",
                        help="TSVに書かず、結果だけ出す")
    parser.add_argument("--redo", action="store_true",
                        help="要約済みのものも書き直す")
    parser.add_argument("--workers", type=int,
                        help="同時に投げる数。既定はバックエンドごと。429が出たら下げる")
    parser.add_argument("--skip-images", action="store_true",
                        help="本文が取れないもの（画像が要るもの）を飛ばす。**まずこれで流す**")
    parser.add_argument("--images-only", action="store_true",
                        help="本文が取れないものだけを画像で読む。テキストを片付けたあとに")
    args = parser.parse_args()

    llm = LLM.from_name(args.backend)
    if args.model:
        llm.backend.model = args.model
    workers = args.workers or (IMAGE_WORKERS if args.images_only
                               else llm.backend.workers)
    # **サーバが受け付けられる数を超えない。** 超えて投げても断られず、
    # キューに積まれて全員が遅くなるだけ
    workers, note = llm.cap_workers(workers)
    if note:
        print(note)

    rows = load_tsv()
    by_url = {r["URL"]: r for r in rows}
    codes = args.codes or sorted(portfolio_codes())

    todo = []
    for code in codes:
        for row in disclosure_pdf.find(code, months=240):
            url = row[5]
            if SKIP_TITLE.search(row[4]):
                continue
            if not args.redo and (by_url.get(url) or {}).get("要約"):
                continue
            todo.append((code, row[0], row[4], url))
    todo.sort(key=lambda x: x[1], reverse=True)   # 新しいものから
    if args.limit:
        todo = todo[:args.limit]

    print(f"対象 {len(todo):,}件 / {llm.backend.name} {llm.backend.model}"
          f" / 同時 {workers}")
    done = failed = 0
    started = time.time()

    def work(item):
        """PDFを読んでモデルに投げる。**書き込みはしない**（1本に集める）"""
        code, day, title, url = item
        body = disclosure_pdf.fetch(url) or ""
        needs_image = len(body.strip()) < MIN_BODY
        if args.skip_images and needs_image:
            return item, None, "本文が取れないので後回し（--images-only で拾う）"
        if args.images_only and not needs_image:
            return item, None, "本文が取れるので対象外"
        images = []
        if needs_image:
            # **本文が取れないものは画像で読ませる。** 6%あり、行政処分のような
            # 落とすと痛い開示が混ざっている。画像を見られないバックエンドでは諦める
            if not llm.can_see:
                return item, None, f"本文を取れず（{len(body.strip())}字・画像非対応）"
            images = page_images(url)
            if not images:
                return item, None, f"本文も画像も取れず（{len(body.strip())}字）"
            body = "（本文を抽出できないため、PDFのページを画像で添えています）"
        prompt = PROMPT.format(code=code, date=day, title=title,
                               body=body[:BODY_CHARS])
        text, usage = llm.ask(prompt, images=images or None)
        got = parse(text)

        # **数字を検算して、合わなければ言い直させる。** 実測でいちばん多い誤りが
        # 数字のでっち上げ（複数の区分を足して存在しない合計を作る）で、
        # 本文と突き合わせれば機械で気づける
        if got and not images:
            missing = unverified_numbers(got["要約"], body)
            if missing:
                retry = (prompt + "\n\n【やり直し】前回の要約に、本文に無い数字が"
                         f"含まれていました: {', '.join(missing[:5])}。"
                         "**本文にある表記だけを写してください。足し算をしないでください。**"
                         "確認できない数字は書かず、言葉で述べてください。")
                text2, usage2 = llm.ask(retry, tries=2)
                got2 = parse(text2 or "")
                if got2:
                    left = unverified_numbers(got2["要約"], body)
                    if not left:
                        got, usage = got2, usage2
                    else:
                        # **2回言っても直らない数字は、書かせるより消す。**
                        # でっち上げた数字が残るくらいなら、数字が減るほうがまし
                        got, usage = got2, usage2
                        got["要約"] = _drop_numbers(got2["要約"], left)
        if not got:
            # **返答が壊れることがある。** 上流が途中で切ることがあり、
            # completion_tokens が2桁で返ってきた例があった。言い直して1回だけ試す
            time.sleep(2.0)
            text, usage = ask(key, args.model,
                              prompt + "\n\n必ず1行のJSONだけを返してください。",
                              tries=2)
            got = parse(text)
        return item, got, ("" if got else str(usage)[:80])

    # **`map` は投入順にしか返さない。** 1件目が遅いと、あとが終わっていても
    # 表示されず「止まっている」ように見える。終わったものから出す
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(work, it) for it in todo]
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            item, got, why = future.result()
            code, day, title, url = item
            if not got:
                print(f"  {i}/{len(todo)} {code} {day} 失敗: {why}")
                failed += 1
                continue

            print(f"  {i}/{len(todo)} {code} {day} [{got['株主にとって']}] {title[:26]}")
            if args.dry_run:
                print(f"        {got['要約']}")
            else:
                row = by_url.get(url) or {"URL": url, "銘柄コード": code,
                                          "開示日": day, "タイトル": title}
                row.update(got)
                row["作成日"] = date.today().isoformat()
                if url not in by_url:
                    rows.append(row)
                    by_url[url] = row
                # 途中で止めても書いたぶんは残るように、こまめに保存する
                if i % 20 == 0:
                    save_tsv(rows)
            done += 1

    if not args.dry_run and done:
        save_tsv(rows)
    span = time.time() - started
    print(f"\n書けた {done}件 / 失敗 {failed}件 / {span/60:.1f}分"
          + (f" （1件 {span/max(done+failed,1):.1f}秒）" if done or failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
