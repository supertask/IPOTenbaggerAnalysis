# このリポジトリで作業するときの前提

セットアップ・デプロイは `README.md`、これからやることは `docs/TODO.md`。
手順の詳細はスキルに置いてある。

**`docs/TODO.md` を更新したら、同じ内容を GitHub の issue #1 にも反映する。**

```bash
gh issue edit 1 --repo supertask/IPOTenbaggerAnalysis --body-file docs/TODO.md
```

保有銘柄の**生データ**は **MCPサーバ（`mcp_server.py`）から呼べる。**
`.mcp.json` を置いてあるので、Claude Codeなら起動時に読み込まれる。
**引数と使い分けの詳細は `docs/MCP.md`**（以下は要点だけ）。

| ツール | 返すもの |
|---|---|
| `list_holdings` | 保有32銘柄（コード・上場日・市場・業種・倍率・保有区分） |
| `company_metrics` | 38指標を競合・業種中央値・10倍株の3群と並べる |
| `annual_report_xbrl` | **有報のXBRLをタグ名か項目名で検索。1銘柄386種類**（画面に出しているのは65種類だけ） |
| `annual_report_text` | 有報の本文（事業の内容・役員・MD&A・リスク・研究開発・設備・セグメント・経営方針） |
| `company_disclosures` | 適時開示の一覧（日付・タイトル・URL） |
| `disclosure_text` | 適時開示PDFの**本文**。grepで必要なところだけ抜ける |
| `tanshin_xbrl` | 決算短信サマリーのXBRL。**会社自身の業績予想はここにしか無い**。予想の修正が短信ごとに追える |
| `tanshin_text` | 決算短信の添付資料の本文。**四半期のBS・PL・CF・セグメント情報**と、四半期ごとの経営成績の説明 |
| `company_shareholders` | 持株の推移と5%超の売買 |
| `company_facilities` | 1拠点あたりの採算（単位は店舗/台/戸） |
| `price_history` | 株価・公開価格・初値・現在何倍・N倍まで何年 |
| `ipo_facts` | 上場時の諸元（公開価格・社長株%・オーナー株%・公募/売出%・注目度） |
| `search_books` | **投資本の原文を検索して周辺だけ返す。** 要約ではない |
| `list_books` | 検索できる本の一覧 |

`annual_report_xbrl` と `annual_report_text` は `year` で過去の年度も読める
（6099は有報を12年ぶん、3496は8年ぶん持っている）。`report_type` は
`annual`（41,308件）／`quarterly`（361件・保有銘柄のみ）／
`securities_registration`（2,231件・上場時の届出書）。

**MCPは長い文字列ではなく構造を返す。** 読む側が毎回パースし直さなくて済むよう、
`company_metrics` は `metric_compare_dump.collect()`、`company_shareholders` は
`holdings_service.get_holdings_history()` の構造をそのまま渡す。
**キーの言語も揃える** — サービス層は英語のキーで返すので、MCPの外に出すところで
日本語に直す（`_rename`）。文字列のまま返すのは、それ自体が中身である
`本文`（有報・開示PDF）と `原文`（本）だけ。
`annual_report_text` の `section` は日本語の節名でも受ける。

**有報のXBRLには実績しか無い。会社の予想は決算短信にしか無い。**
`tanshin_xbrl` が見ているのは東証の適時開示ページに並んでいるサマリーの
iXBRLで、来期・今期の売上／営業利益／経常利益／純利益／EPS／配当が
タグ付きで入っている。短信ごとに並べれば、いつ何を上方（下方）修正したかが出る。
**PDFのURLからは導けない**（拡張子を .zip に変えても404）ので、
`tdnet_disclosure_scraper.py` が行の2本目のリンクとして拾い、
`data/output/tanshin/index.tsv` に貯めている。中身の取り込みは
`collectors/tanshin_xbrl_collector.py`。

同じ行の3本目のリンクが**添付資料のHTML**で、こちらには
**四半期のBS・PL・CF・セグメント情報**と、会社が四半期ごとに書いた
経営成績の説明が入っている（`collectors/tanshin_text_collector.py` → `tanshin_text`）。
有報は年1回、四半期報告書は保有銘柄でも361件しか無いので、**四半期の財務三表は
実質ここだけ**。PDFではないので表が崩れない。ただし**出し始めた時期は会社ごとに
違い**、保有銘柄では2022年2月〜2025年7月にばらけていて667件中337件しか無い。
それより古い期はPDFを `disclosure_text` で読む。

**全銘柄には広げない。** 東証のページを1社ずつ開くので4,164社で約87時間かかる。
EDINETの四半期・半期（99,400件・13.6GB・40〜55時間）も広げていない。
書類が3.3倍になるとインデックスの再ビルドが45分→2.5時間になり、
**エイリアスを1つ足すたびにそれを払う**ことになるため。

**投資本の本文はこのリポジトリに置かない。** 環境変数 `BOOK_TEXTS_DIR` で
場所を指す（既定は `../BookScraper/book_texts/stock_investment`）。
無ければツールがエラーと対処法を返す。**サブモジュールにはしない** —
このリポジトリは公開なので、非公開リポジトリを参照していることがURLごと
公開されるうえ、他人のcloneが失敗する。

**適時開示は東証のサイトから取っているので、東証に上場していない銘柄は取れない。**
353Aエレベーターコミュニケーションズ（札証アンビシャス）と
9388パパネッツ（福証Qボード）がこれに当たり、この2社だけ開示が0件。

**MCPはAIが書いたものを出さない。** `business_profile.tsv`（事業の読み解き・
判定・買う理由）と `disclosure_reading.tsv`（開示の要約）は返さない。
**書いた時点のAIの精度がそのまま残り、あとから読む側を古い結論で縛るため。**
呼ぶ側がそのつど生データから判断できるように、一次資料と、そこから
機械的に計算した数字だけを返す。画面は「AIによる解釈」のバッジで区別できるが、
MCPには区別する手段が無いので最初から混ぜない。

**インデックスを直接引かず、visualizer のサービス層と collectors を通す。**
同じインデックスを読む場所が増えるとタグの持ち方がずれる（2026-08-14に
`METRIC_ALIASES`・`metric_diagnose`・`facility_service` の3箇所がずれていて、
IFRSの会社で営業利益率0.07%という数字が出ていた）。画面と同じ関数を通す。

**stdioでJSONRPCをやりとりするので、標準出力に1行でも print すると壊れる。**
ツールは `@quiet` で標準出力を捨てている（捨てた内容は標準エラーへ）。
`config.py` にあったデバッグ用の `print(f"BASE_DIR: ...")` はこれで消した。

| スキル | 使うとき | 画面のどこ |
|---|---|---|
| `holding-review` | **画面に出るAIの解釈を書く／直すとき**（四半期ごと） | 事業の内容 / 役員の状況 / 財務指標の比較 / 総括カード / 「5%超の売買」タブの理由の下 |
| `facility-count` | 拠点数の抽出判定（`facility_count_collector.py`）を触るとき | 「拠点あたりの採算」カードの拠点数 |

`holding-review` の書き先は2つ。`business_profile.tsv`（1銘柄1行）と
`disclosure_reading.tsv`（1開示1行）。**粒度が違うのでTSVは分けているが、
読む材料が重なるので手順は1つ。** 開示のPDFを2回読まないため。

投資本（リンチ『株で勝つ』・清原『我が投資術』・テンバガー投資家X）の抜き書きは
`.claude/skills/holding-review/references/investor-books.md`。
**本文は非公開の別リポジトリ `../BookScraper` にあり、ここには置かない**
（このリポジトリは公開なので、持ってくると本文がそのまま公開される）。

同じ置き場所にエミン・ユルマズの10倍株の4条件があるが、**これだけは本ではなく
媒体記事から写したもの**で、確からしさが一段違う（ファイルの冒頭に出典と
その旨を書いてある）。プレジデントオンラインと楽待新聞という独立した2媒体で
同じ4条件・同じ数値が確認できたものだけを残し、出所がnote記事しか無かった
「6条件」（PSR1倍未満・ネットキャッシュ>時価総額など）は落とした。

## いちばん大事な方針: 重いデータは保有銘柄だけ

有価証券報告書・適時開示・期中の報告書のように、**全上場企業ぶんを取ると量が跳ね上がる
データは、保有銘柄だけを対象にする。** それ以外の銘柄は従来どおり（有報の年1回など）。

- **ディスク**。全銘柄に広げると数万件の書類になり、PCに収まらなくなる恐れがある
  （現状でもインデックスのDBが2.1GB、有報のTSVが44,000件）
- **トークン**。AIに読ませる処理を全銘柄でやると消費が激しい

保有銘柄は次の3区分。大元はGoogleスプレッドシート「保有割合」で、タブが区分に対応する。

| 区分 | 置き場所 | 株数・金額 |
|---|---|---|
| 自分 | `data/output/portfolio/myself.tsv` | あり |
| テンバガーX | `data/output/portfolio/tenbagger_x.tsv` | あり |
| お気に入り | `data/output/portfolio/favorites.tsv` | 無し（保有していない監視銘柄）。**見出しだけの空ファイル。** 銘柄コードの列だけ埋めれば足りる |

**一覧の既定の絞り込みは「保有あり」。** 見るのはたいてい持っている銘柄なので、
全銘柄から探し直さなくていいようにしてある（`components/index/holder_filter.html`）。
全件から見せたいページは `{% set default_holder_filter = '' %}` を include の前に置く。

対象を取るときは `collectors/holding_profile_dump.py` の `portfolio_codes()`。
`data/output/portfolio/*.tsv` を読むので、TSVを足せば自動で対象に入る。
画面のラベルは `visualizer/portfolio.py` の `PORTFOLIOS`。

この方針で絞っているもの: 期中の報告書の取得（`interim_report_collector.py`）、
期中の拠点数（`facility_count_collector.py --interim`）、`data/meta/` の
`business_profile.tsv` `business_model.tsv` `facility_override.tsv`。

例外が大量保有報告書（`large_holding_collector.py`）で、こちらは全銘柄を対象にする。
1書類5KBと軽く、AIも通さないため。ただし本文の取得は5〜6時間かかるので
`--all` を明示したときだけ全銘柄に広がり、既定は保有銘柄。

AIの分担は、保有銘柄はClaudeで読んでTSVに書く、それ以外は将来 OpenRouter の
無料モデルで一括（`docs/TODO.md`）。

## データの扱い

- `data/` 配下の収集結果は**勝手にコミットしない**。ユーザーの判断を待つ
- 収集結果は再生成できる。壊れたら collector を流し直す
- **例外が `data/output/large_holdings/`。** 大量保有報告書はEDINETに5年しか
  残らないので、消すと二度と取れない

## 抽出した数字と、AIの解釈を混ぜない

画面に出る数字は、原則として決まった手順での抽出（正規表現やXBRLのタグ）であって、
AIが読んで書いたものではない。両者が混ざると、どこまで信用していいか分からなくなる。

AIの解釈が入るのは `data/meta/` の `business_profile.tsv` `business_model.tsv`
`disclosure_reading.tsv` だけで、画面では「AIによる解釈」「AI」のバッジを出している。
新しくAI由来のものを足すときも、出所が分かるようにすること。

## 開示の性質で気をつけること

実データで確かめた前提。推測で書き換えないこと。

- **大株主の状況** … 有報のほか、中間期の四半期報告書と半期報告書に載る。
  第1・第3四半期には載らない。したがって最大でも年2回
- **役員の状況** … 有報にしか載らない。年1回。期中の報告書にも節はあるが
  中身は異動の届出で、361件中356件が「該当事項はありません」。株数は載らない
- **大量保有報告書**（`large_holding_collector.py`）… 5%超を持つ人が、保有割合が
  1%動くたびに5営業日以内に出す。**日付単位**で追え、しかも提出事由と保有目的という
  形で理由が付く。ただし**EDINETの保存は5年しかない**（有報は10年）。
  落としたTSVが5年より前の唯一の記録になるので、再生成できるものとして扱わない
- 同じ有報の中でも基準日が違う。**大株主は期末時点、役員は提出日現在**
- 四半期報告書は2024年4月に廃止され、半期報告書に置き換わった
- **株数の分割調整**は提出日ではなく株数の時点で行う。国内の分割は期末を基準日にして
  翌日に効力が出るのが通例で、株価が落ちる権利落ち日はその数営業日前に来る
- **「主要な経営指標等の推移」のコンテキストIDは、連結に移った年から変わる。**
  単体だけの会社は `CurrentYearDuration_NonConsolidatedMember`、連結のある会社は
  素の `CurrentYearDuration`。片方しか見ないと、連結に移った年でグラフが止まる
  （3,923社中3,528社がこれで欠けていた）。同じ有報に両方載る年は連結を採る
- **拠点数はタグ付けされていない**。本文から拾うため取り違えが起きる（→ `facility-count`）
- **四季報オンラインの比較企業は向こうが入れ替える**。一度取ったきりだと古いまま
  残るので、保有銘柄は `collectors/refresh_competitors.py` で取り直す。
  それでも業態がずれるときは `data/meta/competitor_override.tsv` に人が書く
- **売上原価明細書**はサービス業では作らない企業が多く、仕入・労務費の内訳は
  全体の7%（268社）でしか取れない

## インデックス

`python -m visualizer.build_index` で `data/output/index/visualizer.db` を作る。
44,695件の書類を読むので**20分ほどかかる**。スキーマを変えたら
`visualizer/db.py` の `SCHEMA_VERSION` を上げる（上げないと古いDBを読み続ける）。
ビルド中はvisualizerを止めておく（Windowsでは開いたままだと差し替えに失敗する）。
**`--output` で別の場所に作れる。** 生きているDBに触らずに試せるので、
ビルドを変えたときはこれで作って中身を突き合わせてから差し替える。

**インデックスに入る指標は `METRIC_ALIASES`（両アプリのconfig）から決まる。**
そこに無いタグは1行も入らないので、グラフを足すときは
「エイリアスを足す → ビルドし直す」の順になる。エイリアスだけ足しても出ない。

**DBはTSVの索引であって、原本ではない。** 原本は
`data/output/edinet_db/` のTSVで、EDINETが出したCSVを1行も落とさず置いてある
（1ファイル1,294〜1,464行）。DBはそのうち**14%**しか持たない。
だから指標を足したくなったら、エイリアスを足して作り直せばいい。
**「あとで使うかもしれない」を理由にDBへ行を増やさない** — 財務諸表の明細を
丸ごと入れる案を測ったら、行が4.4倍（830万→3,690万）でDBが13GBになるのに、
得られるのは再ビルドを省けることだけだった。

**`pandas` でDataFrameを作らない。** 1ファイル1,409行のうち使うのは13%で、
残りのためにオブジェクトを作るのが高くつく。標準の `csv` で読みながら弾き、
指標・大株主・本文・期末日を**1回のループでまとめて拾う**（`_scan_report_rows`）。
無作為250ファイルで前の実装と4種類すべて一致することを確かめたうえで4.3倍になった。
**`iterrows()` は使わない**（1行ごとにSeriesを作り直すので実測18.4倍遅い）。
**pandasの欠損の扱いに合わせる** — `read_csv` は空欄だけでなく `"NA"` や `"nan"`
もNaNにし、NaNはSQLiteにNULLで入る。`csv` で読むと空文字になり、
**NULLと空文字は別物**なのでDBの中身が変わる（`STR_NA_VALUES` で揃えている）。

## 動作確認

```bash
python -m visualizer.app                    # http://127.0.0.1:5000
python scripts/verify_visualizer_deep.py    # 3アプリの主要ページとAPIを回す
```

画面を変えたら**スマホ幅（390px）でも確認する**。ユーザーはスマホで見ている。
`document.documentElement.scrollWidth - clientWidth` が 0 であること。
表は `.table-responsive` に入れる。

## 環境

- Windows。`.venv` はプロジェクト直下。pyenv-win の Python 3.12.3

**URLと鍵はリポジトリに書かず、環境変数から取る。** ここは公開リポジトリなので、
書いたものはそのまま公開される。設定が無ければその機能を出さない（他人がcloneしても壊れない）。

| 環境変数 | 何に使うか | 無いとどうなるか |
|---|---|---|
| `EDINET_API_KEY` | EDINETから書類を取る | collectorが動かない |
| `BOOK_TEXTS_DIR` | 投資本の本文の置き場所（既定は `../BookScraper/book_texts/stock_investment`） | `search_books` がエラーと対処法を返す |
| `PORTFOLIO_SHEET_URL` | 一覧の絞り込みの下に出す「保有割合のスプレッドシート」へのリンク | リンクを出さない |

```powershell
[Environment]::SetEnvironmentVariable("PORTFOLIO_SHEET_URL", "https://…", "User")
```

**設定したら visualizer を再起動する。** 環境変数はプロセスの起動時にしか読まれない。
**起動しっぱなしのプロセスが残っていないかも確認する** — 多重起動すると、
古い環境のプロセスが5000番を握ったままになり、直したはずの表示が出ない。

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*visualizer.app*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```
