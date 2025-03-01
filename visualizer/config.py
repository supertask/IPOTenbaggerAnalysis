from pathlib import Path
from typing import List, Dict

# ディレクトリパス設定
BASE_DIR = Path(__file__).parent.parent
print(BASE_DIR)
IPO_REPORTS_DIR = BASE_DIR / 'data/output/edinet/edinet_database/ipo_reports'
COMPARISON_DIR = BASE_DIR / 'data/output/comparison'
ALL_COMPANIES_PATH = BASE_DIR / 'data/output/combiner/all_companies.tsv'

# 重要な財務指標のリスト
METRICS_IN_DOCS: List[str] = [
    '売上高',
    '営業利益',
    '経常利益',
    '当期純利益',
    '自己資本利益率',
    '純資産額',
    '自己資本比率',
    '株価収益率',
    '従業員数',
    #'営業活動によるキャッシュ・フロー',
    #'投資活動によるキャッシュ・フロー',
    #'財務活動によるキャッシュ・フロー',
    #'現金及び現金同等物の期末残高',
]

# 指標の代替名マッピング
# TODO: 連結と個別のマッピングを追加する
METRIC_ALIASES: Dict[str, List[str]] = {
    '売上高': ['jpcrp_cor:NetSalesSummaryOfBusinessResults', 'jpcrp_cor:RevenueIFRSSummaryOfBusinessResults', 'jpcrp_cor:RevenuesUSGAAPSummaryOfBusinessResults'],
    '営業利益': ['jppfs_cor:OperatingIncome'],
    '経常利益': ['jppfs_cor:OrdinaryIncome', 'jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults'],
    '当期純利益': ['jpcrp_cor:ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults', 'jppfs_cor:ProfitLossAttributableToOwnersOfParent'],
    '自己資本利益率': ['jpcrp_cor:RateOfReturnOnEquitySummaryOfBusinessResults'],
    '株価収益率': ['jpcrp_cor:PriceEarningsRatioSummaryOfBusinessResults'],
    '自己資本比率': ['jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResult'],
    '純資産額': ['jpcrp_cor:NetAssetsSummaryOfBusinessResults'],
    #'営業活動によるキャッシュ・フロー': ['jpcrp_cor:CashFlowsFromOperatingActivities', 'jpcrp_cor:NetCashProvidedByUsedInOperatingActivities'],
    #'投資活動によるキャッシュ・フロー': ['jpcrp_cor:CashFlowsFromInvestingActivities', 'jpcrp_cor:NetCashProvidedByUsedInInvestingActivities'],
    #'財務活動によるキャッシュ・フロー': ['jpcrp_cor:CashFlowsFromFinancingActivities', 'jpcrp_cor:NetCashProvidedByUsedInFinancingActivities'],
    #'現金及び現金同等物の期末残高': ['jpcrp_cor:CashAndCashEquivalents', 'jpcrp_cor:CashAndDeposits'],
    '従業員数': ['jpcrp_cor:NumberOfEmployees'],
}

# グラフの表示順序設定
# 数値が小さいほど先頭に表示される。指定されていない指標は後ろに表示される
CHART_DISPLAY_ORDER: Dict[str, int] = {
    '自己資本利益率': 2,
    '営業利益率': 3,
    '売上高と売上高成長率': 4,
    '営業利益と営業利益成長率': 5,

    '自己資本比率': 6,
    '経常利益': 7,
    '当期純利益': 8,
    '総資産': 9,
    '純資産額': 10,
    '株価収益率': 11,
    '従業員数': 12,
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