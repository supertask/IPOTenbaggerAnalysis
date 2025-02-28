# yfinance API 仕様書


## yfinance API で株価と財務諸表の時系列データを取得する

https://note.com/hrt_ebihara/n/nb0036034d412

```
ipo_traders_details.pyにプログラムを作ります。settings.pyにはKisoScraperSettingsのクラスを作ります。

ipo_kiso_details.pyにあるように

        input_file = os.path.join(kiso_scraper_settings.input_dir, f'companies_{year}.tsv')

を使うと、

企業名	コード	URL
アイセイ薬局	3170	/company/2011/aisei.html
ミサワ	3169	/company/2011/unico.html
スターフライヤー	9206	/company/2011/starflyer.html

のようにコードを取得できるので、

そのコードをもとに
https://www.traders.co.jp/ipo/<コード>
のhtmlファイルを取得し、

data/cache/traders/<年>/<コード>_<会社名>.html
にキャッシュするようにします。

そのファイルは下のファイルAです。これをBeautifulSoupで解析します。

取得したい情報は
「上場日」、「業種」、「想定価格」、「仮条件」、「公開価格」、「初値予想」、「初値」、「代表者名」、「設立年」、「従業員数」、「平均年齢」、「年収」、「株主数」、「資本金」、「上場時発行株式数」、「公開株式数」、「公募株数」、「売り出し株数」、「調達資金使途」、「大株主の大株主名、摘要、株数、比率をtsv形式で」、「業績動向をtsv形式で」、「参考類似企業のコード、会社名、今期予想PERをtsv形式で」、「事業詳細」
です。

これをipo_kiso_details.pyのようにoutput_fileに書き出して欲しいです。


ファイルA↓
===============
```


## Memo


```
 リフレッシュトークンを使用してIDトークンを取得する関数
def get_id_token(refresh_token):
    r_post = requests.post(
        f"https://api.jquants.com/v1/token/auth_refresh?refreshtoken={refresh_token}"
    )
    id_token = r_post.json()['idToken']
    return id_token

 株価情報を取得する関数
def get_stock_prices(id_token, code):
    headers = {'Authorization': 'Bearer {}'.format(id_token)}
    r = requests.get(
        f"https://api.jquants.com/v1/prices/daily_quotes?code={code}",
        headers=headers
    )
    price_df = pd.DataFrame(r.json()['daily_quotes'])
    return price_df
    
def get_min_stock_price(id_token, code):
    daily_quotes = get_stock_prices(id_token, code)
    if daily_quotes.empty: 
        return None

    close_param = 'Close'
    #close_param = 'AdjustmentClose'
    if close_param in daily_quotes.columns:
        min_price_row = daily_quotes.loc[daily_quotes[close_param].idxmin()]
        min_price = min_price_row[close_param]
        #min_price_date = min_price_row['Date']
        return min_price
    else:
        return None
        #raise ValueError("'AdjustmentClose' column not found in daily quotes dataframe")

# 財務データを取得する関数
def get_financial_statements(id_token, code):
    headers = {'Authorization': 'Bearer {}'.format(id_token)}
    r = requests.get(
        f"https://api.jquants.com/v1/fins/statements?code={code}",
        headers=headers
    )
    statements_df = pd.DataFrame(r.json()['statements'])
    return statements_df

def market_cap_in_oku(market_cap):
    oku = 10**8
    return "{:.2f}".format(market_cap / oku)

def estimate_ipo_market_cap(id_token, code):
    statements_df = get_financial_statements(id_token, code)
    
    if statements_df.empty:
        return None
        #raise ValueError("Financial statements dataframe is empty")

    if 'NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock' not in statements_df.columns:
        raise ValueError("Column 'NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock' not found in financial statements dataframe")

    shares = int(statements_df.iloc[-1]['NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock']) # 株数を取得
    
    min_price = get_min_stock_price(id_token, code)  # 修正: get_min_stock_priceの戻り値を調整
    if not min_price:
        return None

    return shares * min_price
```