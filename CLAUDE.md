# このリポジトリで作業するときの前提

セットアップ・デプロイは `README.md`、これからやることは `docs/TODO.md`。
手順の詳細はスキルに置いてある。

**`docs/TODO.md` を更新したら、同じ内容を GitHub の issue #1 にも反映する。**

```bash
gh issue edit 1 --repo supertask/IPOTenbaggerAnalysis --body-file docs/TODO.md
```

| スキル | 使うとき | 画面のどこ |
|---|---|---|
| `holding-profile` | 保有銘柄の事業・経営陣の読み解きと総括を書く／直すとき | 詳細ページの「事業の内容」「役員の状況」の各カード先頭と、「総括」カード |
| `disclosure-reading` | 大株主が動いた理由を開示から書くとき | 「株主構成」→「持株の推移」→「5%超の売買」タブの理由の下 |
| `metric-reading` | 比較チャートのどれをどう見るかを書くとき | ページ下部「財務指標の比較」の見出しの直下 |
| `facility-count` | 拠点数の抽出判定（`facility_count_collector.py`）を触るとき | 「拠点あたりの採算」カードの拠点数 |

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
| お気に入り | `data/output/portfolio/favorites.tsv`（未作成） | 無し（保有していない監視銘柄） |

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
`disclosure_reading.tsv` `metric_reading.tsv` だけで、画面では
「AIによる解釈」「AI」のバッジを出している。
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
- **拠点数はタグ付けされていない**。本文から拾うため取り違えが起きる（→ `facility-count`）
- **売上原価明細書**はサービス業では作らない企業が多く、仕入・労務費の内訳は
  全体の7%（268社）でしか取れない

## インデックス

`python -m visualizer.build_index` で `data/output/index/visualizer.db` を作る。
44,000件の書類を読むので**45分ほどかかる**。スキーマを変えたら
`visualizer/db.py` の `SCHEMA_VERSION` を上げる（上げないと古いDBを読み続ける）。
ビルド中はvisualizerを止めておく（Windowsでは開いたままだと差し替えに失敗する）。

## 動作確認

```bash
python -m visualizer.app                    # http://127.0.0.1:5000
python scripts/verify_visualizer_deep.py    # 3アプリの主要ページとAPIを回す
```

画面を変えたら**スマホ幅（390px）でも確認する**。ユーザーはスマホで見ている。
`document.documentElement.scrollWidth - clientWidth` が 0 であること。
表は `.table-responsive` に入れる。

## 環境

- Windows。`EDINET_API_KEY` はユーザーの環境変数に設定済み（コミットしない）
- `.venv` はプロジェクト直下。pyenv-win の Python 3.12.3
