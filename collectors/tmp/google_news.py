import feedparser
from datetime import datetime
import urllib.parse

# 検索クエリ
query = "國江仙嗣 フィットイージー 想い"
encoded_query = urllib.parse.quote(query)  # URLエンコード

# GoogleニュースRSSのURL（日本語版）
url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"

# RSSフィードの解析
feed = feedparser.parse(url)

# 日付範囲の指定（例: 2018-01-01～2022-01-01）
from_date = datetime.strptime("2018-01-01", "%Y-%m-%d")
to_date = datetime.strptime("2022-01-01", "%Y-%m-%d")

# 最大取得件数
max_items = 5
count = 0

for entry in feed.entries:
    if count >= max_items:
        break

    # published_parsedが存在するかチェックし、日時を取得
    if hasattr(entry, 'published_parsed'):
        published = datetime(*entry.published_parsed[:6])
    else:
        continue

    # 指定した日付範囲内の記事のみ処理
    if from_date <= published <= to_date:
        title = entry.title
        summary = entry.summary
        link = entry.link

        print("Title:", title)
        print("Published:", published.strftime("%Y-%m-%d %H:%M:%S"))
        print("Summary:", summary)
        print("Link:", link)
        print('---------------------')
        count += 1
