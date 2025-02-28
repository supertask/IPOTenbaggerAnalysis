import yfinance as yf

symbols = [
'6556.T'
]

sector_dict = {
    "Consumer Defensive": "消費者防衛",
    "Consumer Cyclical": "消費者循環",
    "Real Estate": "不動産",
    "Communication Services": "通信サービス",
    "Technology": "技術",
    "Healthcare": "ヘルスケア",
    "Industrials": "産業",
    "Financial Services": "金融サービス",
    "Basic Materials": "基礎材料",
    "Energy": "エネルギー"
}

industry_dict = {
    "Consumer Defensive": "消費者防衛",
    "Consumer Cyclical": "消費者循環",
    "Real Estate": "不動産",
    "Communication Services": "通信サービス",
    "Technology": "技術",
    "Healthcare": "ヘルスケア",
    "Industrials": "産業",
    "Financial Services": "金融サービス",
    "Basic Materials": "基礎材料",
    "Energy": "エネルギー",
    "Household & Personal Products": "家庭用品・個人用品",
    "Personal Services": "個人サービス",
    "Real Estate Services": "不動産サービス",
    "Entertainment": "娯楽",
    "Advertising Agencies": "広告代理店",
    "Electronic Gaming & Multimedia": "電子ゲーム・マルチメディア",
    "Telecom Services": "電気通信サービス",
    "Software-Infrastructure": "ソフトウェア-インフラストラクチャ",
    "Leisure": "レジャー",
    "Drug Manufacturers-Specialty & Generic": "医薬品メーカー-専門・ジェネリック",
    "Internet Content & Information": "インターネットコンテンツ・情報",
    "Tools & Accessories": "ツール・アクセサリー",
    "Information Technology Services": "情報技術サービス",
    "REIT-Hotel & Motel": "REIT-ホテル・モーテル",
    "Software-Application": "ソフトウェア-アプリケーション",
    "Specialty Business Services": "専門ビジネスサービス",
    "Credit Services": "信用サービス",
    "Banks-Regional": "銀行-地域",
    "Insurance-Life": "保険-生命",
    "Restaurants": "レストラン",
    "Biotechnology": "バイオテクノロジー",
    "Publishing": "出版",
    "Internet Retail": "インターネット小売",
    "Engineering & Construction": "工学・建設",
    "Apparel Retail": "衣料品小売",
    "Building Materials": "建材",
    "Packaged Foods": "包装食品",
    "REIT-Residential": "REIT-住宅",
    "Oil & Gas Refining & Marketing": "石油・ガス精製・販売",
    "Medical Instruments & Supplies": "医療機器・用品",
    "Specialty Industrial Machinery": "特殊産業機械",
    "Electronic Components": "電子部品",
    "Staffing & Employment Services": "人材派遣・雇用サービス",
    "REIT-Diversified": "REIT-多様化",
    "Resorts & Casinos": "リゾート・カジノ",
    "Electronic Components": "電子部品",
    "Electronics & Computer Distribution": "電子機器・コンピュータ流通",
    "Residential Construction": "住宅建設",
    "Semiconductors": "半導体",
    "REIT-Healthcare Facilities": "REIT-医療施設",
    "Farm Products": "農産物",
    "Asset Management": "資産運用",
    "Specialty Chemicals": "特殊化学品"
}


for symbol in symbols:
    try:
        ticker_info = yf.Ticker(symbol).info
        sector = ticker_info.get('sector')
        industry = ticker_info.get('industry')
        
        sector = sector_dict.get(sector, sector)
        industry = industry_dict.get(industry, industry)
        
        code = symbol.replace('.T', '')

        print(f"code = {code}, sector = {sector}, industry = {industry}")
    except Exception as e:
        print(f"Error retrieving data for {symbol}: {e}")
