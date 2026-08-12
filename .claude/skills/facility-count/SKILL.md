---
name: facility-count
description: 拠点数の抽出（collectors/facility_count_collector.py）を触るときに使う。本文から店舗数を拾う判定は取り違えやすく、片方を直すと別の銘柄が壊れる。既知の実例で当て直す手順と、これまでに踏んだ罠の一覧。
---

# 拠点数の抽出を触るとき

拠点数はXBRLにタグが無く、有報の本文から拾うしかない。
本文には自社の拠点でない数字が同じ形で出てくるため、**取り違えが起きる**。

**判定を1文字でも変えたら、下の実例で必ず当て直すこと。**
片方を直すともう片方が壊れる。実際に何度も壊した。

## 当て直しの実行

```bash
python -c "
import sys; sys.path.insert(0,'.')
from visualizer import db as _db
from collectors.facility_count_collector import extract_from_report
conn=_db.get_conn()
cases=[('7061','annual','59施設'),('9158','annual','95拠点'),('9158','quarterly','取れず'),
       ('141A','annual','352店舗'),('141A','quarterly','611店舗'),('212A','annual','238店舗'),
       ('212A','quarterly','275店舗'),('9346','quarterly','124拠点'),('2670','annual','1505店舗'),
       ('2674','annual','1078店舗'),('6574','annual','80店舗(計画値/override済)')]
for code, rtype, want in cases:
    r=conn.execute('''SELECT report_date, file_path FROM report_files WHERE company_code=? AND report_type=?
                      ORDER BY report_date DESC LIMIT 1''',(code,rtype)).fetchone()
    res=extract_from_report(str(_db.BASE_DIR/r['file_path'])) if r else None
    got=f\"{res['count']:,.0f}{res['unit']}\" if res else '取れず'
    mark='OK ' if got.replace(',','')==want.replace(',','').split('(')[0] else 'NG '
    print(f'{mark}{code} {rtype:10} 期待={want:12} 実際={got}')
"
```

11件すべてOKになってから全件を流す。

```bash
python collectors/facility_count_collector.py             # 有報。41,000件で7〜8分
python collectors/facility_count_collector.py --interim   # 期中の報告書。保有銘柄のみ。数秒
```

流したあとは前回のTSVと差分を取り、値が変わった銘柄を数件抜き取って本文を読む。

## 踏んだ罠

| 誤って拾うもの | 本文の例 | 正しい値 |
|---|---|---|
| 導入先の店舗数 | 「Skip Cartの…導入店舗数は258店舗」 | 352店舗（141A） |
| 増えたぶんの数 | 「支援先主要拠点数は106（前年同期比18拠点増）」 | 95拠点（9158） |
| 新規開設の数 | 「ホスピス施設11施設を新規開設した」 | 59施設（7061） |
| 改装した数 | 「19店舗を改装しており」 | 352店舗（141A） |
| 翌期の計画値 | 「翌事業年度末の店舗数を80店舗と計画」 | 73店舗（6574） |
| 市場規模 | 「全国の訪問看護ステーション数は…約18,000事業所」 | 95拠点（9158） |
| 顧客の数 | 「705病院」（医療情報会社の顧客） | 拠点の概念なし（3902） |

## 判定の勘どころ

- **「新規」は数値の前にも後ろにも来る**。「新規施設（11施設）」と「11施設を新規開設」。
  ただし「95拠点であり、今後も積極的な新規拠点展開を」は総数なので、
  **後ろは8文字までしか見ない**。ここを広げるとシーユーシーの4期が1期に減り、
  グラフごと消える（2期以上ないと描かない）
- 直前に「店舗数」「合計」「末時点」があれば総数として救う。
  ただし「導入も含む導入店舗数は258店舗」のように打ち消しが挟まれば救わない
- 「約18,000事業所」のような概数は市場規模。自社の拠点数は実数なので概数にならない

## 単位を増やすとき

「1拠点あたりの採算」が意味を持つのは、拠点を増やすことが成長の形になっている業態だけ。
工場・倉庫・支店・営業所は数えられても採算の単位ではないので入れない。
実際に入れたら、拠点数94のダイドーが「4工場」に化けた。
病院も外した（医療情報の会社が顧客の705病院を自社の拠点として拾う）。

## それでも誤るとき

`data/meta/facility_override.tsv` に人が確かめた値を書く。
拠点数を空にすれば、その銘柄では拠点あたりの採算を出さない
（エランのように、そもそも拠点あたりが成り立たない業態がある）。
