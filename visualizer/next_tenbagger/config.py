from pathlib import Path
from typing import List, Dict
from collections import OrderedDict

# ディレクトリパス設定
BASE_DIR = Path(__file__).parent.parent.parent
print(f"BASE_DIR: {BASE_DIR}")
IPO_REPORTS_NEW_DIR = BASE_DIR / 'data/output/edinet_db/ipo_reports_new'
COMPARISON_DIR = BASE_DIR / 'data/output/comparison'
ALL_COMPANIES_PATH = BASE_DIR / 'data/output/combiner/all_companies.tsv'
RECENT_IPO_COMPANIES_PATH = BASE_DIR / 'data/output/combiner/recent_ipo_companies.tsv'

# 指標の代替名マッピング（順序付き）
# 辞書のキーの順序が指標の処理順序を決定します
# 四半期報告書用の指標IDを追加
METRIC_ALIASES: Dict[str, List[str]] = OrderedDict([
    ('売上高', ['jpcrp_cor:NetSalesSummaryOfBusinessResults', 
               'jpcrp_cor:RevenueIFRSSummaryOfBusinessResults', 
               'jpcrp_cor:RevenuesUSGAAPSummaryOfBusinessResults',
               'jpcrp_qcor:NetSalesQuarterlySummaryOfBusinessResults',
               'jpcrp_qcor:RevenueIFRSQuarterlySummaryOfBusinessResults',
               'jpcrp_qcor:RevenuesUSGAAPQuarterlySummaryOfBusinessResults']),
    ('営業利益', ['jppfs_cor:OperatingIncome',
                 'jppfs_qcor:OperatingIncomeQuarterly']),
    ('経常利益', ['jppfs_cor:OrdinaryIncome', 
                 'jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults',
                 'jppfs_qcor:OrdinaryIncomeQuarterly',
                 'jpcrp_qcor:OrdinaryIncomeLossQuarterlySummaryOfBusinessResults']),
    ('四半期純利益', ['jpcrp_qcor:ProfitLossAttributableToOwnersOfParentQuarterlySummaryOfBusinessResults',
                   'jppfs_qcor:ProfitLossAttributableToOwnersOfParentQuarterly',
                   'jpcrp_qcor:NetIncomeLossQuarterlySummaryOfBusinessResults']),
    ('ROE（自己資本利益率）', ['jpcrp_cor:RateOfReturnOnEquitySummaryOfBusinessResults',
                          'jpcrp_qcor:RateOfReturnOnEquityQuarterlySummaryOfBusinessResults']),
    ('純資産', ['jpcrp_cor:NetAssetsSummaryOfBusinessResults',
               'jpcrp_qcor:NetAssetsQuarterlySummaryOfBusinessResults']),
    ('総資産', ['jpcrp_cor:TotalAssetsSummaryOfBusinessResults',
               'jpcrp_qcor:TotalAssetsQuarterlySummaryOfBusinessResults']),
    ('自己資本比率', ['jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResult',
                   'jpcrp_qcor:EquityToAssetRatioQuarterlySummaryOfBusinessResult']),
    ('PER（株価収益率）', ['jpcrp_cor:PriceEarningsRatioSummaryOfBusinessResults',
                        'jpcrp_qcor:PriceEarningsRatioQuarterlySummaryOfBusinessResults']),
    ('従業員数', ['jpcrp_cor:NumberOfEmployees',
                'jpcrp_qcor:NumberOfEmployeesQuarterly']),
    ('１株当たり四半期純利益（EPS）', ['jpcrp_qcor:DilutedEarningsPerShareQuarterlySummaryOfBusinessResults', 
                                'jpcrp_qcor:BasicEarningsLossPerShareQuarterlySummaryOfBusinessResults']),
])

# グラフの表示順序設定
# リスト内の位置が表示順序を決定します（先頭が最初に表示）
CHART_DISPLAY_ORDER = [
    'ROE（自己資本利益率）', #ウォーレン・バフェット
    'ROA（総資産利益率）',
    '従業員数',
    '従業員一人当たり営業利益',
    '営業利益率',
    '営業利益と営業利益成長率',
    '売上高と売上高成長率',
    '１株当たり四半期純利益（EPS）と１株当たり四半期純利益（EPS）成長率',
    'PEGレシオ（PER / EPS成長率）', #ピーター・リンチ
    'PER（株価収益率）',
    '自己資本比率',
    '四半期純利益',
    '純資産',
    '総資産',
    '経常利益',
]

# グラフ設定
CHART_COLORS = {
    'main': {
        'bar': 'rgba(0, 128, 255, 1.0)',  # past_tenbaggerと区別するために青色に変更
        'line': 'rgba(0, 128, 255, 1.0)',
    },
    'competitor_base': [
        [255, 0, 0],      # 赤
        [0, 180, 0],      # 緑
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