import requests
import os
import csv
import re
import json
import locale
import statistics
from datetime import datetime
import yfinance as yf
import pandas as pd
from bs4 import BeautifulSoup
from tqdm import tqdm
from requests.exceptions import HTTPError

from collectors.settings import GeneralSettings, KisoScraperSettings

class IPOKisoDetailsCollector:
    def __init__(self):
        self.general_settings = GeneralSettings()
        self.kiso_scraper_settings = KisoScraperSettings()
        locale.setlocale(locale.LC_ALL, self.general_settings.locale_settings)
        self.base_url = self.kiso_scraper_settings.base_url

    def string_to_float(self, value):
        try:
            return locale.atof(value)
        except ValueError:
            return None

    def clean_value(self, value, company_name, relative_url):
        try:
            value = re.sub(r'[^\d\.\-\(\)％%]', '', value) #[] の中は「許可される文字」のリストを示します。

            if value == '' or value == "-" or value == "(-)" or value == "（-）":
                return None
            else:
                value = value.strip('()（）%％')
                value = value.replace(",", "").replace('△', '-')
                return float(value)
        except ValueError as e:
            print(f"ValueError at value '{value}' for {company_name} at {self.base_url}{relative_url}: {e}")
            return None

    def is_float(self, value):
        try:
            float(value)
            return True
        except ValueError:
            return False

    def clean_shareholder_ratio(self, shareholders, relative_url):
        try:
            for shareholder in shareholders:
                ratio_str = shareholder["比率"].replace(",", ".")  # サイト上の表記が間違えている時があるため、カンマをピリオドに置換
                if ratio_str.endswith("％") or ratio_str.endswith("%"):
                    ratio_str = ratio_str[:-1]  # Remove the "％" character
                
                shareholder["比率"] = float(ratio_str)
                shareholder["isCEO"] = "社長" in shareholder["株主名"]
            return shareholders
        except ValueError as e:
            print(f"Error cleaning shareholder ratio for {self.base_url}{relative_url}: {e}")
            return []

    def is_increasing(self, data, normalized_tolerance = 0.2):
        prev_value = None
        
        for key, value in data.items():
            if value is None:
                continue
            
            if prev_value is not None:
                tolerance_value = prev_value * normalized_tolerance
                if value < prev_value - tolerance_value:
                    return False
            
            prev_value = value
        
        return True

    def save_html_to_cache(self, html, year, company_code, company_name):
        """ HTMLを指定されたパスに保存する """
        # ファイル名に使用できない文字を削除
        sanitized_name = re.sub(r'[<>:"/\\|?*]', '_', company_name)
        cache_dir = f"{self.kiso_scraper_settings.cache_dir}/{year}"
        os.makedirs(cache_dir, exist_ok=True)
        file_path = os.path.join(cache_dir, f"{company_code}_{sanitized_name}.html")
        
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(html)
            
        return file_path

    def load_html_from_cache(self, year, company_code, company_name):
        """ キャッシュされたHTMLを読み込む """
        sanitized_name = re.sub(r'[<>:"/\\|?*]', '_', company_name)
        file_path = f"{self.kiso_scraper_settings.cache_dir}/{year}/{company_code}_{sanitized_name}.html"
        
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        
        return None

    def scrape_company_data(self, relative_url, year, company_code, company_name):
        """ 企業データを取得し、キャッシュがあればそれを使用 """
        cached_html = self.load_html_from_cache(year, company_code, company_name)
        
        if cached_html:
            html = cached_html
        else:
            url = f'{self.base_url}{relative_url}'
            response = requests.get(url)
            html = response.content.decode('utf-8')  # bytesからstrへ変換
            
            # キャッシュとして保存
            self.save_html_to_cache(html, year, company_code, company_name)

        soup = BeautifulSoup(html, 'html.parser')

        company_name_tag = soup.find(string=re.compile("会社名"))
        company_name = company_name_tag.find_next().text.strip() if company_name_tag else ''

        company_url_tag = soup.find(string=re.compile("会社URL"))
        company_url = company_url_tag.find_next().text.strip() if company_url_tag else ''

        company_establishment_tag = soup.find(string=re.compile("会社設立"))
        company_establishment = company_establishment_tag.find_next().text.strip() if company_establishment_tag else ''

        listing_date = ''
        listing_date_tag = soup.find(string=re.compile("上場日"))
        if (listing_date_tag):
            listing_date = listing_date_tag.find_next('td').text.strip()

        shareholder_table = soup.find('table', class_='kobetudate05')
        shareholders = []
        if shareholder_table:
            for row in shareholder_table.find_all('tr')[1:]:
                cols = row.find_all('td')
                if len(cols) >= 3:
                    name = cols[0].text.strip()
                    ratio = cols[1].text.strip()
                    lockup = cols[2].text.strip()
                    shareholders.append({"株主名": name, "比率": ratio, "ロックアップ": lockup})
                elif len(cols) >= 2:
                    name = cols[0].text.strip()
                    ratio = cols[1].text.strip()
                    shareholders.append({"株主名": name, "比率": ratio, "ロックアップ": "None"})

        shareholders = self.clean_shareholder_ratio(shareholders, relative_url)

        performance_table_tags = soup.find_all('table', class_='kobetudate04')
        performance_data = []
        indicators = []
        if len(performance_table_tags) >= 2:
            performance_table = performance_table_tags[-1]
            #print(performance_table)

            years = [td.text.strip() for td in performance_table.find('tr').find_all('td')[1:]]

            for row in performance_table.find_all('tr')[1:]:
                header_columns = row.find_all('th')
                columns = row.find_all('td')
                if len(header_columns) == 0:
                    first_column = columns[0]
                    #print("No header_columns: %s, row: %s, URL: %s. " % (first_column, row, url) )
                else:
                    first_column = header_columns[0]
                if len(columns) > 1:
                    first_col_header = first_column.text.strip()
                    row_data = {first_col_header: {}}
                    for i, year in enumerate(years):
                        year = year.replace("\r\n", "")
                        cell = columns[i + 1].text.strip()
                        cleaned_cell = self.clean_value(cell, company_name, relative_url)
                        #print("before: %s, after: %s" % (cell, cleaned_cell))
                        row_data[first_col_header][year] = cleaned_cell
                    performance_data.append(row_data)


        business_content = ''
        for p_tag in soup.find_all('p'):
            match = re.search(r'事業内容は「(.*?)」で', p_tag.text)
            if match:
                business_content = match.group(1)
                break

        admin_comment = ''
        admin_comment_tag = soup.find('h2', string='管理人からのコメント')
        if admin_comment_tag:
            next_p_tag = admin_comment_tag.find_next('p')
            if next_p_tag:
                admin_comment = next_p_tag.text.strip()

        captial_threshold = 250
        market_capital = ''
        per = ''
        for p_tag in soup.find_all('p'):
            match = re.search(r'想定時価総額([\d,]+\.\d+)億円', p_tag.text)
            if match:
                market_capital_value = self.string_to_float(match.group(1))
                market_capital = market_capital_value

                if market_capital_value and market_capital_value <= captial_threshold:
                    indicators.append("\n時価%s億↓" % captial_threshold)
            #match = re.search(r'PER.*(\d+\.\d+)倍', p_tag.text)
            #match = re.search(r'PER.*(\d+(?:\.\d+)?)倍', p_tag.text)
            match = re.search(r'PER.*?(\d+(?:\.\d+)?)(?=倍)', p_tag.text)

            if match:
                per = match.group(1)
                if not self.is_float(per):
                    #print(f"Error: Extracted PER value '{per}' is not a valid float. Source: {p_tag.text.strip()}")
                    raise ValueError(f"Invalid PER value: '{per}' from text '{p_tag.text.strip()}'")

        ceo_stock_ratio = ''
        for shareholder in shareholders:
            if shareholder["isCEO"] and shareholder["比率"] > 10:
                ceo_stock_ratio = str(shareholder["比率"])
                ceo_stock = f"社長株{ceo_stock_ratio}%"
                indicators.append("\n" + ceo_stock)
                break

        securities_report_url = ''
        for a_tag in soup.find_all('a', href=True):
            if 'https://disclosure2dl.edinet-fsa.go.jp/searchdocument/' in a_tag['href']:
                securities_report_url = a_tag['href']
                break

        return {
            "企業名": company_name, # どの市場かの情報も入っている
            "会社URL": company_url,
            "会社設立": company_establishment,
            "PER": per,
            "社長株%": ceo_stock_ratio,
            "想定時価総額（億円）": market_capital,
            "上場日": listing_date,
            "株主名と比率": json.dumps(shareholders, ensure_ascii=False),
            "企業業績のデータ（5年分）": json.dumps(performance_data, ensure_ascii=False),
            "事業内容": business_content,
            "管理人からのコメント": admin_comment,
            #"テンバガー指標": "".join(indicators),
            "有価証券報告書": securities_report_url
        }

    def format_performance_data(self, performance_data):
        """ '企業業績のデータ（5年分）'から整形されたテキストを生成し、決算と決算伸び率%を別のカラムに分ける """
        # 整形前のデータのデバッグ
        #print(performance_data)

        financial_data = [] #整形して保存
        financial_growth_rate_data = []  # 決算伸び率%用データ
        sales_growth_rates = []  # 売上高の伸び率を格納
        operating_profit_ratios = {}  # 年ごとの経常利益率を格納
        
        # 売上高と経常利益のデータを抽出するための変数
        sales_data = None
        operating_profit_data = None

        #
        # 決算データに関して
        #   1. 数値を整形
        #   2. 成長率を計算
        #
        for entry in performance_data:
            for key, yearly_data in entry.items():
                if any(ex_key in key for ex_key in self.kiso_scraper_settings.exclude_keys):
                    continue  # 不要な項目をスキップ

                # 決算データ
                values = []
                prev_value = None
                yearly_growth = []

                for year, value in yearly_data.items():
                    if value is not None:
                        if "自己資本利益率" in key or "自己資本比率" in key:
                            formatted_value = f"{value:.1f}"  # 小数第1位までのfloat
                        else:
                            formatted_value = f"{int(value)}"  # int型としてフォーマット

                        # 成長率計算
                        if prev_value is not None and prev_value != 0:
                            growth = ((value - prev_value) / abs(prev_value)) * 100
                            yearly_growth.append(f"{growth:.0f}%")

                            # 売上高の伸び率を記録
                            if "売上高" in key:
                                sales_growth_rates.append(growth)
                        else:
                            yearly_growth.append("None")  # 初年度や前値がNoneの場合
                    else:
                        formatted_value = "None"
                        yearly_growth.append("None")

                    values.append(formatted_value)
                    prev_value = value

                # フォーマットされた決算データを追加
                financial_data.append(f"{key}\t" + "\t".join(values))
                financial_growth_rate_data.append("\t".join(yearly_growth))
                
                # 売上高と経常利益のデータを保存
                if "売上高" in key:
                    sales_data = yearly_data
                elif "経常利益" in key:
                    operating_profit_data = yearly_data

        #
        # 独自計算
        # 売上に対しての経常利益を計算し、各年ごとに保存
        #
        if sales_data and operating_profit_data:
            for year in sales_data:
                sales = sales_data.get(year)
                profit = operating_profit_data.get(year)
                if sales and profit:
                    profit_ratio = (profit / sales) * 100
                    operating_profit_ratios[year] = round(profit_ratio, 1)
                else:
                    operating_profit_ratios[year] = "None"

            # 経常利益率を「決算」に追加
            profit_ratio_values = [str(operating_profit_ratios[year]) for year in sales_data]
            financial_data.append(f"経常利益率（％）\t" + "\t".join(profit_ratio_values))

#            ## 経常利益率の成長率を計算
#            prev_ratio = None
#            profit_ratio_growth = []
#            for year in sales_data:
#                current_ratio = operating_profit_ratios[year]
#                if current_ratio != "None" and prev_ratio is not None:
#                    growth = ((current_ratio - prev_ratio) / abs(prev_ratio)) * 100
#                    profit_ratio_growth.append(f"{growth:.0f}%")
#                else:
#                    profit_ratio_growth.append("None")
#                prev_ratio = current_ratio if current_ratio != "None" else prev_ratio

            # 経常利益率の成長率を計算（不要なので "None" に固定）
            profit_ratio_growth = ["None"] * len(sales_data)  # 各年に対応する "None"

            financial_growth_rate_data.append("\t".join(profit_ratio_growth))

        #
        # 成長率のデバッグ
        #
        #for year_growth_rate in financial_growth_rate_data:
        #    print(year_growth_rate)


        # 売上高の伸び率計算
        average_sales_growth_rate = (
            round(sum(sales_growth_rates) / len(sales_growth_rates), 1)
            if sales_growth_rates else None
        )

        # 経常利益率の平均
        valid_ratios = list(filter(lambda x: x != "None", operating_profit_ratios.values()))
        average_operating_profit_ratio = (
            round(sum(valid_ratios) / len(valid_ratios), 1)
            if valid_ratios else None
        )

        return "\n".join(financial_data), "\n".join(financial_growth_rate_data), average_sales_growth_rate, average_operating_profit_ratio 

    def run(self):
        for year in self.kiso_scraper_settings.years:
            # DEBUG: 特定の年をデバッグする用
            #if not year in [2011]: continue

            input_file = os.path.join(self.kiso_scraper_settings.input_dir, f'companies_{year}.tsv')
            output_file = os.path.join(self.kiso_scraper_settings.output_dir, f'companies_{year}.tsv')

            #if os.path.exists(output_file):
            #    print(f"{year}年の出力ファイルが既に存在するため、処理をスキップします。")
            #    continue

            with open(input_file, 'r', encoding='utf-8') as infile, open(output_file, 'w', newline='', encoding='utf-8') as outfile:
                reader = csv.reader(infile, delimiter='\t')
                next(reader) # headerをスキップ

                header_row = [
                    "企業名", "コード", "想定時価総額（億円）",  "社長株%", "PER",
                    "IPO情報URL", "IR", "有価証券報告書", "会社URL", "事業内容",
                    "決算", "決算伸び率%", '売上成長率_平均', "経常利益率_平均", "会社設立", "管理人からのコメント",
                    "上場日", "市場", "株主名と比率", "企業業績のデータ（5年分）"
                ]
                writer = csv.DictWriter(outfile, fieldnames=header_row, delimiter='\t')
                writer.writeheader()
                
                market_name_re = r'【([^】]+)】'

                rows = list(reader)
                for index, row in enumerate(tqdm(rows, desc="Processing")):
                    #if index > 0: break #debug
                    
                    if len(row) == 3:
                        relative_url = row[2]

                        company_name, code, ipo_info_url = row
                        company_data = self.scrape_company_data(relative_url, year, code, company_name)
                        match_market_name = re.search(market_name_re, company_data['企業名']) # 市場の名前も企業名に入っている
                        market_name = match_market_name.group(1) if match_market_name else ""
                        company_data["企業名"] = company_name #読み込んだCSVに書かれた企業名で置き換え
                        
                        performance_data_json = company_data.get("企業業績のデータ（5年分）", "[]")
                        performance_data = json.loads(performance_data_json)
                        decisions, growth_rates, avg_sales_growth, avg_operating_profit_ratio = self.format_performance_data(performance_data)
                        company_data["決算"] = decisions
                        company_data["決算伸び率%"] = growth_rates
                        company_data["売上成長率_平均"] = avg_sales_growth
                        company_data["経常利益率_平均"] = avg_operating_profit_ratio

                        full_ipo_info_url = f'{self.base_url}{ipo_info_url}'
                        ir_url = "https://irbank.net/" + code + "/ir"
                        #sector, industry, unlisted = get_company_info(code) #yfinanceから業種を取得

                        company_data.update({
                            "コード": code,
                            "IPO情報URL": full_ipo_info_url,
                            "IR": ir_url,
                            "市場": market_name,
                        })

                        writer.writerow(company_data)
                        #time.sleep(random.uniform(0.02, 0.1))

            print(f"{year}データの取得と書き込みが完了しました。")

if __name__ == "__main__":
    collector = IPOKisoDetailsCollector()
    collector.run()