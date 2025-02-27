import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

def is_delisted(ticker, check_period_days=30):
    try:
        # 現在の日付とチェックする期間の開始日を設定
        end_date = datetime.today()
        start_date = end_date - timedelta(days=check_period_days)

        # 株式データを取得
        data = yf.download(ticker, start=start_date, end=end_date)

        # データが取得できない場合、上場中止と判定
        if data.empty:
            return True
        else:
            return False
    except Exception as e:
        # 何らかのエラーが発生した場合も上場中止と見なす
        print(f"Error retrieving data for {ticker}: {e}")
        return True

# 使用例
tickers = [
"6225.T",
"3930.T",
]
for ticker in tickers:
    if is_delisted(ticker):
        print(f"{ticker} is delisted.")
    else:
        print(f"{ticker} is not delisted.")
