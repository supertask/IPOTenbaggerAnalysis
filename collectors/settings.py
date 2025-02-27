from datetime import datetime
import os
import pandas as pd
from collectors.edinet_report_downloader import EdinetReportDownloader

class GeneralSettings:
    def __init__(self):
        self.sector_dict = {
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
            "Utilities": "公共事業"
        }
        
        self.industry_dict = {
            "Auto & Truck Dealerships": "自動車・トラック販売",
            "Lodging": "宿泊施設",
            "Waste Management": "廃棄物管理",
            "Chemicals": "化学製品",
            "Education & Training Services": "教育・訓練サービス",
            "Travel Services": "旅行サービス",
            "Consulting Services": "コンサルティングサービス",
            "Mortgage Finance": "住宅ローン金融",
            "Apparel Manufacturing": "衣料品製造",
            "Integrated Freight & Logistics": "統合貨物・物流",
            "Furnishings, Fixtures & Appliances": "家具、備品、家電",
            "Lumber & Wood Production": "木材・木製品生産",
            "REIT - Specialty": "REIT - 特殊",
            "Specialty Business Services": "専門ビジネスサービス",
            "Software - Application": "ソフトウェア - アプリケーション",
            "Semiconductors": "半導体",
            "Food Distribution": "食品流通",
            "Leisure": "レジャー",
            "Software - Infrastructure": "ソフトウェア - インフラストラクチャ",
            "REIT - Industrial": "REIT - 産業",
            "Conglomerates": "コングロマリット",
            "Communication Equipment": "通信機器",
            "Real Estate - Development": "不動産開発",
            "Luxury Goods": "高級品",
            "Electronic Gaming & Multimedia": "電子ゲーム・マルチメディア",
            "Advertising Agencies": "広告代理店",
            "Specialty Chemicals": "特殊化学品",
            "Business Equipment & Supplies": "業務用機器・用品",
            "Consumer Electronics": "コンシューマーエレクトロニクス",
            "Pharmaceuticals - Specialty & Generic": "医薬品 - 専門・ジェネリック",
            "Health Information Services": "健康情報サービス",
            "Specialty Retail": "専門小売",
            "Utilities - Renewable": "再生可能エネルギー",
            "Engineering & Construction": "工学・建設",
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
            "Telecom Services": "電気通信サービス",
            "Drug Manufacturers - Specialty & Generic": "医薬品メーカー - 専門・ジェネリック",
            "Internet Content & Information": "インターネットコンテンツ・情報",
            "Tools & Accessories": "ツール・アクセサリー",
            "Information Technology Services": "情報技術サービス",
            "REIT - Hotel & Motel": "REIT - ホテル・モーテル",
            "Credit Services": "信用サービス",
            "Banks - Regional": "銀行 - 地域",
            "Insurance - Life": "保険 - 生命",
            "Restaurants": "レストラン",
            "Biotechnology": "バイオテクノロジー",
            "Publishing": "出版",
            "Internet Retail": "インターネット小売",
            "Apparel Retail": "衣料品小売",
            "Building Materials": "建材",
            "Packaged Foods": "包装食品",
            "REIT - Residential": "REIT - 住宅",
            "Oil & Gas Refining & Marketing": "石油・ガス精製・販売",
            "Medical Instruments & Supplies": "医療機器・用品",
            "Specialty Industrial Machinery": "特殊産業機械",
            "Electronic Components": "電子部品",
            "Staffing & Employment Services": "人材派遣・雇用サービス",
            "REIT - Diversified": "REIT - 多様化",
            "Resorts & Casinos": "リゾート・カジノ",
            "Electronics & Computer Distribution": "電子機器・コンピュータ流通",
            "Residential Construction": "住宅建設",
            "REIT - Healthcare Facilities": "REIT - 医療施設",
            "Farm Products": "農産物",
            "Asset Management": "資産運用",
            "Real Estate - Diversified": "不動産 - 多様化",
            "Footwear & Accessories": "フットウェア＆アクセサリー",
            "Railroads": "鉄道",
            "Medical Care Facilities": "医療施設",
            "Capital Markets": "資本市場",
            "Grocery Stores": "食料品店",
            "Telecommunication Services": "電気通信サービス",
            "Computer Hardware": "コンピュータハードウェア",
            "Department Stores": "百貨店",
            "Insurance - Diversified": "多様化保険",
            "Paper & Paper Products": "紙・紙製品",
            "Metal Fabrication": "金属製造",
            "Medical Distribution": "医療流通",
            "Packaging & Containers": "包装および容器",
            "Rental & Leasing Services": "レンタルおよびリースサービス",
            "Security & Protection Services": "セキュリティおよび保護サービス",
            "Specialty Business Services": "専門ビジネスサービス",
            "Medical Devices & Supplies": "医療機器・用品",
            "REIT - Retail": "REIT - 小売",
            "REIT - Office": "REIT - オフィス"
        }
        self.locale_settings = 'en_US.UTF-8'
        
        
    
class ScraperSettings:
    def __init__(self):
        self.is_debug = False
        # 年度設定
        self.this_year = datetime.now().year
        self.begin_year = 2011
        self.end_year = 2024
        #self.end_year = self.this_year
        self.years = range(self.begin_year, self.end_year + 1)
        self.out_dir_core = os.path.join('data', 'output')
        self.cache_dir_core = os.path.join('data', 'cache')
        self.meta_dir = os.path.join('data', 'meta')
        self.kiso_list_output_dir = os.path.join(self.out_dir_core, 'kiso_urls')

        #NOTE: EDINETから情報取得しているので買収などあったIPOはコードが変わってしまうことがあり、それでも情報取得したい場合は使う
        self.code4_to_company = self._save_company_codes()


    def _save_code4_to_company(self, data, output_path):
        code4_to_company = {code[:-1]: details['company_name'] for code, details in data.items()}
        df = pd.DataFrame(list(code4_to_company.items()), columns=['code', 'company_name'])
        df.to_csv(output_path, sep='\t', index=False)
        return code4_to_company

    def _save_company_codes(self):
        edinet_collector = EdinetReportDownloader()
        code5_to_edinet_dict, edinet_to_company_dict = edinet_collector.download_and_extract_edinet_zip()
        #print(self.meta_dir)
        os.makedirs(self.meta_dir, exist_ok=True)
        code4_to_company = self._save_code4_to_company(code5_to_edinet_dict, os.path.join(self.meta_dir, 'code4_to_company.tsv'))
        return code4_to_company

    def check_format_company(self, kiso_company_code, kiso_company_name):
        for edinet_compnay_code4, edinet_company_name in self.code4_to_company.items():
            if kiso_company_name in edinet_company_name:
                if kiso_company_code == edinet_compnay_code4:
                    return kiso_company_code, edinet_company_name
                else:
                    print(f"edinet_compnay({edinet_compnay_code4}, {edinet_company_name}) does not equal to IPO Kiso's compnay code({kiso_company_code}, {kiso_company_name})")
                    return edinet_compnay_code4, edinet_company_name
        return kiso_company_code, kiso_company_name



class KisoScraperSettings(ScraperSettings):
    def __init__(self):
        super().__init__()
        self.base_url = 'https://www.ipokiso.com'
        self.exclude_keys = {"純資産額", "1株あたりの純資産額", "純資産額"}
        #self.exclude_keys = {"純資産額", "1株あたりの純資産額", "純資産額", "1株あたりの純利益", "自己資本比率"}
        self.capital_threshold = 250  # 想定時価総額の閾値（億円）

        # ディレクトリパス設定
        self.input_dir = self.kiso_list_output_dir
        self.output_dir = os.path.join(self.out_dir_core, 'kiso_details')
        self.cache_dir = os.path.join(self.cache_dir_core, 'kiso')
        
        self.kiso_mistake_companies = {
            'じげん': {
                'wrong': {
                    'code': '6080',
                    'name': 'じげん'
                },
                'correct': {
                    'code': '3679',
                    'name': 'じげん'
                }
            },
            'シグマクシス': {
                'wrong': {
                    'code': '3293',
                    'name': 'シグマクシス'
                },
                'correct': {
                    'code': '6088',
                    'name': 'シグマクシス'
                }
            },
            'アビスト': {
                'wrong': {
                    'code': '3293',
                    'name': 'アビスト'
                },
                'correct': {
                    'code': '6087',
                    'name': 'アビスト'
                }
            },
        }

class TradersScraperSettings(ScraperSettings):
    def __init__(self):
        super().__init__()
        self.base_url = 'https://www.traders.co.jp/ipo'
        
        self.input_dir = self.kiso_list_output_dir
        self.output_dir = os.path.join(self.out_dir_core, 'traders')
        self.cache_dir = os.path.join(self.cache_dir_core, 'traders')

        self.shareholders_ignores = [
            # 混乱を招く系を事前に無視しておく
            "取引先の役員", "前代表取締役", "元代表取締役", "元親会社", "元取締役", "元監査役", "元役員", "元従業員",
            "元CTO", "元取引先", "子会社の役員", "その他の関係会社の役員", "子会社の役員らが議決権の過半数を持つ会社"

            # 明らかにいらなさそうな奴ら
            "顧問","外部協力者", "相談役",
        ]
        self.shareholders_categories = {
            #社長/親族/社長の保有する資産会社
            "社長": [
                "社長", "代表取締役", "創業者", "CEO", "Founder",
                "議決権の過半数",
                "代表取締役社長の資産管理会社", "代表取締役の資産管理会社", "専務取締役の資産管理会社"
            ],
            "役員": [
                "取締役", "役員",  "COO", "CFO", "CTO", "会長", "専務", "常務", "執行役員"
            ],
            "家族": [
                "親族", "血族", "配偶者", "長男"
            ],
            "親会社": ["親会社"],
            "従業員": ["従業員", "元従業員", "持ち株会", "内定者"],
            "VC_ファンド": ["ベンチャーキャピタル", "VC", "ファンド", "ﾌｧﾝﾄﾞ", "金融商品取引業者"],
            "VC_ファンド除く": ["資本提携", "業務提携", "事業会社"],
        }
        self.owners = ["社長", "役員", "家族", "親会社"]       

        
class YFinanceScraperSettings(ScraperSettings):
    def __init__(self):
        super().__init__()
        self.input_dir = self.kiso_list_output_dir
        self.output_dir = os.path.join(self.out_dir_core, 'yfinance')
        self.cache_dir = os.path.join(self.cache_dir_core, 'yfinance')

class CombinerSettings(ScraperSettings):
    def __init__(self):
        super().__init__()
        kiso = KisoScraperSettings()
        traders = TradersScraperSettings()
        yfinance = YFinanceScraperSettings()
        edinet = EdinetCollectorSettings()
        self.kiso_output_dir = kiso.output_dir
        self.traders_output_dir = traders.output_dir
        self.yfinance_output_dir = yfinance.output_dir
        self.edinet_output_dir = edinet.output_dir
        self.output_dir = os.path.join(self.out_dir_core, 'combiner')

class EdinetCollectorSettings(ScraperSettings):
    def __init__(self):
        super().__init__()
        self.input_dir = self.kiso_list_output_dir
        self.output_dir = os.path.join(self.out_dir_core, 'edinet')

class ComparisonCollectorSettings(ScraperSettings):
    def __init__(self):
        super().__init__()
        self.input_dir = self.kiso_list_output_dir
        self.output_dir = os.path.join(self.out_dir_core, 'comparison')
        self.cache_dir = os.path.join(self.cache_dir_core, 'comparison')

class AISummarySettings(ScraperSettings):
    def __init__(self):
        super().__init__()
        self.combiner_input_dir = os.path.join(self.out_dir_core, 'combiner')
        self.edinet_input_dir = os.path.join(self.out_dir_core, 'edinet')
        self.output_dir = os.path.join(self.out_dir_core, 'ai_summary')
        self.top_n_companies = 100  # 上位何件の企業を対象とするかの定数

