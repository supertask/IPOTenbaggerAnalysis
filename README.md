# IPO Tenbagar Analysis

IPO関連の各種データを収集・分析し、可視化するツール群です。

1. 過去にテンバガーになった上場会社の特徴分析
2. これからテンバガーになりそうな上場企業の可視化


## セットアップ

```bash
# 必要なパッケージをインストール
pip install -r requirements.txt
```

## データ収集の実行方法

データ収集は以下のコマンドで実行できます：

```bash
python -m collectors <collector_name>
```

利用可能なコレクター:
- `list`: IPO基礎情報リストの収集
- `details`: IPO詳細情報の収集
- `traders`: トレーダー情報の分析
- `yfinance`: Yahoo Financeからのデータ収集
- `edinet`: EDINETからの有価証券報告書ダウンロード
    - 注意点: 久しぶりに実行する際（1ヶ月ぶりなど）は `data/output/edinet_db/edinet_codes/<prefix>__doc_indexes.tsv.gz` を削除
- `comparison`: 競合他社の分析
- `ai`: AI要約の生成 -　Groqが安くなるまで待つ
- `combiner`: 各種データの統合
- `all`: すべてのデータ収集を実行

例：
```bash
# 特定のコレクターを実行
python3 -m collectors list
python3 -m collectors details
python3 -m collectors traders
python3 -m collectors yfinance
python3 -m collectors edinet
python3 -m collectors comparison 
#python3 -m collectors ai
python3 -m collectors combiner

# すべてのコレクターを実行
python3 -m collectors all
```

## ローカルでの可視化

可視化ツールは以下のコマンドで起動できます：

```bash
# 直接実行
python -m visualizer.app

# または、Flask CLIを使用
export FLASK_APP=visualizer.app
export FLASK_ENV=development
flask run --host=0.0.0.0 --port=8080
```

ブラウザで以下のURLにアクセスできます：
- トップページ: `http://localhost:8080/`
- 企業詳細ページ: `http://localhost:8080/<企業コード>`

## ディレクトリ構造

```
IPODataCollectors/
├── collectors/          # データ収集モジュール
│   ├── __init__.py
│   ├── __main__.py
│   ├── ipo_kiso_details_collector.py
│   ├── ipo_kiso_list_collector.py
│   └── ...
├── visualizer/          # データ可視化モジュール
│   ├── __init__.py
│   ├── app.py
│   ├── config.py
│   ├── data_service.py
│   └── chart_service.py
├── data/               # 収集したデータの保存先
│   └── output/
├── requirements.txt    # 依存パッケージ
└── README.md
```

## 注意事項

- データ収集には各種APIキーが必要な場合があります
- データ収集には時間がかかる場合があります

## Oracle Cloud Infrastructureでの環境構築

install tools
    sudo apt update
    sudo apt install -y python3-pip
    sudo apt install python3-venv
    sudo apt install nginx
    sudo apt install firewalld
    sudo apt install iptables-persistent

install python tools
    python3 -m venv .venv           # 任意の場所・名前で OK
    source .venv/bin/activate       # ← 仮想環境に入る
    pip install --upgrade pip
    pip install -r requirements.txt
    
save routing
    sudo iptables -I INPUT 5 -p tcp --dport 80 -m conntrack --ctstate NEW -j ACCEPT #ALLOW 80
    sudo iptables -L INPUT -n --line-numbers | grep ':80'

    sudo netfilter-persistent save            # 既存ルールを /etc/iptables/* に保存

[Free Tier: Ubuntu VMへのFlaskのインストール
](https://docs.oracle.com/ja-jp/iaas/developer-tutorials/tutorials/flask-on-ubuntu/01oci-ubuntu-flask-summary.htm)を参考に環境構築してね。

Nginxを構築し、サーバでのキャッシュができるようにする
https://gemini.google.com/app/eda7023cb013421a


Firewall setting

    sudo firewall-cmd --permanent --add-port=80/tcp
    sudo firewall-cmd --list-ports
    sudo firewall-cmd --reload
    sudo firewall-cmd --list-ports




## Memo

「現金」と「有利子負債」を取得してネットキャッシュ比率を計算
https://media.monex.co.jp/articles/-/8830

```
([流動資産前期(億円)]+[投資有価証券前期(億円)]*0.7-[流動負債前期(億円)]-[固定負債前期(億円)])/[時価総額(億円)]
```

ネットキャッシュ比率 = (流動資産 + 投資有価証券 * 0.7 - 負債) /　時価総額  

(1346(現金) - 1039（有利子負債）)

PER、ネットキャッシュ、売買売買率を計算

==============

これらのファイルを分析した結果、IPOレポートのTSVファイルには多くの財務指標が含まれていることがわかりました。テンバガー（株価が10倍以上になる銘柄）を見極める上で有用と思われる指標について分析します。
テンバガーを見極める上で特に重要と思われる指標は以下の通りです：
成長性に関する指標：
jpcrp_cor:NetSalesSummaryOfBusinessResults（売上高）：急速な売上成長はテンバガーの重要な条件
jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults（経常利益）：利益の成長率
jpcrp_cor:ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults（当期純利益）：最終的な利益の成長
収益性に関する指標：
jpcrp_cor:RateOfReturnOnEquitySummaryOfBusinessResults（自己資本利益率、ROE）：資本効率の高さを示す
jpcrp_cor:OperatingIncomeLossSummaryOfBusinessResults（営業利益）：本業での収益力
財務健全性に関する指標：
jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResults（自己資本比率）：財務の安定性
jpcrp_cor:NetCashProvidedByUsedInOperatingActivitiesSummaryOfBusinessResults（営業キャッシュフロー）：実際の現金創出能力
4. バリュエーションに関する指標：
jpcrp_cor:PriceEarningsRatioSummaryOfBusinessResults（PER、株価収益率）：割安度を測る指標
jpcrp_cor:BasicEarningsLossPerShareSummaryOfBusinessResults（EPS、1株当たり利益）：株価との比較に重要
成長投資に関する指標：
jpcrp_cor:NetCashProvidedByUsedInInvestingActivitiesSummaryOfBusinessResults（投資キャッシュフロー）：将来の成長への投資状況
経営効率に関する指標：
jpcrp_cor:TotalAssetsSummaryOfBusinessResults（総資産）と売上高の比率：資産効率
テンバガーを見極める上での各指標の活用方法：
売上高の成長率：
過去数年間の売上高の推移を見て、年平均成長率（CAGR）が20%以上あるかどうか
成長率が加速しているか、安定しているか
利益率の改善：
売上高に対する経常利益率や営業利益率が改善傾向にあるか
スケールメリットが効いて利益率が向上しているか
ROEの高さと改善傾向：
ROEが15%以上あるか、または改善傾向にあるか
資本効率の高い企業は株価上昇の可能性が高い
キャッシュフローの質：
営業キャッシュフローが当期純利益を上回っているか（利益の質が高いか）
フリーキャッシュフロー（営業CF - 投資CF）がプラスで成長しているか
PERと成長率のバランス：
PEG（PER÷成長率）が1以下であれば割安と判断できる
成長率に対してPERが低い企業は上昇余地が大きい
6. 自己資本比率と財務安全性：
自己資本比率が30%以上あり、財務的に安定しているか
過剰な負債がなく、成長投資に集中できる状態か
特に重要なのは、これらの指標を単独で見るのではなく、複合的に分析することです。例えば：
売上高が急成長（20%以上）しており、かつ利益率も改善している
ROEが高く（15%以上）、かつ自己資本比率も健全（30%以上）
営業キャッシュフローが潤沢で、積極的な成長投資を行っている
PERが業界平均より低く、成長率に対して割安である
このような複数の条件を満たす企業は、テンバガーになる可能性が高いと言えるでしょう。また、時系列での変化（トレンド）を見ることも重要です。改善傾向にある指標は、将来の株価上昇の可能性を示唆します。

