import yfinance as yf

ticker = '5588.T'
#ticker = 'AAPL'
ticker_info = yf.Ticker(ticker)

date = '2023-12-01'
sharesOutstanding = ticker_info.info["sharesOutstanding"]

print(f"code = {ticker}: ")
#for key, value in ticker_info.info.items():
#	print(key, value)
print(f"sharesOutstanding = {sharesOutstanding}")


historical_shares_outstanding = ticker_info.history(period='max')
print(historical_shares_outstanding)

