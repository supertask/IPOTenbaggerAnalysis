import os
import csv
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import pickle

from collectors.settings import GeneralSettings, YFinanceScraperSettings
from collectors.ipo_analyzer_core import IPOAnalyzerCore

class IPOYFinanceAnalyzer(IPOAnalyzerCore):
    def __init__(self):
        super().__init__()
        self.general_settings = GeneralSettings()
        self.yfinance_settings = YFinanceScraperSettings()
        self.stock_volume_duration_month = 3
        os.makedirs(self.yfinance_settings.cache_dir, exist_ok=True)
        self.cache_data = {}

    def get_cache_path(self, year):
        """特定の年のキャッシュファイルパスを取得"""
        return os.path.join(self.yfinance_settings.cache_dir, f"stock_history_cache_{year}.pkl")

    def load_cache_for_year(self, year):
        """特定の年のキャッシュをロード"""
        cache_path = self.get_cache_path(year)
        if os.path.exists(cache_path):
            with open(cache_path, 'rb') as f:
                return pickle.load(f)
        return {}

    def save_cache_for_year(self, year):
        """特定の年のキャッシュを保存"""
        cache_path = self.get_cache_path(year)
        with open(cache_path, 'wb') as f:
            pickle.dump(self.cache_data, f)

    def calculate_bagger_years(self, daily_quotes, buy_date, buy_price, n_times):
        """Calculate years to achieve N-bagger."""
        bagger_obj = next((row for row in daily_quotes if row['Close'] >= buy_price * n_times), None)
        if bagger_obj:
            bagger_date = pd.to_datetime(bagger_obj['Date'])  # ここで日付を適切に変換
            delta_years = (bagger_date - buy_date).days / 365.0
            return round(delta_years, 2)
        return "None"

    def get_history(self, code):
        symbol = code + ".T"
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="max")
        if hist.empty:
            raise ValueError(f"No historical data for {symbol}")

        hist.reset_index(inplace=True)
        hist['Date'] = pd.to_datetime(hist['Date'], errors='coerce')
        hist['Date'] = hist['Date'].dt.strftime('%Y-%m-%d')     
        return ticker, hist

    def get_company_data(self, code, year):
        """キャッシュまたはyfinanceからデータを取得（年単位で管理）"""
        # キャッシュを年単位でロード
        if not self.cache_data:
            self.cache_data = self.load_cache_for_year(year)

        # キャッシュ確認
        if code in self.cache_data:
            hist_data = pd.DataFrame(self.cache_data[code])
            oldest_date = hist_data['Date'].min()
            end_date = (pd.to_datetime(oldest_date) + timedelta(days=self.stock_volume_duration_month * 30)).strftime('%Y-%m-%d')
            one_month_data = hist_data[(hist_data['Date'] >= oldest_date) & (hist_data['Date'] <= end_date)]
            total_volume = one_month_data['Volume'].sum()

            sector = hist_data['Sector'].iloc[0] if 'Sector' in hist_data.columns else "Unknown"
            industry = hist_data['Industry'].iloc[0] if 'Industry' in hist_data.columns else "Unknown"
            sector = self.general_settings.sector_dict.get(sector, sector)
            industry = self.general_settings.industry_dict.get(industry, industry)

            return sector, industry, total_volume

        # yfinanceからデータを取得
        try:
            ticker, hist = self.get_history(code)
            ticker_info = ticker.info
            sector = ticker_info.get('sector', 'Unknown')
            industry = ticker_info.get('industry', 'Unknown')
            sector = self.general_settings.sector_dict.get(sector, sector)
            industry = self.general_settings.industry_dict.get(industry, industry)
            hist['Sector'] = sector
            hist['Industry'] = industry

            # キャッシュに保存
            self.cache_data[code] = hist.to_dict('records')
            self.save_cache_for_year(year)

            return self.get_company_data(code, year)
        except Exception as e:
            print(f"Error retrieving data for {code}: {e}")
            return "", "", -1

    def get_n_bagger_info(self, code, year, start_date='1900-01-01'):
        """Calculate bagger information with year-based caching."""
        # キャッシュをロード
        if not self.cache_data:
            self.cache_data = self.load_cache_for_year(year)

        # キャッシュ確認
        if code in self.cache_data:
            hist = pd.DataFrame(self.cache_data[code])
        else:
            # yfinanceからデータを取得
            try:
                _, hist = self.get_history(code)

                # キャッシュに保存
                self.cache_data[code] = hist.to_dict('records')
                self.save_cache_for_year(year)
            except Exception as e:
                print(f"Error retrieving data for {code}: {e}")
                return None

        # N倍株計算ロジック
        try:
            hist['Date'] = pd.to_datetime(hist['Date'])
            hist_first_year = hist[hist['Date'] <= (hist['Date'].iloc[0] + timedelta(days=365))]
            min_price_row = hist_first_year.loc[hist_first_year['Close'].idxmin()]
            buy_price = min_price_row['Close']
            buy_date = min_price_row['Date']

            three_bagger_years = self.calculate_bagger_years(hist.to_dict('records'), buy_date, buy_price, 3)
            five_bagger_years = self.calculate_bagger_years(hist.to_dict('records'), buy_date, buy_price, 5)
            seven_bagger_years = self.calculate_bagger_years(hist.to_dict('records'), buy_date, buy_price, 7)
            ten_bagger_years = self.calculate_bagger_years(hist.to_dict('records'), buy_date, buy_price, 10)

            max_price_row = hist.loc[hist['Close'].idxmax()]
            max_n_bagger = round(max_price_row['Close'] / buy_price, 1)
            max_n_bagger_years = round((max_price_row['Date'] - buy_date).days / 365.0, 2)

            current_n_bagger = round(hist['Close'].iloc[-1] / buy_price, 1)

            return {
                "Current_N_Bagger": current_n_bagger,
                "Max_N_Bagger": max_n_bagger,
                "Years_to_3_Bagger": three_bagger_years,
                "Years_to_5_Bagger": five_bagger_years,
                "Years_to_7_Bagger": seven_bagger_years,
                "Years_to_10_Bagger": ten_bagger_years,
                "Max_N_Bagger_Years": max_n_bagger_years,
            }
        except Exception as e:
            print(f"Error retrieving bagger data for {code}: {e}")
            return None


    def get_finance(self, company_code, company_name, year):
        data = {'コード': company_code, '企業名': company_name}  # コードと会社名を最初に追加
        try:
            sector, industry,total_volume = self.get_company_data(company_code, year) #yfinanceから業種を取得
        except ValueError as e:
            sector, industry = "", ""
        data["sector"] = sector
        data["industry"] = industry
        data["上場後の取引量"] = total_volume

        baggers = self.get_n_bagger_info(company_code, year)
        if baggers:
            data['現在何倍株'] = baggers["Current_N_Bagger"]
            data['最大何倍株'] = baggers["Max_N_Bagger"]
            data['3,5,7,10,N倍まで何年'] = f"{baggers['Years_to_3_Bagger']}\n{baggers['Years_to_5_Bagger']}\n{baggers['Years_to_7_Bagger']}\n{baggers['Years_to_10_Bagger']}\n{baggers['Max_N_Bagger_Years']}" 
        else:
            data['現在何倍株'] = None
            data['最大何倍株'] = None
            data['3,5,7,10,N倍まで何年'] = None

        return data

    def run(self):
        for year in self.yfinance_settings.years:
            # DEBUG: 特定の年をデバッグする用
            #if not year in [2011]: continue
            print("year:", year)

            input_file = os.path.join(self.yfinance_settings.input_dir, f'companies_{year}.tsv')
            output_file = os.path.join(self.yfinance_settings.output_dir, f'companies_{year}.tsv')
            os.makedirs(self.yfinance_settings.output_dir, exist_ok=True)
            
            self.cache_data = self.load_cache_for_year(year)  # 年ごとのキャッシュをロード

            company_data_list = []  # 年ごとのすべての会社データを保持するリスト
            with open(input_file, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file, delimiter='\t')
                for row in reader:
                    company_code = row['コード']
                    company_name = row['企業名']

                    data = self.get_finance(company_code, company_name, year)
                    company_data_list.append(data)

            # 年ごとのデータを1つのTSVにまとめて保存
            self.save_to_tsv(company_data_list, output_file)

        # すべての年のファイルを結合
        self.combine_all_files(self.yfinance_settings.output_dir)
        

if __name__ == "__main__":
    analyzer = IPOYFinanceAnalyzer()
    analyzer.run()