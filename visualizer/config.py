from pathlib import Path
from typing import List, Dict

# ディレクトリパス設定
BASE_DIR = Path(__file__).parent.parent
print(BASE_DIR)
IPO_REPORTS_DIR = BASE_DIR / 'data/output/edinet/edinet_database/ipo_reports'
COMPARISON_DIR = BASE_DIR / 'data/output/comparison'
ALL_COMPANIES_PATH = BASE_DIR / 'data/output/combiner/all_companies.tsv'

# 重要な財務指標のリスト
IMPORTANT_METRICS: List[str] = [
    '従業員数',
    '売上高',
    '経常利益',
    '当期純利益',
    '総資産',
    '純資産額',
    '自己資本比率',
    '自己資本利益率',
    '株価収益率',
    '営業活動によるキャッシュ・フロー',
    '投資活動によるキャッシュ・フロー',
    '財務活動によるキャッシュ・フロー',
    '現金及び現金同等物の期末残高',
    '営業利益',
    '営業利益率'
]

# 指標の代替名マッピング
METRIC_ALIASES: Dict[str, List[str]] = {
    '売上高': ['jpcrp_cor:NetSalesSummaryOfBusinessResults', 'jpcrp_cor:RevenueIFRSSummaryOfBusinessResults', 'jpcrp_cor:RevenuesUSGAAPSummaryOfBusinessResults'],
    '営業利益': ['jppfs_cor:OperatingIncome'],
    '経常利益': ['jppfs_cor:OrdinaryIncome', 'jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults'],
    '当期純利益': ['jppfs_cor:ProfitLoss', 'jpcrp_cor:NetIncomeLossSummaryOfBusinessResults'],
    '総資産': ['jpcrp_cor:Assets', 'jpcrp_cor:TotalAssets'],
    '純資産額': ['jpcrp_cor:NetAssets', 'jpcrp_cor:TotalNetAssets'],
    '自己資本比率': ['jpcrp_cor:EquityToAssetRatio', 'jpcrp_cor:ShareholdersEquityRatio'],
    '自己資本利益率': ['jpcrp_cor:ReturnOnEquity', 'jpcrp_cor:ROE'],
    '株価収益率': ['jpcrp_cor:PriceEarningsRatio', 'jpcrp_cor:PER'],
    '営業活動によるキャッシュ・フロー': ['jpcrp_cor:CashFlowsFromOperatingActivities', 'jpcrp_cor:NetCashProvidedByUsedInOperatingActivities'],
    '投資活動によるキャッシュ・フロー': ['jpcrp_cor:CashFlowsFromInvestingActivities', 'jpcrp_cor:NetCashProvidedByUsedInInvestingActivities'],
    '財務活動によるキャッシュ・フロー': ['jpcrp_cor:CashFlowsFromFinancingActivities', 'jpcrp_cor:NetCashProvidedByUsedInFinancingActivities'],
    '現金及び現金同等物の期末残高': ['jpcrp_cor:CashAndCashEquivalents', 'jpcrp_cor:CashAndDeposits'],
    '従業員数': ['jpcrp_cor:NumberOfEmployees'],
}

# グラフ設定
CHART_COLORS = {
    'main': {
        'bar': 'rgba(255, 0, 0, 1.0)',
        'line': 'rgba(255, 0, 0, 1.0)',
    },
    'competitor_base': [
        [0, 128, 255],    # 鮮やかな青
        [0, 180, 0],      # 鮮やかな緑
        [255, 128, 0],    # オレンジ
        [128, 0, 255],    # 紫
        [0, 180, 180],    # ターコイズ
        [180, 0, 180],    # マゼンタ
        [180, 180, 0],    # 黄色
        [90, 90, 90],     # グレー
    ],
    'competitor_alpha': {
        'bar': 0.3,
        'line': 0.4
    }
} 