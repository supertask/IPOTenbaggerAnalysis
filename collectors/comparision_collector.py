import json
import time
import random
import os
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

from collectors.ipo_analyzer_core import IPOAnalyzerCore
from collectors.settings import ComparisonCollectorSettings

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/118.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/118.0"
]

DEVICES = [
    {"viewport": {"width": 1920, "height": 1080}, "device_scale_factor": 1, "is_mobile": False},
    {"viewport": {"width": 1366, "height": 768}, "device_scale_factor": 1, "is_mobile": False},
    {"viewport": {"width": 1536, "height": 864}, "device_scale_factor": 1.25, "is_mobile": False}
]


class ComparisonCollector(IPOAnalyzerCore):
    def __init__(self):
        super().__init__()
        self.is_debug = False
        self.base_url = "https://shikiho.toyokeizai.net/stocks/%s"
        self.comparison_settings = ComparisonCollectorSettings()
        self.cache_file = os.path.join(self.comparison_settings.cache_dir, 'comparison_cache.json')
        self.comparison_cache = self.load_cache()

    def load_cache(self):
        if os.path.exists(self.cache_file):
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_cache(self):
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.comparison_cache, f, ensure_ascii=False, indent=4)

    def playwright_comparisons(self, company_code):
        if company_code in self.comparison_cache and self.comparison_cache[company_code]:
            if self.is_debug:
                print(f"✅ キャッシュヒット: {company_code}")
            return self.comparison_cache[company_code]

        comparison_companies = []        
        with sync_playwright() as p:
            random_user_agent = random.choice(USER_AGENTS)
            random_device = random.choice(DEVICES)

            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_viewport_size(random_device["viewport"])
            page.evaluate("() => { Object.defineProperty(navigator, 'webdriver', { get: () => false }) }")

            #stealth_sync(page)

            target_url = self.base_url % company_code
            response = page.goto(target_url)
            page.wait_for_timeout(10_000)

            # HTTPレスポンスが404ならスキップ
            if (response and response.status == 404) or page.locator("text=ページが見つかりません").count() > 0:
                if self.is_debug:
                    print(f"⚠️ {company_code} のページが404または存在しません。")
                browser.close()
                self.comparison_cache[company_code] = None
                return None

            # Wait for the comparison companies section to load
            try:
                page.wait_for_selector(".rivals__items", timeout=5000)
                comparison_section = page.locator(".rivals__items")
                company_items = comparison_section.locator(".rivals__items__item")

                for i in range(company_items.count()):
                    item = company_items.nth(i)
                    code = item.locator("span").nth(0).inner_text().strip()
                    name = item.locator("span").nth(1).inner_text().strip()
                    comparison_companies.append({"code": code, "name": name})
            except:
                print(f"⚠️ {company_code} の競合情報が取得できませんでした。スキップします。")
            
            browser.close()

        # 空のリストの場合はキャッシュに保存しない
        if comparison_companies:
            self.comparison_cache[company_code] = comparison_companies
            self.save_cache()

        time.sleep(random.uniform(3, 15))

        return comparison_companies

    def on_each_company(self, year, company_code, company_name, ipo_info_url):
        row_dict = {'コード': company_code, '企業名': company_name}  # コードと会社名を最初に追加
        comparison_companies = self.playwright_comparisons(company_code)

        if comparison_companies:
            row_dict['競合リスト'] = json.dumps(comparison_companies, ensure_ascii=False)
        else:
            row_dict['競合リスト'] = ""
        
        return row_dict

    def run(self):
        self.save_companies_info_to_tsv(self.comparison_settings.output_dir, self.on_each_company,
            skip_years=[2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023])
        #self.combine_all_files(self.comparison_settings.output_dir)

    def save_to_json(self, filename="companies.json"):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.companies, f, ensure_ascii=False, indent=4)
        print(f"Data successfully scraped and saved to {filename}")

if __name__ == "__main__":
    scraper = ComparisonCollector()
    scraper.run()
