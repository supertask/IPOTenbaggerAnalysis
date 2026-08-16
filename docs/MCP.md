# MCPサーバ

保有・監視している32銘柄について、**有価証券報告書・決算短信・適時開示・
大量保有報告書の生データ**を、Claudeから直接呼べるようにしたもの。
実装は `mcp_server.py`（956行）、設定は `.mcp.json`。

Claude Codeならリポジトリを開いた時点で `.mcp.json` が読まれるので、
何もしなくても14個のツールが使える。

## いちばん大事な約束: AIが書いたものは返さない

`data/meta/business_profile.tsv`（事業の読み解き・判定・買う理由）と
`data/meta/disclosure_reading.tsv`（開示の要約2,851件）は、**AIが書いたもの**
なのでMCPからは出さない。

**書いた時点のAIの精度がそのまま残り、あとから読む側を古い結論で縛るため。**
呼ぶ側がそのつど生データから判断できるように、一次資料と、そこから機械的に
計算した数字だけを返す。

画面（visualizer）はAIの解釈も出すが、あちらは「AIによる解釈」のバッジで
区別できる。**MCPには区別する手段が無いので、最初から混ぜない。**

## 対象は保有32銘柄だけ

保有外のコードを渡すと、計算せずに理由を返す。

```json
{
  "error": "7203 は保有銘柄ではありません",
  "理由": "重いデータは保有銘柄だけを対象にしている（トークンとディスクのため）",
  "保有銘柄": ["141A", "160A", "..."]
}
```

対象は `data/output/portfolio/*.tsv`（自分・テンバガーX・お気に入り）から
決まる。TSVを足せば自動で対象に入る（`collectors/holding_profile_dump.py`
の `portfolio_codes()`）。

## ツール一覧

| ツール | 引数（`*`は必須） | 返すもの |
|---|---|---|
| `list_holdings` | — | 保有32銘柄。コード・上場日・市場・業種・倍率・保有区分 |
| `company_metrics` | `code*` `brief` | 38指標を競合・業種中央値・10倍株の3群と並べる |
| `annual_report_xbrl` | `code*` `query` `limit` `report_type` `year` | 有報のXBRLをタグ名か項目名で検索。**1銘柄約380種類** |
| `annual_report_text` | `code*` `section` `chars` `report_type` `year` | 有報の本文（事業・役員・MD&A・リスク・研究開発・設備・セグメント・経営方針） |
| `company_disclosures` | `code*` `match` `limit` `months` | 適時開示の一覧（日付・タイトル・URL） |
| `tanshin_xbrl` | `code*` `query` `date` `limit` | 決算短信サマリーのXBRL。**会社自身の業績予想はここにしか無い** |
| `tanshin_text` | `code*` `date` `grep` `chars` | 短信の添付資料の本文。**四半期のBS・PL・CF・セグメント** |
| `disclosure_text` | `url*` `grep` `chars` | 適時開示PDFの**本文**。grepで必要なところだけ |
| `company_shareholders` | `code*` | 持株の推移と5%超の売買（理由のタグ付き） |
| `company_facilities` | `code*` | 1拠点あたりの採算（単位は店舗/台/戸）と原価の構成 |
| `price_history` | `code*` `days` | 株価・公開価格・初値・現在何倍・N倍まで何年 |
| `ipo_facts` | `code*` | 上場時の諸元（公開価格・社長株%・オーナー株%・公募/売出%・注目度） |
| `search_books` | `query*` `limit` `around` | **投資本の原文**を検索して周辺だけ返す。要約ではない |
| `list_books` | — | 検索できる本の一覧 |

## どれを使うか

### 「会社がどう見ているか」と「実績」は置き場所が違う

**有報のXBRLには実績しか無い。会社の予想は決算短信にしか無い。**
ここを取り違えると、いくら `annual_report_xbrl` を探しても予想は出てこない。

| 知りたいこと | ツール |
|---|---|
| 過去の実績（年次） | `annual_report_xbrl` |
| **会社の今期・来期の予想、その修正の履歴** | **`tanshin_xbrl`** |
| 四半期の実績（BS・PL・CF） | `tanshin_text`（`annual_report_xbrl` の quarterly は保有銘柄でも361件しか無い） |
| 四半期ごとの経営成績の説明 | `tanshin_text`（有報には無い） |

### 一次資料を読む流れ

```
company_disclosures(code, match="業績予想")   # 一覧からURLを得る
      ↓
disclosure_text(url, grep="修正の理由")        # 本文の必要なところだけ
```

`disclosure_text` は本文をまるごと返すこともできるが、**grepを使って必要な
ところだけ抜くほうがいい。** 開示は長く、トークンを食う。

### 財務の良し悪しを聞かれたら

`company_metrics`。38指標を競合・業種中央値・「上場後に何倍になったか」で
分けた3群（10倍以上／3〜10倍／2倍未満）と並べる。所見（売上↑なのに利益率↓、
借入で嵩上げされたROEなど）が付くが、**これは規則で当てたものでAIの判断ではない。**

画面に出していない項目が要るときは `annual_report_xbrl`。研究開発費・設備投資・
セグメント情報・リース・税金・従業員の内訳などが取れる。

```
annual_report_xbrl("6099", query="")                    # タグの一覧だけ
annual_report_xbrl("6099", query="研究開発")            # 項目名で検索
annual_report_xbrl("6099", query="CapitalExpenditure")  # タグ名で検索
```

### 過去の年度を読む

`year` を渡す。何年ぶんあるかは、`year` を外して呼んだときの `error` に
「読める提出日」として出る（6099は12年ぶん、3496は8年ぶん）。

`report_type` は3つ。

| 値 | 中身 | 件数 |
|---|---|---|
| `annual` | 有価証券報告書（年1回） | 41,308 |
| `quarterly` | 四半期・半期報告書 | 361（保有銘柄のみ） |
| `securities_registration` | 上場時の有価証券届出書 | 2,231 |

## 設計上、守っていること

**インデックスを直接引かず、visualizer のサービス層と collectors を通す。**
2026-08-14に、同じインデックスを読む場所が3つに分かれてタグの持ち方がずれ、
IFRSの会社で営業利益率0.07%（基準の違う数字どうしの割り算）、表とグラフの
食い違い、拠点あたりの中央値ずれが同時に起きた。**MCPが4つ目の読み手に
ならないよう、画面と同じ関数を通す。**

**長い文字列ではなく構造を返す。** 読む側が毎回パースし直さなくて済むように、
`company_metrics` は `metric_compare_dump.collect()`、`company_shareholders` は
`holdings_service.get_holdings_history()` の構造をそのまま渡す。

**キーの言語も揃える。** サービス層は英語のキーで返すので、MCPの外に出す
ところで日本語に直す（`_rename`）。文字列のまま返すのは、それ自体が中身である
`本文`（有報・開示PDF）と `原文`（本）だけ。

**標準出力に1行も出さない。** stdioでJSONRPCをやりとりするので、`print` が
1行でもあるとプロトコルが壊れる。collectors は進捗を print する作りなので、
`@quiet` で標準出力を捨てている（捨てた内容は標準エラーへ流すので、人は追える）。
`config.py` にあったデバッグ用の `print(f"BASE_DIR: ...")` はこれで消した。

**import は遅延させる。** 起動を軽くし、DBが無い環境でも import は通るように、
重いモジュールはツールの中で import する。

## 落とし穴

**東証に上場していない銘柄は、適時開示も決算短信も取れない。**
353Aエレベーターコミュニケーションズ（札証アンビシャス）と
9388パパネッツ（福証Qボード）がこれで、この2社だけ開示が0件。
`company_disclosures` `disclosure_text` `tanshin_xbrl` `tanshin_text` が空になる。

**`tanshin_text` は会社ごとに読める期間が違う。** 添付HTMLを出し始めた時期が
2022年2月〜2025年7月にばらけていて、**667件中337件しか無い。**
戻り値の `読める短信` にある日付だけが読める。それより古い期が要るときは、
`company_disclosures` で「決算短信」を引いて `disclosure_text` にPDFのURLを渡す。

**`search_books` は本文が別リポジトリにある。** 環境変数 `BOOK_TEXTS_DIR`
（既定は `../BookScraper/book_texts/stock_investment`）で場所を指す。
無ければツールがエラーと対処法を返す。**このリポジトリは公開なので、
本文は置かないしサブモジュールにもしない。**

**`price_history` は既定で終値を返さない。** `days` を渡したときだけ返す。
何百日ぶんもの終値はトークンを食うので、集計（現在何倍・高値からの位置・
N倍まで何年）だけを既定にしてある。

## 設定

`.mcp.json` はリポジトリ直下にある。

```json
{
  "mcpServers": {
    "ipo-tenbagger": {
      "command": ".venv/Scripts/python.exe",
      "args": ["mcp_server.py"],
      "env": { "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1" }
    }
  }
}
```

`PYTHONUTF8` を入れているのは、Windowsの既定がcp932で日本語が化けるため。

**手で起動する必要は無い**（クライアントが起動する）。動くかどうかを確かめる
だけなら、import が通って標準出力に何も漏れないことを見る。

```bash
python -c "import io,contextlib; b=io.StringIO(); \
  exec('with contextlib.redirect_stdout(b): import mcp_server'); \
  print('漏れ', len(b.getvalue().strip()))"
```

`0` 以外が出たらstdioが壊れるので、漏らしている `print` を探す。

## 広げないと決めたこと

**全銘柄には広げない**（2026-08-14に判断）。

| | 件数 | 容量 | 取得 | 再ビルド |
|---|---:|---:|---:|---:|
| 決算短信（東証） | 約151,600 | 6.1 GB | 約188時間 | — |
| 四半期・半期報告書（EDINET） | 約99,400 | 13.6 GB | 40〜55時間 | 33秒 → **数時間** |

東証は1社ずつページを開くので4,164社で87時間かかり、ブロックされる危険もある。
そもそも全銘柄で見ているのは「上場後N年で何倍」「業種の中央値」「10倍株の3群」で
**すべて年次**なので、四半期にしても結論が変わらない。

**公開していない。** claude.aiやスマホから使うには公開が要るが、財務データと
EDINETキーを外に出すことになるので手を付けていない。いまはローカルのstdioだけ。

## 関連

- 方針とデータの扱い … `CLAUDE.md`
- これからやること … `docs/TODO.md`（GitHub issue #1 と同じ内容）
- 画面に出るAIの解釈を書く手順 … `.claude/skills/holding-review/SKILL.md`
