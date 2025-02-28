# モジュールのインポート
import pandas as pd
import requests
import json

# リフレッシュトークンの取得
#mail_address = ""
#password = ""

#data = {"mailaddress":mail_address, "password":password}
#r_post = requests.post(
#    "https://api.jpx-jquants.com/v1/token/auth_user",
#    data=json.dumps(data)
#)
#refresh_token = r_post.json()['refreshToken']

refresh_token = ""

# IDトークンの取得
r_post = requests.post(
    f"https://api.jquants.com/v1/token/auth_refresh?refreshtoken={refresh_token}"
)
id_token = r_post.json()['idToken']

code = "160A"

# 株価情報の取得
headers = {'Authorization': 'Bearer {}'.format(id_token)}
r = requests.get(
    f"https://api.jquants.com/v1/prices/daily_quotes?code={code}",
    headers=headers
)
price_df = pd.DataFrame(r.json()['daily_quotes'])
lastest_stock_price = price_df.iloc[-1]['Close']
print(lastest_stock_price)


# 財務データの取得
headers = {'Authorization': 'Bearer {}'.format(id_token)}
r = requests.get(
    f"https://api.jquants.com/v1/fins/statements?code={code}",
    headers=headers
)
statements_df = pd.DataFrame(r.json()['statements'])
eps = float(statements_df['EarningsPerShare'].iloc[-1])
#print(statements_df[['CurrentPeriodEndDate', 'EarningsPerShare', 'ForecastEarningsPerShare']])
#print(eps)


print(lastest_stock_price / eps)
