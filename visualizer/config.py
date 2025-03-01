from pathlib import Path
from typing import List, Dict
from collections import OrderedDict

# ディレクトリパス設定
BASE_DIR = Path(__file__).parent.parent
print(BASE_DIR)
IPO_REPORTS_DIR = BASE_DIR / 'data/output/edinet/edinet_database/ipo_reports'
COMPARISON_DIR = BASE_DIR / 'data/output/comparison'
ALL_COMPANIES_PATH = BASE_DIR / 'data/output/combiner/all_companies.tsv'



# 指標の代替名マッピング（順序付き）
# 辞書のキーの順序が指標の処理順序を決定します
METRIC_ALIASES: Dict[str, List[str]] = OrderedDict([
    ('売上高', ['jpcrp_cor:NetSalesSummaryOfBusinessResults', 'jpcrp_cor:RevenueIFRSSummaryOfBusinessResults', 'jpcrp_cor:RevenuesUSGAAPSummaryOfBusinessResults']),
    ('営業利益', ['jppfs_cor:OperatingIncome']),
    ('経常利益', ['jppfs_cor:OrdinaryIncome', 'jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults']),
    ('当期純利益', ['jpcrp_cor:ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults',
        'jppfs_cor:ProfitLossAttributableToOwnersOfParent',
        'jpcrp_cor:NetIncomeLossSummaryOfBusinessResults']),
    ('ROE（自己資本利益率）', ['jpcrp_cor:RateOfReturnOnEquitySummaryOfBusinessResults']),
    ('純資産', ['jpcrp_cor:NetAssetsSummaryOfBusinessResults']),
    ('総資産', ['jpcrp_cor:TotalAssetsSummaryOfBusinessResults']),
    ('自己資本比率', ['jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResult']),
    ('PER（株価収益率）', ['jpcrp_cor:PriceEarningsRatioSummaryOfBusinessResults']),
    ('従業員数', ['jpcrp_cor:NumberOfEmployees']),
    ('１株当たり当期純利益（EPS）', ['jpcrp_cor:DilutedEarningsPerShareSummaryOfBusinessResults', 'jpcrp_cor:BasicEarningsLossPerShareSummaryOfBusinessResults']),
    # 以下はコメントアウトされていますが、順序を保持するために含めています
    #('営業活動によるキャッシュ・フロー', ['jpcrp_cor:CashFlowsFromOperatingActivities', 'jpcrp_cor:NetCashProvidedByUsedInOperatingActivities']),
    #('投資活動によるキャッシュ・フロー', ['jpcrp_cor:CashFlowsFromInvestingActivities', 'jpcrp_cor:NetCashProvidedByUsedInInvestingActivities']),
    #('財務活動によるキャッシュ・フロー', ['jpcrp_cor:CashFlowsFromFinancingActivities', 'jpcrp_cor:NetCashProvidedByUsedInFinancingActivities']),
    #('現金及び現金同等物の期末残高', ['jpcrp_cor:CashAndCashEquivalents', 'jpcrp_cor:CashAndDeposits']),
])

# グラフの表示順序設定
# リスト内の位置が表示順序を決定します（先頭が最初に表示）
CHART_DISPLAY_ORDER = [
    'PEGレシオ（PER / EPS成長率）', #ピーター・リンチ
    'PER（株価収益率）',
    'ROE（自己資本利益率）', #ウォーレン・バフェット
    'ROA（総資産利益率）',
    '１株当たり当期純利益（EPS）と１株当たり当期純利益（EPS）成長率',
    '営業利益率',
    '売上高と売上高成長率',
    '営業利益と営業利益成長率',

    '自己資本比率',
    '当期純利益',
    '従業員数',
    '純資産',
    '総資産',
    '経常利益',
]

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