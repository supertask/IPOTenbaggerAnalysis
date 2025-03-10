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
    ('従業員数', ['jpcrp_cor:NumberOfEmployees', 'jpcrp_qcor:NumberOfEmployeesQuarterly']),
    ('平均臨時雇用人員', ['jpcrp_cor:AverageNumberOfTemporaryWorkers']),
    ('１株当たり当期純利益（EPS）', ['jpcrp_cor:BasicEarningsLossPerShareSummaryOfBusinessResults']),
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
    '経常利益',
    '営業利益',
    '売上高',
    '純資産',
    '総資産',
]

# チャートの色設定
CHART_COLORS = {
    "main": {
        "bar": "rgba(0, 123, 255, 0.7)",  # メイン企業の棒グラフの色
        "line": "rgba(220, 53, 69, 1)"    # メイン企業の線グラフの色
    },
    "competitor_base": [
        (108, 117, 125),  # グレー
        (40, 167, 69),    # 緑
        (255, 193, 7),    # 黄色
        (23, 162, 184),   # シアン
        (111, 66, 193),   # 紫
        (253, 126, 20)    # オレンジ
    ],
    "competitor_alpha": {
        "bar": 0.5,       # 競合企業の棒グラフの透明度
        "line": 0.8       # 競合企業の線グラフの透明度
    }
} 