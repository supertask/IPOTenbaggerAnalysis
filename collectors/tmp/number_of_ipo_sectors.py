import yfinance as yf

# S&P 500のシンボルリスト（例として多くの銘柄を追加）
symbols = [
#    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'FB', 'TSLA', 'BRK-B', 'JNJ', 'JPM', 'V',
#    'NVDA', 'UNH', 'HD', 'PG', 'DIS', 'MA', 'PYPL', 'VZ', 'ADBE', 'NFLX',
#    'CMCSA', 'PFE', 'KO', 'PEP', 'INTC', 'T', 'MRK', 'CSCO', 'ABT', 'XOM',
#    'CVX', 'LLY', 'WMT', 'NKE', 'MDT', 'CRM', 'MCD', 'ACN', 'BMY', 'QCOM',
#    'TXN', 'HON', 'UNP', 'LOW', 'NEE', 'ORCL', 'COST', 'AMGN', 'DHR', 'IBM',
#    'PM', 'AVGO', 'SBUX', 'GS', 'MMM', 'ISRG', 'BLK', 'BA', 'CAT', 'CVS',
#    'LMT', 'GE', 'MDLZ', 'TMO', 'AXP', 'ADI', 'NOW', 'ZTS', 'CI', 'SYK',
#    'PLD', 'USB', 'MO', 'AMT', 'DUK', 'CB', 'SCHW', 'SPGI', 'GM', 'MMC',
#    'SO', 'RTN', 'ICE', 'CME', 'C', 'BDX', 'EL', 'NSC', 'NSRGY', 'ADP', 'CL',
#    'KMB', 'LRCX', 'GILD', 'FIS', 'CSX', 'BKNG', 'HUM', 'EW', 'EWBC', 'ITW',
#    'SYF', 'VRTX', 'ETN', 'DE', 'AON', 'AEP', 'ADSK', 'ILMN', 'FISV', 'EXC',
#    'MCO', 'CCI', 'MU', 'TGT', 'EOG', 'COF', 'DLR', 'TJX', 'WBA',
#    'COP', 'FDX', 'PSA', 'SHW', 'APH', 'GIS', 'REGN', 'ADM', 'PRU', 'MET',
#    'DG', 'ECL', 'CLX', 'CINF', 'AFL', 'ALL', 'PGR', 'OXY', 'MPC', 'HCA',
#    'PSX', 'EMR', 'SRE', 'WY', 'HIG', 'LHX', 'TRV', 'CNC', 'SYY', 'WELL',
#    'STT', 'CTSH', 'VLO', 'TSCO', 'DLTR', 'ROST', 'FTNT', 'WEC', 'D',
#    'KMI', 'TEL', 'SPG', 'ES', 'AME', 'EBAY', 'EXPE', 'YUM', 'ROK', 'HSY',
#    'AWK', 'MKC', 'DTE', 'CMS', 'OKE', 'BLL', 'EQR', 'HLT', 'SBAC', 'MTB',
#    'WAT', 'EIX', 'COO', 'ED', 'IQV', 'IFF', 'PAYX', 'RSG', 'SWK', 'XYL',
#    'BAX', 'TSN', 'NUE', 'CDNS', 'UAL', 'CTVA', 'IEX', 'PKI', 'KEYS', 'TER',
#    'FMC', 'DRI', 'HPE', 'IDXX', 'KMX', 'VTRS', 'DVA', 'MLM', 'VRSK', 'WDC',
#    'LEN', 'HST', 'STX', 'FTV', 'WRB', 'AAP', 'ZBH', 'PPG', 'GLW', 'CDW',
#    'TFX', 'MRO', 'NRG', 'AES', 'LVS', 'HPQ', 'MOS', 'CF', 'TXT', 'DOV',
#    'NLOK', 'CTXS', 'VMC', 'MKTX', 'ROL', 'NDSN', 'ALGN', 'VTR', 'TRMB',
#    'HBI', 'WHR', 'NLSN', 'AVB', 'RHI', 'UHS', 'BBY', 'AIZ', 'JBHT', 'CAG',
#    'LKQ', 'SEE', 'ZBRA', 'TRGP', 'NVR', 'STE', 'DISCK', 'DISCA', 'DISCB'


        # 2015年

#        '3465.T',
#        '6185.T',
#        '3464.T',
#        '3928.T',
#        '9416.T',
#        '3927.T',
#        '4595.T',
#        '3926.T',
#        '3925.T',
#        '3924.T',
#        '3923.T',
#        '6184.T',
#        '1435.T',
#        '3921.T',
#        '6182.T',
#        '4594.T',
#        '6177.T',
#        '6176.T',
#        '3920.T',
#        '3415.T',
#        '6173.T',
#        '3139.T',
#        '3461.T',
#        '1431.T',
#        '6049.T',
#        '4980.T',
#        '7781.T',
#        '6239.T',
#        '7780.T',
#        '3135.T',
#        '9417.T',
#        '3914.T',
#        '6047.T',
#        '6046.T',
#        '6044.T',
#        '3458.T',
#        '3134.T',
#        '4592.T',
#        '3913.T',
#        '7813.T',
#        '3912.T',
#        '3457.T',
#        '3445.T',
#        '3907.T',
#        '3906.T',
#        '6036.T'


#'3463.T'
#'6181.T'
'3465.T'
]

# 各銘柄の業種と産業を取得
sectors = []
industries = []

for symbol in symbols:
    try:
        ticker_info = yf.Ticker(symbol).info
        sector = ticker_info.get('sector')
        industry = ticker_info.get('industry')
        if sector:
            sectors.append(sector)
        if industry:
            industries.append(industry)
    except Exception as e:
        print(f"Error retrieving data for {symbol}: {e}")

# ユニークな業種と産業のリストを取得
unique_sectors = set(sectors)
unique_industries = set(industries)

# 業種と産業の数とリストを表示
print(f"Total unique sectors: {len(unique_sectors)}")
for sector in sorted(unique_sectors):
    print(sector)
print('-' * 10)

print(f"\nTotal unique industries: {len(unique_industries)}")
for industry in sorted(unique_industries):
    print(industry)
print('-' * 10)

