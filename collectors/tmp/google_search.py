import os
from googleapiclient.discovery import build

# ご自身のAPIキーとカスタム検索エンジンIDに置き換えてください
GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
SEARCH_ENGINE_ID = os.environ["GCP_WEB_SEARCH_ENGINE_ID"]

# Custom Search API用のサービスオブジェクトを作成
service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)

# 検索クエリ（例として「ニュース」）
query = "國江仙嗣 フィットイージー 想い"
# 日付範囲の指定（例: 2025年1月1日～2025年1月31日）
sort_param = 'date:r:20180101:20220101'

# APIリクエストを実行
response = service.cse().list(
    q=query,
    cx=SEARCH_ENGINE_ID,
    num=10,        # 取得件数（最大10件まで指定可能）
    sort=sort_param
).execute()

# 結果の表示
for item in response.get('items', []):
    title = item.get('title')
    snippet = item.get('snippet')
    link = item.get('link')
    print('Title:', title)
    print('Snippet:', snippet)
    print('Link:', link)
    print('---------------------')
