import sys
import time
import random
import traceback
import os
import re
import glob
import requests
import zipfile
import csv
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright

class TDnetDisclosureScraper:
    def __init__(self):
        self.ipo_years = self.get_ipo_years()
        self.ipo_tsv_path = f"data/output/kiso_urls/companies_%s.tsv"
        self.output_dir = "data/output/tdnet"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        self.playwright = None
        self.browser = None
        self.page = None

    def init_playwright(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=False)
        self.page = self.browser.new_page()
        
        # User Agentを設定
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
        ]
        random_user_agent = random.choice(user_agents)
        self.page.set_extra_http_headers({"User-Agent": random_user_agent})

    def get_ipo_years(self):
        tsv_files = glob.glob("data/output/kiso_urls/companies_*.tsv")
        ipo_years = [re.search(r'companies_(.+)\.tsv', file).group(1) for file in tsv_files]
        return ipo_years

    def scrape_disclosure_history(self, company_code):
        table_rows = []
        
        # 適時開示（決算情報、決定事実）を取得
        kaiji_partial_id = 'closeUpKaiJi'
        elements = self.page.locator(f"[id*='{kaiji_partial_id}']")
        if elements.count() == 0:
            print(f"No elements. company_code = {company_code}")
            return table_rows
        table_pair_ids = self.get_table_pair_ids(elements)
    
        # [決算情報], Table ID 'closeUpKaiJi0_open'
        if len(table_pair_ids) > 0:
            kessan_info_ids = table_pair_ids[0]
            rows = self.scrape_table(company_code, kessan_info_ids[0], kessan_info_ids[1], '決算情報')
            table_rows += self.get_table_rows(company_code, rows)

        # [決定事実 / 発生事実], Table ID 'closeUpKaiJi117_open'
        if len(table_pair_ids) > 1:
            kettei_info_ids = table_pair_ids[1]
            rows = self.scrape_table(company_code, kettei_info_ids[0], kettei_info_ids[1], '決定事実')
            table_rows += self.get_table_rows(company_code, rows)

        # [その他] （事業計画及び成長可能性に関する事項）
        if len(table_pair_ids) > 3:
            other_ids = table_pair_ids[3]
            rows = self.scrape_table(company_code, other_ids[0], other_ids[1], 'その他')
            table_rows += self.get_table_rows(company_code, rows)

        return table_rows

    def get_table_pair_ids(self, elements):
        table_ids = []
        for i in range(elements.count()):
            element = elements.nth(i)
            id_str = element.get_attribute('id')
            if id_str and id_str.endswith("_open"):
                open_id_str = id_str
                close_id_str = id_str.split("_")[0]
                table_ids.append([open_id_str, close_id_str])
        return table_ids

    def go_to_table_page(self, company_code):
        try:
            self.page.goto('https://www2.jpx.co.jp/tseHpFront/JJK010010Action.do')
            time.sleep(random.uniform(2.0, 2.5))

            code_input = self.page.locator('input[name="eqMgrCd"]')
            code_input.fill(company_code)
            time.sleep(random.uniform(0.2, 0.3))

            search_button = self.page.locator('input[name="searchButton"]')
            search_button.click()
            time.sleep(random.uniform(2.0, 2.4))

            detail_button = self.page.locator('input[name="detail_button"]')
            detail_button.click()
            time.sleep(random.uniform(0.6, 0.8))

            # 最初の「適時開示情報」リンクを選択
            disclosure_tab = self.page.locator('a:has-text("適時開示情報")').nth(0)
            disclosure_tab.click()
            time.sleep(random.uniform(0.6, 0.8))
            return True 

        except Exception as e:
            print(f"ERROR OCCURED: {e}")
            traceback.print_exc()
            return False

    def scrape_table(self, company_code, closed_table_id, opened_table_id, doc_type):
        try:
            time.sleep(random.uniform(1.6, 2))

            info_table = self.page.locator(f'#{closed_table_id}')
            info_button = info_table.locator('input[type="button"][value="情報を閲覧する場合はこちら"]')
            info_button.click()

            time.sleep(random.uniform(1.6, 2))
            
            disclosure_table = self.page.locator(f'#{opened_table_id}')
            
            # さらに表示ボタンがあるかチェック
            more_info_button = disclosure_table.locator('input[type="button"][value="さらに表示"]')
            if more_info_button.count() > 0:
                more_info_button.click()
                time.sleep(random.uniform(1.6, 2))
                print(f"Finished to click 「{doc_type}」 の「さらに表示する」: {company_code}")

            rows = disclosure_table.locator('tr').all()
            print(f"Finished to get table 「{doc_type}」 rows: {company_code}")
            return rows
        except Exception as e:
            print(f"ERROR OCCURED: {e}")
            traceback.print_exc()
            return []
            
    def convert_date_format_revised(self, date_str):
        match = re.match(r'(\d{4})/(\d{1,2})/(\d{1,2})', date_str)
        if match:
            year, month, day = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        return None

    def get_table_rows(self, company_code, rows, start_row_index=2, column_num=4):
        if len(rows) < 3:
            print("No disclosure information available.")
            return []
        
        table_rows = []
        for row in rows[start_row_index:]:  # Skipping header rows
            cols = row.locator('td').all()
            
            if len(cols) < column_num:
                continue

            raw_date = cols[0].inner_text().strip()

            if raw_date == "-":
                break
            
            # リンクエレメントを取得
            link_elements = row.locator('a').all()
            if len(link_elements) == 0:
                print(f"No <a> element found in row: {row.inner_text()}")
                continue
                
            link_element = link_elements[0]
            title = link_element.inner_text().strip()
            date = self.convert_date_format_revised(raw_date)
            url = link_element.get_attribute("href").strip()

            record = [date, '00:00', company_code, title, url]
            table_rows.append(record)

        return table_rows

    def get_existing_companies(self, ipo_year):
        """既にスクレイピング済みの企業コードを取得"""
        disclosure_file = os.path.join(self.output_dir, f"disclosures_{ipo_year}.tsv")
        existing_companies = set()
        if os.path.exists(disclosure_file):
            with open(disclosure_file, "r", encoding='utf-8') as file:
                for line in file:
                    parts = line.strip().split('\t')
                    if len(parts) >= 4:  # 日付、時刻、企業名、企業コードの順
                        company_code = parts[3]  # 企業コードは4列目
                        existing_companies.add(company_code)
        return existing_companies

    def get_existing_disclosures(self, ipo_year):
        """既存の開示情報を取得（重複チェック用）"""
        disclosure_file = os.path.join(self.output_dir, f"disclosures_{ipo_year}.tsv")
        existing_disclosures = set()
        if os.path.exists(disclosure_file):
            with open(disclosure_file, "r", encoding='utf-8') as file:
                for line in file:
                    parts = line.strip().split('\t')
                    if len(parts) >= 6:  # 日付、時刻、企業名、企業コード、タイトル、URLの順
                        # 日付+企業コード+タイトルの組み合わせで重複判定
                        key = f"{parts[0]}|{parts[3]}|{parts[4]}"
                        existing_disclosures.add(key)
        return existing_disclosures

    def scrape_and_save(self):
        for ipo_year in self.ipo_years:
            companies = self.read_companies(self.ipo_tsv_path % ipo_year)
            self.disclosure_tsv_path = os.path.join(self.output_dir, f"disclosures_{ipo_year}.tsv")
            
            # 既存の企業コードを取得
            existing_companies = self.get_existing_companies(ipo_year)
            print(f"Year {ipo_year}: {len(existing_companies)} companies already scraped")

            for index, company in enumerate(companies):
                code, name = company
                
                # 既に同じ企業がスクレイピング済みの場合はスキップ
                if code in existing_companies:
                    print(f"Skipping {code} ({name}) - already scraped")
                    continue
                    
                self.scrape_disclosure(index, code, name, ipo_year)

    def scrape_disclosure(self, index, code, name, ipo_year):
        self.init_playwright()

        try:
            print(f"Scraping: index = {index}, code = {code}, company name = {name}")
            found_results = self.go_to_table_page(code)
            if found_results:
                table_rows = self.scrape_disclosure_history(code)
                if table_rows:
                    for row in table_rows:
                        row.insert(2, name)  # 会社名をコードの後に挿入
                    print(f"Found {len(table_rows)} disclosures for {code}")
                    self.save_disclosures(table_rows, ipo_year)  # 年度を渡す
        except Exception as e:
            if "503" in str(e):
                print(f"HTTP 503 Error encountered at index {index}. Exiting.")
                self.save_last_index(index)
                sys.exit(1)
            else:
                print(f"Error: {e}")
        finally:
            self.close_playwright()

    def read_companies(self, filepath):
        companies = []
        with open(filepath, "r", encoding='utf-8') as file:
            reader = csv.DictReader(file, delimiter='\t')
            for row in reader:
                if row['企業名'] and row['コード']:
                    companies.append([row['コード'], row['企業名']])
        return companies

    def save_disclosures(self, disclosures, ipo_year):
        """重複チェックして新しい開示情報のみ保存"""
        # 既存の開示情報を取得
        existing_disclosures = self.get_existing_disclosures(ipo_year)
        
        new_disclosures = []
        for disclosure in disclosures:
            if len(disclosure) >= 6:  # 日付、時刻、企業名、企業コード、タイトル、URL
                # 日付+企業コード+タイトルの組み合わせで重複判定
                key = f"{disclosure[0]}|{disclosure[3]}|{disclosure[4]}"
                if key not in existing_disclosures:
                    new_disclosures.append(disclosure)
                else:
                    print(f"Skipping duplicate disclosure: {disclosure[4][:50]}...")
        
        if new_disclosures:
            with open(self.disclosure_tsv_path, "a", encoding='utf-8') as file:
                for disclosure in new_disclosures:
                    file.write("\t".join(disclosure) + "\n")
            print(f"Saved {len(new_disclosures)} new disclosures (skipped {len(disclosures) - len(new_disclosures)} duplicates)")
        else:
            print("No new disclosures to save")

    def save_last_index(self, index):
        with open("etc/tmp/last_index.txt", "w") as file:
            file.write(str(index))

    def close_playwright(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def close(self):
        self.close_playwright()

if __name__ == "__main__":
    scraper = TDnetDisclosureScraper()
    scraper.scrape_and_save()