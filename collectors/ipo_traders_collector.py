import re
import os
import requests
from bs4 import BeautifulSoup
import csv
import pandas as pd 
from collectors.settings import GeneralSettings, TradersScraperSettings
from collectors.ipo_analyzer_core import IPOAnalyzerCore
import traceback

class IPOTradersAnalyzer(IPOAnalyzerCore):
    def __init__(self):
        super().__init__()
        self.traders_scraper_settings = TradersScraperSettings()
        self.base_url = self.traders_scraper_settings.base_url
        self.shareholders_df = pd.DataFrame(columns=['shareholder_name', 'shareholder_notes', 'count'])
        self.shareholders_notes_df = pd.DataFrame(columns=['shareholder_notes', 'shareholder_name'])

    def fetch_traders_page(self, code, year, company_name, cache_dir):
        url = f"{self.base_url}/{code}"
        cache_path = os.path.join(cache_dir, f"{year}/{code}_{company_name}.html")
    
        if not os.path.exists(os.path.dirname(cache_path)):
            os.makedirs(os.path.dirname(cache_path))
    
        if not os.path.exists(cache_path):
            response = requests.get(url)
            html = response.content.decode('utf-8')  # bytesからstrへ変換
            if response.status_code == 200:
                with open(cache_path, 'w', encoding='utf-8') as file:
                    file.write(html)
            else:
                raise ValueError(f"Failed to fetch page for {company_name} ({code})")
        else:
            with open(cache_path, 'r', encoding='utf-8') as file:
                return file.read()
    
        return response.text
    
    
    def extract_birth_year(self, rep_name_field):
        """代表者名のフィールドから生年を抽出"""
        import re
        # 西暦の年を抽出
        match = re.search(r'(\d{4})年生', rep_name_field)
        if match:
            return int(match.group(1))
        # 和暦の年を変換して抽出
        match = re.search(r'S(\d{2})年生', rep_name_field)
        if match:
            year = int(match.group(1))
            return 1925 + year  # 昭和は1925年から
        return None
    
    
    def convert_to_western_year(self, established_year):
        """
        設立年を西暦に変換する関数
        :param established_year: 設立年の文字列（例："H12年", "S34年", "2003年"）
        :return: 西暦の設立年
        """
        import re
        if "H" in established_year:
            year = int(re.search(r'H(\d+)', established_year).group(1))
            return 1988 + year  # 平成は1988年から
        elif "S" in established_year:
            year = int(re.search(r'S(\d+)', established_year).group(1))
            return 1925 + year  # 昭和は1925年から
        elif "T" in established_year:
            year = int(re.search(r'T(\d+)', established_year).group(1))
            return 1911 + year  # 大正は1911年から
        elif "R" in established_year:
            year = int(re.search(r'R(\d+)', established_year).group(1))
            return 2018 + year  # 令和は2018年から
        else:
            # 西暦の場合
            year = int(re.search(r'(\d{4})', established_year).group(1))
            return year
    
    def extract_capital_value(self, capital_text):
        """
        資本金のテキストから数値部分のみを抽出
        """
        import re
        cleaned_text = capital_text.replace('\u3000', '').replace(',', '')
        match = re.search(r'\d+', cleaned_text)
        if match:
            return int(match.group(0))
        else:
            raise ValueError(f"資本金の数値を抽出できません: {capital_text}")
    
    def extract_shares_count(self, shares_field):
        """
        上場時発行株式数から数値部分のみを抽出
        """
        import re
        main_shares = re.sub(r'\(.*?\)', '', shares_field)  # 括弧内の情報を削除
        main_shares = main_shares.replace(',', '').replace('株', '').strip()
        match = re.search(r'\d+', main_shares)
        if match:
            return int(match.group(0))
        else:
            raise ValueError(f"上場時発行株式数の数値を抽出できません: {shares_field}")
    
    def extract_public_shares(self, public_shares_field):
        """
        公開株式数フィールドを解析して、公開株式数、内訳の公募、売り出し、オーバーアロットメントを抽出
        """
        import re
        # カッコ内の情報を取得
        main_shares = re.sub(r'\(.*?\)', '', public_shares_field).replace(',', '').replace('株', '').strip()
        match = re.search(r'\d+', main_shares)
        
        if not match:
            raise ValueError(f"公開株式数の数値を抽出できません: {public_shares_field}")
        
        public_shares = int(match.group(0))
    
        # 内訳を抽出
        sub_fields = re.findall(r'公募(\d+)|売り出し(\d+)|オーバーアロットメント(\d+)', public_shares_field.replace(',', ''))
        sub_values = {'公募': 0, '売り出し': 0, 'オーバーアロットメント': 0}
        
        for group in sub_fields:
            if group[0]:
                sub_values['公募'] = int(group[0])
            elif group[1]:
                sub_values['売り出し'] = int(group[1])
            elif group[2]:
                sub_values['オーバーアロットメント'] = int(group[2])
        
        return public_shares, sub_values['公募'], sub_values['売り出し'], sub_values['オーバーアロットメント']
    
    
    def parse_traders_web(self, html, code, company_name, listing_year):
        data = {'コード': code, '企業名': company_name}  # コードと会社名を最初に追加
        soup = BeautifulSoup(html, 'html.parser')
    
        # スケジュールセクションのパース
        schedule_data = self.parse_schedule_section(soup, code, company_name)
        data.update(schedule_data)
    
        # 基本情報セクションのパース
        basic_info_data = self.parse_basic_info_section(soup, code, company_name, listing_year)
        data.update(basic_info_data)
        data['想定時価総額'] = schedule_data['想定価格'] * basic_info_data['上場時発行済株数']
    
        # 大株主セクションのパース
        shareholders_data = self.parse_shareholders_section(soup, code, company_name)
        data.update(shareholders_data)
    
        #TODO: 参考類似企業, 事業詳細を取得できるようにする

        return data
    
    def parse_schedule_section(self, soup, code, company_name):
        data = {}
        # スケジュールセクションを絞り込む
        schedule_div = soup.find('div', class_='zone_title', string=lambda text: 'スケジュール' in text)
        if not schedule_div:
            raise ValueError(f"スケジュールセクションが見つかりません: コード={code}, 企業名={company_name}")
    
        schedule_section = schedule_div.find_next('div', class_='d-flex flex-md-nowrap flex-wrap')
        if not schedule_section:
            raise ValueError(f"スケジュールセクションの構造が異なります: コード={code}, 企業名={company_name}")
    
        price_info_table = schedule_section.find_all('table')[1] if len(schedule_section.find_all('table')) > 1 else None
        if not price_info_table:
            raise ValueError(f"価格情報テーブルが見つかりません: コード={code}, 企業名={company_name}")
            

        def stock_price_int(field, value):
            try:
                value_str = value.replace('円', '').replace(',', '').replace('-', '').strip()
                if not value_str:
                    if self.traders_scraper_settings.is_debug:
                        raise ValueError("値が空または不正な形式です")
                    return None
                return int(value_str)
            except ValueError as e:
                raise ValueError(f"整数に変換できませんでした: {field}, {value}") from e
    
        try:
            data['上場日'] = schedule_section.find('th', string='上場日').find_next_sibling('td').text.strip()
                
            # 想定価格の加工
            value = price_info_table.find('th', string='想定価格').find_next_sibling('td').text.strip()
            if '-' in value:
                min_value, max_value = map(lambda x: stock_price_int("想定価格", x), value.split('-'))
                average_price = (min_value + max_value) // 2  # 平均値を計算
                data['想定価格'] = average_price
            else:
                data['想定価格'] = stock_price_int("想定価格", value)
    
            # 公開価格、初値予想、初値の加工
            for field in ['公開価格', '初値予想', '初値']:
                value = price_info_table.find('th', string=field).find_next_sibling('td').text.strip()
                data[field] = stock_price_int(field, value)
    
            # 仮条件の加工
            tentative_condition = price_info_table.find('th', string='仮条件').find_next_sibling('td').text.strip()
            if '-' in tentative_condition:
                min_value, max_value = map(lambda x: stock_price_int('仮条件', x), tentative_condition.split('-'))
                data['仮条件min'] = min_value
                data['仮条件max'] = max_value
            else:
                tentative_condition_value = stock_price_int('仮条件', tentative_condition)
                data['仮条件min'] = data['仮条件max'] = tentative_condition_value

            # 想定価格の加工
            value = price_info_table.find('th', string='想定価格').find_next_sibling('td').text.strip()
            if '-' in value:
                min_value, max_value = map(lambda x: stock_price_int("想定価格", x), value.split('-'))
                average_price = (min_value + max_value) // 2  # 平均値を計算
                data['想定価格'] = average_price
            else:
                data['想定価格'] = stock_price_int("想定価格", value)
            

        except AttributeError as e:
            print(traceback.format_exc())
            raise ValueError(f"スケジュールデータが正しく取得できません: コード={code}, 企業名={company_name}, エラー={e}")
        return data
    
    def parse_basic_info_section(self, soup, code, company_name, listing_year):
        data = {}
        # 基本情報セクションを絞り込む
        info_div = soup.find('div', class_='zone_title', string=lambda text: '基本情報' in text)
        if not info_div:
            raise ValueError(f"基本情報セクションが見つかりません: コード={code}, 企業名={company_name}")
    
        basic_info_section = info_div.find_next('div', class_='w-100')
        try:
            data['代表者名'] = basic_info_section.find('th', string='代表者名').find_next_sibling('td').text.strip()
            birth_year = self.extract_birth_year(data['代表者名'])
            data['代表者の上場時の年齢'] = listing_year - birth_year if birth_year else "不明"
            data['設立年'] = self.convert_to_western_year(basic_info_section.find('th', string='設立年').find_next_sibling('td').text.strip())
    
            employee_text = basic_info_section.find('th', string='従業員数').find_next_sibling('td').text.strip()
            match = re.search(r'(\d+)', employee_text)
            data['従業員数'] = int(match.group(1)) if match else None
    
            shareholder_text = basic_info_section.find('th', string='株主数').find_next_sibling('td').text.strip()
            match = re.search(r'(\d+)', shareholder_text)
            data['株主数'] = int(match.group(1)) if match else None
    
            capital_text = basic_info_section.find('th', string='資本金').find_next_sibling('td').text.strip()
            data['資本金'] = self.extract_capital_value(capital_text)
    
            shares_text = basic_info_section.find('th', string='上場時発行済株数').find_next_sibling('td').text.strip()
            data['上場時発行済株数'] = self.extract_shares_count(shares_text)
    
            # 公開株式数の抽出
            public_shares_field = basic_info_section.find('th', string='公開株数').find_next_sibling('td').text.strip()
            public_shares, public_offering, selling_shares, over_allotment = self.extract_public_shares(public_shares_field)
            data['公開株式数'] = public_shares
            data['公募%'] = round(100 * public_offering / float(public_shares), 1)
            data['売り出し%'] = round(100 * selling_shares / float(public_shares), 1)
            data['オーバーアロットメント%'] = round(100 *  over_allotment  / float(public_shares), 1)
    
            data['調達資金使途'] = basic_info_section.find('th', string='調達資金使途').find_next_sibling('td').text.strip()
        except AttributeError as e:
            print(traceback.format_exc())
            raise ValueError(f"基本情報データが正しく取得できません: コード={code}, 企業名={company_name}, エラー={e}")
    
        return data
    
    def parse_shareholders_section(self, soup, code, company_name):
        data = {}
        # 大株主セクションを絞り込む
        shareholders_div = soup.find('div', class_='zone_title', string=lambda text: '大株主' in text)
        if not shareholders_div:
            raise ValueError(f"大株主セクションが見つかりません: コード={code}, 企業名={company_name}")
    
        # 大株主テーブルを直接検索
        shareholders_table = shareholders_div.find_next('table', class_='data_table')
        if not shareholders_table:
            raise ValueError(f"大株主テーブルが見つかりません: コード={code}, 企業名={company_name}")
    
        category_totals = {category: 0 for category in self.traders_scraper_settings.shareholders_categories}
        ignore_keywords = self.traders_scraper_settings.shareholders_ignores
    
        shareholders_data = []
        rows = shareholders_table.find_all('tr')[1:]  # ヘッダー行をスキップ
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 4:
                continue
            shareholder_name = cells[0].text.strip()
            shareholder_notes = cells[1].text.strip()
            shareholder_stocks = cells[2].text.strip().replace(',', '')
            shareholder_ratio = float(cells[3].text.strip().replace('%', ''))
    
            shareholders_data.append(f"{shareholder_name}\t{shareholder_notes}\t{shareholder_stocks}\t{shareholder_ratio}")
    
            if any(keyword in shareholder_notes for keyword in ignore_keywords):
                continue
            
            for category, keywords in self.traders_scraper_settings.shareholders_categories.items():
                if any(keyword in shareholder_notes for keyword in keywords):
                    category_totals[category] += shareholder_ratio
                    break
                
            if (self.shareholders_df['shareholder_name'] == shareholder_name).any():
                self.shareholders_df.loc[self.shareholders_df['shareholder_name'] == shareholder_name, 'count'] += 1
                self.shareholders_df.loc[self.shareholders_df['shareholder_name'] == shareholder_name, 'shareholder_notes'] = \
                    self.shareholders_df.loc[self.shareholders_df['shareholder_name'] == shareholder_name, 'shareholder_notes'].apply(
                        lambda notes: list(set(notes + [shareholder_notes]))
                    )
            else:
                self.shareholders_df = pd.concat([self.shareholders_df, pd.DataFrame({
                    'shareholder_name': [shareholder_name],
                    'shareholder_notes': [[shareholder_notes]],
                    'count': [1]
                })], ignore_index=True)
    
            if not (self.shareholders_notes_df['shareholder_notes'] == shareholder_notes).any():
                self.shareholders_notes_df = pd.concat([self.shareholders_notes_df, pd.DataFrame({
                    'shareholder_notes': [shareholder_notes],
                    'shareholder_name': [[shareholder_name]]
                })], ignore_index=True)
            else:
                self.shareholders_notes_df.loc[self.shareholders_notes_df['shareholder_notes'] == shareholder_notes, 'shareholder_name'] = \
                    self.shareholders_notes_df.loc[self.shareholders_notes_df['shareholder_notes'] == shareholder_notes, 'shareholder_name'].apply(
                        lambda names: list(set(names + [shareholder_name]))
                    )
    
        data['オーナー株%'] = 0
        for category, total in category_totals.items():
            data[f"{category}_株%"] = total
            if category in self.traders_scraper_settings.owners:
                data['オーナー株%'] += total
    
        # 「大株主」情報を結合してデータに追加
        data['大株主'] = "\n".join(shareholders_data)
    
        return data
    


    def run(self):
        for year in self.traders_scraper_settings.years:
            # DEBUG: 特定の年をデバッグする用
            #if not year in [2011]: continue
            print("year:", year)
    
            input_file = os.path.join(self.traders_scraper_settings.input_dir, f'companies_{year}.tsv')
            output_file = os.path.join(self.traders_scraper_settings.output_dir, f'companies_{year}.tsv')
    
            os.makedirs(self.traders_scraper_settings.output_dir, exist_ok=True)  # 出力ディレクトリを作成
    
            company_data_list = []  # 年ごとのすべての会社データを保持するリスト
    
            with open(input_file, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file, delimiter='\t')
                for row in reader:
                    company_name = row['企業名']
                    company_code = row['コード']

                    is_success = False
                    error_count = 0
                    traders_web_info = None

                    while True:
                        if is_success:
                            break
                        if error_count >= 2:
                            break
                        try:
                            html = self.fetch_traders_page(company_code, year, company_name, self.traders_scraper_settings.cache_dir)
                        except ValueError as e:
                            print(f"ERROR: {e}")
                            break
                        if html:
                            try:
                                traders_web_info = self.parse_traders_web(html, company_code, company_name, year)
                                print(f"{traders_web_info['コード']}: {traders_web_info['企業名']}")

                                if error_count >= 1:
                                    print(f"Successed to get one-time errored company ({company_code}, {company_name})")
                                is_success = True
                            except ValueError as e:
                                if error_count == 0:
                                    company_code, company_name = self.traders_scraper_settings.check_format_company(company_code, company_name)
                                else:
                                    print(f"ERROR: {e}")
                                error_count += 1
                    if traders_web_info:
                        company_data_list.append(traders_web_info)
    
    
            # 年ごとのデータを1つのTSVにまとめて保存
            self.save_to_tsv(company_data_list, output_file)
    
        sorted_shareholders_df = self.shareholders_df.sort_values(by='count', ascending=False)
        meta_output_file = os.path.join(self.traders_scraper_settings.meta_dir, 'shareholder_summary.tsv')
        sorted_shareholders_df.to_csv(meta_output_file, sep='\t', index=False)
        
        shareholder_notes_file = os.path.join(self.traders_scraper_settings.meta_dir, 'shareholder_notes_dict.tsv')
        self.shareholders_notes_df.to_csv(shareholder_notes_file, sep='\t', index=False)

        shareholder_notes_file = os.path.join(self.traders_scraper_settings.meta_dir, 'shareholder_notes.tsv')
        shareholders_notes_df = self.shareholders_notes_df.drop(columns=['shareholder_name'])
        shareholders_notes_df.to_csv(shareholder_notes_file, sep='\t', index=False)

if __name__ == "__main__":
    analyzer = IPOTradersAnalyzer()
    analyzer.run()