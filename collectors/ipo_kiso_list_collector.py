import os
import requests
from bs4 import BeautifulSoup
import csv
import re
from collectors.settings import GeneralSettings, KisoScraperSettings

class IPOKisoListCollector:
    def __init__(self):
        self.general_settings = GeneralSettings()
        self.kiso_scraper_settings = KisoScraperSettings()
        self.years = self.kiso_scraper_settings.years
        self.base_url = self.kiso_scraper_settings.base_url

    def correct_company(self, company_code, company_name):
        if company_name in self.kiso_scraper_settings.kiso_mistake_companies:
            mistake = self.kiso_scraper_settings.kiso_mistake_companies[company_name]
            if mistake['wrong']['code'] == company_code:
                return mistake['correct']['code'], mistake['correct']['name']
            if mistake['wrong']['name'] == company_name:
                return mistake['correct']['code'], mistake['correct']['name']
        return company_code, company_name

    def get_company_data_from_2018(self, soup):
        tables = soup.find_all('table')
        company_data = []
        for table in tables:
            for row in table.find_all('tr'):
                columns = row.find_all('td')
                if len(columns) > 0:
                    company_column = columns[0]
                    company_info = company_column.text.strip()
                    if company_info:
                        company_name = re.split(r'\n|\（|\）', company_info)[0].strip()
                        company_code = re.search(r'[\(（](.*?)[\)）]', company_info)
                        company_code = company_code.group(1) if company_code else ''
                        company_a_tags = company_column.find_all('a')
                        if company_a_tags:
                            company_a_tag = company_a_tags[0]
                            company_name = company_a_tag.get_text(separator='', strip=True)
                            company_url = company_a_tag['href']
                            company_code, company_name = self.correct_company(company_code, company_name)
                            company_data.append([company_name, company_code, company_url])
        return company_data

    def get_company_data_before_2018(self, soup):
        tables = soup.find_all('table')
        company_data = []
        for table in tables:
            for row in table.find_all('tr'):
                columns = row.find_all('td')
                if len(columns) > 0:
                    company_column = columns[1]
                    company_code_column = columns[2]
                    company_info = company_column.text.strip()
                    if company_info:
                        company_code_match = re.search(r'[\(（](\d{3}[0-9A-Z])[\)）]', company_info)
                        if company_code_match:
                            company_code = company_code_match.group(1)
                        else:
                            company_code = company_code_column.text.strip()
                        company_a_tags = company_column.find_all('a')
                        if company_a_tags:
                            company_a_tag = company_a_tags[0]
                            company_name = company_a_tag.get_text(separator='', strip=True)
                            company_url = company_a_tag['href']
                            company_code, company_name = self.correct_company(company_code, company_name)
                            company_data.append([company_name, company_code, company_url])
        return company_data

    def run(self):
        for year in self.years:
            url = f"{self.base_url}/company/" if year == self.kiso_scraper_settings.this_year else f"{self.base_url}/company/{year}.html"
            response = requests.get(url)
            html = response.content
            soup = BeautifulSoup(html, 'html.parser')
            if year >= 2018:
                company_data = self.get_company_data_from_2018(soup)
            else:
                company_data = self.get_company_data_before_2018(soup)
            output_dir = self.kiso_scraper_settings.kiso_list_output_dir
            os.makedirs(output_dir, exist_ok=True)
            file_name = os.path.join(output_dir, f'companies_{year}.tsv')
            with open(file_name, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file, delimiter='\t')
                writer.writerow(['企業名', 'コード', 'URL'])
                writer.writerows(company_data)
            print(f"{year}年のデータの取得と書き込みが完了しました。")

if __name__ == "__main__":
    collector = IPOKisoListCollector()
    collector.run()

