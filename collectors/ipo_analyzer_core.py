import os
import csv
from collectors.settings import GeneralSettings, ScraperSettings
from tqdm import tqdm
import pandas as pd


class IPOAnalyzerCore:
    def __init__(self):
        self.scraper_settings = ScraperSettings()
    
    def save_to_tsv(self,data_list, output_path):
        """
        年ごとのTSVファイルに全ての会社データをまとめて書き込む。
        :param data_list: 会社データのリスト（各データは辞書）
        :param output_path: TSVファイルの出力パス
        """
        with open(output_path, 'w', encoding='utf-8', newline='') as file:
            writer = csv.writer(file, delimiter='\t')
            # ヘッダーを1回だけ書き込む
            if data_list:
                writer.writerow(data_list[0].keys())
            # 各会社のデータを1行ずつ書き込む
            for data in data_list:
                writer.writerow(data.values())
                
        
    def save_companies_info_to_tsv(self, output_dir, on_each_company, skip_years = []):
        os.makedirs(output_dir, exist_ok=True)

        for year in self.scraper_settings.years:
            # DEBUG: 特定の年をデバッグする用
            if year in skip_years: continue
            print(f"Process on {year}")
            input_file = os.path.join(self.scraper_settings.kiso_list_output_dir, f'companies_{year}.tsv')
            output_file = os.path.join(output_dir, f'companies_{year}.tsv')
            company_data_list = []

            with open(input_file, 'r', encoding='utf-8') as infile, open(output_file, 'w', newline='', encoding='utf-8') as outfile:
                reader = csv.reader(infile, delimiter='\t')
                next(reader) # headerをスキップ
                
                rows = list(reader)
                for index, row in enumerate(tqdm(rows, desc="Processing")):
                    if len(row) == 3:
                        company_name, company_code, ipo_info_url = row
                        company_data = on_each_company(year, company_code, company_name, ipo_info_url)
                        if company_data:
                            company_data_list.append(company_data)

            # 年ごとのデータを1つのTSVにまとめて保存
            self.save_to_tsv(company_data_list, output_file)


    def combine_all_files(self, output_dir):
        """
        設定されたすべての年のCSVファイルを結合する
        """
        combined_df = pd.DataFrame()
        for year in self.scraper_settings.years:
            input_file = os.path.join(output_dir, f'companies_{year}.tsv')
            if os.path.exists(input_file):
                try:
                    df = pd.read_csv(input_file, delimiter='\t')
                    combined_df = pd.concat([combined_df, df], ignore_index=True)
                except pd.errors.ParserError as e:
                    print(f"Error parsing {input_file}: {e}")
        if not combined_df.empty:
            output_file = os.path.join(output_dir, 'all_companies.tsv')
            combined_df.to_csv(output_file, sep='\t', index=False)