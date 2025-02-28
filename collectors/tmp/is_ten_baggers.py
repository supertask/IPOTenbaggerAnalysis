import pandas as pd
import requests
from datetime import datetime
import yfinance as yf

def get_token_from_file(file_path):
    try:
        with open(file_path, 'r') as file:
            token = file.readline().strip()
        return token
    except Exception as e:
        print(f"Error reading token from file: {e}")
        return None

refresh_token = get_token_from_file("../.tokens/jquants_refresh_token")


# リフレッシュトークンを使用してIDトークンを取得する関数
def get_id_token(refresh_token):
    r_post = requests.post(
        f"https://api.jquants.com/v1/token/auth_refresh?refreshtoken={refresh_token}"
    )
    id_token = r_post.json()['idToken']
    return id_token

# 株価情報を取得する関数
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

    close_param = 'AdjustmentClose'
    #close_param = 'Close'
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

# 時価総額を兆、億、万単位で表示する関数
def format_market_cap(market_cap):
    units = [("兆", 10**12), ("億", 10**8), ("万", 10**4)]
    parts = []
    for unit_name, unit_value in units:
        if market_cap >= unit_value:
            market_cap_on_unit = int(market_cap // unit_value)
            parts.append(f"{market_cap_on_unit}{unit_name}")
            market_cap %= unit_value
    if market_cap > 0 or not parts:
        market_cap = int(market_cap)
        parts.append(f"{market_cap}円")
    return "".join(parts)
    
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


def get_ten_bagger_description(ticker, id_token):

    # 株価データを取得
    price_df = get_stock_prices(id_token, ticker)
    
    #close_param = 'AdjustmentClose'
    close_param = 'Close'

    # 約最初の12ヶ月(上場して1年以内)に購入することを前提とするため
    month = 12
    first_year_price_df = price_df.iloc[:min(month * 20, len(price_df))]
    min_price_index = first_year_price_df[close_param].idxmin()
    buy_price = first_year_price_df[close_param].min()
    buy_date_str = first_year_price_df.loc[min_price_index, 'Date']
    
    entire_period_price_df = price_df.iloc[:]  # 全ての期間
    max_price_index = entire_period_price_df[close_param].idxmax()
    sell_price = entire_period_price_df[close_param].max()
    sell_date_str = entire_period_price_df.loc[max_price_index, 'Date']

    buy_date = datetime.strptime(buy_date_str, '%Y-%m-%d')
    sell_date = datetime.strptime(sell_date_str, '%Y-%m-%d')

    # 期間を計算
    delta = sell_date - buy_date
    years = delta.days // 365
    months = (delta.days % 365) // 30
    days = (delta.days % 365) % 30

    n_times = round(sell_price / buy_price, 1)

    ten_bagger_description = f"{years}年{months}ヶ月{days}日で{n_times}倍株\n"

    if sell_price >= 10 * buy_price:
        pass
    else:
        pass
        
    ten_bagger_description += f"最小: {buy_price}円 on {buy_date_str}\n最大: {sell_price}円 on {sell_date_str}"
    #ten_bagger_description += f"最初の12ヶ月の最小株価: {buy_price}円 ({buy_date_str}),\n全ての期間での最大株価: {sell_price}円 ({sell_date_str})"
    return ten_bagger_description


def main():
    codes = [
    #    '7203', #トヨタ
    #    '5588', #ファーストアカウンティング
    #    '9166', #GENDA
    #    '3496', #アズーム
    #    '3974', #ティビィシィ・スキヤツト #TODO: 下落をトラックできるように
    #    '3970', #イノベーション #TODO: 下落をトラックできるように
            
        # 2024
        '177A',
        '176A',
        '175A',
        '173A',
        '168A',
        '160A',
        '157A',
        '156A',
        '153A',
        '155A',
        '149A',
        '151A',
        '146A',
        '148A',
        '150A',

        '145A',
        '147A',
        '143A',
        '142A',
        '5859',
        '141A',

        # 2015年
        #'3974',
        #'3969',
        #'3477',
        #'3970',
        #'6541',
        #'3968',
        #'3556',
        #'6540',
    ]
    id_token = get_id_token(refresh_token) # IDトークンを取得
    for code in codes:
        market_cap = estimate_ipo_market_cap(id_token, code)
        #formatted_market_cap = format_market_cap(market_cap)
        #print(formatted_market_cap)

        if market_cap is None:
            market_cap_oku = ""
        else:
            market_cap_oku = market_cap_in_oku(market_cap)

        print(f"code = {code}, market_cap_oku = {market_cap_oku}")

        #description = get_ten_bagger_description(code, id_token)
        #print(f"コード: {code}\n{description}\n")

main()