import yfinance as yf
from datetime import datetime, timedelta

def format_market_cap(market_cap):
    n_cho = market_cap // 1_000_000_000_000
    market_cap %= 1_000_000_000_000
    n_oku = market_cap // 100_000_000
    market_cap %= 100_000_000
    n_man = market_cap // 10_000
    
    parts = []
    if n_cho > 0:
        parts.append(f"{int(n_cho)}兆")
    if n_oku > 0:
        parts.append(f"{int(n_oku)}億")
    if n_man > 0:
        parts.append(f"{int(n_man)}万")
    
    return "".join(parts) + '円'

def get_market_cap_after_1_month(ticker):
    stock = yf.Ticker(ticker)
    
    # 全ての履歴データを取得
    hist = stock.history(period="max")
    if hist.empty:
        raise ValueError("履歴データが見つかりません。")
    
    # 最初の日付を上場日とする
    ipo_date = hist.index[0]
    one_month_later = ipo_date + timedelta(days=30)
    print(ipo_date)
    
    # 一ヶ月後の株価を取得. 休日もあるので+10日のマージンを入れている
    hist_1_month = stock.history(start=one_month_later.strftime("%Y-%m-%d"), end=(one_month_later + timedelta(days=10)).strftime("%Y-%m-%d"))
    if hist_1_month.empty:
        raise ValueError("一ヶ月後のデータが見つかりません。")
    
    closing_price = hist_1_month['Close'][0]
    
    # 発行済株式数を取得
    shares_outstanding = stock.info.get('sharesOutstanding')
    if not shares_outstanding:
        raise ValueError("発行済株式数が見つかりません。")
    
    # 時価総額を計算
    market_cap = closing_price * shares_outstanding
    print(market_cap)
    return format_market_cap(market_cap)


#
# TODO: 以下のJquants APIで過去の期末発行済株式数を取得して、それをもとに時価総額の計算が必要
# https://jpx.gitbook.io/j-quants-ja/api-reference/statements#dta
#

#ticker = "9166.T"
ticker = "5588.T"
market_cap = get_market_cap_after_1_month(ticker)
print(f"上場して1ヶ月後の時価総額: {market_cap}")
