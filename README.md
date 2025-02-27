# IPO Predictor

IPOの株のCSVを作成


## 実行方法

        # 各IPO企業のTSVを取得
        python collectors.py kiso_list
        python collectors.py kiso_details
        python collectors.py traders
        python collectors.py yfinance
        # python collectors.py edinet #修正する
        python collectors.py combiner

        # TODO: 上記の各企業の情報から、AIでストックビジネス, 競合リスト, 店舗数, 海外進出するか, を取得
        python collectors.py ai_annotation
        
        # TODO: 競合の役員, 競合の財務情報をAI使って比較
        python collectors.py compare_compititors
        
        python collectors.py combiner2

## 可視化ツールの使用方法

IPO企業と競合企業の財務指標を可視化するためのウェブアプリケーションを提供しています。

### 実行方法

1. 必要なパッケージをインストール
```
pip install -r requirements.txt
```

2. 可視化ツールを起動
```
python visualizer.py
```

3. ブラウザで以下のURLにアクセス
```
http://localhost:8080/
```

4. 特定の企業の詳細を見るには、以下のURLにアクセス
```
http://localhost:8080/<銘柄コード>
```

### 機能

- トップページでは、すべての企業の一覧を表示
- 企業詳細ページでは、選択した企業と競合企業の財務指標を比較したグラフを表示
- 表示される主な指標：
  - 売上高
  - 経常利益
  - 当期純利益
  - 総資産
  - 純資産額
  - 自己資本比率
  - 自己資本利益率
  - 株価収益率
  - キャッシュフロー関連指標

## Memo

「現金」と「有利子負債」を取得してネットキャッシュ比率を計算
https://media.monex.co.jp/articles/-/8830

```
([流動資産前期(億円)]+[投資有価証券前期(億円)]*0.7-[流動負債前期(億円)]-[固定負債前期(億円)])/[時価総額(億円)]
```

ネットキャッシュ比率 = (流動資産 + 投資有価証券 * 0.7 - 負債) /　時価総額  

(1346(現金) - 1039（有利子負債）)

PER、ネットキャッシュ、売買売買率を計算


