import json
import time
import random
import os
from datetime import datetime, timedelta
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
        self.fetched_at_file = os.path.join(self.comparison_settings.cache_dir,
                                            'comparison_fetched_at.json')
        self.comparison_cache = self.load_cache()
        self.fetched_at = self.load_fetched_at()

    def load_cache(self):
        if os.path.exists(self.cache_file):
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_cache(self):
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.comparison_cache, f, ensure_ascii=False, indent=4)
        self.save_fetched_at()

    def load_fetched_at(self):
        """いつ取ったか。キャッシュ本体とは別ファイルにして、
        既存の comparison_cache.json の形（{コード: [競合]}）を変えない"""
        if os.path.exists(self.fetched_at_file):
            with open(self.fetched_at_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_fetched_at(self):
        with open(self.fetched_at_file, 'w', encoding='utf-8') as f:
            json.dump(self.fetched_at, f, ensure_ascii=False, indent=4,
                      sort_keys=True)

    def stale_codes(self, codes, days):
        """取得から days 日以上たった銘柄。取得日の記録が無いものも古い扱い。

        記録を始めたのが2026年8月なので、それ以前に取ったぶんは
        いつ取ったか分からない。分からないものは取り直す側に倒す"""
        limit = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return {c for c in codes if self.fetched_at.get(c, "") < limit}

    def playwright_comparisons(self, company_code, refresh=False):
        # 四季報側は比較企業を入れ替える。一度取れたら二度と見に行かないので
        # 古いまま残る。デジタルグリッド(350A)は上場直後に取った
        # レジル・GMOペイ・ラクスルのままだったが、いまはグリムス・GMOペイ・
        # Eチェンジに変わっていた（ラクスルは印刷のECで土俵が違う）
        if (not refresh and company_code in self.comparison_cache
                and self.comparison_cache[company_code]):
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
            self.fetched_at[company_code] = datetime.now().strftime("%Y-%m-%d")
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
            skip_years=[2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024])
        #self.combine_all_files(self.comparison_settings.output_dir)

    def refresh(self, codes):
        """指定した銘柄だけ、キャッシュを無視して取り直す。

        比較企業は四季報側が入れ替えるので、保有銘柄は定期的に取り直す。
        全1,150社を回すと1銘柄あたり10秒待ち＋3〜15秒のランダム待機で
        6時間を超えるため、対象を絞って使う。
        """
        changed = []
        for i, code in enumerate(sorted(codes), 1):
            before = self.comparison_cache.get(code)
            after = self.playwright_comparisons(code, refresh=True)
            names = lambda x: [c.get("name") for c in (x or [])]
            if names(before) != names(after):
                changed.append((code, names(before), names(after)))
                print(f"  変わった {code}: {names(before)} → {names(after)}")
            if i % 5 == 0:
                print(f"  {i}/{len(codes)}銘柄")
        self.save_cache()
        print(f"\n{len(codes)}銘柄を取り直し、{len(changed)}銘柄で比較企業が変わりました")
        return changed

    def save_to_json(self, filename="companies.json"):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.companies, f, ensure_ascii=False, indent=4)
        print(f"Data successfully scraped and saved to {filename}")

if __name__ == "__main__":
    scraper = ComparisonCollector()
    scraper.run()
