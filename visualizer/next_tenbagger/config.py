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
    # 当期純利益。ROAの計算に要る。これが無いとROAのグラフが一度も描かれない
    ('当期純利益', ['jpcrp_cor:ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults',
                 'jpcrp_cor:NetIncomeLossSummaryOfBusinessResults',
                 'jppfs_cor:ProfitLossAttributableToOwnersOfParent',
                 'jpcrp_qcor:ProfitLossAttributableToOwnersOfParentQuarterlySummaryOfBusinessResults']),
    # 末尾のsが抜けていた。next側は要素IDを完全一致で引くので、
    # 4,021社ぶんデータがあるのにグラフが一度も出ていなかった
    ('自己資本比率', ['jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResults',
                   'jpcrp_qcor:EquityToAssetRatioQuarterlySummaryOfBusinessResults']),
    ('PER（株価収益率）', ['jpcrp_cor:PriceEarningsRatioSummaryOfBusinessResults',
                        'jpcrp_qcor:PriceEarningsRatioQuarterlySummaryOfBusinessResults']),
    ('従業員数', ['jpcrp_cor:NumberOfEmployees', 'jpcrp_qcor:NumberOfEmployeesQuarterly']),
    ('平均臨時雇用人員', ['jpcrp_cor:AverageNumberOfTemporaryWorkers']),
    ('１株当たり当期純利益（EPS）', ['jpcrp_cor:BasicEarningsLossPerShareSummaryOfBusinessResults']),
    # 潜在株式を織り込んだEPS。基本EPSとの差が新株予約権などによる希薄化。
    # 小型株は発行株数が少ないぶん希薄化がリターンを食いやすい（オニールのS）
    ('希薄化後EPS', ['jpcrp_cor:DilutedEarningsPerShareSummaryOfBusinessResults']),
    ('平均年齢', ['jpcrp_cor:AverageAgeYearsInformationAboutReportingCompanyInformationAboutEmployees']),
    ('平均勤続年数', ['jpcrp_cor:AverageLengthOfServiceYearsInformationAboutReportingCompanyInformationAboutEmployees']),
    ('平均年間給与', ['jpcrp_cor:AverageAnnualSalaryInformationAboutReportingCompanyInformationAboutEmployees']),
])

# グラフの表示順序設定
# リスト内の位置が表示順序を決定します（先頭が最初に表示）
# 小型の成長株を探す前提で、上から順に「規模 → 成長 → 採算 → 価格 → 財務の質」。
# 括弧内はその指標を重く見る投資家
# 並べ替えはグラフの「タイトル」と突き合わせる。売上高・営業利益・EPSは
# 成長率との複合グラフだが、タイトルは素の指標名なので、ここもその名前で書く。
# 「売上高と売上高成長率」と書いていたときは一致せず、末尾に飛ばされていた。
#
# 小型の成長株を探す前提で「規模 → 成長 → 価格 → 資本効率 → 財務の質 → 人」の順。
# 括弧内はその指標を重く見る投資家
CHART_DISPLAY_ORDER = [
    '時価総額（PER×当期純利益）',      # 小さいほど倍率が伸びる（リンチ、オニールのS）
    '売上高',                        # 成長の本体（リンチのfast grower、オニールのA）
    '営業利益',
    '１株当たり当期純利益（EPS）',
    'PEGレシオ（PER / EPS成長率）',   # 成長に対して割高でないか（リンチ。1.0が適正）
    'PER（株価収益率）',
    'ROE（自己資本利益率）',          # 資本効率（バフェット、オニールは17%以上）
    'ROA（総資産利益率）',            # ROEが借入で嵩上げされていないか（バフェット）
    '自己資本比率',                  # 借金の少なさ（リンチ「無借金なら潰れない」）
    '営業利益率',                    # 採算（フィッシャー）
    '潜在株式による希薄化率',          # 株数が増えて1株あたりが薄まっていないか
    '希薄化後EPS',
    '総人員あたり営業利益',            # 正社員だけで割った下の指標の分母を直したもの
    '従業員一人当たり営業利益',
    '総人員（正社員＋臨時）',
    '臨時雇用の比率',
    '従業員数',
    '平均臨時雇用人員',
    '当期純利益',
    '経常利益',
    '純資産',
    '総資産',
    '平均年間給与',
    '平均勤続年数',
    '平均年齢',
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